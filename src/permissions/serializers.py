"""
Serializers for the permissions app.
Generic: Works with any DRF project.
"""
from rest_framework import serializers
from .models import (
    BackendEndpoint,
    DashboardPage,
    DashboardFeature,
    PermissionGroup,
    AdminPermission
)


class BackendEndpointSerializer(serializers.ModelSerializer):
    """Serializer for backend endpoints (developer use)"""
    class Meta:
        model = BackendEndpoint
        fields = ['id', 'view_name', 'method', 'description']


class DashboardFeatureSimpleSerializer(serializers.ModelSerializer):
    """Simple serializer for features (used in sidebar)"""
    class Meta:
        model = DashboardFeature
        fields = ['code', 'name']


class DashboardPageSerializer(serializers.ModelSerializer):
    """Serializer for dashboard pages with nested features and children"""
    features = DashboardFeatureSimpleSerializer(many=True, read_only=True)
    children = serializers.SerializerMethodField()

    class Meta:
        model = DashboardPage
        fields = ['code', 'name', 'route_name', 'icon', 'features', 'children']

    def get_children(self, obj):
        children = obj.children.filter(is_active=True).order_by('display_order')
        return DashboardPageSerializer(children, many=True).data


class DashboardFeatureDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for features (admin management)"""
    page = serializers.StringRelatedField()
    endpoints = BackendEndpointSerializer(many=True, read_only=True)

    class Meta:
        model = DashboardFeature
        fields = [
            'id', 'name', 'code', 'description', 'page', 'page_name',
            'endpoints', 'display_order', 'is_active'
        ]


class PermissionGroupSerializer(serializers.ModelSerializer):
    """Serializer for permission groups"""
    denied_pages = DashboardPageSerializer(many=True, read_only=True)
    denied_features = DashboardFeatureSimpleSerializer(many=True, read_only=True)
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = PermissionGroup
        fields = [
            'id', 'name', 'description', 'denied_pages',
            'denied_features', 'member_count', 'is_active'
        ]

    def get_member_count(self, obj):
        return obj.admin_permissions.count()


class PermissionGroupCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating permission groups"""
    denied_pages = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=DashboardPage.objects.filter(is_active=True),
        required=False
    )
    denied_features = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=DashboardFeature.objects.filter(is_active=True),
        required=False
    )

    class Meta:
        model = PermissionGroup
        fields = ['name', 'description', 'denied_pages', 'denied_features', 'is_active']


class AdminPermissionSerializer(serializers.ModelSerializer):
    """Serializer for admin permissions (admin management)"""
    user_display = serializers.SerializerMethodField()
    permission_group_name = serializers.SerializerMethodField()

    class Meta:
        model = AdminPermission
        fields = [
            'id', 'user', 'user_display', 'permission_group',
            'permission_group_name', 'is_super_admin', 'is_blocked',
            'created_at', 'updated_at'
        ]

    def get_user_display(self, obj):
        return str(obj.user)

    def get_permission_group_name(self, obj):
        return obj.permission_group.name if obj.permission_group else None


class AdminPermissionCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating admin permissions"""
    extra_denied_pages = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=DashboardPage.objects.filter(is_active=True),
        required=False
    )
    extra_denied_features = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=DashboardFeature.objects.filter(is_active=True),
        required=False
    )

    class Meta:
        model = AdminPermission
        fields = [
            'user', 'permission_group', 'extra_denied_pages',
            'extra_denied_features', 'is_super_admin', 'is_blocked'
        ]


class UserPermissionsResponseSerializer:
    """
    Response formatter for frontend login.
    Provides sidebar structure with allowed pages and features.
    Generic: Works with any frontend framework.
    """

    @staticmethod
    def get_permissions_data(admin_permission):
        """
        Generate permission data for login response.
        Returns structured data for frontend permission handling.
        """
        if admin_permission.is_blocked:
            return {
                'is_super_admin': False,
                'is_blocked': True,
                'sidebar': [],
                'denied_pages': [],
                'denied_features': [],
                'denied_routes': [],
            }

        # Get sidebar data
        sidebar = admin_permission.get_sidebar_data()

        # Get denied items for frontend checks
        denied_pages = list(
            admin_permission.get_all_denied_pages()
            .values_list('code', flat=True)
        )
        denied_features = list(
            admin_permission.get_all_denied_features()
            .values_list('code', flat=True)
        )
        denied_routes = list(
            admin_permission.get_all_denied_pages()
            .exclude(route_name='')
            .values_list('route_name', flat=True)
        )

        return {
            'is_super_admin': admin_permission.is_super_admin,
            'is_blocked': False,
            'sidebar': sidebar,
            'denied_pages': denied_pages,
            'denied_features': denied_features,
            'denied_routes': denied_routes,
        }
