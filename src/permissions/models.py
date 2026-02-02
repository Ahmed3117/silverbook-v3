from django.db import models
from django.conf import settings


class BackendEndpoint(models.Model):
    """
    Represents a single backend API endpoint.
    Managed by developers, not superusers.
    Generic: Works with any Django REST Framework project.
    """
    view_name = models.CharField(
        max_length=255,
        help_text="Django view name (e.g., 'products:product-list')"
    )
    method = models.CharField(
        max_length=10,
        choices=[
            ('GET', 'GET'),
            ('POST', 'POST'),
            ('PUT', 'PUT'),
            ('PATCH', 'PATCH'),
            ('DELETE', 'DELETE'),
            ('*', 'ALL'),
        ]
    )
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ['view_name', 'method']
        ordering = ['view_name', 'method']
        verbose_name = "Backend Endpoint"
        verbose_name_plural = "Backend Endpoints"

    def __str__(self):
        return f"{self.method} - {self.view_name}"


class DashboardPage(models.Model):
    """
    Represents a page/menu item in the dashboard sidebar.
    Controls what the admin SEES in the navigation.
    Generic: Works with any frontend framework (Vue, React, Angular).
    """
    name = models.CharField(
        max_length=255,
        help_text="Display name in sidebar (e.g., 'Users', 'Products')"
    )
    code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique code (e.g., 'page.users', 'page.products')"
    )
    route_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Frontend route name (e.g., 'dashboard-users')"
    )

    # Hierarchy for nested menus
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        help_text="Parent page for nested menus"
    )

    # Visual properties
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon name for sidebar"
    )
    display_order = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Dashboard Page"
        verbose_name_plural = "Dashboard Pages"

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name

    def get_all_children(self):
        """Get all child pages recursively"""
        children = list(self.children.filter(is_active=True))
        for child in self.children.filter(is_active=True):
            children.extend(child.get_all_children())
        return children


class DashboardFeature(models.Model):
    """
    Represents a specific action/feature within a page.
    Controls what the admin CAN DO on a page.
    Generic: Can be used for any CRUD operations or custom actions.
    """
    name = models.CharField(
        max_length=255,
        help_text="User-friendly name (e.g., 'Create User', 'Delete Product')"
    )
    code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique code (e.g., 'users.create', 'products.delete')"
    )
    description = models.TextField(blank=True)

    # Link to page
    page = models.ForeignKey(
        DashboardPage,
        on_delete=models.CASCADE,
        related_name='features',
        null=True,
        blank=True,
        help_text="The page this feature belongs to"
    )

    # Backend endpoints for this feature
    # Logic: If endpoint belongs to ANY allowed feature, it's accessible
    endpoints = models.ManyToManyField(
        BackendEndpoint,
        blank=True,
        related_name='features',
        help_text="API endpoints used by this feature. If user has ANY feature using an endpoint, they can access it."
    )

    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['page', 'display_order', 'name']
        verbose_name = "Dashboard Feature"
        verbose_name_plural = "Dashboard Features"

    def __str__(self):
        if self.page:
            return f"[{self.page.name}] {self.name}"
        return self.name


