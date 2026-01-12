from django.contrib import admin

from dashboard_logs.models import DashboardRequestLog


@admin.register(DashboardRequestLog)
class DashboardRequestLogAdmin(admin.ModelAdmin):
    list_display = ('requested_at', 'method', 'path', 'response_status', 'user')
    list_filter = ('method', 'response_status', 'requested_at')
    search_fields = ('path', 'request_body', 'response_body', 'user__username')
    readonly_fields = (
        'requested_at',
        'method',
        'path',
        'request_body',
        'response_status',
        'response_body',
        'user',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
