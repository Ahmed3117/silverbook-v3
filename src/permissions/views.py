"""
API views for the permissions app.
Generic: Works with any DRF project.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from .models import (
    DashboardPage,
    DashboardFeature,
    PermissionGroup,
    AdminPermission
)
from .serializers import (
    DashboardPageSerializer,
    DashboardFeatureSimpleSerializer,
    DashboardFeatureDetailSerializer,
    PermissionGroupSerializer,
    PermissionGroupCreateUpdateSerializer,
    AdminPermissionSerializer,
    AdminPermissionCreateUpdateSerializer,
)
from .utils import get_user_permissions_for_response


class DashboardPageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing dashboard pages.
    Used for populating permission group forms.
    """
    queryset = DashboardPage.objects.filter(is_active=True)
    serializer_class = DashboardPageSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        queryset = super().get_queryset()
        # Only return root pages (children are nested)
        if self.action == 'list':
            queryset = queryset.filter(parent__isnull=True)
        return queryset.order_by('display_order')

    @action(detail=False, methods=['get'])
    def flat_list(self, request):
        """Get all pages as a flat list without pagination (returns full data)
        
        Query params:
        - is_active: true/false (optional, filters by active status)
        """
        queryset = DashboardPage.objects.filter(parent__isnull=True)
        
        # Filter by active status if provided
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        pages = queryset.order_by('display_order')
        serializer = DashboardPageSerializer(pages, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def flat_detail(self, request, pk=None):
        """Get a single page in flat format (with full serialization)"""
        page = self.get_object()
        serializer = DashboardPageSerializer(page)
        return Response(serializer.data)


class DashboardFeatureViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing dashboard features.
    Used for populating permission group forms.
    """
    queryset = DashboardFeature.objects.filter(is_active=True)
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DashboardFeatureDetailSerializer
        return DashboardFeatureSimpleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by page if provided (use page_id to avoid conflicts with pagination)
        page_id = self.request.query_params.get('page_id')
        if page_id:
            queryset = queryset.filter(page_id=page_id)
        return queryset.order_by('page__display_order', 'display_order')

    @action(detail=False, methods=['get'])
    def flat_list(self, request):
        """Get all features as a flat list (for select dropdowns)"""
        features = DashboardFeature.objects.filter(is_active=True).order_by(
            'page__display_order', 'display_order'
        )
        data = [
            {
                'id': feature.id,
                'code': feature.code,
                'name': str(feature),  # Includes page name
            }
            for feature in features
        ]
        return Response(data)


class PermissionGroupViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing permission groups.
    """
    queryset = PermissionGroup.objects.all()
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PermissionGroupCreateUpdateSerializer
        return PermissionGroupSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by active status if provided
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        return queryset.order_by('name')

    @action(detail=False, methods=['get'])
    def flat_list(self, request):
        """Get all permission groups as a flat list without pagination (returns full data)
        
        Query params:
        - is_active: true/false (optional, filters by active status)
        """
        queryset = PermissionGroup.objects.all()
        
        # Filter by active status if provided
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        groups = queryset.order_by('name')
        serializer = PermissionGroupSerializer(groups, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def flat_detail(self, request, pk=None):
        """Get a single permission group in flat format (with full serialization)"""
        group = self.get_object()
        serializer = PermissionGroupSerializer(group)
        return Response(serializer.data)


class AdminPermissionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing admin permissions.
    """
    queryset = AdminPermission.objects.all()
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AdminPermissionCreateUpdateSerializer
        return AdminPermissionSerializer

    def get_queryset(self):
        queryset = super().get_queryset().select_related('user', 'permission_group')

        # Filter by user
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Filter by permission group
        group_id = self.request.query_params.get('permission_group')
        if group_id:
            queryset = queryset.filter(permission_group_id=group_id)

        # Filter by status
        is_blocked = self.request.query_params.get('is_blocked')
        if is_blocked is not None:
            queryset = queryset.filter(is_blocked=is_blocked.lower() == 'true')

        is_super_admin = self.request.query_params.get('is_super_admin')
        if is_super_admin is not None:
            queryset = queryset.filter(is_super_admin=is_super_admin.lower() == 'true')

        return queryset.order_by('-created_at')

    @action(detail=False, methods=['get'])
    def my_permissions(self, request):
        """Get current user's permissions"""
        permissions = get_user_permissions_for_response(request.user)
        if permissions is None:
            return Response(
                {'detail': 'No admin permissions found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(permissions)

    @action(detail=True, methods=['post'])
    def toggle_blocked(self, request, pk=None):
        """Toggle blocked status for an admin"""
        admin_permission = self.get_object()
        admin_permission.is_blocked = not admin_permission.is_blocked
        admin_permission.save(update_fields=['is_blocked', 'updated_at'])
        return Response({
            'is_blocked': admin_permission.is_blocked,
            'message': f"Admin {'blocked' if admin_permission.is_blocked else 'unblocked'} successfully."
        })

    @action(detail=True, methods=['post'])
    def toggle_super_admin(self, request, pk=None):
        """Toggle super admin status"""
        admin_permission = self.get_object()
        admin_permission.is_super_admin = not admin_permission.is_super_admin
        admin_permission.save(update_fields=['is_super_admin', 'updated_at'])
        return Response({
            'is_super_admin': admin_permission.is_super_admin,
            'message': f"Super admin status {'enabled' if admin_permission.is_super_admin else 'disabled'}."
        })
