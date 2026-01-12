"""
Security service for managing authentication rate limiting and progressive blocking.
Handles failed login attempts and password reset request limits.
"""
from django.utils import timezone
from django.conf import settings
from django.db import models
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class SecurityService:
    """
    Centralized service for handling authentication security, rate limiting,
    and progressive blocking mechanisms.
    """
    
    def __init__(self):
        """Initialize with configurable settings"""
        # Get settings with defaults
        self.max_attempts = getattr(settings, 'SECURITY_MAX_FAILED_ATTEMPTS', 3)
        self.block_durations = getattr(settings, 'SECURITY_BLOCK_DURATIONS', [
            15,    # 15 minutes for first block
            60,    # 1 hour for second block
            360,   # 6 hours for third block
            1440,  # 24 hours for fourth block
            10080, # 7 days for fifth block
        ])
        self.attempt_window_minutes = getattr(settings, 'SECURITY_ATTEMPT_WINDOW_MINUTES', 60)
        self.reset_after_hours = getattr(settings, 'SECURITY_RESET_CONSECUTIVE_BLOCKS_HOURS', 168)  # 7 days
    
    def check_and_record_attempt(self, phone_number, attempt_type, success, 
                                  ip_address=None, user_agent=None, device_id=None, failure_reason=None):
        """
        Check if attempt is allowed and record it.
        Returns dict with: allowed (bool), reason (str), block_info (dict or None)
        
        Args:
            phone_number: Phone number attempting authentication
            attempt_type: 'login' or 'password_reset'
            success: Whether attempt was successful
            ip_address: IP address of attempt
            user_agent: User agent string
            device_id: Device ID from mobile app (primary identifier)
            failure_reason: Reason for failure if applicable
        """
        # Import here to avoid circular imports
        from accounts.security_models import SecurityBlock, AuthenticationAttempt
        
        # Check if phone number is currently blocked
        active_block = self._get_active_block(phone_number, attempt_type)
        
        if active_block:
            # Check if block has expired
            if active_block.is_expired():
                active_block.is_active = False
                active_block.save(update_fields=['is_active'])
                logger.info(f"Block expired for {phone_number}, proceeding with attempt")
            else:
                # Still blocked - record blocked attempt
                AuthenticationAttempt.objects.create(
                    phone_number=phone_number,
                    attempt_type=attempt_type,
                    result='blocked',
                    ip_address=ip_address,
                    user_agent=user_agent,
                    device_id=device_id,
                    failure_reason=f"محظور حتى {active_block.blocked_until}",
                    related_block=active_block
                )
                
                return {
                    'allowed': False,
                    'reason': 'blocked',
                    'block_info': {
                        'blocked_until': active_block.blocked_until,
                        'remaining_seconds': active_block.remaining_time(),
                        'remaining_formatted': active_block.remaining_time_formatted(),
                        'block_level': active_block.block_level,
                        'message_ar': self._get_block_message_ar(active_block),
                        'message_en': self._get_block_message_en(active_block)
                    }
                }
        
        # Record the attempt
        result = 'success' if success else 'failed'
        attempt = AuthenticationAttempt.objects.create(
            phone_number=phone_number,
            attempt_type=attempt_type,
            result=result,
            ip_address=ip_address,
            user_agent=user_agent,
            device_id=device_id,
            failure_reason=failure_reason
        )
        
        if success:
            # Successful attempt - no further action needed
            return {
                'allowed': True,
                'reason': 'success',
                'block_info': None
            }
        
        # Failed attempt - check if we need to create a block
        return self._check_and_create_block_if_needed(
            phone_number, attempt_type, ip_address, user_agent, device_id
        )
    
    def _get_active_block(self, phone_number, attempt_type):
        """Get active block for phone number and attempt type"""
        from accounts.security_models import SecurityBlock
        
        # Check for specific block type or combined block
        active_blocks = SecurityBlock.objects.filter(
            phone_number=phone_number,
            is_active=True,
            blocked_until__gt=timezone.now()
        ).filter(
            models.Q(block_type=attempt_type) | models.Q(block_type='combined')
        ).order_by('-blocked_at')
        
        return active_blocks.first()
    
    def _check_and_create_block_if_needed(self, phone_number, attempt_type, 
                                          ip_address, user_agent, device_id=None):
        """
        Check recent failed attempts and create block if threshold exceeded.
        Returns dict with allowed status and block info.
        """
        from accounts.security_models import AuthenticationAttempt, SecurityBlock
        
        # Get recent failed attempts within the window.
        # If an admin manually unblocked this phone number, treat that moment as a reset point
        # so the student starts over “as if never blocked”.
        cutoff_time = timezone.now() - timedelta(minutes=self.attempt_window_minutes)

        last_manual_unblock = (
            SecurityBlock.objects.filter(
                phone_number=phone_number,
                manually_unblocked=True,
                unblocked_at__isnull=False,
            )
            .order_by('-unblocked_at')
            .first()
        )

        if last_manual_unblock and last_manual_unblock.unblocked_at:
            cutoff_time = max(cutoff_time, last_manual_unblock.unblocked_at)
        recent_failed = AuthenticationAttempt.objects.filter(
            phone_number=phone_number,
            attempt_type=attempt_type,
            result='failed',
            attempted_at__gte=cutoff_time
        ).count()
        
        logger.info(f"Phone {phone_number}: {recent_failed} failed {attempt_type} attempts in last {self.attempt_window_minutes} minutes")
        
        if recent_failed >= self.max_attempts:
            # Need to create a block
            block = self._create_progressive_block(
                phone_number, attempt_type, ip_address, user_agent, device_id
            )
            
            return {
                'allowed': False,
                'reason': 'threshold_exceeded',
                'block_info': {
                    'blocked_until': block.blocked_until,
                    'remaining_seconds': block.remaining_time(),
                    'remaining_formatted': block.remaining_time_formatted(),
                    'block_level': block.block_level,
                    'message_ar': self._get_block_message_ar(block),
                    'message_en': self._get_block_message_en(block)
                }
            }
        
        # Not blocked yet, but inform about remaining attempts
        # Note: recent_failed already includes the current failed attempt
        # So we calculate: max_attempts - recent_failed (how many more failures before block)
        remaining_attempts = max(0, self.max_attempts - recent_failed)
        return {
            'allowed': True,
            'reason': 'attempt_recorded',
            'block_info': None,
            'remaining_attempts': remaining_attempts
        }
    
    def _create_progressive_block(self, phone_number, attempt_type, 
                                  ip_address, user_agent, device_id=None):
        """
        Create progressive block with increasing duration.
        """
        # Import here to avoid circular imports
        from accounts.security_models import SecurityBlock, AuthenticationAttempt
        
        # Get previous blocks to determine level
        reset_cutoff = timezone.now() - timedelta(hours=self.reset_after_hours)
        previous_blocks = SecurityBlock.objects.filter(
            phone_number=phone_number,
            block_type=attempt_type,
            blocked_at__gte=reset_cutoff
        ).order_by('-blocked_at')
        
        # Check if we should reset the progression
        # If the most recent block was manually unblocked, treat it as a fresh start
        should_reset = False
        if previous_blocks.exists():
            last_block = previous_blocks.first()
            
            # Reset to level 1 if:
            # 1. Last block was manually unblocked by admin (shows forgiveness/resolution)
            # 2. This indicates admin intervention and user should get a fresh start
            if last_block.manually_unblocked:
                should_reset = True
                logger.info(f"Resetting block level for {phone_number} - previous block was manually unblocked by admin")
        
        if should_reset or not previous_blocks.exists():
            # Fresh start - begin at level 1
            block_level = 1
            consecutive_blocks = 1
        else:
            # Continue progression from last block
            last_block = previous_blocks.first()
            block_level = last_block.block_level + 1
            consecutive_blocks = last_block.consecutive_blocks + 1
        
        # Calculate block duration
        duration_index = min(block_level - 1, len(self.block_durations) - 1)
        duration_minutes = self.block_durations[duration_index]
        blocked_until = timezone.now() + timedelta(minutes=duration_minutes)
        
        # Collect recent attempt details
        recent_attempts = AuthenticationAttempt.objects.filter(
            phone_number=phone_number,
            attempt_type=attempt_type,
            result='failed'
        ).order_by('-attempted_at')[:self.max_attempts]
        
        failed_attempts_data = []
        ip_addresses = set()
        user_agents_set = set()
        device_ids_set = set()
        
        for attempt in recent_attempts:
            failed_attempts_data.append({
                'timestamp': attempt.attempted_at.isoformat(),
                'ip_address': attempt.ip_address,
                'device_id': attempt.device_id,
                'failure_reason': attempt.failure_reason
            })
            if attempt.ip_address:
                ip_addresses.add(attempt.ip_address)
            if attempt.user_agent:
                user_agents_set.add(attempt.user_agent[:100])  # Truncate long user agents
            if attempt.device_id:
                device_ids_set.add(attempt.device_id)
        
        # Create block
        block = SecurityBlock.objects.create(
            phone_number=phone_number,
            block_type=attempt_type,
            blocked_until=blocked_until,
            block_level=block_level,
            consecutive_blocks=consecutive_blocks,
            is_active=True,
            failed_attempts=failed_attempts_data,
            ip_addresses=list(ip_addresses),
            user_agents=list(user_agents_set),
            device_ids=list(device_ids_set)
        )
        
        logger.warning(
            f"Created block level {block_level} for {phone_number} ({attempt_type}) "
            f"until {blocked_until} ({duration_minutes} minutes)"
        )
        
        return block
    
    def manually_unblock(self, phone_number, unblocked_by_user, reason=None):
        """
        Manually unblock a phone number (admin action).
        Returns number of blocks that were unblocked.
        """
        from accounts.security_models import SecurityBlock
        
        active_blocks = SecurityBlock.objects.filter(
            phone_number=phone_number,
            is_active=True
        )
        
        count = 0
        for block in active_blocks:
            block.is_active = False
            block.manually_unblocked = True
            block.unblocked_by = unblocked_by_user
            block.unblocked_at = timezone.now()
            block.unblock_reason = reason or "تم رفع الحظر يدويًا بواسطة المدير"
            block.save()
            count += 1
            
            logger.info(
                f"Admin {unblocked_by_user.username} manually unblocked "
                f"{phone_number} (Block ID: {block.id})"
            )
        
        return count
    
    def get_block_status(self, phone_number, attempt_type=None):
        """
        Get current block status for a phone number.
        Returns dict with block info or None if not blocked.
        """
        from accounts.security_models import SecurityBlock
        
        query = SecurityBlock.objects.filter(
            phone_number=phone_number,
            is_active=True,
            blocked_until__gt=timezone.now()
        )
        
        if attempt_type:
            query = query.filter(
                models.Q(block_type=attempt_type) | models.Q(block_type='combined')
            )
        
        block = query.order_by('-blocked_at').first()
        
        if not block:
            return None
        
        # Auto-deactivate if expired
        if block.is_expired():
            block.is_active = False
            block.save(update_fields=['is_active'])
            return None
        
        return {
            'is_blocked': True,
            'block_type': block.block_type,
            'blocked_until': block.blocked_until,
            'remaining_seconds': block.remaining_time(),
            'remaining_formatted': block.remaining_time_formatted(),
            'block_level': block.block_level,
            'consecutive_blocks': block.consecutive_blocks,
            'message_ar': self._get_block_message_ar(block),
            'message_en': self._get_block_message_en(block)
        }
    
    def _get_block_message_ar(self, block):
        """Get Arabic block message"""
        operation = "تسجيل الدخول" if block.block_type == "login" else "إعادة تعيين كلمة المرور"
        return (
            f"تم حظر محاولات {operation} لهذا الرقم مؤقتاً بسبب تجاوز عدد المحاولات المسموحة. "
            f"سيتم رفع الحظر تلقائياً بعد {block.remaining_time_formatted()}. "
            f"إذا لم تكن أنت من قام بهذه المحاولات، يرجى التواصل مع الدعم الفني فوراً."
        )
    
    def _get_block_message_en(self, block):
        """Get English block message (kept for backward-compat keys, but Arabic per project requirement)"""
        return self._get_block_message_ar(block)
    from accounts.security_models import AuthenticationAttempt
        
        
    def get_recent_attempts(self, phone_number, attempt_type=None, limit=10):
        """Get recent authentication attempts for a phone number"""
        query = AuthenticationAttempt.objects.filter(phone_number=phone_number)
        
        if attempt_type:
            query = query.filter(attempt_type=attempt_type)
        
        return query.order_by('-attempted_at')[:limit]
    
    def cleanup_old_records(self, days=30):
        """
        Clean up old authentication attempts and inactive blocks.
        Should be run periodically (e.g., daily cron job).
        """
        from accounts.security_models import SecurityBlock, AuthenticationAttempt
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Delete old attempts
        deleted_attempts = AuthenticationAttempt.objects.filter(
            attempted_at__lt=cutoff_date
        ).delete()
        
        # Delete old inactive blocks
        deleted_blocks = SecurityBlock.objects.filter(
            is_active=False,
            blocked_at__lt=cutoff_date
        ).delete()
        
        logger.info(
            f"Cleanup: Deleted {deleted_attempts[0]} old attempts and "
            f"{deleted_blocks[0]} old blocks"
        )
        
        return {
            'attempts_deleted': deleted_attempts[0],
            'blocks_deleted': deleted_blocks[0]
        }


# Global instance
security_service = SecurityService()
