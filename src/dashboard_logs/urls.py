from django.urls import path

from dashboard_logs.views import DashboardRequestLogListView

app_name = 'dashboard_logs'

urlpatterns = [
    path('', DashboardRequestLogListView.as_view(), name='dashboard-request-logs'),
]
