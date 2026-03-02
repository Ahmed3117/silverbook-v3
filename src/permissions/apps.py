from django.apps import AppConfig


class PermissionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'permissions'
    verbose_name = 'Admin Permissions System'

    def ready(self):
        # Import signal handlers (decorator-based signals register automatically)
        import permissions.signals  # noqa: F401

        # Connect M2M signals to specific through models
        from django.db.models.signals import m2m_changed
        from permissions.models import PermissionGroup, AdminPermission
        from permissions.signals import (
            group_m2m_changed,
            admin_permission_m2m_changed,
        )

        m2m_changed.connect(group_m2m_changed, sender=PermissionGroup.denied_pages.through)
        m2m_changed.connect(group_m2m_changed, sender=PermissionGroup.denied_features.through)
        m2m_changed.connect(admin_permission_m2m_changed, sender=AdminPermission.extra_denied_pages.through)
        m2m_changed.connect(admin_permission_m2m_changed, sender=AdminPermission.extra_denied_features.through)
