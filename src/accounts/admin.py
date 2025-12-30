from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User, UserProfileImage, UserDevice

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
            return format_html('<img src="{}" width="100" />', obj.image.url)
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