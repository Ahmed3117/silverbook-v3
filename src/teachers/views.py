from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import ListAPIView
from django.db.models import Count, Sum, Q, F
from django.db.models.functions import Coalesce

from products.models import Teacher, Product, PurchasedBook, PURCHASE_METHOD_CHOICES
from products.serializers import get_full_file_url
from accounts.models import GOVERNMENT_CHOICES
from accounts.pagination import CustomPageNumberPagination
from .serializers import TeacherDashboardSerializer, TeacherProductDetailSerializer, PurchasedBookDetailSerializer

# Build lookup dicts for display values
PURCHASE_METHOD_DISPLAY = dict(PURCHASE_METHOD_CHOICES)
GOVERNMENT_DISPLAY = dict(GOVERNMENT_CHOICES)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_dashboard(request):
    """
    Returns full analytical info for the authenticated teacher.
    
    - Verifies the authenticated user has user_type='teacher'
    - Matches the user to a Teacher model instance by name
    - Returns: teacher profile, products with purchase analytics, and summary stats
    
    Optional query params:
    - from_date (YYYY-MM-DD): filter purchases from this date
    - to_date (YYYY-MM-DD): filter purchases up to this date
    - year: filter products by academic year
    - type: filter products by type (book/package)
    """
    user = request.user

    # 1. Check user is a teacher
    if user.user_type != 'teacher':
        return Response(
            {'detail': 'هذا الحساب ليس حساب مدرس.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    # 2. Find the Teacher instance linked to this user
    teacher = Teacher.objects.select_related('subject').filter(user=user).first()
    if not teacher:
        return Response(
            {'detail': 'لم يتم العثور على ملف المدرس. تأكد من ربط حسابك بملف المدرس.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    # 3. Parse optional filters
    from_date = request.query_params.get('from_date') or request.query_params.get('date_from')
    to_date = request.query_params.get('to_date') or request.query_params.get('date_to')
    year = request.query_params.get('year')
    product_type = request.query_params.get('type')

    # 4. Build products queryset
    products_qs = Product.objects.filter(teacher=teacher).select_related('subject')

    if year:
        products_qs = products_qs.filter(year=year)
    if product_type:
        products_qs = products_qs.filter(type=product_type)

    # Build date filter for purchased books
    date_q = Q()
    if from_date:
        date_q &= Q(purchased_books__created_at__date__gte=from_date)
    if to_date:
        date_q &= Q(purchased_books__created_at__date__lte=to_date)

    # Annotate each product with purchase counts by method
    paid_q = date_q & Q(purchased_books__purchase_method='user_paid')
    free_q = date_q & Q(purchased_books__purchase_method='free')
    admin_q = date_q & Q(purchased_books__purchase_method='admin_added')

    products_qs = products_qs.annotate(
        paid_count=Count('purchased_books', filter=paid_q, distinct=True),
        free_count=Count('purchased_books', filter=free_q, distinct=True),
        admin_added_count=Count('purchased_books', filter=admin_q, distinct=True),
    ).annotate(
        total_purchases=(
            Coalesce(F('paid_count'), 0)
            + Coalesce(F('free_count'), 0)
            + Coalesce(F('admin_added_count'), 0)
        ),
        total_revenue=Coalesce(
            Sum('purchased_books__price_at_sale', filter=paid_q),
            0.0,
        ),
    ).order_by('-total_purchases')

    # 5. Build product results
    product_results = []
    for product in products_qs:
        product_results.append({
            'id': product.id,
            'product_number': product.product_number,
            'name': product.name,
            'type': product.type,
            'year': product.year,
            'price': product.price,
            'discounted_price': product.discounted_price(),
            'has_discount': product.has_discount(),
            'is_available': product.is_available,
            'base_image': get_full_file_url(product.base_image, request) if product.base_image else None,
            'subject_id': product.subject_id,
            'subject_name': product.subject.name if product.subject else None,
            'date_added': product.date_added,
            'paid_count': product.paid_count,
            'free_count': product.free_count,
            'admin_added_count': product.admin_added_count,
            'total_purchases': product.total_purchases,
            'total_revenue': float(product.total_revenue or 0),
        })

    # 6. Build summary
    total_products = len(product_results)
    total_paid = sum(p['paid_count'] for p in product_results)
    total_free = sum(p['free_count'] for p in product_results)
    total_admin = sum(p['admin_added_count'] for p in product_results)
    total_all_purchases = sum(p['total_purchases'] for p in product_results)
    total_revenue = sum(p['total_revenue'] for p in product_results)

    summary = {
        'total_products': total_products,
        'total_paid_purchases': total_paid,
        'total_free_purchases': total_free,
        'total_admin_added': total_admin,
        'total_all_purchases': total_all_purchases,
        'total_revenue': round(total_revenue, 2),
    }

    # 7. Build teacher profile
    teacher_data = {
        'id': teacher.id,
        'name': teacher.name,
        'bio': teacher.bio,
        'image': get_full_file_url(teacher.image, request) if teacher.image else None,
        'subject_id': teacher.subject_id,
        'subject_name': teacher.subject.name if teacher.subject else None,
        'facebook': teacher.facebook,
        'instagram': teacher.instagram,
        'twitter': teacher.twitter,
        'youtube': teacher.youtube,
        'linkedin': teacher.linkedin,
        'telegram': teacher.telegram,
        'website': teacher.website,
        'tiktok': teacher.tiktok,
        'whatsapp': teacher.whatsapp,
    }

    # 8. Build best sellers list (sorted by paid_count desc)
    best_sellers = sorted(
        [
            {
                'product_id': p['id'],
                'product_name': p['name'],
                'product_number': p['product_number'],
                'year': p['year'],
                'base_image': p['base_image'],
                'paid_count': p['paid_count'],
                'total_revenue': p['total_revenue'],
            }
            for p in product_results
            if p['paid_count'] > 0
        ],
        key=lambda x: x['paid_count'],
        reverse=True,
    )

    # 9. Serialize and return
    payload = {
        'teacher': teacher_data,
        'summary': summary,
        'best_sellers': best_sellers,
        'products': product_results,
    }
    serializer = TeacherDashboardSerializer(payload)
    return Response(serializer.data)


def _get_teacher_for_request(request):
    """Validate teacher user and return (teacher, error_response) tuple."""
    user = request.user
    if user.user_type != 'teacher':
        return None, Response(
            {'detail': 'هذا الحساب ليس حساب مدرس.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    teacher = Teacher.objects.select_related('subject').filter(user=user).first()
    if not teacher:
        return None, Response(
            {'detail': 'لم يتم العثور على ملف المدرس. تأكد من ربط حسابك بملف المدرس.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    return teacher, None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_product_detail(request, product_id):
    """
    Returns detailed analytics for a specific product belonging to the authenticated teacher.

    URL: /teachers/products/<product_id>/

    Optional query params:
    - from_date (YYYY-MM-DD): filter purchases from this date
    - to_date (YYYY-MM-DD): filter purchases up to this date
    """
    teacher, error = _get_teacher_for_request(request)
    if error:
        return error

    # Find the product and verify it belongs to this teacher
    product = Product.objects.select_related('subject', 'teacher').filter(
        id=product_id, teacher=teacher
    ).first()
    if not product:
        return Response(
            {'detail': 'المنتج غير موجود أو لا ينتمي إليك.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Parse date filters
    from_date = request.query_params.get('from_date') or request.query_params.get('date_from')
    to_date = request.query_params.get('to_date') or request.query_params.get('date_to')

    # Fetch purchased books for this product
    pb_qs = PurchasedBook.objects.filter(
        product=product
    ).select_related('user')

    if from_date:
        pb_qs = pb_qs.filter(created_at__date__gte=from_date)
    if to_date:
        pb_qs = pb_qs.filter(created_at__date__lte=to_date)

    # Build purchased books list and compute counts
    purchased_books = []
    paid_count = 0
    free_count = 0
    admin_added_count = 0
    total_revenue = 0.0

    for pb in pb_qs:
        u = pb.user
        purchased_books.append({
            'id': pb.id,
            'student_name': u.name if u else None,
            'student_phone': u.username if u else None,
            'student_year': u.get_year_display() if u and u.year else None,
            'student_government': GOVERNMENT_DISPLAY.get(u.government) if u and u.government else None,
            'purchase_method': pb.purchase_method,
            'purchase_method_display': PURCHASE_METHOD_DISPLAY.get(pb.purchase_method, pb.purchase_method),
            'price_at_sale': pb.price_at_sale,
            'created_at': pb.created_at,
        })

        if pb.purchase_method == 'user_paid':
            paid_count += 1
            total_revenue += float(pb.price_at_sale or 0)
        elif pb.purchase_method == 'free':
            free_count += 1
        elif pb.purchase_method == 'admin_added':
            admin_added_count += 1

    total_purchases = paid_count + free_count + admin_added_count

    product_data = {
        'id': product.id,
        'product_number': product.product_number,
        'name': product.name,
        'type': product.type,
        'year': product.year,
        'price': product.price,
        'discounted_price': product.discounted_price(),
        'has_discount': product.has_discount(),
        'is_available': product.is_available,
        'base_image': get_full_file_url(product.base_image, request) if product.base_image else None,
        'subject_id': product.subject_id,
        'subject_name': product.subject.name if product.subject else None,
        'date_added': product.date_added,
        'paid_count': paid_count,
        'free_count': free_count,
        'admin_added_count': admin_added_count,
        'total_purchases': total_purchases,
        'total_revenue': round(total_revenue, 2),
    }

    summary = {
        'paid_count': paid_count,
        'free_count': free_count,
        'admin_added_count': admin_added_count,
        'total_purchases': total_purchases,
        'total_revenue': round(total_revenue, 2),
    }

    serializer = TeacherProductDetailSerializer({'product': product_data, 'summary': summary})
    return Response(serializer.data)


class ProductPurchasedBooksView(ListAPIView):
    """
    Paginated list of purchased books for a specific product belonging to the authenticated teacher.

    URL: /teachers/products/<product_id>/purchasers/

    Optional query params:
    - from_date (YYYY-MM-DD): filter purchases from this date
    - to_date (YYYY-MM-DD): filter purchases up to this date
    - purchase_method: filter by purchase method (user_paid / free / admin_added)
    - year: filter by student year (first-secondary / second-secondary / third-secondary)
    - government: filter by student government code (1-27)
    - division: filter by student division
    - search: search by student name or phone number (partial match)
    - ordering: order by field (created_at, -created_at, price_at_sale, -price_at_sale,
                student_name, -student_name). Default: -created_at
    - page: page number (default 1)
    - per_page: page size (default 100)
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PurchasedBookDetailSerializer
    pagination_class = CustomPageNumberPagination

    ALLOWED_ORDERING = {
        'created_at': 'created_at',
        '-created_at': '-created_at',
        'price_at_sale': 'price_at_sale',
        '-price_at_sale': '-price_at_sale',
        'student_name': 'user__name',
        '-student_name': '-user__name',
    }

    def get_queryset(self):
        return PurchasedBook.objects.none()

    def list(self, request, *args, **kwargs):
        teacher, error = _get_teacher_for_request(request)
        if error:
            return error

        product_id = kwargs.get('product_id')
        product = Product.objects.filter(id=product_id, teacher=teacher).first()
        if not product:
            return Response(
                {'detail': 'المنتج غير موجود أو لا ينتمي إليك.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Date filters
        from_date = request.query_params.get('from_date') or request.query_params.get('date_from')
        to_date = request.query_params.get('to_date') or request.query_params.get('date_to')

        pb_qs = PurchasedBook.objects.filter(
            product=product
        ).select_related('user')

        if from_date:
            pb_qs = pb_qs.filter(created_at__date__gte=from_date)
        if to_date:
            pb_qs = pb_qs.filter(created_at__date__lte=to_date)

        # Purchase method filter
        purchase_method = request.query_params.get('purchase_method')
        if purchase_method:
            pb_qs = pb_qs.filter(purchase_method=purchase_method)

        # Student year filter
        year = request.query_params.get('year')
        if year:
            pb_qs = pb_qs.filter(user__year=year)

        # Student government filter
        government = request.query_params.get('government')
        if government:
            pb_qs = pb_qs.filter(user__government=government)

        # Student division filter
        division = request.query_params.get('division')
        if division:
            pb_qs = pb_qs.filter(user__division=division)

        # Search by student name or phone
        search = request.query_params.get('search')
        if search:
            pb_qs = pb_qs.filter(
                Q(user__name__icontains=search) | Q(user__username__icontains=search)
            )

        # Ordering
        ordering = request.query_params.get('ordering', '-created_at')
        order_field = self.ALLOWED_ORDERING.get(ordering, '-created_at')
        pb_qs = pb_qs.order_by(order_field)

        page = self.paginate_queryset(pb_qs)
        results = []
        for pb in (page if page is not None else pb_qs):
            u = pb.user
            results.append({
                'id': pb.id,
                'student_name': u.name if u else None,
                'student_phone': u.username if u else None,
                'student_year': u.get_year_display() if u and u.year else None,
                'student_government': GOVERNMENT_DISPLAY.get(u.government) if u and u.government else None,
                'purchase_method': pb.purchase_method,
                'purchase_method_display': PURCHASE_METHOD_DISPLAY.get(pb.purchase_method, pb.purchase_method),
                'price_at_sale': pb.price_at_sale,
                'created_at': pb.created_at,
            })

        serializer = PurchasedBookDetailSerializer(results, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