class PermissionGroup(models.Model):
    """
    A group of DENIED pages and features (blacklist approach).
    Superuser selects what to DENY, everything else is allowed.
    Generic: Can be reused across different projects.
    """
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)

    # Pages DENIED for this group
    denied_pages = models.ManyToManyField(
        DashboardPage,
        blank=True,
        related_name='denied_in_groups',
        help_text="Pages hidden from sidebar and blocked for this group"
    )

    # Features DENIED for this group
    denied_features = models.ManyToManyField(
        DashboardFeature,
        blank=True,
        related_name='denied_in_groups',
        help_text="Features/actions blocked for this group"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Permission Group"
        verbose_name_plural = "Permission Groups"

    def __str__(self):
        return self.name


class AdminPermission(models.Model):
    """
    Links an admin user to their permission restrictions.
    Controls both PAGE visibility and FEATURE access.
    Generic: Uses AUTH_USER_MODEL from settings.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admin_permission'
    )

    # Group assignment
    permission_group = models.ForeignKey(
        PermissionGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admin_permissions'
    )

    # Additional individual DENIED pages
    extra_denied_pages = models.ManyToManyField(
        DashboardPage,
        blank=True,
        related_name='denied_for_admins',
        help_text="Additional pages to hide/block for this admin"
    )

    # Additional individual DENIED features
    extra_denied_features = models.ManyToManyField(
        DashboardFeature,
        blank=True,
        related_name='denied_for_admins',
        help_text="Additional features to block for this admin"
    )

    is_super_admin = models.BooleanField(
        default=False,
        help_text="Super admins have full access to everything"
    )
    is_blocked = models.BooleanField(
        default=False,
        help_text="Blocked admins have NO access"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Admin Permission"
        verbose_name_plural = "Admin Permissions"

    def __str__(self):
        return f"Permissions for {self.user}"

    # ==================== PAGE METHODS ====================

    def get_all_denied_pages(self):
        """Returns all denied pages (group + extra)"""
        if self.is_super_admin:
            return DashboardPage.objects.none()

        denied_ids = set()

        # Add group denied pages
        if self.permission_group and self.permission_group.is_active:
            denied_ids.update(
                self.permission_group.denied_pages
                .filter(is_active=True)
                .values_list('id', flat=True)
            )

        # Add extra denied pages
        denied_ids.update(
            self.extra_denied_pages
            .filter(is_active=True)
            .values_list('id', flat=True)
        )

        return DashboardPage.objects.filter(id__in=denied_ids, is_active=True)

    def get_all_allowed_pages(self):
        """Returns all allowed pages (for sidebar)"""
        if self.is_blocked:
            return DashboardPage.objects.none()

        if self.is_super_admin:
            return DashboardPage.objects.filter(is_active=True)

        denied_ids = set(self.get_all_denied_pages().values_list('id', flat=True))

        # Also deny children of denied pages
        for page in self.get_all_denied_pages():
            for child in page.get_all_children():
                denied_ids.add(child.id)

        return DashboardPage.objects.filter(is_active=True).exclude(id__in=denied_ids)

    def has_page_permission(self, page_code):
        """Check if user can access a specific page"""
        if self.is_blocked:
            return False

        if self.is_super_admin:
            return True

        # Check if page is denied
        is_denied = self.get_all_denied_pages().filter(code=page_code).exists()

        if is_denied:
            return False

        # Check if any parent page is denied
        page = DashboardPage.objects.filter(code=page_code, is_active=True).first()
        if page and page.parent:
            return self.has_page_permission(page.parent.code)

        return True

    def has_route_permission(self, route_name):
        """Check if user can access a specific route"""
        if self.is_blocked:
            return False

        if self.is_super_admin:
            return True

        # Check pages
        is_page_denied = self.get_all_denied_pages().filter(route_name=route_name).exists()
        if is_page_denied:
            return False

        return True

    # ==================== FEATURE METHODS ====================

    def get_all_denied_features(self):
        """Returns all denied features (group + extra + features of denied pages)"""
        if self.is_super_admin:
            return DashboardFeature.objects.none()

        denied_ids = set()

        # Add group denied features
        if self.permission_group and self.permission_group.is_active:
            denied_ids.update(
                self.permission_group.denied_features
                .filter(is_active=True)
                .values_list('id', flat=True)
            )

        # Add extra denied features
        denied_ids.update(
            self.extra_denied_features
            .filter(is_active=True)
            .values_list('id', flat=True)
        )

        # Add ALL features of denied pages
        denied_pages = self.get_all_denied_pages()
        denied_ids.update(
            DashboardFeature.objects.filter(
                page__in=denied_pages,
                is_active=True
            ).values_list('id', flat=True)
        )

        return DashboardFeature.objects.filter(id__in=denied_ids, is_active=True)

    def get_all_allowed_features(self):
        """Returns all allowed features"""
        if self.is_blocked:
            return DashboardFeature.objects.none()

        if self.is_super_admin:
            return DashboardFeature.objects.filter(is_active=True)

        denied_ids = set(self.get_all_denied_features().values_list('id', flat=True))
        return DashboardFeature.objects.filter(is_active=True).exclude(id__in=denied_ids)

    def has_feature_permission(self, feature_code):
        """Check if user can use a specific feature"""
        if self.is_blocked:
            return False

        if self.is_super_admin:
            return True

        is_denied = self.get_all_denied_features().filter(code=feature_code).exists()
        return not is_denied

    # ==================== ENDPOINT METHODS ====================

    def has_endpoint_permission(self, view_name, method, feature_code=None, page_code=None):
        """
        Simplified endpoint permission check.
        
        Logic (YOUR PROPOSED APPROACH):
        1. If page_code provided and page is denied → BLOCK
        2. If feature_code provided and feature is denied → BLOCK
        3. Find the endpoint
        4. If endpoint belongs to ANY allowed feature → ALLOW
        5. If endpoint belongs to ALL denied features → BLOCK
        6. If endpoint not linked to anything → ALLOW (not protected)
        """
        if self.is_blocked:
            return False

        if self.is_super_admin:
            return True

        # Check page permission first
        if page_code and not self.has_page_permission(page_code):
            return False

        # Check feature permission
        if feature_code and not self.has_feature_permission(feature_code):
            return False

        # Find the endpoint
        endpoint = BackendEndpoint.objects.filter(
            models.Q(view_name=view_name) &
            (models.Q(method=method) | models.Q(method='*'))
        ).first()

        if not endpoint:
            # Endpoint not registered = not protected
            return True

        # Get all features that use this endpoint
        features_using_endpoint = DashboardFeature.objects.filter(
            endpoints=endpoint,
            is_active=True
        )

        if not features_using_endpoint.exists():
            # Endpoint not linked to any feature = not protected
            return True

        # Get allowed and denied features
        allowed_features = self.get_all_allowed_features()
        denied_features = self.get_all_denied_features()

        # Check if endpoint belongs to ANY allowed feature
        endpoint_in_allowed = features_using_endpoint.filter(
            id__in=allowed_features.values_list('id', flat=True)
        ).exists()

        if endpoint_in_allowed:
            # User has at least ONE feature that uses this endpoint
            return True

        # Check if endpoint belongs to ANY denied feature
        endpoint_in_denied = features_using_endpoint.filter(
            id__in=denied_features.values_list('id', flat=True)
        ).exists()

        if endpoint_in_denied:
            # Endpoint only belongs to denied features
            return False

        # Default: allow (shouldn't reach here normally)
        return True

    # ==================== SIDEBAR DATA ====================

    def get_sidebar_data(self):
        """
        Returns structured data for building the sidebar menu.
        Only includes allowed pages.
        """
        allowed_pages = self.get_all_allowed_pages()
        allowed_features = self.get_all_allowed_features()

        # Get root pages (no parent)
        root_pages = allowed_pages.filter(parent__isnull=True).order_by('display_order')

        def build_page_data(page):
            children = allowed_pages.filter(parent=page).order_by('display_order')
            page_features = allowed_features.filter(page=page).order_by('display_order')

            return {
                'code': page.code,
                'name': page.name,
                'route_name': page.route_name,
                'icon': page.icon,
                'features': [
                    {
                        'code': f.code,
                        'name': f.name,
                    }
                    for f in page_features
                ],
                'children': [build_page_data(child) for child in children],
            }

        return [build_page_data(page) for page in root_pages]
