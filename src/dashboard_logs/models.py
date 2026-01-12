from django.conf import settings
from django.db import models


class DashboardRequestLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dashboard_request_logs',
        help_text='Authenticated user who made the request (if any)',
    )
    method = models.CharField(max_length=10, db_index=True)
    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)

    path = models.TextField(help_text='Request path')
    request_body = models.TextField(blank=True, null=True)

    response_status = models.PositiveIntegerField(db_index=True)
    response_body = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-requested_at']
        verbose_name = 'Dashboard Request Log'
        verbose_name_plural = 'Dashboard Request Logs'
        indexes = [
            models.Index(fields=['-requested_at']),
            models.Index(fields=['method', '-requested_at']),
            models.Index(fields=['response_status', '-requested_at']),
        ]

    def __str__(self):
        return f"{self.method} {self.path} ({self.response_status})"
