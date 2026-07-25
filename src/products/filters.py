
from .models import Pill, Product, ProductImage, CouponDiscount, PurchasedBook, BookPublishRequest, PromoCode, GiftCode
from django_filters import rest_framework as filters
from django.db.models import Q, F, FloatField, Case, When, Exists, OuterRef
from django.utils import timezone

class ProductFilter(filters.FilterSet):
    price_min = filters.NumberFilter(method='filter_by_discounted_price_min')
    price_max = filters.NumberFilter(method='filter_by_discounted_price_max')
    size = filters.CharFilter(method='filter_by_size')
    has_images = filters.BooleanFilter(method='filter_has_images')

    class Meta:
        model = Product
        fields = ['subject', 'teacher', 'year', 'type', 'is_downloadable']

    def filter_by_discounted_price_min(self, queryset, name, value):
        now = timezone.now()

        # Annotate the queryset with product discounts
        queryset = queryset.annotate(
            product_discount_price=Case(
                When(
                    Q(discounts__discount_start__lte=now) &
                    Q(discounts__discount_end__gte=now),
                    then=F('price') * (1 - F('discounts__discount') / 100)
                ),
                default=F('price'),
                output_field=FloatField()
            )
        )

        return queryset.filter(product_discount_price__gte=value).distinct()

    def filter_by_discounted_price_max(self, queryset, name, value):
        now = timezone.now()

        # Same annotation logic as above
        queryset = queryset.annotate(
            product_discount_price=Case(
                When(
                    Q(discounts__discount_start__lte=now) &
                    Q(discounts__discount_end__gte=now),
                    then=F('price') * (1 - F('discounts__discount') / 100)
                ),
                default=F('price'),
                output_field=FloatField()
            )
        )

        return queryset.filter(product_discount_price__lte=value).distinct()

    def filter_by_size(self, queryset, name, value):
        return queryset.filter(availabilities__size__iexact=value).distinct()

    def filter_has_images(self, queryset, name, value):
        if value:
            # Filter products that have at least one related image
            return queryset.filter(Exists(ProductImage.objects.filter(product=OuterRef('pk'))))
        else:
            # Filter products that do not have any related images
            return queryset.filter(~Exists(ProductImage.objects.filter(product=OuterRef('pk'))))

    def filter_queryset(self, queryset):
        # Apply all filters (including search)
        queryset = super().filter_queryset(queryset)
        # Simply order the results without slicing
        return queryset.order_by('-date_added')
    
    
    
    
    
    
class CouponDiscountFilter(filters.FilterSet):
    available = filters.BooleanFilter(method='filter_available')

    class Meta:
        model = CouponDiscount
        fields = ['available']

    def filter_available(self, queryset, name, value):
        now = timezone.now()
        if value:
            return queryset.filter(
                available_use_times__gt=0,
                coupon_start__lte=now,
                coupon_end__gte=now
            )
        return queryset

class PillFilter(filters.FilterSet):
    # Add a date range filter for the `date_added` field
    start_date = filters.DateFilter(field_name='date_added', lookup_expr='gte', label='Start Date')
    end_date = filters.DateFilter(field_name='date_added', lookup_expr='lte', label='End Date')

    class Meta:
        model = Pill
        fields = ['status', 'user', 'pill_number']


class BookPublishRequestFilter(filters.FilterSet):
    start_date = filters.DateFilter(field_name='created_at', lookup_expr='date__gte', label='Start Date')
    end_date = filters.DateFilter(field_name='created_at', lookup_expr='date__lte', label='End Date')

    class Meta:
        model = BookPublishRequest
        fields = ['status', 'start_date', 'end_date']


