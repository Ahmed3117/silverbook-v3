from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated,IsAdminUser
from rest_framework.response import Response
from django.db.models import Count, Sum, Q, F, IntegerField, OuterRef, Subquery, Case, When, Value, CharField
from django.db.models.functions import Coalesce
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qs
from datetime import datetime, timedelta
from products.models import PurchasedBook, Product, Pill
from accounts.models import YEAR_CHOICES
from .serializers import SalesAnalyticsSerializer, BestSellerProductSerializer
from rest_framework import generics
from accounts.pagination import CustomPageNumberPagination
from accounts.models import User
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters as rest_filters


@api_view(['GET'])
@permission_classes([IsAdminUser])
def products_analytics_list(request):
    """List all products in the same response shape as dashboard purchased-books, plus paid_times.

    Filters (query params):
    - year
    - teacher (teacher id)
    - subject (subject id)
    - type (book/package)
    - from_date (YYYY-MM-DD) -> affects paid_times calculation and optional filtering
    - to_date (YYYY-MM-DD)

    Search (query param `search`): book_token, product_number, name
    """

    qs = Product.objects.all().select_related('subject', 'teacher')

    year = request.query_params.get('year')
    teacher = request.query_params.get('teacher') or request.query_params.get('teacher_id')
    subject = request.query_params.get('subject') or request.query_params.get('subject_id')
    product_type = request.query_params.get('type')
    from_date = request.query_params.get('from_date') or request.query_params.get('date_from')
    to_date = request.query_params.get('to_date') or request.query_params.get('date_to')
    search = (request.query_params.get('search') or '').strip()

    if year:
        qs = qs.filter(year=year)
    if teacher:
        qs = qs.filter(teacher_id=teacher)
    if subject:
        qs = qs.filter(subject_id=subject)
    if product_type:
        qs = qs.filter(type=product_type)

    if search:
        qs = qs.filter(
            Q(book_token__icontains=search)
            | Q(product_number__icontains=search)
            | Q(name__icontains=search)
        )

    date_q = Q()
    if from_date:
        date_q &= Q(purchased_books__created_at__date__gte=from_date)
    if to_date:
        date_q &= Q(purchased_books__created_at__date__lte=to_date)

    paid_q = date_q & Q(purchased_books__purchase_method='user_paid')
    free_q = date_q & Q(purchased_books__purchase_method='free')
    manual_q = date_q & Q(purchased_books__purchase_method='admin_added')

    qs = qs.annotate(
        paid_times=Count('purchased_books', filter=paid_q, distinct=True),
        free_paid_times=Count('purchased_books', filter=free_q, distinct=True),
        manual_assigned_times=Count('purchased_books', filter=manual_q, distinct=True),
    ).annotate(
        total_paid_times=(
            Coalesce(F('paid_times'), 0)
            + Coalesce(F('free_paid_times'), 0)
            + Coalesce(F('manual_assigned_times'), 0)
        )
    )

    # Simple ordering
    ordering = request.query_params.get('ordering') or '-total_paid_times'

    # Aliases for convenience
    if ordering in {'product_name', '-product_name'}:
        ordering = ordering.replace('product_name', 'name')
    allowed_ordering = {
        'paid_times',
        '-paid_times',
        'free_paid_times',
        '-free_paid_times',
        'manual_assigned_times',
        '-manual_assigned_times',
        'total_paid_times',
        '-total_paid_times',
        'date_added',
        '-date_added',
        'name',
        '-name',
    }
    if ordering not in allowed_ordering:
        ordering = '-total_paid_times'
    qs = qs.order_by(ordering)

    # Pagination (lightweight, page/page_size)
    try:
        page = int(request.query_params.get('page', 1))
    except ValueError:
        page = 1

    # Accept `per_page` as an alias of `page_size` for consistency with other endpoints.
    raw_page_size = request.query_params.get('per_page') or request.query_params.get('page_size') or 20
    try:
        page_size = int(raw_page_size)
    except (TypeError, ValueError):
        page_size = 20
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)

    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = list(qs[start:end])

    def _build_page_url(target_page: int):
        parts = urlsplit(request.build_absolute_uri())
        query = parse_qs(parts.query)
        query['page'] = [str(target_page)]
        # Preserve caller's page size param style.
        if 'per_page' in query or 'page_size' not in query:
            query['per_page'] = [str(page_size)]
            query.pop('page_size', None)
        else:
            query['page_size'] = [str(page_size)]
            query.pop('per_page', None)
        new_query = urlencode(query, doseq=True)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))

    next_url = _build_page_url(page + 1) if end < total else None
    previous_url = _build_page_url(page - 1) if page > 1 else None

    # Build response rows in PurchasedBook-like shape.
    from .serializers import AnalysisProductListSerializer, _get_full_file_url

    request_obj = request
    results = []
    for product in items:
        results.append(
            {
                'id': product.id,
                'book_token': product.book_token,
                'product_number': product.product_number,
                'name': product.name,
                'product_name': product.name,
                'created_at': product.date_added,
                'student_name': None,
                'student_phone': None,
                'type': product.type,
                'year': product.year,
                'subject_id': product.subject_id,
                'subject_name': product.subject.name if product.subject else None,
                'teacher_id': product.teacher_id,
                'teacher_name': product.teacher.name if product.teacher else None,
                'base_image': _get_full_file_url(product.base_image, request_obj) if product.base_image else None,
                'pdf_file': _get_full_file_url(product.pdf_file, request_obj) if product.pdf_file else None,
                'paid_times': int(getattr(product, 'paid_times', 0) or 0),
                'free_paid_times': int(getattr(product, 'free_paid_times', 0) or 0),
                'manual_assigned_times': int(getattr(product, 'manual_assigned_times', 0) or 0),
                'total_paid_times': int(getattr(product, 'total_paid_times', 0) or 0),
            }
        )

    payload = {
        'count': total,
        'next': next_url,
        'previous': previous_url,
        'results': AnalysisProductListSerializer(results, many=True).data,
    }
    return Response(payload)


class ProductPurchasersListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, rest_filters.SearchFilter]
    filterset_fields = ['year']
    search_fields = ['name', 'username']

    def get_serializer_class(self):
        from .serializers import AnalysisPurchaserUserSerializer
        return AnalysisPurchaserUserSerializer

    def get_queryset(self):
        product_id = self.kwargs.get('product_id')

        from_date = self.request.query_params.get('from_date') or self.request.query_params.get('date_from')
        to_date = self.request.query_params.get('to_date') or self.request.query_params.get('date_to')
        paid_only = (self.request.query_params.get('paid_only') or 'false').lower() == 'true'
        purchase_method = (self.request.query_params.get('purchase_method') or '').strip()

        pb_filter = Q(purchased_books__product_id=product_id)
        if from_date:
            pb_filter &= Q(purchased_books__created_at__date__gte=from_date)
        if to_date:
            pb_filter &= Q(purchased_books__created_at__date__lte=to_date)

        # Optional filter by how the user got the product.
        # Accept Arabic labels or English aliases (and stored codes).
        purchase_method_to_code = {
            'تعيين يدوي': 'admin_added',
            'manual': 'admin_added',
            'admin_added': 'admin_added',
            'مجاني': 'free',
            'free': 'free',
            'مدفوع': 'user_paid',
            'paid': 'user_paid',
            'user_paid': 'user_paid',
        }
        method_code = purchase_method_to_code.get(purchase_method)
        if method_code:
            pb_filter &= Q(purchased_books__purchase_method=method_code)
        else:
            # Default aligns with /analysis/products/: include any of the three methods.
            # paid_only excludes admin assignments.
            if paid_only:
                pb_filter &= Q(purchased_books__purchase_method__in=['user_paid', 'free'])
            else:
                pb_filter &= Q(purchased_books__purchase_method__in=['user_paid', 'free', 'admin_added'])

        # Derive *how* the user got the product from the latest qualifying PurchasedBook.
        purchased_books_latest = PurchasedBook.objects.filter(user_id=OuterRef('pk'), product_id=product_id)
        if from_date:
            purchased_books_latest = purchased_books_latest.filter(created_at__date__gte=from_date)
        if to_date:
            purchased_books_latest = purchased_books_latest.filter(created_at__date__lte=to_date)

        # Keep annotation source consistent with filtering.
        if method_code:
            purchased_books_latest = purchased_books_latest.filter(purchase_method=method_code)
        else:
            if paid_only:
                purchased_books_latest = purchased_books_latest.filter(purchase_method__in=['user_paid', 'free'])
            else:
                purchased_books_latest = purchased_books_latest.filter(purchase_method__in=['user_paid', 'free', 'admin_added'])

        purchased_books_latest = (
            purchased_books_latest.annotate(
                purchase_method_label=Case(
                    When(purchase_method='admin_added', then=Value('تعيين يدوي')),
                    When(purchase_method='free', then=Value('مجاني')),
                    When(purchase_method='user_paid', then=Value('مدفوع')),
                    default=Value('غير محدد'),
                    output_field=CharField(),
                )
            )
            .order_by('-created_at', '-id')
            .values('purchase_method_label')
        )

        return (
            User.objects.filter(pb_filter)
            .only('id', 'name', 'username', 'year')
            .annotate(purchase_method_label=Subquery(purchased_books_latest[:1]))
            .distinct()
            .order_by('username')
        )


