"""
Permission mixins and decorators for Django REST Framework views.
Generic: Works with any DRF project.
"""
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from django.urls import resolve
from functools import wraps


class HasEndpointPermission(BasePermission):
    """
    Permission class that checks endpoint access based on admin permissions.

    Supports context via:
    1. View attributes: feature_code, page_code
    2. Request headers: X-Feature-Code, X-Page-Code
    3. Query parameters: feature_code, page_code

    Generic: Works with any DRF viewset or APIView.
    """
    message = "You don't have permission to access this endpoint."

    def has_permission(self, request, view):
        user = request.user

        if not user.is_authenticated:
            return False

        # Non-staff users bypass admin permission checks
        # Customize this based on your user model
        if not getattr(user, 'is_staff', False):
            return True

        # Django superusers always have access
        if user.is_superuser:
            return True

        # Check admin permission record
        try:
            admin_permission = user.admin_permission
        except AttributeError:
            # No record = no restrictions = full access
            return True

        if admin_permission.is_blocked:
            self.message = "Your admin access has been blocked."
            return False

        if admin_permission.is_super_admin:
            return True

        view_name = self._get_view_name(request, view)
        method = request.method
        feature_code = self._get_feature_code(request, view)
        page_code = self._get_page_code(request, view)

        has_access = admin_permission.has_endpoint_permission(
            view_name,
            method,
            feature_code=feature_code,
            page_code=page_code
        )

        if not has_access:
            self.message = "You don't have permission to perform this action."

        return has_access

    def _get_view_name(self, request, view):
        """Get the view name for permission checking."""
        try:
            resolved = resolve(request.path)
            if resolved.url_name:
                namespace = resolved.namespace
                if namespace:
                    return f"{namespace}:{resolved.url_name}"
                return resolved.url_name
        except Exception:
            pass

        view_class = getattr(view, '__class__', None)
        if view_class:
            return f"{view_class.__module__}.{view_class.__name__}"

        return request.path

    def _get_feature_code(self, request, view):
        """Get feature code from various sources."""
        # 1. View attribute
        feature_code = getattr(view, 'feature_code', None)
        if feature_code:
            return feature_code

        # 2. Request header
        feature_code = request.headers.get('X-Feature-Code')
        if feature_code:
            return feature_code

        # 3. Query parameter
        feature_code = request.query_params.get('feature_code')
        if feature_code:
            return feature_code

        return None

    def _get_page_code(self, request, view):
        """Get page code from various sources."""
        # 1. View attribute
        page_code = getattr(view, 'page_code', None)
        if page_code:
            return page_code

        # 2. Request header
        page_code = request.headers.get('X-Page-Code')
        if page_code:
            return page_code

        # 3. Query parameter
        page_code = request.query_params.get('page_code')
        if page_code:
            return page_code

        return None


class AdminPermissionMixin:
    """
    Mixin for class-based views.
    Set feature_code and/or page_code on the view class.

    Usage:
        class MyView(AdminPermissionMixin, APIView):
            feature_code = 'users.create'
            page_code = 'page.users'
    """
    feature_code = None
    page_code = None

    def get_permissions(self):
        permissions = super().get_permissions()
        permissions.append(HasEndpointPermission())
        return permissions


def require_permission(feature_code=None, page_code=None):
    """
    Decorator to specify which feature/page an endpoint belongs to.

    Usage for class-based views:
        @require_permission(feature_code='users.delete')
        class DeleteUserView(APIView):
            ...

        @require_permission(page_code='page.users')
        class UsersPageView(APIView):
            ...

        @require_permission(feature_code='users.create', page_code='page.users')
        class CreateUserView(APIView):
            ...

    Usage for function-based views:
        @api_view(['DELETE'])
        @require_permission(feature_code='users.delete')
        def delete_user(request, pk):
            ...
    """
    def decorator(view_class_or_func):
        if feature_code:
            view_class_or_func.feature_code = feature_code
        if page_code:
            view_class_or_func.page_code = page_code
        return view_class_or_func

    return decorator


def check_feature_permission(feature_code):
    """
    Decorator for function-based views that checks feature permission.
    Raises PermissionDenied if user doesn't have the feature.

    Usage:
        @api_view(['POST'])
        @check_feature_permission('users.create')
        def create_user(request):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            user = request.user

            if not user.is_authenticated:
                raise PermissionDenied("Authentication required.")

            # Non-staff bypass
            if not getattr(user, 'is_staff', False):
                return func(request, *args, **kwargs)

            # Superuser bypass
            if user.is_superuser:
                return func(request, *args, **kwargs)

            try:
                admin_permission = user.admin_permission
            except AttributeError:
                return func(request, *args, **kwargs)

            if admin_permission.is_blocked:
                raise PermissionDenied("Your admin access has been blocked.")

            if admin_permission.is_super_admin:
                return func(request, *args, **kwargs)

            if not admin_permission.has_feature_permission(feature_code):
                raise PermissionDenied(
                    f"You don't have permission for this action: {feature_code}"
                )

            return func(request, *args, **kwargs)
        return wrapper
    return decorator


def check_page_permission(page_code):
    """
    Decorator for function-based views that checks page permission.
    Raises PermissionDenied if user doesn't have access to the page.

    Usage:
        @api_view(['GET'])
        @check_page_permission('page.users')
        def get_users_page_data(request):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            user = request.user

            if not user.is_authenticated:
                raise PermissionDenied("Authentication required.")

            # Non-staff bypass
            if not getattr(user, 'is_staff', False):
                return func(request, *args, **kwargs)

            # Superuser bypass
            if user.is_superuser:
                return func(request, *args, **kwargs)

            try:
                admin_permission = user.admin_permission
            except AttributeError:
                return func(request, *args, **kwargs)

            if admin_permission.is_blocked:
                raise PermissionDenied("Your admin access has been blocked.")

            if admin_permission.is_super_admin:
                return func(request, *args, **kwargs)

            if not admin_permission.has_page_permission(page_code):
                raise PermissionDenied(
                    f"You don't have access to this page: {page_code}"
                )

            return func(request, *args, **kwargs)
        return wrapper
    return decorator
