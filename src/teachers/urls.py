from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.teacher_dashboard, name='teacher-dashboard'),
    path('products/<int:product_id>/', views.teacher_product_detail, name='teacher-product-detail'),
    path('products/<int:product_id>/purchasers/', views.ProductPurchasedBooksView.as_view(), name='teacher-product-purchasers'),
]