@api_view(['GET'])
@permission_classes([IsAdminUser])
def sales_analytics(request):
    """
    Get sales analytics from PurchasedBook records
    
    Query Parameters:
    - ordering: 'ascend' or 'descend' (default: 'descend')
    - limit: number to limit results per list (default: no limit)
    - date_from: filter from this date (format: YYYY-MM-DD or ISO format with time like 2026-02-03T14:30:00)
    - date_to: filter to this date (format: YYYY-MM-DD or ISO format with time like 2026-02-03T18:45:00)
    
    Examples:
    - /analysis/sales-analytics/?date_from=2026-02-03&date_to=2026-02-03
      Returns all records from 2026-02-03 (00:00:00 to 23:59:59)
    
    - /analysis/sales-analytics/?date_from=2026-02-03T14:30:00&date_to=2026-02-03T18:45:00
      Returns records between 2:30 PM and 6:45 PM on 2026-02-03
    
    - /analysis/sales-analytics/?date_from=2026-02-03&date_to=2026-02-05
      Returns records from entire day on 2026-02-03 through entire day on 2026-02-05
    """
    # Get query parameters
    ordering = request.query_params.get('ordering', 'descend')
    limit = request.query_params.get('limit', None)
    date_from = request.query_params.get('date_from', None)
    date_to = request.query_params.get('date_to', None)
    
    # Validate ordering
    if ordering not in ['ascend', 'descend']:
        ordering = 'descend'
    
    # Parse limit
    if limit is not None:
        try:
            limit = int(limit)
            if limit < 0:
                limit = None
        except ValueError:
            limit = None
    else:
        limit = None
    
    # Determine ordering direction
    order_prefix = '' if ordering == 'ascend' else '-'
    
    # Helper function to parse date strings and handle end-of-day for date_to
    def _parse_datetime(date_str, is_end_of_day=False):
        """Parse date string. If is_end_of_day=True and only date is provided, set to 23:59:59."""
        if not date_str:
            return None
        try:
            # Try parsing as datetime first (ISO format with time)
            if 'T' in date_str or ' ' in date_str:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            else:
                # Parse as date only (YYYY-MM-DD)
                parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                if is_end_of_day:
                    # Set to end of day (23:59:59)
                    return datetime.combine(parsed_date, datetime.max.time())
                else:
                    # Set to start of day (00:00:00)
                    return datetime.combine(parsed_date, datetime.min.time())
        except (ValueError, AttributeError):
            return None
    
    # Parse dates
    date_from_parsed = _parse_datetime(date_from, is_end_of_day=False)
    date_to_parsed = _parse_datetime(date_to, is_end_of_day=True)
    
    # Query purchased books (these represent completed sales)
    purchased_books = PurchasedBook.objects.select_related(
        'product__subject',
        'product__teacher'
    )
    
    # Apply date filters if provided
    if date_from_parsed:
        purchased_books = purchased_books.filter(created_at__gte=date_from_parsed)
    if date_to_parsed:
        purchased_books = purchased_books.filter(created_at__lte=date_to_parsed)
    
    # Query all pills for total orders count
    all_pills = Pill.objects.all()
    
    # Apply date filters to all_pills as well
    if date_from_parsed:
        all_pills = all_pills.filter(date_added__gte=date_from_parsed)
    if date_to_parsed:
        all_pills = all_pills.filter(date_added__lte=date_to_parsed)
    
    # Summary statistics
    summary = {
        'total_paid_books': purchased_books.count(),
        'total_orders': all_pills.count(),
        'paid_orders': all_pills.filter(status='p').count(),
        'waiting_orders': all_pills.filter(
            Q(status='w') | Q(status='i')
        ).count(),
        'total_revenue': float(purchased_books.aggregate(
            total=Sum('price_at_sale')
        )['total'] or 0.0)
    }
    
    # Subjects analytics
    subjects_data = purchased_books.filter(
        product__subject__isnull=False
    ).values(
        'product__subject__id',
        'product__subject__name'
    ).annotate(
        count=Count('id')
    ).order_by(f'{order_prefix}count')
    
    if limit is not None:
        subjects_data = subjects_data[:limit]
    
    subjects = [
        {
            'id': item['product__subject__id'],
            'name': item['product__subject__name'],
            'count': item['count']
        }
        for item in subjects_data
    ]
    
    # Teachers analytics
    teachers_data = purchased_books.filter(
        product__teacher__isnull=False
    ).values(
        'product__teacher__id',
        'product__teacher__name'
    ).annotate(
        count=Count('id')
    ).order_by(f'{order_prefix}count')
    
    if limit is not None:
        teachers_data = teachers_data[:limit]
    
    teachers = [
        {
            'id': item['product__teacher__id'],
            'name': item['product__teacher__name'],
            'count': item['count']
        }
        for item in teachers_data
    ]
    
    # Years analytics - include all years from YEAR_CHOICES
    # Years list is not affected by ordering or limit parameters
    years = []
    for year_code, year_name in YEAR_CHOICES:
        count = purchased_books.filter(product__year=year_code).count()
        years.append({
            'year': year_code,
            'count': count
        })
    
    # Prepare response data
    data = {
        'summary': summary,
        'subjects': subjects,
        'teachers': teachers,
        'years': years
    }
    
    serializer = SalesAnalyticsSerializer(data)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def best_seller_products(request):
    """
    Get best seller products based on PurchasedBook records
    
    Query Parameters:
    - limit: number to limit results (default: 10)
    - date_from: filter from this date (format: YYYY-MM-DD or ISO format with time like 2026-02-03T14:30:00)
    - date_to: filter to this date (format: YYYY-MM-DD or ISO format with time like 2026-02-03T18:45:00)
    
    Examples:
    - /analysis/best-seller-products/?date_from=2026-02-03&date_to=2026-02-03
      Returns best sellers from entire day on 2026-02-03
    
    - /analysis/best-seller-products/?date_from=2026-02-03T14:30:00&date_to=2026-02-03T18:45:00&limit=5
      Returns top 5 best sellers between 2:30 PM and 6:45 PM
    """
    # Get query parameters
    limit = request.query_params.get('limit', 10)
    date_from = request.query_params.get('date_from', None)
    date_to = request.query_params.get('date_to', None)
    
    # Parse limit
    try:
        limit = int(limit)
        if limit < 0:
            limit = 10
    except ValueError:
        limit = 10
    
    # Helper function to parse date strings and handle end-of-day for date_to
    def _parse_datetime(date_str, is_end_of_day=False):
        """Parse date string. If is_end_of_day=True and only date is provided, set to 23:59:59."""
        if not date_str:
            return None
        try:
            # Try parsing as datetime first (ISO format with time)
            if 'T' in date_str or ' ' in date_str:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            else:
                # Parse as date only (YYYY-MM-DD)
                parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                if is_end_of_day:
                    # Set to end of day (23:59:59)
                    return datetime.combine(parsed_date, datetime.max.time())
                else:
                    # Set to start of day (00:00:00)
                    return datetime.combine(parsed_date, datetime.min.time())
        except (ValueError, AttributeError):
            return None
    
    # Parse dates
    date_from_parsed = _parse_datetime(date_from, is_end_of_day=False)
    date_to_parsed = _parse_datetime(date_to, is_end_of_day=True)
    
    # Get best selling products from PurchasedBook with date filtering
    best_sellers = PurchasedBook.objects.all()
    
    # Apply date filters if provided
    if date_from_parsed:
        best_sellers = best_sellers.filter(created_at__gte=date_from_parsed)
    if date_to_parsed:
        best_sellers = best_sellers.filter(created_at__lte=date_to_parsed)
    
    # Continue with aggregation
    best_sellers = best_sellers.values(
        'product__id',
        'product__name',
        'product__price',
        'product__subject__name',
        'product__teacher__name',
        'product__year'
    ).annotate(
        sales_count=Count('id'),
        total_revenue=Sum('price_at_sale')
    ).order_by('-sales_count')
    
    if limit is not None:
        best_sellers = best_sellers[:limit]
    
    # Format the response
    products = [
        {
            'id': item['product__id'],
            'name': item['product__name'],
            'price': item['product__price'],
            'subject': item['product__subject__name'],
            'teacher': item['product__teacher__name'],
            'year': item['product__year'],
            'sales_count': item['sales_count'],
            'total_revenue': float(item['total_revenue'] or 0.0)
        }
        for item in best_sellers
    ]
    
    serializer = BestSellerProductSerializer(products, many=True)
    return Response(serializer.data)
