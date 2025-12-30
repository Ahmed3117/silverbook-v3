"""
Custom JWT Authentication for multi-device login enforcement.
Students can only be logged in from a limited number of devices (default 2).
Admins can adjust the limit per student and remove devices.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.utils import timezone


class MultiDeviceJWTAuthentication(JWTAuthentication):
    """
    Custom JWT Authentication that enforces multi-device login limits for students.
    
    When a student logs in, a unique device_token is generated and stored in UserDevice.
    On each request, this authentication class validates that the device_token
    in the JWT exists in the user's active devices.
    
    If the device limit is reached and a new login occurs, the oldest device is removed.
    Admins can also manually remove devices or adjust the max_allowed_devices per student.
    
    This restriction only applies to users with user_type='student'.
    Teachers, parents, and other user types can use unlimited devices.
    """
    
    def authenticate(self, request):
        # First, perform standard JWT authentication
        result = super().authenticate(request)
        
        if result is None:
            return None
        
        user, validated_token = result
        
        # Only enforce device limits for students
        if user.user_type == 'student':
            # Get the device token from the JWT
            token_device_id = validated_token.get('device_token')
            
            # If there's no device_token in the JWT, it's an old token - still allow for backward compatibility
            # You can change this to reject old tokens after migration period
            if token_device_id is not None:
                # Import here to avoid circular imports
                from accounts.models import UserDevice
                
                # Check if this device_token exists and is active for this user
                device = UserDevice.objects.filter(
                    user=user,
                    device_token=token_device_id,
                    is_active=True
                ).first()
                
                if not device:
                    raise AuthenticationFailed(
                        detail='Session expired. This device has been logged out or removed.',
                        code='device_token_invalid'
                    )
                
                # Update last_used_at timestamp
                device.last_used_at = timezone.now()
                device.save(update_fields=['last_used_at'])
        
        return (user, validated_token)
