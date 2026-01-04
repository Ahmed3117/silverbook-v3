"""
Generic OTP Service
===================
A reusable OTP service for managing one-time passwords across different use cases
(signup, password reset, phone verification, etc.)

Features:
- Generate random OTP codes
- Send OTP via WhatsApp
- Validate OTP codes
- Rate limiting (prevent spam)
- Attempt limiting (security)
- Expiration handling

Usage:
------
from services.otp_service import OTPService

# Generate and send OTP
otp_service = OTPService()
result = otp_service.send_otp(
    phone_number='01234567890',
    purpose='signup',  # or 'password_reset', 'phone_verification', etc.
    user=user_instance  # optional
)

# Verify OTP
is_valid = otp_service.verify_otp(
    phone_number='01234567890',
    otp_code='123456',
    purpose='signup'
)

# Check if can resend
can_resend, wait_time = otp_service.can_resend_otp(
    phone_number='01234567890',
    purpose='signup'
)
"""

import random
import logging
from datetime import timedelta
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


class OTPService:
    """Generic OTP service for handling one-time password operations"""
    
    # Configuration constants (can be overridden)
    OTP_LENGTH = 6
    OTP_EXPIRY_MINUTES = 10  # OTP expires after 10 minutes
    RESEND_COOLDOWN_SECONDS = 120  # 2 minutes between resend attempts
    MAX_ATTEMPTS_PER_SESSION = 5  # Maximum OTP send attempts per phone/purpose
    MAX_VERIFICATION_ATTEMPTS = 3  # Maximum wrong OTP entries before blocking
    
    def __init__(self):
        pass
    
    def generate_otp(self, length=None):
        """
        Generate a random numeric OTP code
        
        Args:
            length (int): Length of OTP code (default: 6)
            
        Returns:
            str: Generated OTP code
        """
        length = length or self.OTP_LENGTH
        otp = ''.join([str(random.randint(0, 9)) for _ in range(length)])
        logger.info(f"Generated OTP: {otp[:2]}****")
        return otp
    
    def send_otp_via_whatsapp(self, phone_number, otp_code, purpose='verification'):
        """
        Send OTP via WhatsApp
        
        Args:
            phone_number (str): Recipient phone number
            otp_code (str): OTP code to send
            purpose (str): Purpose of OTP (for message customization)
            
        Returns:
            dict: Result with success status and message
        """
        try:
            from products.utils import send_whatsapp_message
            
            # Customize message based on purpose
            purpose_messages = {
                'signup': f'مرحباً! رمز التحقق الخاص بك لإنشاء حساب جديد هو: {otp_code}\n\nالرمز صالح لمدة {self.OTP_EXPIRY_MINUTES} دقائق.',
                'password_reset': f'رمز إعادة تعيين كلمة المرور الخاص بك هو: {otp_code}\n\nالرمز صالح لمدة {self.OTP_EXPIRY_MINUTES} دقائق.',
                'phone_verification': f'رمز التحقق من رقم الهاتف: {otp_code}\n\nالرمز صالح لمدة {self.OTP_EXPIRY_MINUTES} دقائق.',
                'default': f'رمز التحقق الخاص بك هو: {otp_code}\n\nالرمز صالح لمدة {self.OTP_EXPIRY_MINUTES} دقائق.'
            }
            
            message = purpose_messages.get(purpose, purpose_messages['default'])
            
            # Send via WhatsApp
            response = send_whatsapp_message(phone_number=phone_number, message=message)
            
            logger.info(f"OTP sent to {phone_number} for {purpose}: {response}")
            
            return {
                'success': True,
                'message': 'تم إرسال رمز التحقق بنجاح',
                'response': response
            }
            
        except Exception as e:
            logger.error(f"Failed to send OTP to {phone_number}: {str(e)}")
            return {
                'success': False,
                'message': 'فشل إرسال رمز التحقق',
                'error': str(e)
            }
    
    def send_otp(self, phone_number, purpose='verification', user=None):
        """
        Generate and send OTP to a phone number
        
        Args:
            phone_number (str): Recipient phone number
            purpose (str): Purpose of OTP (signup, password_reset, etc.)
            user (User): Optional user instance for tracking
            
        Returns:
            dict: Result with success status, OTP record, and message
        """
        from accounts.models import OTP
        
        # Check rate limiting
        can_resend, wait_time = self.can_resend_otp(phone_number, purpose)
        if not can_resend:
            return {
                'success': False,
                'error': f'يرجى الانتظار {wait_time} ثانية قبل إعادة إرسال الرمز',
                'wait_time': wait_time
            }
        
        # Check attempt limit
        recent_attempts = OTP.objects.filter(
            phone_number=phone_number,
            purpose=purpose,
            created_at__gte=timezone.now() - timedelta(hours=1)  # Last hour
        ).count()
        
        if recent_attempts >= self.MAX_ATTEMPTS_PER_SESSION:
            return {
                'success': False,
                'error': f'تم تجاوز الحد الأقصى لمحاولات الإرسال ({self.MAX_ATTEMPTS_PER_SESSION}). يرجى المحاولة لاحقاً',
                'max_attempts_reached': True
            }
        
        # Generate OTP
        otp_code = self.generate_otp()
        
        # Save OTP record
        otp_record = OTP.objects.create(
            phone_number=phone_number,
            otp_code=otp_code,
            purpose=purpose,
            user=user,
            expires_at=timezone.now() + timedelta(minutes=self.OTP_EXPIRY_MINUTES)
        )
        
        # Send OTP
        send_result = self.send_otp_via_whatsapp(phone_number, otp_code, purpose)
        
        if send_result['success']:
            return {
                'success': True,
                'message': send_result['message'],
                'otp_id': otp_record.id,
                'expires_in_minutes': self.OTP_EXPIRY_MINUTES
            }
        else:
            # Delete OTP record if sending failed
            otp_record.delete()
            return {
                'success': False,
                'error': send_result['message']
            }
    
    def verify_otp(self, phone_number, otp_code, purpose='verification', mark_as_used=True):
        """
        Verify OTP code
        
        Args:
            phone_number (str): Phone number to verify
            otp_code (str): OTP code to check
            purpose (str): Purpose of OTP
            mark_as_used (bool): Whether to mark OTP as used after verification
            
        Returns:
            dict: Verification result with success status and OTP record
        """
        from accounts.models import OTP
        
        try:
            # Find the most recent unused OTP for this phone/purpose
            otp_record = OTP.objects.filter(
                phone_number=phone_number,
                purpose=purpose,
                is_used=False,
                is_verified=False
            ).order_by('-created_at').first()
            
            if not otp_record:
                return {
                    'success': False,
                    'error': 'لم يتم العثور على رمز تحقق صالح',
                    'error_code': 'OTP_NOT_FOUND'
                }
            
            # Check if OTP is expired
            if timezone.now() > otp_record.expires_at:
                return {
                    'success': False,
                    'error': 'انتهت صلاحية رمز التحقق. يرجى طلب رمز جديد',
                    'error_code': 'OTP_EXPIRED'
                }
            
            # Check verification attempts
            if otp_record.verification_attempts >= self.MAX_VERIFICATION_ATTEMPTS:
                return {
                    'success': False,
                    'error': 'تم تجاوز الحد الأقصى لمحاولات التحقق',
                    'error_code': 'MAX_ATTEMPTS_EXCEEDED'
                }
            
            # Verify OTP code
            if otp_record.otp_code == otp_code:
                # OTP is correct
                otp_record.is_verified = True
                otp_record.verified_at = timezone.now()
                
                if mark_as_used:
                    otp_record.is_used = True
                
                otp_record.save(update_fields=['is_verified', 'verified_at', 'is_used'])
                
                logger.info(f"OTP verified successfully for {phone_number} ({purpose})")
                
                return {
                    'success': True,
                    'message': 'تم التحقق بنجاح',
                    'otp_record': otp_record
                }
            else:
                # OTP is incorrect
                otp_record.verification_attempts += 1
                otp_record.save(update_fields=['verification_attempts'])
                
                remaining_attempts = self.MAX_VERIFICATION_ATTEMPTS - otp_record.verification_attempts
                
                logger.warning(f"Invalid OTP attempt for {phone_number}. Remaining attempts: {remaining_attempts}")
                
                return {
                    'success': False,
                    'error': f'رمز التحقق غير صحيح. المحاولات المتبقية: {remaining_attempts}',
                    'error_code': 'INVALID_OTP',
                    'remaining_attempts': remaining_attempts
                }
                
        except Exception as e:
            logger.error(f"Error verifying OTP for {phone_number}: {str(e)}")
            return {
                'success': False,
                'error': 'حدث خطأ أثناء التحقق',
                'error_code': 'VERIFICATION_ERROR'
            }
    
    def can_resend_otp(self, phone_number, purpose='verification'):
        """
        Check if OTP can be resent (rate limiting)
        
        Args:
            phone_number (str): Phone number
            purpose (str): Purpose of OTP
            
        Returns:
            tuple: (can_resend: bool, wait_time: int in seconds)
        """
        from accounts.models import OTP
        
        # Get the most recent OTP for this phone/purpose
        last_otp = OTP.objects.filter(
            phone_number=phone_number,
            purpose=purpose
        ).order_by('-created_at').first()
        
        if not last_otp:
            # No previous OTP, can send
            return (True, 0)
        
        # Calculate time since last OTP
        time_since_last = (timezone.now() - last_otp.created_at).total_seconds()
        
        if time_since_last >= self.RESEND_COOLDOWN_SECONDS:
            return (True, 0)
        else:
            wait_time = int(self.RESEND_COOLDOWN_SECONDS - time_since_last)
            return (False, wait_time)
    
    def cleanup_expired_otps(self):
        """
        Clean up expired and old OTP records
        Should be run periodically (e.g., via cron job or celery task)
        
        Returns:
            int: Number of deleted records
        """
        from accounts.models import OTP
        
        # Delete OTPs older than 24 hours
        cutoff_time = timezone.now() - timedelta(hours=24)
        deleted_count, _ = OTP.objects.filter(created_at__lt=cutoff_time).delete()
        
        logger.info(f"Cleaned up {deleted_count} expired OTP records")
        return deleted_count


# Create a singleton instance for easy import
otp_service = OTPService()
