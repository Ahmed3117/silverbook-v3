"""
Middleware for automatic admin permission checking on all API requests.
This eliminates the need to manually add permission classes to every view.
"""
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.urls import resolve
from permissions.models import AdminPermission


class AdminPermissionMiddleware(MiddlewareMixin):
    """
    Global middleware that checks admin permissions for ALL requests.
    
    - Applies only to authenticated staff users
    - Checks endpoint permissions automatically
    - Supports context via headers or query params
    
    Advantages:
    - No need to add permission classes to each view
    - Consistent enforcement across all endpoints
    - Easy to enable/disable globally
    """

    # Endpoints that should bypass permission checks
    EXCLUDED_PATHS = [
        '/admin/',           # Django admin
        '/accounts/login/',  # Login endpoints
        '/accounts/signin/', 
        '/accounts/dashboard/signin/',
        '/accounts/signup/',
        '/accounts/token/',  # JWT token endpoints
        '/static/',          # Static files
        '/media/',           # Media files
        '/permissions/admins/my_permissions/',  # User's own permissions
    ]

    def process_request(self, request):
        """
        Check permissions before the view is called.
        Return JsonResponse if permission denied, None to continue.
        """
        # Skip excluded paths
        if any(request.path.startswith(path) for path in self.EXCLUDED_PATHS):
            return None

        # Only check authenticated users
        if not request.user.is_authenticated:
            return None

        # Non-staff users bypass admin permission checks
        if not getattr(request.user, 'is_staff', False):
            return None

        # Django superusers always have access
        if request.user.is_superuser:
            return None

        # Get admin permission
        try:
            admin_permission = request.user.admin_permission
        except (AttributeError, AdminPermission.DoesNotExist):
            # No admin permission record = full access
            return None

        # Check if blocked
        if admin_permission.is_blocked:
            return JsonResponse({
                'detail': 'Your admin access has been blocked. Please contact a superuser.'
            }, status=403)

        # Super admins have full access
        if admin_permission.is_super_admin:
            return None

        # Get view information
        view_name = self._get_view_name(request)
        method = request.method
        feature_code = self._get_feature_code(request)
        page_code = self._get_page_code(request)

        # Check permission
        has_access = admin_permission.has_endpoint_permission(
            view_name,
            method,
            feature_code=feature_code,
            page_code=page_code
        )

        if not has_access:
            # Prepare detailed error message
            error_message = "You don't have permission to perform this action."
            
            if feature_code:
                error_message = f"Access denied. Feature '{feature_code}' is not allowed for your account."
            elif page_code:
                error_message = f"Access denied. Page '{page_code}' is not accessible."

            return JsonResponse({
                'detail': error_message,
                'denied_feature': feature_code,
                'denied_page': page_code,
            }, status=403)

        # Permission granted, continue to view
        return None

    def _get_view_name(self, request):
        """Get the Django view name for permission checking."""
        try:
            resolved = resolve(request.path)
            if resolved.url_name:
                namespace = resolved.namespace
                if namespace:
                    return f"{namespace}:{resolved.url_name}"
                return resolved.url_name
        except Exception:
            pass

        return request.path

    def _get_feature_code(self, request):
        """Get feature code from headers or query params."""
        # 1. Request header
        feature_code = request.headers.get('X-Feature-Code')
        if feature_code:
            return feature_code

        # 2. Query parameter
        feature_code = request.GET.get('feature_code')
        if feature_code:
            return feature_code

        # 3. POST/PUT body (for JSON requests)
        if request.content_type == 'application/json' and hasattr(request, 'data'):
            try:
                feature_code = request.data.get('feature_code')
                if feature_code:
                    return feature_code
            except Exception:
                pass

        return None

    def _get_page_code(self, request):
        """Get page code from headers or query params."""
        # 1. Request header
        page_code = request.headers.get('X-Page-Code')
        if page_code:
            return page_code

        # 2. Query parameter
        page_code = request.GET.get('page_code')
        if page_code:
            return page_code

        # 3. POST/PUT body (for JSON requests)
        if request.content_type == 'application/json' and hasattr(request, 'data'):
            try:
                page_code = request.data.get('page_code')
                if page_code:
                    return page_code
            except Exception:
                pass

        return None
