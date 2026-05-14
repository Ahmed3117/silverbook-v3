from django.db.models import Prefetch
from django.utils import timezone

from .models import Discount, PackageProduct, PillItem, PurchasedBook


def active_discount_queryset():
    now = timezone.now()
    return Discount.objects.filter(
        is_active=True,
        discount_start__lte=now,
        discount_end__gte=now,
    ).order_by('-discount', '-discount_end')


def package_product_queryset():
    return PackageProduct.objects.select_related(
        'related_product',
        'related_product__subject',
        'related_product__teacher',
        'related_product__teacher__user',
    ).order_by('-created_at')


def optimize_pill_item_queryset(queryset=None):
    if queryset is None:
        queryset = PillItem.objects.all()

    return queryset.select_related(
        'product',
        'product__subject',
        'product__teacher',
        'product__teacher__user',
    ).prefetch_related(
        Prefetch('product__discounts', queryset=active_discount_queryset(), to_attr='prefetched_active_discounts'),
        Prefetch('product__package_products', queryset=package_product_queryset(), to_attr='prefetched_package_products'),
    )


def optimize_pill_queryset(queryset):
    return queryset.select_related(
        'user',
        'coupon',
    ).prefetch_related(
        Prefetch('items', queryset=optimize_pill_item_queryset()),
    )


def optimize_purchased_book_queryset(queryset=None):
    if queryset is None:
        queryset = PurchasedBook.objects.all()

    return queryset.select_related(
        'user',
        'product',
        'product__subject',
        'product__teacher',
        'product__teacher__user',
        'pill',
        'pill_item',
    ).prefetch_related(
        Prefetch('product__package_products', queryset=package_product_queryset(), to_attr='prefetched_package_products'),
    )
