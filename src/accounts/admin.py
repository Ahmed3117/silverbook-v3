from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import mark_safe
from django.utils import timezone
from .models import User, UserProfileImage, UserDevice, OTP, SecurityBlock, AuthenticationAttempt
from django.contrib import messages

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'name', 'email', 'user_type', 'is_staff', 'max_allowed_devices', 'get_active_devices')
    list_filter = ('user_type', 'is_staff', 'is_superuser', 'is_active', 'groups', 'government', 'year')
    search_fields = ('username', 'name', 'email')
    ordering = ('-date_joined',)
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('name', 'email')}),
        ('User Type Specifics', {'fields': ('user_type', 'year', 'parent_phone', 'division')}),
        ('Device Management', {'fields': ('max_allowed_devices',)}),
        ('Location', {'fields': ('government',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('OTP', {'fields': ('otp', 'otp_created_at')}),
    )
    readonly_fields = ('last_login', 'date_joined', 'otp_created_at')

    # Profile image field removed from User model; no preview available
    
    @admin.display(description='Active Devices')
    def get_active_devices(self, obj):
        if obj.user_type == 'student':
            count = obj.devices.filter(is_active=True).count()
            return f"{count}/{obj.max_allowed_devices}"
        return "-"

@admin.register(UserProfileImage)
class UserProfileImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_image_preview', 'created_at')
    readonly_fields = ('get_image_preview', 'created_at', 'updated_at')
    search_fields = ('id',)

    @admin.display(description='Image Preview')
    def get_image_preview(self, obj):
        if obj.image:
            return mark_safe(f'<img src="{obj.image.url}" width="100" />')
        return "No Image"


@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
    list_display = ('user', 'device_name', 'short_device_id', 'ip_address', 'is_active', 'logged_in_at', 'last_used_at')
    list_filter = ('is_active', 'device_name', 'logged_in_at', 'last_used_at')
    search_fields = ('user__username', 'user__name', 'device_name', 'ip_address', 'device_id', 'device_token')
    readonly_fields = ('device_token', 'device_id', 'ip_address', 'user_agent', 'logged_in_at', 'last_used_at')
    raw_id_fields = ('user',)
    ordering = ('-last_used_at',)
    
    fieldsets = (
        ('Device Info', {'fields': ('user', 'device_name', 'device_id', 'ip_address', 'user_agent')}),
        ('Session', {'fields': ('device_token', 'is_active')}),
        ('Timestamps', {'fields': ('logged_in_at', 'last_used_at')}),
    )
    
    @admin.display(description='Device ID')
    def short_device_id(self, obj):
        if obj.device_id:
            return f"{obj.device_id[:15]}..." if len(obj.device_id) > 15 else obj.device_id
        return "IP Only"
    
    actions = ['deactivate_devices', 'activate_devices', 'delete_selected']
    
    @admin.action(description='Deactivate selected devices')
    def deactivate_devices(self, request, queryset):
        queryset.update(is_active=False)
    
    @admin.action(description='Activate selected devices')
    def activate_devices(self, request, queryset):
        queryset.update(is_active=True)

# register OTP model
admin.site.register(OTP)


@admin.register(SecurityBlock)
class SecurityBlockAdmin(admin.ModelAdmin):
    """Admin interface for managing security blocks"""
    list_display = (
        'phone_number', 
        'block_type', 
        'block_level',
        'consecutive_blocks',
        'is_active',
        'blocked_at', 
        'remaining_time_display',
        'manually_unblocked',
        'unblocked_by'
    )
    list_filter = (
        'is_active',
        'block_type',
        'block_level',
        'manually_unblocked',
        'blocked_at',
    )
    search_fields = ('phone_number', 'unblock_reason')
    readonly_fields = (
        'phone_number',
        'block_type',
        'blocked_at',
        'blocked_until',
        'block_level',
        'consecutive_blocks',
        'failed_attempts',
        'ip_addresses',
        'user_agents',
        'remaining_time_display',
        'is_expired_display'
    )
    ordering = ('-blocked_at',)
    
    fieldsets = (
        ('Block Information', {
            'fields': (
                'phone_number',
                'block_type',
                'block_level',
                'consecutive_blocks',
                'is_active'
            )
        }),
        ('Timing', {
            'fields': (
                'blocked_at',
                'blocked_until',
                'remaining_time_display',
                'is_expired_display'
            )
        }),
        ('Manual Unblock', {
            'fields': (
                'manually_unblocked',
                'unblocked_by',
                'unblocked_at',
                'unblock_reason'
            )
        }),
        ('Attempt Details', {
            'fields': (
                'failed_attempts',
                'ip_addresses',
                'user_agents'
            ),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['manually_unblock_selected', 'deactivate_selected_blocks']
    
    @admin.display(description='Remaining Time')
    def remaining_time_display(self, obj):
        if not obj.is_active:
            return "غير نشط"
        if obj.is_expired():
            return mark_safe('<span style="color: green;">منتهي</span>')
        return obj.remaining_time_formatted()
    
    @admin.display(description='Is Expired?', boolean=True)
    def is_expired_display(self, obj):
        return obj.is_expired()
    
    @admin.action(description='Manually unblock selected phone numbers')
    def manually_unblock_selected(self, request, queryset):
        """Manually unblock selected security blocks"""
        count = 0
        for block in queryset.filter(is_active=True):
            block.is_active = False
            block.manually_unblocked = True
            block.unblocked_by = request.user
            block.unblocked_at = timezone.now()
            block.unblock_reason = f"تم رفع الحظر يدويًا بواسطة {request.user.username} عبر لوحة الإدارة"
            block.save()
            count += 1
        
        self.message_user(
            request,
            f"تم رفع الحظر بنجاح عن {count} رقم/أرقام.",
            messages.SUCCESS
        )
    
    @admin.action(description='Deactivate selected blocks (without marking as manually unblocked)')
    def deactivate_selected_blocks(self, request, queryset):
        """Deactivate blocks without marking as manual"""
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f"تم إلغاء تفعيل {updated} عملية/عمليات حظر.",
            messages.SUCCESS
        )
    
    def has_add_permission(self, request):
        """Blocks should only be created automatically by the system"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Allow deletion for cleanup purposes"""
        return request.user.is_superuser


@admin.register(AuthenticationAttempt)
class AuthenticationAttemptAdmin(admin.ModelAdmin):
    """Admin interface for viewing authentication attempts"""
    list_display = (
        'phone_number',
        'attempt_type',
        'result',
        'attempted_at',
        'ip_address',
        'short_failure_reason'
    )
    list_filter = (
        'attempt_type',
        'result',
        'attempted_at',
    )
    search_fields = ('phone_number', 'ip_address', 'failure_reason')
    readonly_fields = (
        'phone_number',
        'attempt_type',
        'result',
        'attempted_at',
        'ip_address',
        'user_agent',
        'failure_reason',
        'related_block'
    )
    ordering = ('-attempted_at',)
    date_hierarchy = 'attempted_at'
    
    fieldsets = (
        ('Attempt Information', {
            'fields': (
                'phone_number',
                'attempt_type',
                'result',
                'attempted_at'
            )
        }),
        ('Client Information', {
            'fields': (
                'ip_address',
                'user_agent'
            )
        }),
        ('Failure Details', {
            'fields': (
                'failure_reason',
                'related_block'
            )
        }),
    )
    
    @admin.display(description='Failure Reason')
    def short_failure_reason(self, obj):
        if obj.failure_reason:
            return obj.failure_reason[:50] + "..." if len(obj.failure_reason) > 50 else obj.failure_reason
        return "-"
    
    def has_add_permission(self, request):
        """Attempts should only be created automatically by the system"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Attempts are read-only"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Allow deletion for cleanup purposes"""
        return request.user.is_superuser
