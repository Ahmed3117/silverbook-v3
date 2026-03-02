"""
Django signals for automatic permission change tracking.

When any permission-related data changes (group updated, admin permission modified,
M2M denied pages/features changed), the affected AdminPermission records get their
`permissions_changed_at` timestamp updated. The middleware then compares this with
the JWT token's `iat` to force re-login when permissions are stale.

Covers all mutation paths:
1. AdminPermission saved (group changed, is_blocked, is_super_admin, etc.)
2. AdminPermission.extra_denied_pages M2M changed
3. AdminPermission.extra_denied_features M2M changed
4. PermissionGroup saved (name, description, is_active changed)
5. PermissionGroup.denied_pages M2M changed
6. PermissionGroup.denied_features M2M changed
7. PermissionGroup deleted (before FK is SET_NULL)
"""
import logging
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


# ==================== AdminPermission Signals ====================

@receiver(post_save, sender='permissions.AdminPermission')
def admin_permission_saved(sender, instance, created, **kwargs):
    """
    When an AdminPermission is updated (not created), mark permissions as changed.
    Uses .update() to avoid re-triggering post_save.
    """
    if not created:
        sender.objects.filter(pk=instance.pk).update(
            permissions_changed_at=timezone.now()
        )
        logger.info(
            f"Permissions changed for user {instance.user_id} "
            f"(AdminPermission updated)"
        )


# ==================== PermissionGroup Signals ====================

@receiver(post_save, sender='permissions.PermissionGroup')
def permission_group_saved(sender, instance, **kwargs):
    """
    When a PermissionGroup is updated, invalidate tokens for all admins using it.
    """
    from permissions.models import AdminPermission
    count = AdminPermission.objects.filter(
        permission_group=instance
    ).update(permissions_changed_at=timezone.now())

    if count > 0:
        logger.info(
            f"Permissions changed for {count} admin(s) "
            f"(PermissionGroup '{instance.name}' updated)"
        )


@receiver(pre_delete, sender='permissions.PermissionGroup')
def permission_group_deleted(sender, instance, **kwargs):
    """
    Before a PermissionGroup is deleted, invalidate tokens for all admins using it.
    Must be pre_delete because after deletion the FK is SET_NULL (lost reference).
    """
    from permissions.models import AdminPermission
    count = AdminPermission.objects.filter(
        permission_group=instance
    ).update(permissions_changed_at=timezone.now())

    if count > 0:
        logger.info(
            f"Permissions changed for {count} admin(s) "
            f"(PermissionGroup '{instance.name}' deleted)"
        )


# ==================== M2M Signals ====================
# These are connected in PermissionsConfig.ready() to the specific through models.

def group_m2m_changed(sender, instance, action, **kwargs):
    """
    When a PermissionGroup's denied_pages or denied_features M2M changes,
    invalidate tokens for all admins using that group.
    """
    if action in ('post_add', 'post_remove', 'post_clear'):
        from permissions.models import AdminPermission
        count = AdminPermission.objects.filter(
            permission_group=instance
        ).update(permissions_changed_at=timezone.now())

        if count > 0:
            logger.info(
                f"Permissions changed for {count} admin(s) "
                f"(PermissionGroup '{instance.name}' M2M updated)"
            )


def admin_permission_m2m_changed(sender, instance, action, **kwargs):
    """
    When an AdminPermission's extra_denied_pages or extra_denied_features M2M changes,
    invalidate that admin's token.
    """
    if action in ('post_add', 'post_remove', 'post_clear'):
        from permissions.models import AdminPermission
        AdminPermission.objects.filter(pk=instance.pk).update(
            permissions_changed_at=timezone.now()
        )
        logger.info(
            f"Permissions changed for user {instance.user_id} "
            f"(AdminPermission M2M updated)"
        )
