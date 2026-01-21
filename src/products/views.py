from datetime import timedelta
import random
import logging
from django.shortcuts import get_object_or_404, render
from django.db.models import Count, Sum, F, Avg
from django.db import transaction
import json
import mimetypes

logger = logging.getLogger(__name__)
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponse
from django.db.models import Sum, F, Count, Q, Case, When, IntegerField
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework import filters as rest_filters
from rest_framework.filters import OrderingFilter
from accounts.pagination import CustomPageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from .serializers import *
from .filters import CouponDiscountFilter, PillFilter, ProductFilter, PurchasedBookFilter
from .models import (
    CouponDiscount,
    ProductImage, Product, Pill,
    PurchasedBook, PillItem, Subject, Teacher
)
from accounts.models import User
from .permissions import IsOwner, IsOwnerOrReadOnly
from services.s3_service import s3_service

class SubjectListView(generics.ListAPIView):
    queryset = Subject.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = SubjectSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter]
    search_fields = ['name', ]
 
class TeacherListView(generics.ListAPIView):
    queryset = Teacher.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = TeacherSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter]
    filterset_fields = ['subject']
    search_fields = ['name', 'subject__name']

class TeacherDetailView(generics.RetrieveAPIView):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get(self, request, *args, **kwargs):
        teacher = self.get_object()
        serializer = self.get_serializer(teacher, context={'request': request})
        return Response(serializer.data)

class ProductListView(generics.ListAPIView):
    queryset = Product.objects.filter(is_available=True)
    permission_classes = [IsAuthenticated]
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'subject__name' , 'teacher__name', 'description']


class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = ProductSerializer
    lookup_field = 'id'

class Last10ProductsListView(generics.ListAPIView):
    queryset = Product.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter]
    filterset_class = ProductFilter

class ActiveSpecialProductsView(generics.ListAPIView):
    serializer_class = SpecialProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SpecialProduct.objects.filter(is_active=True).order_by('-order')
    
class ActiveBestProductsView(generics.ListAPIView):
    serializer_class = BestProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return BestProduct.objects.filter(is_active=True).order_by('-order')



class CombinedProductsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        # Get limit parameter with default of 10
        limit = int(request.query_params.get('limit', 10))
        
        # Prepare response data
        data = {
            'last_products': self.get_last_products(limit),
            'important_products': self.get_important_products(limit),
            'first_year_products': self.get_year_products('first-secondary', limit),
            'second_year_products': self.get_year_products('second-secondary', limit),
            'third_year_products': self.get_year_products('third-secondary', limit),
        }
        
        return Response(data, status=status.HTTP_200_OK)
    
    def get_last_products(self, limit):
        queryset = Product.objects.all().order_by('-id')[:limit]
        serializer = ProductSerializer(queryset, many=True, context={'request': self.request})
        return serializer.data
    
    def get_important_products(self, limit):
        # Since is_important field was removed, return an empty list
        return []
    
    def get_year_products(self, year, limit):
        queryset = Product.objects.filter(
            year=year
        ).order_by('-date_added')[:limit]
        serializer = ProductSerializer(queryset, many=True, context={'request': self.request})
        return serializer.data

class SpecialBestProductsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        # Get limit parameter with default of 10
        limit = int(request.query_params.get('limit', 10))
        
        # Prepare response data
        data = {
            'special_products': self.get_special_products(limit),
            'best_products': self.get_best_products(limit),
        }
        
        return Response(data, status=status.HTTP_200_OK)
    
    def get_special_products(self, limit):
        # Get the special products with their related product data
        special_products = SpecialProduct.objects.filter(
            is_active=True
        ).order_by('-order')[:limit].select_related('product')
        
        # Serialize with additional fields
        result = []
        for sp in special_products:
            product_data = ProductSerializer(sp.product, context={'request': self.request}).data
            result.append({
                'order': sp.order,
                'special_image': self.get_special_image_url(sp),
                **product_data
            })
        return result
    
    def get_special_image_url(self, special_product):
        if special_product.special_image and hasattr(special_product.special_image, 'url'):
            if hasattr(self, 'request'):
                return self.request.build_absolute_uri(special_product.special_image.url)
            return special_product.special_image.url
        return None
    
    def get_best_products(self, limit):
        # Get the best products with their related product data
        best_products = BestProduct.objects.filter(
            is_active=True
        ).order_by('-order')[:limit].select_related('product')
        
        # Serialize with additional fields
        result = []
        for bp in best_products:
            product_data = ProductSerializer(bp.product, context={'request': self.request}).data
            result.append({
                'order': bp.order,
                **product_data
            })
        return result


class TeacherProductsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, teacher_id, *args, **kwargs):
        try:
            teacher = Teacher.objects.get(pk=teacher_id)
        except Teacher.DoesNotExist:
            return Response({'error': 'المعلم غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get parameters with defaults
        limit = int(request.query_params.get('limit', 10))
        is_important = request.query_params.get('important', 'false').lower() == 'true'
        
        # Prepare response data
        data = {
            'teacher': TeacherSerializer(teacher, context={'request': request}).data,
            'books': self.get_books(teacher, limit, is_important),
            'products': self.get_products(teacher, limit, is_important),
        }
        
        return Response(data, status=status.HTTP_200_OK)
    
    def get_books(self, teacher, limit, is_important):
        queryset = Product.objects.filter(
            teacher=teacher,
            type='book'
        )
        
        if is_important:
            queryset = queryset.filter(is_important=True)
            
        queryset = queryset.order_by('-date_added')[:limit]
        serializer = ProductSerializer(queryset, many=True, context={'request': self.request})
        return serializer.data
    
    def get_products(self, teacher, limit, is_important):
        queryset = Product.objects.filter(
            teacher=teacher,
            type='product'
        )
        
        if is_important:
            queryset = queryset.filter(is_important=True)
            
        queryset = queryset.order_by('-date_added')[:limit]
        serializer = ProductSerializer(queryset, many=True, context={'request': self.request})
        return serializer.data


class PillItemPermissionMixin:
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user

class PillCreateView(generics.CreateAPIView):
    queryset = Pill.objects.all()
    serializer_class = PillCreateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, status='i')

class PillCouponApplyView(generics.GenericAPIView):
    serializer_class = PillCouponApplySerializer
    lookup_field = 'id'
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Pill.objects.filter(user=self.request.user)

    def post(self, request, *args, **kwargs):
        return self._apply_coupon(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return self._apply_coupon(request, *args, **kwargs)

    def _apply_coupon(self, request, *args, **kwargs):
        pill = self.get_object()
        serializer = self.get_serializer(pill, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)




class PillDetailView(generics.RetrieveAPIView, PillItemPermissionMixin):
    queryset = Pill.objects.all()
    serializer_class = PillDetailSerializer
    lookup_field = 'id'
    permission_classes = [IsAuthenticated]

    def get_object(self):
        pill_id = self.kwargs.get('id')
        return get_object_or_404(Pill, id=pill_id, user=self.request.user)

class UserPillsView(generics.ListAPIView):
    serializer_class = PillDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Allow filtering by pill status via query param `status`.
        # Example: ?status=p  or ?status=p,i (comma-separated)
        queryset = Pill.objects.filter(user=self.request.user).order_by('-date_added')
        status_param = self.request.query_params.get('status')
        if status_param:
            statuses = [s.strip() for s in status_param.split(',') if s.strip()]
            if statuses:
                queryset = queryset.filter(status__in=statuses)
        return queryset


class UserUnpaidPillsView(generics.ListAPIView):
    """
    List unpaid pills for the authenticated user.
    
    This endpoint helps students check which unpaid pills they have
    before creating a new pill, so they're aware which ones will be cancelled.
    
    Returns only pills with status not in ['p', 'c', 'e'] (not paid, cancelled, or expired)
    
    URL: GET /products/pills/unpaid/
    """
    serializer_class = UnpaidPillListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Return all unpaid pills (excluding paid, cancelled, expired) for the current user
        return Pill.objects.filter(user=self.request.user).exclude(status__in=['p', 'c', 'e']).order_by('-date_added')


class CancelInvoiceView(APIView):
    """
    Cancel an EasyPay invoice (Admin only).
    
    This endpoint allows administrators to manually cancel unpaid invoices.
    
    POST /products/dashboard/cancel-invoice/
    Body: {
        "fawry_ref": "9566331553"
    }
    
    Returns:
        200 OK: Invoice cancelled successfully
        400 Bad Request: Invalid request or missing fawry_ref
        500 Internal Server Error: Cancellation failed
    """
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        from services.easypay_service import easypay_service
        
        fawry_ref = request.data.get('fawry_ref')
        
        if not fawry_ref:
            return Response(
                {'error': 'حقل fawry_ref مطلوب'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        logger.info(f"🔧 [ADMIN_CANCEL] Admin {request.user.username} (ID: {request.user.id}) requesting invoice cancellation for fawry_ref: {fawry_ref}")
        
        try:
            result = easypay_service.cancel_invoice(fawry_ref)
            
            if result['success']:
                logger.info(f"✅ [ADMIN_CANCEL] Successfully cancelled invoice {fawry_ref}")
                return Response(
                    {
                        'success': True,
                        'message': f'تم إلغاء الفاتورة {fawry_ref} بنجاح',
                        'fawry_ref': fawry_ref,
                        'data': result.get('data', {})
                    },
                    status=status.HTTP_200_OK
                )
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"❌ [ADMIN_CANCEL] Failed to cancel invoice {fawry_ref}: {error_msg}")
                return Response(
                    {
                        'success': False,
                        'error': f'فشل إلغاء الفاتورة: {error_msg}',
                        'fawry_ref': fawry_ref
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        except Exception as e:
            logger.error(f"❌ [ADMIN_CANCEL] Exception while cancelling invoice {fawry_ref}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response(
                {
                    'success': False,
                    'error': f'حدث استثناء أثناء إلغاء الفاتورة: {str(e)}',
                    'fawry_ref': fawry_ref
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PurchasedBookListView(generics.ListAPIView):
    serializer_class = PurchasedBookSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            PurchasedBook.objects.filter(user=self.request.user)
            .select_related('product', 'product__teacher', 'pill')
            .order_by('-created_at')
        )


class PurchasedBookPDFDownloadView(APIView):
    """
    Get a presigned URL for downloading a purchased book's PDF.
    
    This endpoint generates a temporary URL (valid for 1 hour) that allows
    the user to download the PDF file. The user must own the book.
    
    URL: GET /products/my-books/<purchased_book_id>/download/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, purchased_book_id):
        from services.s3_service import s3_service
        
        # Check if user owns this book
        purchased_book = get_object_or_404(
            PurchasedBook.objects.select_related('product'),
            id=purchased_book_id,
            user=request.user
        )
        
        product = purchased_book.product
        
        # Check if product has a PDF file
        if not product.pdf_file:
            return Response({'error': 'هذا الكتاب لا يحتوي على ملف PDF متاح.'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the file key from the pdf_file field
        # The pdf_file.name contains the S3 key (e.g., 'pdfs/book.pdf')
        file_key = product.pdf_file.name
        
        # Generate presigned URL (valid for 1 hour)
        result = s3_service.generate_presigned_download_url(
            object_key=file_key,
            expiration=3600  # 1 hour
        )
        
        if result['success']:
            return Response({
                'success': True,
                'product_name': product.name,
                'download_url': result['url'],
                'expires_in': 3600,
                'expires_in_human': '1 hour'
            }, status=status.HTTP_200_OK)
        else:
            logger.error(f"Failed to generate PDF download URL for purchased book {purchased_book_id}: {result['error']}")
            return Response({'error': 'فشل إنشاء رابط التحميل، يرجى المحاولة لاحقًا.'}, status=status.HTTP_400_BAD_REQUEST)


class DeeplinkView(APIView):
    """
    Serve a small HTML page that attempts to open the native app via a custom URL scheme
    and falls back to a web/universal link. The base web URL is taken from
    `settings.SITE_URL` (configured from .env).

    Usage: GET /products/deeplink/mybooks/  -> attempts to open `com.easytech.booklet://mybooks`
    """
    permission_classes = [AllowAny]

    def get(self, request, target):
        scheme = getattr(settings, 'DEEPLINK_SCHEME', 'com.easytech.booklet')
        site_url = getattr(settings, 'SITE_URL', '').strip()

        app_url = f"{scheme}://{target}"
        
        # Build absolute fallback URL
        if site_url:
            # Ensure site_url starts with http:// or https://
            if not site_url.startswith(('http://', 'https://')):
                site_url = f"https://{site_url}"
            web_fallback = f"{site_url}/products/app/{target}"
        else:
            # Fallback to request's domain if SITE_URL not set
            web_fallback = request.build_absolute_uri(f"/products/app/{target}")

        context = {
            'app_url': app_url,
            'web_fallback': web_fallback
        }
        return render(request, 'products/deeplink.html', context)


class AppFallbackView(APIView):
    """
    Fallback page for users who don't have the app installed.
    Shows download buttons for Play Store and App Store.
    """
    permission_classes = [AllowAny]

    def get(self, request, target='mybooks'):
        return render(request, 'products/app_fallback.html')


class ProductOwnedCheckView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, product_number):
        owned = PurchasedBook.objects.filter(
            user=request.user,
            product__product_number=product_number
        ).exists()

        product_id = (
            Product.objects.filter(product_number=product_number)
            .values_list('id', flat=True)
            .first()
        )

        return Response(
            {
                'product_number': product_number,
                'product_id': product_id,
                'owned': owned
            },
            status=status.HTTP_200_OK
        )


class AddFreeBookView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, product_number):
        product = get_object_or_404(
            Product,
            product_number=product_number,
            is_available=True
        )

        effective_price = product.discounted_price()
        if effective_price is None:
            effective_price = product.price or 0

        if float(effective_price or 0) > 0:
            return Response(
                {'detail': 'Product is not free and cannot be added directly.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if PurchasedBook.objects.filter(user=request.user, product=product).exists():
            return Response(
                {'detail': 'This book already exists in your library.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            pill = Pill.objects.create(user=request.user, status='p')
            pill_item = PillItem.objects.create(
                user=request.user,
                product=product,
                status='p',
                pill=pill,
                price_at_sale=float(effective_price or 0)
            )
            pill.items.add(pill_item)
            pill.grant_purchased_books(purchase_method='free')

        purchased_book = PurchasedBook.objects.get(user=request.user, product=product)
        serializer = PurchasedBookSerializer(purchased_book, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProductsWithActiveDiscountAPIView(APIView):
    def get(self, request):
        now = timezone.now()
        product_discounts = Discount.objects.filter(
            is_active=True,
            discount_start__lte=now,
            discount_end__gte=now,
            product__isnull=False
        ).values_list('product_id', flat=True)
        products = Product.objects.filter(id__in=product_discounts).distinct()
        serializer = ProductSerializer(products, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

class LovedProductListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return LovedProductListSerializer
        return LovedProductSerializer

    def get_queryset(self):
        return LovedProduct.objects.filter(user=self.request.user).select_related(
            'product', 'product__subject', 
            'product__teacher'
        ).prefetch_related('product__images')

    def perform_create(self, serializer):
        serializer.save()

class LovedProductRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    serializer_class = LovedProductListSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'product_id'

    def get_queryset(self):
        return LovedProduct.objects.filter(user=self.request.user).select_related(
            'product', 'product__subject', 
            'product__teacher'
        ).prefetch_related('product__images')

    def get_object(self):
        product_id = self.kwargs.get('product_id')
        return get_object_or_404(
            LovedProduct,
            user=self.request.user,
            product_id=product_id
        )

class NewArrivalsView(generics.ListAPIView):
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Product.objects.all().order_by('-date_added')
        days = self.request.query_params.get('days', None)
        if days:
            date_threshold = timezone.now() - timedelta(days=int(days))
            queryset = queryset.filter(date_added__gte=date_threshold)
        return queryset

class BestSellersView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        # Get products with paid/delivered items
        queryset = Product.objects.annotate(
            total_sold=Sum(
                Case(
                    When(
                        pill_items__status__in=['p'],
                        then='pill_items__quantity'
                    ),
                    default=0,
                    output_field=IntegerField()
                )
            )
        ).filter(
            total_sold__gt=0
        ).order_by('-total_sold')
        
        # Apply date filter if provided
        days = self.request.query_params.get('days', None)
        if days:
            date_threshold = timezone.now() - timedelta(days=int(days))
            queryset = queryset.annotate(
                recent_sold=Sum(
                    Case(
                        When(
                            pill_items__status__in=['p'],
                            pill_items__date_sold__gte=date_threshold,
                            then='pill_items__quantity'
                        ),
                        default=0,
                        output_field=IntegerField()
                    )
                )
            ).filter(
                recent_sold__gt=0
            ).order_by('-recent_sold')
        
        return queryset

class FrequentlyBoughtTogetherView(generics.ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        product_id = self.request.query_params.get('product_id')
        if not product_id:
            return Product.objects.none()
        
        # Get pills that contain the requested product
        pill_ids = PillItem.objects.filter(
            product_id=product_id,
            status__in=['p']
        ).values_list('pill_id', flat=True)
        
        # Find other products in those pills
        frequent_products = Product.objects.filter(
            pill_items__pill_id__in=pill_ids,
            pill_items__status__in=['p']
        ).exclude(
            id=product_id
        ).annotate(
            co_purchase_count=Count('pill_items__id')
        ).order_by('-co_purchase_count')[:5]
        
        return frequent_products


class ProductRecommendationsView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        current_product_id = self.request.query_params.get('product_id')
        recommendations = []
        
        if current_product_id:
            current_product = get_object_or_404(Product, id=current_product_id)
            similar_products = Product.objects.filter(
                Q(subject=current_product.subject) |
                Q(teacher=current_product.teacher)
            ).exclude(id=current_product_id).distinct()
            recommendations.extend(list(similar_products))
        
        # Loved products
        loved_products = Product.objects.filter(
            lovedproduct__user=user
        ).exclude(id__in=[p.id for p in recommendations]).distinct()
        recommendations.extend(list(loved_products))
        
        # Purchased products (using PillItem now)
        purchased_products = Product.objects.filter(
            pill_items__user=user,
            pill_items__status__in=['p']
        ).exclude(id__in=[p.id for p in recommendations]).distinct()
        recommendations.extend(list(purchased_products))
        
        # Deduplicate
        seen = set()
        unique_recommendations = []
        for product in recommendations:
            if product.id not in seen:
                seen.add(product.id)
                unique_recommendations.append(product)
            if len(unique_recommendations) >= 12:
                break
                
        return unique_recommendations


from rest_framework import filters

class CustomPillFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        pill_id = request.query_params.get('pill')
        if pill_id is not None:
            # First validate that the pill exists
            if Pill.objects.filter(id=pill_id).exists():
                return queryset.filter(pill__id=pill_id)
            else:
                # Return empty queryset if pill doesn't exist
                return queryset.none()
        return queryset


class PillItemListCreateView(generics.ListCreateAPIView):
    queryset = PillItem.objects.select_related(
        'user', 'product', 'pill'
    ).prefetch_related('product__images')
    serializer_class = AdminPillItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [CustomPillFilterBackend, OrderingFilter]
    ordering_fields = ['date_added', 'quantity']
    ordering = ['-date_added']
    

class PillItemRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = PillItem.objects.select_related(
        'user', 'product', 'pill'
    )
    serializer_class = AdminPillItemSerializer
    permission_classes = [IsAdminUser]
    lookup_field = 'pk'

    def perform_destroy(self, instance):
        if instance.pill and instance.pill.status == 'p':
            raise serializers.ValidationError("لا يمكن حذف عنصر من فاتورة تم توصيلها او مدفوعة.")
        instance.delete()


class RemovePillItemView(APIView):
    """
    API endpoint to remove an item from a pill
    """
    permission_classes = [IsAuthenticated]
    
    def delete(self, request, pill_id, item_id):
        """
        Remove a specific item from a pill
        """
        try:
            # Get the pill and ensure it belongs to the authenticated user
            pill = get_object_or_404(Pill, id=pill_id, user=request.user)
            
            # Get the pill item to remove
            try:
                pill_item = pill.items.get(id=item_id)
            except pill.items.model.DoesNotExist:
                return Response({'error': 'العنصر غير موجود في هذه الفاتورة'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Store item info for response
            removed_item_info = {
                'id': pill_item.id,
                'product_name': pill_item.product.name,
                'quantity': pill_item.quantity,
                'price': float(pill_item.price)
            }
            
            # Remove the item
            pill_item.delete()
            
            # Check if pill has any items left
            remaining_items_count = pill.items.count()
            
            if remaining_items_count == 0:
                # If no items left, delete the pill
                pill.delete()
                return Response({
                    'success': True,
                    'message': 'تم حذف العنصر والفاتورة بالكامل لعدم وجود عناصر أخرى',
                    'pill_deleted': True,
                    'removed_item': removed_item_info
                }, status=status.HTTP_200_OK)
            
            # Recalculate pill totals
            pill.save()  # This will trigger recalculation in the save method
            
            return Response({
                'success': True,
                'message': 'تم حذف العنصر بنجاح',
                'pill_deleted': False,
                'removed_item': removed_item_info,
                'remaining_items_count': remaining_items_count,
                'updated_pill': {
                    'id': pill.id,
                    'pill_number': pill.pill_number,
                    'total_amount': float(pill.final_price()),
                    'items_count': remaining_items_count
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Exception removing item {item_id} from pill {pill_id}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({'error': 'حدث خطأ في الخادم، يرجى المحاولة لاحقًا.'}, status=status.HTTP_400_BAD_REQUEST)























# Admin Endpoints
class AdminLovedProductListCreateView(generics.ListCreateAPIView):
    queryset = LovedProduct.objects.select_related(
        'user', 'product'
    ).prefetch_related('product__images')
    permission_classes = [IsAdminUser]
    serializer_class = AdminLovedProductSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = {
        'user': ['exact'],
        'product': ['exact'],
        'created_at': ['gte', 'lte', 'exact']
    }
    ordering_fields = ['created_at']
    ordering = ['-created_at']

class AdminLovedProductRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    queryset = LovedProduct.objects.select_related('user', 'product')
    serializer_class = AdminLovedProductSerializer
    lookup_field = 'pk'
    permission_classes = [IsAdminUser]

class SubjectListCreateView(generics.ListCreateAPIView):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter, OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['id', 'name', 'created_at']
    ordering = ['-created_at']
    permission_classes = [IsAdminUser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            errors = serializer.errors
            # Prefer field-specific message for 'name', else join other messages
            if isinstance(errors, dict):
                if 'name' in errors and isinstance(errors['name'], (list, tuple)) and errors['name']:
                    return Response({'error': errors['name'][0]}, status=status.HTTP_400_BAD_REQUEST)
                # fallback: take first message found
                for v in errors.values():
                    if isinstance(v, (list, tuple)) and v:
                        return Response({'error': v[0]}, status=status.HTTP_400_BAD_REQUEST)
            # default: return joined str of errors
            return Response({'error': str(errors)}, status=status.HTTP_400_BAD_REQUEST)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

class SubjectRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [IsAdminUser]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            errors = serializer.errors
            if isinstance(errors, dict):
                if 'name' in errors and isinstance(errors['name'], (list, tuple)) and errors['name']:
                    return Response({'error': errors['name'][0]}, status=status.HTTP_400_BAD_REQUEST)
                for v in errors.values():
                    if isinstance(v, (list, tuple)) and v:
                        return Response({'error': v[0]}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'error': str(errors)}, status=status.HTTP_400_BAD_REQUEST)

        self.perform_update(serializer)
        return Response(serializer.data)
    

class TeacherListCreateView(generics.ListCreateAPIView):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter, OrderingFilter]
    filterset_fields = ['subject']
    search_fields = ['name', 'subject__name']
    ordering_fields = ['id', 'name', 'created_at']
    ordering = ['-created_at']
    permission_classes = [IsAdminUser]

class TeacherRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsAdminUser]
    

class ProductListCreateView(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = AdminProductSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'description']
    ordering_fields = ['id', 'name', 'price', 'discounted_price', 'date_added', 'year']
    ordering = ['-date_added']
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAdminUser]  # Changed for testing - change back to IsAdminUser in production

class ProductListBreifedView(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductBreifedSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'description']
    ordering_fields = ['id', 'name', 'price', 'discounted_price', 'date_added', 'year']
    ordering = ['-date_added']
    permission_classes = [IsAdminUser]

class ProductSimpleListView(generics.ListAPIView):
    """Simple product list endpoint with minimal fields for dropdowns/selections"""
    queryset = Product.objects.all()
    serializer_class = SimpleProductSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter]
    filterset_fields = ['is_available', 'type', 'teacher', 'subject','year']
    search_fields = ['name']
    permission_classes = [IsAdminUser]
    pagination_class = None  # Disable pagination for direct list response

class SubjectSimpleListView(generics.ListAPIView):
    """Simple subject list endpoint with minimal fields for dropdowns/selections"""
    queryset = Subject.objects.all()
    serializer_class = SimpleSubjectSerializer
    filter_backends = [rest_filters.SearchFilter]
    search_fields = ['name']
    permission_classes = [IsAdminUser]
    pagination_class = None  # Disable pagination for direct list response

class TeacherSimpleListView(generics.ListAPIView):
    """Simple teacher list endpoint with minimal fields for dropdowns/selections"""
    queryset = Teacher.objects.all()
    serializer_class = SimpleTeacherSerializer
    filter_backends = [rest_filters.SearchFilter, DjangoFilterBackend]
    filterset_fields = ['subject']
    search_fields = ['name']
    permission_classes = [IsAdminUser]
    pagination_class = None  # Disable pagination for direct list response

class ProductRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = AdminProductSerializer
    permission_classes = [IsAdminUser]

class ProductImageListCreateView(generics.ListCreateAPIView):
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['product']
    ordering_fields = ['id', 'created_at', 'product']
    ordering = ['-created_at']
    permission_classes = [IsAdminUser]

class ProductImageBulkCreateView(generics.CreateAPIView):
    permission_classes = [IsAdminUser]

    def post(self, request, *args, **kwargs):
        serializer = ProductImageBulkUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data['product']
        images = serializer.validated_data['images']
        product_images = [
            ProductImage(product=product, image=image)
            for image in images
        ]
        ProductImage.objects.bulk_create(product_images)
        return Response(
            {"message": "Images uploaded successfully."},
            status=status.HTTP_201_CREATED
        )


class ProductImageBulkS3CreateView(generics.CreateAPIView):
    """
    Bulk create product images from S3 object keys.
    
    POST /products/dashboard/product-images/bulk-upload-s3/
    
    Request body:
    {
        "product": 1,
        "image_object_keys": [
            "products/uuid1.jpg",
            "products/uuid2.jpg"
        ]
    }
    """
    permission_classes = [IsAdminUser]  # Allow any user for testing - change to IsAdminUser in production
    parser_classes = [JSONParser]

    def post(self, request, *args, **kwargs):
        serializer = ProductImageBulkS3UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created_images = serializer.save()
        
        # Build full URLs for the images
        from django.conf import settings
        custom_domain = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', None)
        
        def get_full_url(image_field):
            if not image_field:
                return None
            file_path = image_field.name if hasattr(image_field, 'name') else str(image_field)
            if not file_path:
                return None
            if file_path.startswith('http://') or file_path.startswith('https://'):
                return file_path
            if custom_domain:
                return f"https://{custom_domain}/{file_path}"
            return file_path
        
        # Return the created images data with full URLs
        response_data = [
            {
                'id': img.id,
                'product': img.product_id,
                'image': get_full_url(img.image)
            }
            for img in created_images
        ]
        return Response(response_data, status=status.HTTP_201_CREATED)

class ProductImageDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer
    permission_classes = [IsAdminUser]

class SpecialProductListCreateView(generics.ListCreateAPIView):
    queryset = SpecialProduct.objects.all()
    serializer_class = AdminSpecialProductSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'product']
    search_fields = ['product__name', 'product__subject__name']
    ordering_fields = ['order', 'created_at']
    ordering = ['-order', '-created_at']
    permission_classes = [IsAdminUser]
    # Allow multipart/form-data for file uploads
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def perform_create(self, serializer):
        serializer.save()

class SpecialProductRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = SpecialProduct.objects.all()
    serializer_class = AdminSpecialProductSerializer
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

class BestProductListCreateView(generics.ListCreateAPIView):
    queryset = BestProduct.objects.all()
    serializer_class = AdminBestProductSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'product']
    search_fields = ['product__name', 'product__subject__name']
    ordering_fields = ['order', 'created_at']
    ordering = ['-order', '-created_at']
    permission_classes = [IsAdminUser]

    def perform_create(self, serializer):
        serializer.save()

class BestProductRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = BestProduct.objects.all()
    serializer_class = AdminBestProductSerializer
    permission_classes = [IsAdminUser]

from django.db.models import Prefetch

class PillListCreateView(generics.ListCreateAPIView):
    serializer_class = PillCreateSerializer
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter, OrderingFilter]
    filterset_class = PillFilter
    search_fields = ['user__name', 'user__username', 'pill_number', 'user__parent_phone', 'shakeout_invoice_id', 'shakeout_invoice_ref', 'easypay_invoice_uid', 'easypay_invoice_sequence', 'easypay_fawry_ref']
    ordering_fields = ['id', 'date_added', 'status', 'user__username', 'pill_number', 'final_price']
    ordering = ['-date_added']
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        # Optimize queryset with select_related, prefetch_related, and annotations
        queryset = Pill.objects.select_related(
            'user',
            'coupon'
        ).prefetch_related(
            Prefetch(
                'items',
                queryset=PillItem.objects.select_related('product')
            )
        ).annotate(
            items_count=Count('items')
        ).order_by('-date_added')
        
        # REMOVED: No automatic date filtering
        # This will return all pills
        
        return queryset

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return PillCreateSerializer
        return PillSerializer

class PillRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    Admin endpoint to retrieve, update, or delete a pill
    GET /products/dashboard/pills/<pk>/
    PUT /products/dashboard/pills/<pk>/
    PATCH /products/dashboard/pills/<pk>/
    DELETE /products/dashboard/pills/<pk>/
    
    Delete restrictions:
    - Cannot delete paid pills (status='p')
    - Cannot delete cancelled pills (status='c')
    - Can only delete initiated ('i') or waiting ('w') pills
    """
    queryset = Pill.objects.all()
    serializer_class = PillDetailWithoutItemsSerializer
    permission_classes = [IsAdminUser]
    
    def destroy(self, request, *args, **kwargs):
        """Override destroy to cancel pills instead of deleting them"""
        from services.easypay_service import easypay_service
        
        pill = self.get_object()
        
        # Prevent deletion of paid pills
        if pill.status == 'p':
            return Response({
                'error': 'لا يمكن حذف فاتورة مدفوعة. الفواتير المدفوعة محمية من الحذف.',
                'pill_number': pill.pill_number,
                'status': pill.status,
                'status_display': 'مدفوعة'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Prevent deletion of cancelled pills
        if pill.status == 'c':
            return Response({
                'error': 'لا يمكن حذف فاتورة ملغاة. الفواتير الملغاة محفوظة للسجلات.',
                'pill_number': pill.pill_number,
                'status': pill.status,
                'status_display': 'ملغاة'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Prevent deletion of expired pills
        if pill.status == 'e':
            return Response({
                'error': 'لا يمكن حذف فاتورة منتهية الصلاحية. الفواتير المنتهية محفوظة للسجلات.',
                'pill_number': pill.pill_number,
                'status': pill.status,
                'status_display': 'منتهية الصلاحية'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # For initiated ('i') or waiting ('w') pills, cancel them instead of deleting
        if pill.status in ['i', 'w']:
            logger.info(f"🚫 [ADMIN_CANCEL_PILL] Admin {request.user.username} cancelling pill {pill.pill_number} (status: {pill.status})")
            
            # Cancel EasyPay invoice if it exists
            if pill.easypay_fawry_ref:
                try:
                    logger.info(f"📞 [ADMIN_CANCEL_PILL] Cancelling EasyPay invoice for pill {pill.pill_number} (fawry_ref: {pill.easypay_fawry_ref})")
                    result = easypay_service.cancel_invoice(pill.easypay_fawry_ref)
                    
                    if result['success']:
                        logger.info(f"✅ [ADMIN_CANCEL_PILL] Successfully cancelled invoice for pill {pill.pill_number}")
                    else:
                        logger.warning(f"⚠️ [ADMIN_CANCEL_PILL] Failed to cancel invoice for pill {pill.pill_number}: {result.get('error')}")
                except Exception as e:
                    logger.error(f"❌ [ADMIN_CANCEL_PILL] Exception cancelling invoice for pill {pill.pill_number}: {str(e)}")
            
            # Mark pill as cancelled
            old_status = pill.status
            pill.status = 'c'
            pill.save(update_fields=['status'])
            
            logger.info(f"✅ [ADMIN_CANCEL_PILL] Cancelled pill {pill.pill_number} (status: {old_status} → c)")
            
            return Response({
                'success': True,
                'message': 'تم إلغاء الفاتورة بنجاح',
                'data': {
                    'pill_number': pill.pill_number,
                    'old_status': old_status,
                    'new_status': 'c',
                    'status_display': 'ملغاة'
                }
            }, status=status.HTTP_200_OK)
        
        # Fallback for any other status
        return Response({
            'error': f'لا يمكن حذف فاتورة بحالة {pill.get_status_display()}.',
            'pill_number': pill.pill_number,
            'status': pill.status
        }, status=status.HTTP_400_BAD_REQUEST)


class PillItemsListView(generics.ListAPIView):
    """
    List items for a specific pill with pagination
    GET /products/dashboard/pills/<pill_id>/items/
    """
    serializer_class = PillItemWithProductSerializer
    permission_classes = [IsAdminUser]
    pagination_class = CustomPageNumberPagination
    filter_backends = [OrderingFilter]
    ordering_fields = ['date_added', 'status']
    ordering = ['-date_added']

    def get_queryset(self):
        pill_id = self.kwargs.get('pk')
        return PillItem.objects.filter(pill_id=pill_id).select_related(
            'product', 'product__teacher', 
            'product__subject'
        ).prefetch_related('product__images')


class DiscountListCreateView(generics.ListCreateAPIView):
    queryset = Discount.objects.all()
    serializer_class = DiscountSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['product', 'is_active']
    ordering_fields = ['id', 'discount', 'discount_start', 'discount_end', 'created_at']
    ordering = ['-created_at']

class DiscountRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Discount.objects.all()
    serializer_class = DiscountSerializer
    permission_classes = [IsAdminUser]

class CouponListCreateView(generics.ListCreateAPIView):
    queryset = CouponDiscount.objects.all()
    serializer_class = CouponDiscountSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = CouponDiscountFilter
    ordering_fields = ['id', 'coupon', 'discount_value', 'created_at', 'coupon_start', 'coupon_end', 'available_use_times']
    ordering = ['-created_at']
    permission_classes = [IsAdminUser]

class CouponRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = CouponDiscount.objects.all()
    serializer_class = CouponDiscountSerializer
    permission_classes = [IsAdminUser]


class BulkCouponCreateView(generics.CreateAPIView):
    """Create multiple coupons at once"""
    serializer_class = BulkCouponDiscountSerializer
    permission_classes = [IsAdminUser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        coupons = serializer.save()
        
        # Return the created coupons using CouponDiscountSerializer
        output_serializer = CouponDiscountSerializer(coupons, many=True)
        return Response({
            'success': True,
            'message': f'تم إنشاء {len(coupons)} كوبون بنجاح',
            'count': len(coupons),
            'coupons': output_serializer.data
        }, status=status.HTTP_201_CREATED)


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from services.shakeout_service import shakeout_service
import logging

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_shakeout_invoice_view(request, pill_id):
    """
    Create a Shake-out invoice for a specific pill
    """
    try:
        # Get the pill
        pill = Pill.objects.get(id=pill_id, user=request.user)
        
        # Check if pill already has a Shake-out invoice
        if pill.shakeout_invoice_id:
            # Check if the existing invoice is expired or invalid
            if pill.is_shakeout_invoice_expired():
                logger.info(f"Existing Shake-out invoice {pill.shakeout_invoice_id} for pill {pill_id} is expired/invalid - creating new one")
                
                # Clear old invoice data to create a new one
                pill.shakeout_invoice_id = None
                pill.shakeout_invoice_ref = None
                pill.shakeout_data = None
                pill.shakeout_created_at = None
                pill.save(update_fields=['shakeout_invoice_id', 'shakeout_invoice_ref', 'shakeout_data', 'shakeout_created_at'])
            else:
                return Response({'error': 'الفاتورة موجودة مسبقًا لهذه الفاتورة.' , 'data': {
                        'invoice_id': pill.shakeout_invoice_id,
                        'invoice_ref': pill.shakeout_invoice_ref,
                        'payment_url': pill.shakeout_payment_url,
                        'created_at': pill.shakeout_created_at.isoformat() if pill.shakeout_created_at else None,
                        'status': 'active'
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create Shake-out invoice
        payment_url = pill.create_shakeout_invoice()
        
        if payment_url:
            # Refresh pill from database to get updated data
            pill.refresh_from_db()
            
            return Response({
                'success': True,
                'message': 'Shake-out invoice created successfully',
                'data': {
                    'invoice_id': pill.shakeout_invoice_id,
                    'invoice_ref': pill.shakeout_invoice_ref,
                    'payment_url': payment_url,
                    'total_amount': pill.final_price(),
                    'pill_number': pill.pill_number
                }
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({'error': 'فشل إنشاء فاتورة الشيك آوت.'}, status=status.HTTP_400_BAD_REQUEST)
            
    except Pill.DoesNotExist:
        return Response({'error': 'الفاتورة غير موجودة أو لا تملك صلاحية الوصول لها'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error creating Shake-out invoice for pill {pill_id}: {str(e)}")
        return Response({'error': 'حدث خطأ أثناء إنشاء الفاتورة، يرجى المحاولة لاحقًا.'}, status=status.HTTP_400_BAD_REQUEST)


class AddBooksToStudentView(APIView):
    """
    Dashboard endpoint to add a list of books directly to a student
    POST /products/add-books-to-student/
    
    Request body:
    {
        "user_id": 1,
        "product_ids": [1, 2, 3, 4]
    }
    """
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        user_id = request.data.get('user_id')
        product_ids = request.data.get('product_ids', [])
        
        # Validate input
        if not user_id:
            return Response({'error': 'حقل user_id مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not product_ids or not isinstance(product_ids, list):
            return Response({'error': 'حقل product_ids يجب أن يكون قائمة غير فارغة'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get the user
            user = User.objects.get(id=user_id)
            
            # Validate all products exist
            products = Product.objects.filter(id__in=product_ids)
            if products.count() != len(product_ids):
                found_ids = list(products.values_list('id', flat=True))
                missing_ids = [pid for pid in product_ids if pid not in found_ids]
                return Response({'error': f'المنتجات غير موجودة: {missing_ids}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Use transaction to ensure atomicity
            with transaction.atomic():
                # Cancel any pending orders (status 'i' or 'w') that contain these products
                from services.easypay_service import easypay_service
                
                # Find all pending pills for this user that contain any of these products
                pending_pills = Pill.objects.filter(
                    user=user,
                    status__in=['i', 'w']
                ).prefetch_related('items__product')
                
                cancelled_pills = []
                for pending_pill in pending_pills:
                    # Check if this pill contains any of the products being added
                    pill_product_ids = set(pending_pill.items.values_list('product_id', flat=True))
                    if pill_product_ids.intersection(set(product_ids)):
                        logger.info(f"🚫 [ADMIN_ADD_BOOK] Cancelling pending pill {pending_pill.pill_number} for user {user.id}")
                        
                        # Cancel EasyPay invoice if it exists
                        if pending_pill.easypay_fawry_ref:
                            try:
                                logger.info(f"📞 [ADMIN_ADD_BOOK] Cancelling EasyPay invoice for pill {pending_pill.pill_number} (fawry_ref: {pending_pill.easypay_fawry_ref})")
                                result = easypay_service.cancel_invoice(pending_pill.easypay_fawry_ref)
                                
                                if result['success']:
                                    logger.info(f"✅ [ADMIN_ADD_BOOK] Successfully cancelled invoice for pill {pending_pill.pill_number}")
                                else:
                                    logger.warning(f"⚠️ [ADMIN_ADD_BOOK] Failed to cancel invoice for pill {pending_pill.pill_number}: {result.get('error')}")
                            except Exception as e:
                                logger.error(f"❌ [ADMIN_ADD_BOOK] Exception cancelling invoice for pill {pending_pill.pill_number}: {str(e)}")
                        
                        # Mark pill as cancelled
                        pending_pill.status = 'c'
                        pending_pill.save(update_fields=['status'])
                        
                        cancelled_pills.append({
                            'pill_number': pending_pill.pill_number,
                            'status': 'cancelled'
                        })
                        
                        logger.info(f"✅ [ADMIN_ADD_BOOK] Cancelled pill {pending_pill.pill_number}")
                
                if cancelled_pills:
                    logger.info(f"✅ [ADMIN_ADD_BOOK] Cancelled {len(cancelled_pills)} pending pill(s) for user {user.id}")
                
                # Create a special pill for admin-added books
                pill = Pill.objects.create(
                    user=user,
                    status='p',  # Mark as paid immediately
                )
                
                added_books = []
                skipped_books = []
                
                for product in products:
                    # Check if user already has this book
                    existing_purchase = PurchasedBook.objects.filter(
                        user=user,
                        product=product
                    ).first()
                    
                    if existing_purchase:
                        skipped_books.append({
                            'id': product.id,
                            'name': product.name,
                            'reason': 'Already purchased'
                        })
                        continue
                    
                    # Create PillItem
                    pill_item = PillItem.objects.create(
                        pill=pill,
                        user=user,
                        product=product,
                        status='p',
                        price_at_sale=0.0,  # Free for admin-added books
                        date_sold=timezone.now()
                    )
                    
                    # Add to pill items
                    pill.items.add(pill_item)
                    
                    # Create PurchasedBook
                    purchased_book = PurchasedBook.objects.create(
                        user=user,
                        pill=pill,
                        product=product,
                        pill_item=pill_item,
                        product_name=product.name,
                        purchase_method='admin_added',
                    )
                    
                    added_books.append({
                        'id': product.id,
                        'name': product.name,
                        'purchased_at': purchased_book.created_at
                    })
                
                return Response({
                    'success': True,
                    'message': f'Successfully added {len(added_books)} book(s) to student',
                    'data': {
                        'user': {
                            'id': user.id,
                            'name': user.name,
                            'username': user.username
                        },
                        'pill_number': pill.pill_number,
                        'added_books': added_books,
                        'skipped_books': skipped_books,
                        'cancelled_pills': cancelled_pills,
                        'total_added': len(added_books),
                        'total_skipped': len(skipped_books),
                        'total_cancelled': len(cancelled_pills)
                    }
                }, status=status.HTTP_201_CREATED)
                
        except User.DoesNotExist:
            return Response({'error': f'المستخدم ذو المعرف {user_id} غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error adding books to student: {str(e)}")
            return Response({'error': 'حدث خطأ أثناء إضافة الكتب، يرجى المحاولة لاحقًا.'}, status=status.HTTP_400_BAD_REQUEST)


class AdminPurchasedBookListCreateView(generics.ListCreateAPIView):
    """
    Admin endpoint to list and create purchased books
    GET /products/dashboard/purchased-books/
    POST /products/dashboard/purchased-books/
    
    POST body format:
    {
        "user": 1,
        "products": [5, 10, 15],  // Required - list of product IDs
        "pill": 10,  // Optional
        "pill_item": 20  // Optional
    }
    
    Filters: user, product, pill, user_id, product_id, pill_id, start_date, end_date, 
             product_name, username, user_name
    Search: product_name, user__username, user__name
    """
    queryset = PurchasedBook.objects.all().select_related(
        'user', 'product', 'pill', 'pill_item',
        'product__subject', 'product__teacher'
    )
    serializer_class = PurchasedBookSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter, OrderingFilter]
    filterset_class = PurchasedBookFilter
    search_fields = ['product_name', 'user__username', 'user__name', 'product__name']
    ordering_fields = ['created_at', 'product_name', 'user__username', 'price_at_sale']
    ordering = ['-created_at']
    pagination_class = CustomPageNumberPagination
    
    def create(self, request, *args, **kwargs):
        user_id = request.data.get('user')
        products = request.data.get('products')
        pill_id = request.data.get('pill')
        pill_item_id = request.data.get('pill_item')
        
        # Validate required fields
        if not user_id:
            return Response({'error': 'حقل user_id مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not products:
            return Response({'error': 'حقل products مطلوب ويجب أن يكون قائمة'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not isinstance(products, list):
            return Response({'error': 'حقل products يجب أن يكون قائمة من معرّفات المنتجات'}, status=status.HTTP_400_BAD_REQUEST)
        
        if len(products) == 0:
            return Response({'error': 'قائمة المنتجات لا يمكن أن تكون فارغة'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Validate user exists
            user = User.objects.get(id=user_id)
            
            # Validate pill if provided
            pill = None
            if pill_id:
                pill = Pill.objects.get(id=pill_id)
            
            # Validate pill_item if provided
            pill_item = None
            if pill_item_id:
                pill_item = PillItem.objects.get(id=pill_item_id)
            
            # Validate all products exist
            product_objs = Product.objects.filter(id__in=products)
            if product_objs.count() != len(products):
                found_ids = list(product_objs.values_list('id', flat=True))
                missing_ids = [pid for pid in products if pid not in found_ids]
                return Response({'error': f'المنتجات غير موجودة: {missing_ids}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Create purchased books
            created_books = []
            skipped_books = []
            
            with transaction.atomic():
                # Cancel any pending orders (status 'i' or 'w') that contain these products
                from services.easypay_service import easypay_service
                
                # Find all pending pills for this user that contain any of these products
                pending_pills = Pill.objects.filter(
                    user=user,
                    status__in=['i', 'w']
                ).prefetch_related('items__product')
                
                cancelled_pills = []
                for pending_pill in pending_pills:
                    # Check if this pill contains any of the products being added
                    pill_product_ids = set(pending_pill.items.values_list('product_id', flat=True))
                    if pill_product_ids.intersection(set(products)):
                        logger.info(f"🚫 [ADMIN_ADD_BOOK] Cancelling pending pill {pending_pill.pill_number} for user {user.id}")
                        
                        # Cancel EasyPay invoice if it exists
                        if pending_pill.easypay_fawry_ref:
                            try:
                                logger.info(f"📞 [ADMIN_ADD_BOOK] Cancelling EasyPay invoice for pill {pending_pill.pill_number} (fawry_ref: {pending_pill.easypay_fawry_ref})")
                                result = easypay_service.cancel_invoice(pending_pill.easypay_fawry_ref)
                                
                                if result['success']:
                                    logger.info(f"✅ [ADMIN_ADD_BOOK] Successfully cancelled invoice for pill {pending_pill.pill_number}")
                                else:
                                    logger.warning(f"⚠️ [ADMIN_ADD_BOOK] Failed to cancel invoice for pill {pending_pill.pill_number}: {result.get('error')}")
                            except Exception as e:
                                logger.error(f"❌ [ADMIN_ADD_BOOK] Exception cancelling invoice for pill {pending_pill.pill_number}: {str(e)}")
                        
                        # Mark pill as cancelled
                        pending_pill.status = 'c'
                        pending_pill.save(update_fields=['status'])
                        
                        cancelled_pills.append({
                            'pill_number': pending_pill.pill_number,
                            'status': 'cancelled'
                        })
                        
                        logger.info(f"✅ [ADMIN_ADD_BOOK] Cancelled pill {pending_pill.pill_number}")
                
                if cancelled_pills:
                    logger.info(f"✅ [ADMIN_ADD_BOOK] Cancelled {len(cancelled_pills)} pending pill(s) for user {user.id}")
                
                for product in product_objs:
                    # Check if already exists
                    existing = PurchasedBook.objects.filter(
                        user=user,
                        product=product
                    ).first()
                    
                    if existing:
                        skipped_books.append({
                            'id': product.id,
                            'name': product.name,
                            'reason': 'Already exists'
                        })
                        continue
                    
                    # Create purchased book
                    purchased_book = PurchasedBook.objects.create(
                        user=user,
                        product=product,
                        pill=pill,
                        pill_item=pill_item,
                        purchase_method='admin_added',
                    )
                    
                    created_books.append(
                        PurchasedBookSerializer(purchased_book, context={'request': request}).data
                    )
            
            return Response({
                'success': True,
                'message': f'تم إنشاء {len(created_books)} كتاب مشترى بنجاح',
                'data': {
                    'created_books': created_books,
                    'skipped_books': skipped_books,
                    'cancelled_pills': cancelled_pills,
                    'total_created': len(created_books),
                    'total_skipped': len(skipped_books),
                    'total_cancelled': len(cancelled_pills)
                }
            }, status=status.HTTP_201_CREATED)
            
        except User.DoesNotExist:
            return Response({'error': f'المستخدم ذو المعرف {user_id} غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
        except Pill.DoesNotExist:
            return Response({'error': f'الفاتورة ذات المعرف {pill_id} غير موجودة'}, status=status.HTTP_400_BAD_REQUEST)
        except PillItem.DoesNotExist:
            return Response({'error': f'عنصر الفاتورة ذو المعرف {pill_item_id} غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error creating purchased books: {str(e)}")
            return Response({'error': 'حدث خطأ أثناء إنشاء السجلات، يرجى المحاولة لاحقًا.'}, status=status.HTTP_400_BAD_REQUEST)


class AdminUserPurchasedBooksView(generics.ListAPIView):
    """
    Admin endpoint to list purchased books for a specific user
    GET /products/dashboard/purchased-books/by-user/<user_id>/
    """
    serializer_class = PurchasedBookSerializer
    permission_classes = [IsAdminUser]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        user_id = self.kwargs.get('user_id')
        return PurchasedBook.objects.filter(user_id=user_id).select_related(
            'user', 'product', 'pill', 'pill_item',
            'product__subject', 'product__teacher'
        )

    # Optionally, allow ordering and searching if needed
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter, OrderingFilter]
    search_fields = ['product_name', 'user__username', 'user__name', 'product__name']
    ordering_fields = ['created_at', 'product_name', 'user__username', 'price_at_sale']
    ordering = ['-created_at']

class AdminPurchasedBookRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    Admin endpoint to retrieve, update, or delete a purchased book
    GET /products/dashboard/purchased-books/<id>/
    PUT /products/dashboard/purchased-books/<id>/
    PATCH /products/dashboard/purchased-books/<id>/
    DELETE /products/dashboard/purchased-books/<id>/
    """
    queryset = PurchasedBook.objects.all().select_related(
        'user', 'product', 'pill', 'pill_item'
    )
    serializer_class = PurchasedBookSerializer
    permission_classes = [IsAdminUser]


class GeneratePresignedUploadUrlView(APIView):
    """
    Generate presigned URLs for direct S3 uploads.
    
    This endpoint allows clients to upload large files directly to S3
    without storing them on the server first.
    
    POST /products/api/generate-presigned-url/
    
    Request body:
    {
        "file_name": "my-pdf.pdf",
        "file_type": "application/pdf",
        "file_category": "pdf"  # or "image"
    }
    
    Response:
    {
        "success": true,
        "url": "https://s3-presigned-url...",
        "public_url": "https://custom-domain/path/file.pdf",
        "object_key": "pdfs/uuid-filename.pdf",
        "file_type": "application/pdf"
    }
    """
    permission_classes = [IsAdminUser]  
    parser_classes = [JSONParser]
    
    def post(self, request):
        try:
            file_name = request.data.get('file_name', '')
            file_type = request.data.get('file_type', 'application/octet-stream')
            file_category = request.data.get('file_category', 'uploads')  # 'pdf', 'image', or custom folder
            
            if not file_name:
                return Response({'error': 'حقل file_name مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate file category
            allowed_categories = ['pdf', 'image', 'uploads']
            if file_category not in allowed_categories:
                return Response({'error': f'حقل file_category يجب أن يكون أحد القيم: {", ".join(allowed_categories)}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Generate a unique object key
            import uuid
            file_ext = file_name.split('.')[-1] if '.' in file_name else ''
            unique_name = f"{uuid.uuid4()}.{file_ext}" if file_ext else str(uuid.uuid4())
            
            # Map category to S3 folder
            folder_map = {
                'pdf': 'pdfs',
                'image': 'products',
                'uploads': 'uploads'
            }
            folder = folder_map.get(file_category, 'uploads')
            object_key = f"{folder}/{unique_name}"
            
            # Generate presigned URL
            result = s3_service.generate_presigned_upload_url(
                object_key,
                expiration=3600,  # 1 hour
                content_type=file_type
            )
            
            if result['success']:
                return Response(result, status=status.HTTP_200_OK)
            else:
                return Response({'error': result.get('error', 'فشل إنشاء رابط التحميل')}, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            return Response({'error': 'حدث خطأ أثناء إنشاء رابط التحميل، يرجى المحاولة لاحقًا.'}, status=status.HTTP_400_BAD_REQUEST)


# ========== Package Product Views ==========

class MyPackageDetailsView(APIView):
    """Get related products of a package that the user owns"""
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
            
            if product.type != 'package':
                return Response(
                    {'message': 'هذا الكتاب ليس حزمة'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if user owns this package
            purchased_package = PurchasedBook.objects.filter(
                user=request.user,
                product=product
            ).first()
            
            if not purchased_package:
                return Response(
                    {'error': 'أنت لا تملك هذه الحزمة'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get related products
            from .models import PackageProduct
            package_products = PackageProduct.objects.filter(
                package_product=product
            ).select_related('related_product').order_by('-created_at')
            
            books_list = []
            for pp in package_products:
                related = pp.related_product
                books_list.append({
                    'related_product_id': pp.id,
                    'created_at': pp.created_at,
                    'product_id': related.id,
                    'product_number': related.product_number,
                    'name': related.name,
                    'type': related.type,
                    'subject_id': related.subject.id if related.subject else None,
                    'subject_name': related.subject.name if related.subject else None,
                    'teacher_id': related.teacher.id if related.teacher else None,
                    'teacher_name': related.teacher.name if related.teacher else None,
                    'description': related.description,
                    'base_image': get_full_file_url(related.base_image, request) if related.base_image else None,
                    'pdf_file': get_full_file_url(related.pdf_file, request) if related.pdf_file else None,
                    'year': related.year,
                    'is_available': related.is_available,
                    'date_added': related.date_added,
                })
            
            return Response(books_list, status=status.HTTP_200_OK)
            
        except Product.DoesNotExist:
            return Response(
                {'error': 'المنتج غير موجود'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error getting package details: {str(e)}")
            return Response(
                {'error': 'حدث خطأ أثناء جلب تفاصيل الحزمة'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ProductRelatedProductsView(APIView):
    """Get related products of a package product (for browsing, not ownership required)"""
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
            
            if product.type != 'package':
                return Response(
                    {'message': 'هذا الكتاب ليس حزمة'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get related products
            from .models import PackageProduct
            package_products = PackageProduct.objects.filter(
                package_product=product
            ).select_related('related_product').order_by('-created_at')
            
            books_list = []
            for pp in package_products:
                related = pp.related_product
                books_list.append({
                    'related_product_id': pp.id,
                    'created_at': pp.created_at,
                    'product_id': related.id,
                    'product_number': related.product_number,
                    'name': related.name,
                    'type': related.type,
                    'subject_id': related.subject.id if related.subject else None,
                    'subject_name': related.subject.name if related.subject else None,
                    'teacher_id': related.teacher.id if related.teacher else None,
                    'teacher_name': related.teacher.name if related.teacher else None,
                    'description': related.description,
                    'base_image': get_full_file_url(related.base_image, request) if related.base_image else None,
                    'year': related.year,
                    'is_available': related.is_available,
                    'date_added': related.date_added,
                })
            
            return Response(books_list, status=status.HTTP_200_OK)
            
        except Product.DoesNotExist:
            return Response(
                {'error': 'المنتج غير موجود'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error getting related products: {str(e)}")
            return Response(
                {'error': 'حدث خطأ أثناء جلب المنتجات المرتبطة'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AddBooksToPackageView(APIView):
    """Add books to a package (Dashboard endpoint)"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        try:
            package_id = request.data.get('package')
            related_product_ids = request.data.get('related_products', [])
            
            if not package_id:
                return Response(
                    {'error': 'حقل package مطلوب'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not related_product_ids or not isinstance(related_product_ids, list):
                return Response(
                    {'error': 'حقل related_products يجب أن يكون قائمة من معرفات المنتجات'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get package product
            try:
                package = Product.objects.get(id=package_id)
            except Product.DoesNotExist:
                return Response(
                    {'error': 'المنتج الحزمة غير موجود'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            if package.type != 'package':
                return Response(
                    {'error': 'المنتج المحدد ليس من نوع حزمة'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Process each related product
            from .models import PackageProduct
            added = []
            skipped = []
            wrong_type = []
            
            for product_id in related_product_ids:
                try:
                    related_product = Product.objects.get(id=product_id)
                    
                    # Check if it's a book
                    if related_product.type != 'book':
                        wrong_type.append({
                            'id': product_id,
                            'name': related_product.name,
                            'type': related_product.type
                        })
                        continue
                    
                    # Check if already exists
                    if PackageProduct.objects.filter(
                        package_product=package,
                        related_product=related_product
                    ).exists():
                        skipped.append({
                            'id': product_id,
                            'name': related_product.name
                        })
                        continue
                    
                    # Add to package
                    PackageProduct.objects.create(
                        package_product=package,
                        related_product=related_product
                    )
                    added.append({
                        'id': product_id,
                        'name': related_product.name
                    })
                    
                except Product.DoesNotExist:
                    wrong_type.append({
                        'id': product_id,
                        'name': 'غير موجود',
                        'type': 'not_found'
                    })
            
            return Response({
                'message': 'تمت العملية بنجاح',
                'added': added,
                'skipped': skipped,
                'wrong_type': wrong_type,
                'summary': {
                    'total_requested': len(related_product_ids),
                    'added_count': len(added),
                    'skipped_count': len(skipped),
                    'wrong_type_count': len(wrong_type)
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error adding books to package: {str(e)}")
            return Response(
                {'error': 'حدث خطأ أثناء إضافة الكتب للحزمة'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RemoveBookFromPackageView(APIView):
    """Remove a book from a package (Dashboard endpoint)"""
    permission_classes = [IsAdminUser]

    def delete(self, request, pk):
        try:
            from .models import PackageProduct
            package_product = PackageProduct.objects.get(id=pk)
            package_name = package_product.package_product.name
            book_name = package_product.related_product.name
            package_product.delete()
            
            return Response({
                'message': f'تم حذف الكتاب "{book_name}" من الحزمة "{package_name}" بنجاح'
            }, status=status.HTTP_200_OK)
            
        except PackageProduct.DoesNotExist:
            return Response(
                {'error': 'العلاقة غير موجودة'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error removing book from package: {str(e)}")
            return Response(
                {'error': 'حدث خطأ أثناء حذف الكتاب من الحزمة'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RemoveAllProductRelationshipsView(APIView):
    """Remove all PackageProduct relationships for a given product (Dashboard endpoint)"""
    permission_classes = [IsAdminUser]

    def delete(self, request, product_id):
        try:
            from .models import PackageProduct, Product
            
            # Verify product exists
            product = Product.objects.get(id=product_id)
            
            # Get all relationships where this product is involved
            # Either as package_product or related_product
            relationships = PackageProduct.objects.filter(
                Q(package_product=product) | Q(related_product=product)
            )
            
            count = relationships.count()
            
            if count == 0:
                return Response({
                    'message': f'لا توجد علاقات للمنتج "{product.name}"'
                }, status=status.HTTP_200_OK)
            
            # Delete all relationships
            relationships.delete()
            
            return Response({
                'message': f'تم حذف {count} علاقة للمنتج "{product.name}" بنجاح',
                'deleted_count': count
            }, status=status.HTTP_200_OK)
            
        except Product.DoesNotExist:
            return Response(
                {'error': 'المنتج غير موجود'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error removing product relationships: {str(e)}")
            return Response(
                {'error': 'حدث خطأ أثناء حذف علاقات المنتج'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PackageProductListView(generics.ListAPIView):
    """List all package-product relationships (Dashboard)"""
    permission_classes = [IsAdminUser]
    serializer_class = PackageProductListSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = {
        'package_product__is_available': ['exact'],
        'package_product__subject': ['exact'],
        'package_product__teacher': ['exact'],
        'package_product__type': ['exact'],
        'package_product__year': ['exact'],
    }
    ordering_fields = ['id', 'created_at', 'package_product__name', 'related_product__name']
    ordering = ['-created_at']
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        from .models import PackageProduct, Product
        # Get all unique package products (type='package') that have relationships
        # SQLite doesn't support DISTINCT ON, so we'll use values() with distinct()
        package_ids = PackageProduct.objects.filter(
            package_product__type='package'
        ).values_list('package_product_id', flat=True).distinct()
        
        # Get the first PackageProduct PK for each unique package
        pk_list = []
        for package_id in package_ids:
            pp = PackageProduct.objects.filter(
                package_product_id=package_id
            ).values_list('pk', flat=True).first()
            if pp:
                pk_list.append(pp)
        
        # Return a proper QuerySet filtered by these PKs
        return PackageProduct.objects.filter(
            pk__in=pk_list
        ).select_related(
            'package_product__subject',
            'package_product__teacher',
        ).prefetch_related(
            'package_product__package_products__related_product__subject',
            'package_product__package_products__related_product__teacher'
        )


class PackageBooksListView(APIView):
    """Get all books in a specific package (Dashboard)"""
    permission_classes = [IsAdminUser]

    def get(self, request, package_id):
        try:
            # Verify package exists and is a package type
            package = Product.objects.get(id=package_id)
            
            if package.type != 'package':
                return Response(
                    {'error': 'المنتج المحدد ليس من نوع حزمة'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get all related books
            from .models import PackageProduct
            package_products = PackageProduct.objects.filter(
                package_product=package
            ).select_related('related_product').order_by('-created_at')
            
            books_list = []
            for pp in package_products:
                related = pp.related_product
                books_list.append({
                    'related_product_id': pp.id,
                    'created_at': pp.created_at,
                    'product_id': related.id,
                    'product_number': related.product_number,
                    'name': related.name,
                    'type': related.type,
                    'subject_id': related.subject.id if related.subject else None,
                    'subject_name': related.subject.name if related.subject else None,
                    'teacher_id': related.teacher.id if related.teacher else None,
                    'teacher_name': related.teacher.name if related.teacher else None,
                    'description': related.description,
                    'base_image': get_full_file_url(related.base_image, request) if related.base_image else None,
                    'pdf_file': get_full_file_url(related.pdf_file, request) if related.pdf_file else None,
                    'year': related.year,
                    'is_available': related.is_available,
                    'date_added': related.date_added,
                })
            
            return Response(books_list, status=status.HTTP_200_OK)
            
        except Product.DoesNotExist:
            return Response(
                {'error': 'المنتج غير موجود'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error getting package books: {str(e)}")
            return Response(
                {'error': 'حدث خطأ أثناء جلب كتب الحزمة'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


