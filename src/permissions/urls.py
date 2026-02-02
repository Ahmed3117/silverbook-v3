"""
URL configuration for the permissions app.
Generic: Works with any Django REST Framework project.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DashboardPageViewSet,
    DashboardFeatureViewSet,
    PermissionGroupViewSet,
    AdminPermissionViewSet,
)

router = DefaultRouter()
router.register(r'pages', DashboardPageViewSet, basename='dashboard-page')
router.register(r'features', DashboardFeatureViewSet, basename='dashboard-feature')
router.register(r'groups', PermissionGroupViewSet, basename='permission-group')
router.register(r'admins', AdminPermissionViewSet, basename='admin-permission')

urlpatterns = [
    path('', include(router.urls)),
]
