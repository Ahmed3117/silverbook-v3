from django.urls import path
from . import views

urlpatterns = [
    path('sales-analytics/', views.sales_analytics, name='sales-analytics'),
    path('best-sellers/', views.best_seller_products, name='best-sellers'),
]