class PurchasedBookFilter(filters.FilterSet):
    user_id = filters.NumberFilter(field_name='user__id')
    product_id = filters.NumberFilter(field_name='product__id')
    pill_id = filters.NumberFilter(field_name='pill__id')
    start_date = filters.DateFilter(field_name='created_at', lookup_expr='gte', label='Start Date')
    end_date = filters.DateFilter(field_name='created_at', lookup_expr='lte', label='End Date')
    product_name = filters.CharFilter(field_name='product_name', lookup_expr='icontains')
    code = filters.CharFilter(field_name='code', lookup_expr='icontains')
    username = filters.CharFilter(field_name='user__username', lookup_expr='icontains')
    user_name = filters.CharFilter(field_name='user__name', lookup_expr='icontains')
    added_by = filters.CharFilter(method='filter_by_added_by')

    class Meta:
        model = PurchasedBook
        fields = ['user', 'product', 'pill', 'code']
    
    def filter_by_added_by(self, queryset, name, value):
        """
        Filter books by who added them:
        - 'admin': Books added by admin directly (pill is null)
        - 'student': Books added by students (pill has a value)
        """
        if value.lower() == 'admin':
            return queryset.filter(pill__isnull=True)
        elif value.lower() == 'student':
            return queryset.filter(pill__isnull=False)
        return queryset


class PromoCodeFilter(filters.FilterSet):
    code = filters.CharFilter(field_name='code', lookup_expr='icontains')
    title = filters.CharFilter(field_name='title', lookup_expr='icontains')
    is_general = filters.BooleanFilter(method='filter_is_general')
    book_id = filters.NumberFilter(field_name='book__id')
    book_name = filters.CharFilter(field_name='book__name', lookup_expr='icontains')
    is_active = filters.BooleanFilter(field_name='is_active')
    is_used = filters.BooleanFilter(field_name='is_used')
    is_valid = filters.BooleanFilter(method='filter_is_valid')
    created_by = filters.NumberFilter(field_name='created_by__id')
    used_by = filters.NumberFilter(field_name='used_by__id')
    start_date = filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    end_date = filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    used_after = filters.DateTimeFilter(field_name='used_at', lookup_expr='gte')
    used_before = filters.DateTimeFilter(field_name='used_at', lookup_expr='lte')

    class Meta:
        model = PromoCode
        fields = ['code', 'is_active', 'is_used']

    def filter_is_general(self, queryset, name, value):
        if value:
            return queryset.filter(book__isnull=True)
        return queryset.filter(book__isnull=False)

    def filter_is_valid(self, queryset, name, value):
        now = timezone.now()
        if value:
            return queryset.filter(
                is_active=True,
                is_used=False,
            ).filter(
                Q(valid_from__isnull=True) | Q(valid_from__lte=now)
            ).filter(
                Q(valid_until__isnull=True) | Q(valid_until__gte=now)
            )
        else:
            return queryset.filter(
                Q(is_active=False) |
                Q(is_used=True) |
                Q(valid_from__gt=now) |
                Q(valid_until__lt=now)
            )


class GiftCodeFilter(filters.FilterSet):
    code = filters.CharFilter(field_name='code', lookup_expr='icontains')
    product_id = filters.NumberFilter(field_name='product__id')
    product_number = filters.CharFilter(field_name='product__product_number', lookup_expr='icontains')
    product_name = filters.CharFilter(field_name='product__name', lookup_expr='icontains')
    product_type = filters.CharFilter(field_name='product__type', lookup_expr='iexact')
    product_year = filters.CharFilter(field_name='product__year', lookup_expr='iexact')
    is_active = filters.BooleanFilter(field_name='is_active')
    is_used = filters.BooleanFilter(field_name='is_used')
    used_for_user_id = filters.NumberFilter(field_name='used_for_user__id')
    used_for_pill_id = filters.NumberFilter(field_name='used_for_pill__id')
    pill_number = filters.CharFilter(field_name='used_for_pill__pill_number', lookup_expr='icontains')
    used_for_purchasedbook_id = filters.NumberFilter(field_name='used_for_purchasedbook__id')
    start_date = filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    end_date = filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    used_after = filters.DateTimeFilter(field_name='used_at', lookup_expr='gte')
    used_before = filters.DateTimeFilter(field_name='used_at', lookup_expr='lte')

    class Meta:
        model = GiftCode
        fields = [
            'code', 'product_id', 'product_number', 'product_name', 'product_type',
            'product_year', 'is_active', 'is_used', 'used_for_user_id',
            'used_for_pill_id', 'pill_number', 'used_for_purchasedbook_id',
        ]
