"""
Security models for tracking authentication attempts and progressive blocking.
Implements rate limiting for login attempts and password reset requests.
"""
from django.db import models
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class SecurityBlock(models.Model):
    """
    Tracks security blocks for phone numbers due to repeated failed attempts.
    Implements progressive blocking: each subsequent block has a longer duration.
    """
    BLOCK_TYPE_CHOICES = [
        ('login', 'Failed Login Attempts'),
        ('password_reset', 'Password Reset Request'),
        ('combined', 'Combined (Login + Reset)'),
    ]
    
    phone_number = models.CharField(
        max_length=20,
        db_index=True,
        help_text="Phone number that is blocked"
    )
    block_type = models.CharField(
        max_length=20,
        choices=BLOCK_TYPE_CHOICES,
        default='login',
        help_text="Type of operation that was blocked"
    )
    
    # Block timing
    blocked_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the block was initiated"
    )
    blocked_until = models.DateTimeField(
        help_text="When the block expires"
    )
    
    # Block progression
    block_level = models.PositiveIntegerField(
        default=1,
        help_text="Progressive block level (1, 2, 3, etc.)"
    )
    consecutive_blocks = models.PositiveIntegerField(
        default=1,
        help_text="Number of consecutive blocks for this phone number"
    )
    
    # Unblock control
    is_active = models.BooleanField(
        default=True,
        help_text="Whether block is currently active"
    )
    manually_unblocked = models.BooleanField(
        default=False,
        help_text="Whether block was manually lifted by admin"
    )
    unblocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unblocked_security_blocks',
        help_text="Admin who manually unblocked"
    )
    unblocked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When block was manually removed"
    )
    unblock_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Reason for manual unblock"
    )
    
    # Metadata
    failed_attempts = models.JSONField(
        default=list,
        help_text="List of failed attempt details (timestamps, IPs, device_ids, etc.)"
    )
    ip_addresses = models.JSONField(
        default=list,
        help_text="IP addresses involved in failed attempts"
    )
    user_agents = models.JSONField(
        default=list,
        help_text="User agents involved in failed attempts"
    )
    device_ids = models.JSONField(
        default=list,
        help_text="Device IDs involved in failed attempts"
    )
    
    class Meta:
        ordering = ['-blocked_at']
        verbose_name = 'Security Block'
        verbose_name_plural = 'Security Blocks'
        indexes = [
            models.Index(fields=['phone_number', 'is_active']),
            models.Index(fields=['phone_number', 'block_type', 'is_active']),
            models.Index(fields=['-blocked_at']),
            models.Index(fields=['blocked_until']),
        ]
    
    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.phone_number} - {self.get_block_type_display()} - Level {self.block_level} ({status})"
    
    def is_expired(self):
        """Check if block has naturally expired"""
        return timezone.now() >= self.blocked_until
    
    def remaining_time(self):
        """Get remaining block time in seconds"""
        if not self.is_active or self.is_expired():
            return 0
        delta = self.blocked_until - timezone.now()
        return max(0, int(delta.total_seconds()))
    
    def remaining_time_formatted(self):
        """Get remaining time in human-readable format"""
        seconds = self.remaining_time()
        if seconds == 0:
            return "انتهت مدة الحظر"
        
        minutes = seconds // 60
        hours = minutes // 60
        days = hours // 24
        
        if days > 0:
            return f"{days} يوم و {hours % 24} ساعة"
        elif hours > 0:
            return f"{hours} ساعة و {minutes % 60} دقيقة"
        elif minutes > 0:
            return f"{minutes} دقيقة"
        else:
            return f"{seconds} ثانية"
    
    def auto_deactivate_if_expired(self):
        """Automatically deactivate if block has expired"""
        if self.is_active and self.is_expired():
            self.is_active = False
            self.save(update_fields=['is_active'])
            logger.info(f"Auto-deactivated expired block for {self.phone_number}")
            return True
        return False


class AuthenticationAttempt(models.Model):
    """
    Tracks individual authentication attempts (login or password reset).
    Used to calculate when to trigger blocks.
    """
    ATTEMPT_TYPE_CHOICES = [
        ('login', 'Login Attempt'),
        ('password_reset', 'Password Reset Request'),
    ]
    
    ATTEMPT_RESULT_CHOICES = [
        ('success', 'Successful'),
        ('failed', 'Failed'),
        ('blocked', 'Blocked'),
    ]
    
    phone_number = models.CharField(
        max_length=20,
        db_index=True,
        help_text="Phone number attempting authentication"
    )
    attempt_type = models.CharField(
        max_length=20,
        choices=ATTEMPT_TYPE_CHOICES,
        help_text="Type of authentication attempt"
    )
    result = models.CharField(
        max_length=20,
        choices=ATTEMPT_RESULT_CHOICES,
        help_text="Result of the attempt"
    )
    
    # Attempt details
    attempted_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the attempt was made"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the attempt"
    )
    user_agent = models.TextField(
        blank=True,
        null=True,
        help_text="User agent string"
    )
    device_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Device ID from the mobile app"
    )
    
    # Error details for failed attempts
    failure_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Reason for failure (e.g., wrong password)"
    )
    
    # Related block if attempt was blocked
    related_block = models.ForeignKey(
        SecurityBlock,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attempts',
        help_text="Security block that prevented this attempt"
    )
    
    class Meta:
        ordering = ['-attempted_at']
        verbose_name = 'Authentication Attempt'
        verbose_name_plural = 'Authentication Attempts'
        indexes = [
            models.Index(fields=['phone_number', '-attempted_at']),
            models.Index(fields=['phone_number', 'attempt_type', 'result', '-attempted_at']),
            models.Index(fields=['-attempted_at']),
        ]
    
    def __str__(self):
        return f"{self.phone_number} - {self.get_attempt_type_display()} - {self.get_result_display()} - {self.attempted_at.strftime('%Y-%m-%d %H:%M:%S')}"
