from django.urls import path
from . import views

urlpatterns = [
    path('sales-analytics/', views.sales_analytics, name='sales-analytics'),
    path('best-sellers/', views.best_seller_products, name='best-sellers'),
    path('products/', views.products_analytics_list, name='analysis-products'),
    path('products/<int:product_id>/purchasers/', views.ProductPurchasersListView.as_view(), name='analysis-product-purchasers'),
]
