
from .models import Pill, Product, ProductImage, CouponDiscount, PurchasedBook
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
        fields = ['subject', 'teacher', 'year', 'type']

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


class PurchasedBookFilter(filters.FilterSet):
    user_id = filters.NumberFilter(field_name='user__id')
    product_id = filters.NumberFilter(field_name='product__id')
    pill_id = filters.NumberFilter(field_name='pill__id')
    start_date = filters.DateFilter(field_name='created_at', lookup_expr='gte', label='Start Date')
    end_date = filters.DateFilter(field_name='created_at', lookup_expr='lte', label='End Date')
    product_name = filters.CharFilter(field_name='product_name', lookup_expr='icontains')
    username = filters.CharFilter(field_name='user__username', lookup_expr='icontains')
    user_name = filters.CharFilter(field_name='user__name', lookup_expr='icontains')

    class Meta:
        model = PurchasedBook
        fields = ['user', 'product', 'pill']
        
        
        