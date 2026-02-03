from django.contrib import admin
from django.utils.html import mark_safe
from .models import BackendEndpoint, DashboardPage, DashboardFeature, PermissionGroup, AdminPermission


@admin.register(BackendEndpoint)
class BackendEndpointAdmin(admin.ModelAdmin):
    """
    For DEVELOPERS only.
    Manages backend API endpoints that are linked to pages/features.
    """
    list_display = ['view_name', 'method', 'description', 'used_in_pages', 'used_in_features']
    list_filter = ['method']
    search_fields = ['view_name', 'description']
    ordering = ['view_name']

    def used_in_pages(self, obj):
        # Get unique pages from all features that use this endpoint
        pages = set()
        for feature in obj.features.all():
            if feature.page:
                pages.add(feature.page)
        if pages:
            return ", ".join([p.name for p in list(pages)[:3]])
        return "-"
    used_in_pages.short_description = 'Pages'

    def used_in_features(self, obj):
        features = list(obj.features.all()[:5])
        if features:
            return ", ".join([f.name for f in features])
        return mark_safe('<span style="color: orange;">Not linked</span>')
    used_in_features.short_description = 'Features'

    def has_module_permission(self, request):
        # Only show to superusers (developers)
        return request.user.is_superuser


class DashboardFeatureInline(admin.TabularInline):
    """Inline for showing features within a page"""
    model = DashboardFeature
    extra = 0
    fields = ['name', 'code', 'display_order', 'is_active']
    ordering = ['display_order']
    show_change_link = True


class ChildPageInline(admin.TabularInline):
    """Inline for showing child pages"""
    model = DashboardPage
    fk_name = 'parent'
    extra = 0
    fields = ['name', 'code', 'route_name', 'icon', 'display_order', 'is_active']
    ordering = ['display_order']
    show_change_link = True
    verbose_name = "Child Page"
    verbose_name_plural = "Child Pages"


@admin.register(DashboardPage)
class DashboardPageAdmin(admin.ModelAdmin):
    """
    Manages dashboard sidebar pages.
    Superusers can see and organize pages.
    """
    list_display = ['name', 'code', 'parent', 'route_name', 'feature_count', 'display_order', 'is_active']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'code', 'route_name']
    list_editable = ['display_order', 'is_active']
    ordering = ['parent__name', 'display_order']
    inlines = [DashboardFeatureInline, ChildPageInline]

    fieldsets = (
        ('Page Information', {
            'fields': ('name', 'code', 'parent', 'icon', 'display_order', 'is_active'),
        }),
        ('Frontend Route', {
            'fields': ('route_name',),
            'description': 'The frontend route name for this page.',
        }),
    )

    def feature_count(self, obj):
        return obj.features.count()
    feature_count.short_description = 'Features'


@admin.register(DashboardFeature)
class DashboardFeatureAdmin(admin.ModelAdmin):
    """
    Manages specific actions/features within pages.
    """
    list_display = ['name', 'code', 'page', 'endpoint_count', 'display_order', 'is_active']
    list_filter = ['page', 'is_active']
    search_fields = ['name', 'code', 'description']
    list_editable = ['display_order', 'is_active']
    ordering = ['page__name', 'display_order']

    fieldsets = (
        ('Feature Information', {
            'fields': ('name', 'code', 'description', 'page', 'display_order', 'is_active'),
        }),
        ('Backend Endpoints (Developer Section)', {
            'fields': ('endpoints',),
            'classes': ('collapse',),
            'description': 'API endpoints used by this feature. If admin has ANY feature using an endpoint, they can access it.',
        }),
    )

    filter_horizontal = ['endpoints']

    def endpoint_count(self, obj):
        return obj.endpoints.count()
    endpoint_count.short_description = 'Endpoints'


@admin.register(PermissionGroup)
class PermissionGroupAdmin(admin.ModelAdmin):
    """
    Manages permission groups with denied pages and features.
    User-friendly interface for superusers.
    """
    list_display = ['name', 'restrictions_summary', 'member_count', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'description']

    fieldsets = (
        ('Group Information', {
            'fields': ('name', 'description', 'is_active'),
        }),
        ('Page Restrictions', {
            'fields': ('denied_pages',),
            'description': 'Pages that will be HIDDEN from sidebar and BLOCKED for this group.',
        }),
        ('Feature Restrictions', {
            'fields': ('denied_features',),
            'description': 'Specific features/actions that will be BLOCKED for this group (even if page is allowed).',
        }),
    )

    filter_horizontal = ['denied_pages', 'denied_features']

    def restrictions_summary(self, obj):
        pages = obj.denied_pages.count()
        features = obj.denied_features.count()
        if pages == 0 and features == 0:
            return mark_safe('<span style="color: green;">Full Access</span>')
        return f"{pages} pages, {features} features denied"
    restrictions_summary.short_description = 'Restrictions'

    def member_count(self, obj):
        return obj.admin_permissions.count()
    member_count.short_description = 'Members'


@admin.register(AdminPermission)
class AdminPermissionAdmin(admin.ModelAdmin):
    """
    Manages individual admin permissions.
    Assigns admins to groups and sets extra restrictions.
    """
    list_display = ['user', 'permission_group', 'extra_restrictions', 'is_super_admin', 'is_blocked', 'status_badge']
    list_filter = ['is_super_admin', 'is_blocked', 'permission_group']
    search_fields = ['user__email', 'user__phone', 'user__first_name', 'user__last_name']
    autocomplete_fields = ['user']

    fieldsets = (
        ('Admin User', {
            'fields': ('user',),
        }),
        ('Access Level', {
            'fields': ('is_super_admin', 'is_blocked'),
            'description': '• Super Admin: Full access to everything.\n• Blocked: No access at all.',
        }),
        ('Group Assignment', {
            'fields': ('permission_group',),
            'description': 'Assign to a group to apply its restrictions.',
        }),
        ('Additional Page Restrictions', {
            'fields': ('extra_denied_pages',),
            'classes': ('collapse',),
            'description': 'Extra pages to hide/block for this specific admin.',
        }),
        ('Additional Feature Restrictions', {
            'fields': ('extra_denied_features',),
            'classes': ('collapse',),
            'description': 'Extra features to block for this specific admin.',
        }),
    )

    filter_horizontal = ['extra_denied_pages', 'extra_denied_features']

    def extra_restrictions(self, obj):
        pages = obj.extra_denied_pages.count()
        features = obj.extra_denied_features.count()
        if pages == 0 and features == 0:
            return "-"
        return f"+{pages} pages, +{features} features"
    extra_restrictions.short_description = 'Extra Denied'

    def status_badge(self, obj):
        if obj.is_blocked:
            return mark_safe(
                '<span style="background: #dc3545; color: white; padding: 2px 8px; '
                'border-radius: 3px; font-size: 11px;">BLOCKED</span>'
            )
        if obj.is_super_admin:
            return mark_safe(
                '<span style="background: #28a745; color: white; padding: 2px 8px; '
                'border-radius: 3px; font-size: 11px;">SUPER ADMIN</span>'
            )
        return mark_safe(
            '<span style="background: #007bff; color: white; padding: 2px 8px; '
            'border-radius: 3px; font-size: 11px;">ACTIVE</span>'
        )
    status_badge.short_description = 'Status'
