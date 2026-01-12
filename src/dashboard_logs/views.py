from rest_framework import generics
from rest_framework.permissions import IsAdminUser

from dashboard_logs.models import DashboardRequestLog
from dashboard_logs.serializers import DashboardRequestLogSerializer
from dashboard_logs.pagination import CustomPageNumberPagination


class DashboardRequestLogListView(generics.ListAPIView):
    """Read-only endpoint for dashboard request logs (GET only)."""

    queryset = DashboardRequestLog.objects.select_related('user').all()
    serializer_class = DashboardRequestLogSerializer
    permission_classes = [IsAdminUser]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by user: accepts user id or username
        user_param = self.request.query_params.get('user')
        if user_param:
            if user_param.isdigit():
                queryset = queryset.filter(user_id=int(user_param))
            else:
                queryset = queryset.filter(user__username__iexact=user_param)

        # Filter by requested_at date range (ISO datetime strings)
        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(requested_at__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(requested_at__lte=date_to)

        return queryset.order_by('-requested_at')
