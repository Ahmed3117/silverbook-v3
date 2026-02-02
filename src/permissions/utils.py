"""
Utility functions for the permissions app.
Generic: Works with any Django project.
"""
from .serializers import UserPermissionsResponseSerializer
from .models import DashboardPage, DashboardFeature


def get_full_sidebar_data():
    """
    Get full sidebar structure (for super admins or unrestricted users).
    Returns all active pages with their features.
    """
    root_pages = DashboardPage.objects.filter(
        is_active=True,
        parent__isnull=True
    ).order_by('display_order')

    def build_page_data(page):
        children = page.children.filter(is_active=True).order_by('display_order')
        features = page.features.filter(is_active=True).order_by('display_order')

        return {
            'code': page.code,
            'name': page.name,
            'route_name': page.route_name,
            'icon': page.icon,
            'features': [
                {'code': f.code, 'name': f.name}
                for f in features
            ],
            'children': [build_page_data(child) for child in children],
        }

    return [build_page_data(page) for page in root_pages]


def get_user_permissions_for_response(user):
    """
    Get user permissions formatted for login response.
    Returns None if user is not staff.

    Usage in login view:
        permissions = get_user_permissions_for_response(user)
        if permissions:
            response_data['admin_permissions'] = permissions
    """
    # Only staff members get permission data
    if not getattr(user, 'is_staff', False):
        return None

    # Django superusers get full access
    if user.is_superuser:
        return {
            'is_super_admin': True,
            'is_blocked': False,
            'sidebar': get_full_sidebar_data(),
            'denied_pages': [],
            'denied_features': [],
            'denied_routes': [],
        }

    try:
        admin_permission = user.admin_permission
        return UserPermissionsResponseSerializer.get_permissions_data(admin_permission)
    except AttributeError:
        # No AdminPermission record = no restrictions = full access
        return {
            'is_super_admin': False,
            'is_blocked': False,
            'sidebar': get_full_sidebar_data(),
            'denied_pages': [],
            'denied_features': [],
            'denied_routes': [],
        }


def add_permissions_to_login_response(user, response_data):
    """
    Add permissions to login response if user is staff.

    Usage in login view:
        response_data = {
            'user': user_data,
            'tokens': tokens,
        }
        add_permissions_to_login_response(user, response_data)
        return Response(response_data)
    """
    permissions = get_user_permissions_for_response(user)
    if permissions is not None:
        response_data['admin_permissions'] = permissions
    return response_data


def check_user_permission(user, feature_code=None, page_code=None):
    """
    Utility function to check user permissions programmatically.

    Args:
        user: The user object
        feature_code: Optional feature code to check
        page_code: Optional page code to check

    Returns:
        bool: True if user has permission, False otherwise

    Usage:
        if check_user_permission(request.user, feature_code='users.delete'):
            # User can delete users
            ...
    """
    # Non-staff have no admin restrictions
    if not getattr(user, 'is_staff', False):
        return True

    # Superusers always have permission
    if user.is_superuser:
        return True

    try:
        admin_permission = user.admin_permission
    except AttributeError:
        # No record = full access
        return True

    if admin_permission.is_blocked:
        return False

    if admin_permission.is_super_admin:
        return True

    # Check feature permission
    if feature_code and not admin_permission.has_feature_permission(feature_code):
        return False

    # Check page permission
    if page_code and not admin_permission.has_page_permission(page_code):
        return False

    return True


def get_user_allowed_features(user):
    """
    Get list of all allowed feature codes for a user.

    Usage:
        allowed_features = get_user_allowed_features(request.user)
        if 'users.delete' in allowed_features:
            ...
    """
    if not getattr(user, 'is_staff', False):
        return []

    if user.is_superuser:
        return list(
            DashboardFeature.objects.filter(is_active=True)
            .values_list('code', flat=True)
        )

    try:
        admin_permission = user.admin_permission
    except AttributeError:
        return list(
            DashboardFeature.objects.filter(is_active=True)
            .values_list('code', flat=True)
        )

    if admin_permission.is_blocked:
        return []

    if admin_permission.is_super_admin:
        return list(
            DashboardFeature.objects.filter(is_active=True)
            .values_list('code', flat=True)
        )

    return list(
        admin_permission.get_all_allowed_features()
        .values_list('code', flat=True)
    )


def get_user_allowed_pages(user):
    """
    Get list of all allowed page codes for a user.

    Usage:
        allowed_pages = get_user_allowed_pages(request.user)
        if 'page.users' in allowed_pages:
            ...
    """
    if not getattr(user, 'is_staff', False):
        return []

    if user.is_superuser:
        return list(
            DashboardPage.objects.filter(is_active=True)
            .values_list('code', flat=True)
        )

    try:
        admin_permission = user.admin_permission
    except AttributeError:
        return list(
            DashboardPage.objects.filter(is_active=True)
            .values_list('code', flat=True)
        )

    if admin_permission.is_blocked:
        return []

    if admin_permission.is_super_admin:
        return list(
            DashboardPage.objects.filter(is_active=True)
            .values_list('code', flat=True)
        )

    return list(
        admin_permission.get_all_allowed_pages()
        .values_list('code', flat=True)
    )
