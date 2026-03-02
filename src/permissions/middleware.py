"""
Middleware for automatic admin permission checking on all API requests.
This eliminates the need to manually add permission classes to every view.

Also enforces token staleness: when an admin's permissions change,
any JWT token issued before the change is rejected with 401,
forcing the frontend to re-login and get fresh permissions.
"""
from datetime import datetime, timezone as dt_timezone
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.urls import resolve
from django.conf import settings
from permissions.models import AdminPermission


class AdminPermissionMiddleware(MiddlewareMixin):
    """
    Global middleware that checks admin permissions for ALL requests.
    
    - Applies only to authenticated staff users
    - Checks endpoint permissions automatically
    - Supports context via headers or query params
    - Handles JWT authentication for DRF APIs (since DRF auth runs inside the view,
      but middleware runs before the view)
    
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

        # Try to get the authenticated user
        # Django's AuthenticationMiddleware sets request.user for session-based auth,
        # but DRF JWT auth runs inside the view (too late for middleware).
        # So we manually parse the JWT token here if the user isn't authenticated yet.
        user = request.user
        if not user.is_authenticated:
            user = self._get_jwt_user(request)
            if user is None:
                return None

        # Non-staff users bypass admin permission checks
        if not getattr(user, 'is_staff', False):
            return None

        # Django superusers always have access
        if user.is_superuser:
            return None

        # Get admin permission
        try:
            admin_permission = user.admin_permission
        except (AttributeError, AdminPermission.DoesNotExist):
            # No admin permission record = full access
            return None

        # Check if token was issued before permissions changed (force re-login)
        if self._is_token_stale(request, admin_permission):
            return JsonResponse({
                'detail': 'Your permissions have been updated. Please login again.',
                'code': 'permissions_changed',
            }, status=401)

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

    def _get_jwt_user(self, request):
        """
        Manually parse the JWT token from the request to get the user.
        This is needed because DRF authentication runs inside the view,
        but the middleware runs before the view.
        """
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from django.contrib.auth import get_user_model
            User = get_user_model()

            # Read the auth header configured in SIMPLE_JWT settings
            # AUTH_HEADER_NAME = 'HTTP_AUTH' means the header is 'Auth: Bearer <token>'
            header_name = getattr(settings, 'SIMPLE_JWT', {}).get('AUTH_HEADER_NAME', 'HTTP_AUTHORIZATION')
            auth_header = request.META.get(header_name, '')

            if not auth_header:
                return None

            # Parse 'Bearer <token>'
            parts = auth_header.split()
            if len(parts) != 2:
                return None

            header_type = getattr(settings, 'SIMPLE_JWT', {}).get('AUTH_HEADER_TYPES', 'Bearer')
            # AUTH_HEADER_TYPES can be a string or tuple
            if isinstance(header_type, str):
                header_type = (header_type,)

            if parts[0] not in header_type:
                return None

            raw_token = parts[1]

            # Validate token and get user
            validated_token = AccessToken(raw_token)
            user_id = validated_token.get('user_id')
            if user_id is None:
                return None

            # Store token issued-at time for staleness check later
            token_iat = validated_token.get('iat')
            if token_iat:
                request._jwt_iat = token_iat

            user = User.objects.select_related('admin_permission').get(pk=user_id)
            return user

        except Exception:
            return None

    def _is_token_stale(self, request, admin_permission):
        """
        Check if the JWT token was issued before the last permission change.
        If so, the token is stale and the admin must re-login to get fresh permissions.
        """
        # No change timestamp = permissions never changed since creation = not stale
        if not admin_permission.permissions_changed_at:
            return False

        # Get the token's issued-at time (stored during _get_jwt_user)
        token_iat = getattr(request, '_jwt_iat', None)
        if token_iat is None:
            return False

        try:
            # Convert Unix timestamp to timezone-aware datetime
            token_issued_at = datetime.fromtimestamp(token_iat, tz=dt_timezone.utc)

            # Ensure permissions_changed_at is timezone-aware
            perm_changed_at = admin_permission.permissions_changed_at
            if perm_changed_at.tzinfo is None:
                from django.utils import timezone as django_tz
                perm_changed_at = django_tz.make_aware(perm_changed_at)

            return perm_changed_at > token_issued_at
        except Exception:
            return False

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
