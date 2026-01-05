from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny,IsAuthenticated,IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters
from rest_framework.views import APIView
from django.contrib.auth import authenticate
from services.beon_service import send_beon_sms
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
import random
import secrets
import logging

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Extract client IP address from request headers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', 'Unknown')
    return ip


def get_device_info_from_request(request):
    """
    Extract device information from request headers.
    Returns a dict with IP, User-Agent, and parsed device name.
    """
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown')
    
    # Parse User-Agent to get a friendly device name
    device_name = 'Unknown Device'
    if user_agent and user_agent != 'Unknown':
        ua_lower = user_agent.lower()
        if 'iphone' in ua_lower:
            device_name = 'iPhone'
        elif 'ipad' in ua_lower:
            device_name = 'iPad'
        elif 'android' in ua_lower:
            device_name = 'Android Device'
        elif 'windows' in ua_lower:
            device_name = 'Windows PC'
        elif 'macintosh' in ua_lower or 'mac os' in ua_lower:
            device_name = 'Mac'
        elif 'linux' in ua_lower:
            device_name = 'Linux PC'
        else:
            # Use first part of user agent as fallback
            device_name = user_agent[:50] if len(user_agent) > 50 else user_agent
    
    return {
        'ip_address': ip_address,
        'user_agent': user_agent,
        'device_name': device_name
    }
from accounts.pagination import CustomPageNumberPagination
from products.models import Pill, PillItem
from django.db.models import Prefetch
from .serializers import (
    ChangePasswordSerializer,
    UserProfileImageCreateSerializer,
    UserProfileImageSerializer,
    UserSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    UserOrderSerializer,
    UserDeviceSerializer,
    StudentDeviceListSerializer,
    UpdateMaxDevicesSerializer,
)
from .models import User, UserProfileImage, UserDevice
from django.contrib.auth import update_session_auth_hash
from rest_framework import generics
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Count, Q


# ============================================
# OTP-Based Signup Flow
# ============================================

@api_view(['POST'])
@permission_classes([AllowAny])
def signup(request):
    """
    Step 1: Validate user data and send OTP
    
    POST /accounts/signup/
    {
        "username": "01234567890",  // phone number
        "password": "password123",
        "name": "Student Name",
        "user_type": "student",
        "parent_phone": "01111111111",
        "year": "first-secondary",
        "division": "علمى",
        "government": "1"
    }
    
    Response:
    {
        "success": true,
        "message": "تم إرسال رمز التحقق إلى رقم هاتفك",
        "phone_number": "01234567890",
        "expires_in_minutes": 10
    }
    """
    from services.otp_service import otp_service
    
    # Prevent admin registration - تسجيل الحساب للطلاب فقط
    if request.data.get('user_type') != 'student':
        return Response({'error': 'تسجيل الحساب للطلاب فقط'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate data using serializer (but don't save yet)
    serializer = UserSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if username (phone number) already exists
    username = request.data.get('username')
    if User.objects.filter(username=username).exists():
        return Response({'error': 'رقم الهاتف مسجل بالفعل'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Store validated data temporarily in session or cache
    # For simplicity, we'll rely on client to resend data during verification
    # In production, you might want to cache this data
    
    # Send OTP
    otp_result = otp_service.send_otp(
        phone_number=username,
        purpose='signup'
    )
    
    if otp_result['success']:
        return Response({
            'success': True,
            'message': otp_result['message'],
            'phone_number': username,
            'expires_in_minutes': otp_result['expires_in_minutes']
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            'error': otp_result.get('error', 'فشل إرسال رمز التحقق'),
            'wait_time': otp_result.get('wait_time'),
            'max_attempts_reached': otp_result.get('max_attempts_reached', False)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_signup_otp(request):
    """
    Step 2: Verify OTP and complete registration
    
    POST /accounts/signup/verify-otp/
    {
        "username": "01234567890",
        "password": "password123",
        "name": "Student Name",
        "otp_code": "123456",
        "user_type": "student",
        "parent_phone": "01111111111",
        "year": "first-secondary",
        "division": "علمى",
        "government": "1",
        "device_id": "optional_device_id",
        "device_name": "optional_device_name"
    }
    
    Response:
    {
        "refresh": "token",
        "access": "token"
    }
    """
    from services.otp_service import otp_service
    
    username = request.data.get('username')
    otp_code = request.data.get('otp_code')
    
    if not username or not otp_code:
        return Response({
            'error': 'رقم الهاتف ورمز التحقق مطلوبان'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Verify OTP
    verification_result = otp_service.verify_otp(
        phone_number=username,
        otp_code=otp_code,
        purpose='signup'
    )
    
    if not verification_result['success']:
        return Response({
            'error': verification_result['error'],
            'error_code': verification_result.get('error_code'),
            'remaining_attempts': verification_result.get('remaining_attempts')
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # OTP verified successfully, now create user
    # Prevent admin registration
    if request.data.get('user_type') != 'student':
        return Response({'error': 'تسجيل الحساب للطلاب فقط'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate and create user
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        
        # Generate device token and register device for students
        device_token = None
        if user.user_type == 'student':
            # Get device info from request body (sent by mobile app)
            device_id = request.data.get('device_id')  # Unique ID from mobile app
            device_name_from_request = request.data.get('device_name')
            
            # Auto-detect device info from request headers (fallback)
            device_info_data = get_device_info_from_request(request)
            device_token = secrets.token_hex(32)  # 64 character hex string
            
            # Use device_name from request if provided, otherwise use auto-detected
            final_device_name = device_name_from_request or device_info_data['device_name']
            
            # Create device record
            UserDevice.objects.create(
                user=user,
                device_token=device_token,
                device_id=device_id,  # From mobile app (may be None)
                device_name=final_device_name,
                ip_address=device_info_data['ip_address'],
                user_agent=device_info_data['user_agent'],
                is_active=True
            )
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        # Add device_token to JWT payload for students
        if device_token:
            refresh['device_token'] = device_token

        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def resend_signup_otp(request):
    """
    Resend OTP for signup (with 120-second rate limit)
    
    POST /accounts/signup/resend-otp/
    {
        "username": "01234567890"
    }
    
    Response:
    {
        "success": true,
        "message": "تم إعادة إرسال رمز التحقق",
        "expires_in_minutes": 10
    }
    """
    from services.otp_service import otp_service
    
    username = request.data.get('username')
    if not username:
        return Response({'error': 'رقم الهاتف مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if username already exists
    if User.objects.filter(username=username).exists():
        return Response({'error': 'رقم الهاتف مسجل بالفعل'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Send OTP
    otp_result = otp_service.send_otp(
        phone_number=username,
        purpose='signup'
    )
    
    if otp_result['success']:
        return Response({
            'success': True,
            'message': otp_result['message'],
            'expires_in_minutes': otp_result['expires_in_minutes']
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            'error': otp_result.get('error', 'فشل إرسال رمز التحقق'),
            'wait_time': otp_result.get('wait_time'),
            'max_attempts_reached': otp_result.get('max_attempts_reached', False)
        }, status=status.HTTP_400_BAD_REQUEST)


# ============================================
# End OTP-Based Signup Flow
# ============================================


@api_view(['POST'])
@permission_classes([AllowAny])
def signin(request):
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(username=username, password=password)
    if not user:
        return Response({'error': 'بيانات الدخول غير صحيحة، من فضلك تحقق.'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if user is banned
    if user.is_banned:
        return Response({'error': 'لقد تم حظر هذا الحساب'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        device_token = None

        # Handle device registration for students (same logic as before)
        if user.user_type == 'student':
            device_id = request.data.get('device_id')
            device_name_from_request = request.data.get('device_name')
            device_info_data = get_device_info_from_request(request)
            ip_address = device_info_data['ip_address']
            final_device_name = device_name_from_request or device_info_data['device_name']

            existing_device = None
            if device_id:
                existing_device = UserDevice.objects.filter(
                    user=user,
                    is_active=True,
                    device_id=device_id
                ).first()
                
                # Check if this device is banned
                if existing_device and existing_device.is_banned:
                    return Response({'error': 'لقد تم حظر هذا الجهاز'}, status=status.HTTP_403_FORBIDDEN)
            else:
                existing_device = UserDevice.objects.filter(
                    user=user,
                    is_active=True,
                    ip_address=ip_address,
                    device_id__isnull=True
                ).first()

            if existing_device:
                existing_device.last_used_at = timezone.now()
                existing_device.user_agent = device_info_data['user_agent']
                existing_device.device_name = final_device_name
                existing_device.ip_address = ip_address
                if device_id and not existing_device.device_id:
                    existing_device.device_id = device_id
                existing_device.save(update_fields=['last_used_at', 'user_agent', 'device_name', 'ip_address', 'device_id'])
                device_token = existing_device.device_token
            else:
                active_devices_count = UserDevice.objects.filter(user=user, is_active=True).count()
                if active_devices_count >= user.max_allowed_devices:
                    return Response({'error': 'لقد تجاوزت العدد المسموح به من الأجهزة لتسجيل الدخول إلى حسابك .'}, status=status.HTTP_400_BAD_REQUEST)

                device_token = secrets.token_hex(32)
                UserDevice.objects.create(
                    user=user,
                    device_token=device_token,
                    device_id=device_id,
                    device_name=final_device_name,
                    ip_address=ip_address,
                    user_agent=device_info_data['user_agent'],
                    is_active=True
                )

        refresh = RefreshToken.for_user(user)
        if device_token:
            refresh['device_token'] = device_token

        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })
    except Exception as e:
        return Response({'error': 'فشل إنشاء رمز المصادقة.'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def signin_dashboard(request):
    """Signin endpoint for staff/superusers (dashboard). Returns only tokens."""
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(username=username, password=password)
    if not user:
        return Response({'error': 'بيانات الدخول غير صحيحة، من فضلك تحقق.'}, status=status.HTTP_400_BAD_REQUEST)

    # Only allow staff or superuser to use this endpoint
    if not (user.is_staff or user.is_superuser):
        return Response({'error': 'غير مصرح بالدخول عبر هذا المسار.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })
    except Exception as e:
        return Response({'error': 'فشل إنشاء رمز المصادقة.'}, status=status.HTTP_400_BAD_REQUEST)
    

@api_view(['POST'])
@permission_classes([AllowAny])
def request_password_reset(request):
    """
    Request password reset - Send OTP via WhatsApp
    Uses the new generic OTP service with rate limiting and attempt tracking
    """
    from services.otp_service import otp_service
    
    serializer = PasswordResetRequestSerializer(data=request.data)
    if serializer.is_valid():
        username = serializer.validated_data['username']
        try:
            user = User.objects.filter(username=username).first()
            if not user:
                return Response({'error': 'المستخدم غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Use new OTP service
            otp_result = otp_service.send_otp(
                phone_number=username,
                purpose='password_reset',
                user=user
            )
            
            if otp_result['success']:
                return Response({
                    'success': True,
                    'message': otp_result['message'],
                    'expires_in_minutes': otp_result['expires_in_minutes']
                }, status=status.HTTP_200_OK)
            else:
                logger.error(f"Password reset OTP failed for {username}: {otp_result}")
                return Response({
                    'error': otp_result.get('error', 'فشل إرسال رمز التحقق'),
                    'details': otp_result.get('details'),  # Include error details for debugging
                    'wait_time': otp_result.get('wait_time'),
                    'max_attempts_reached': otp_result.get('max_attempts_reached', False)
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Exception in password reset for {username}: {str(e)}")
            return Response({'error': 'حدث خطأ، يرجى المحاولة لاحقًا.', 'details': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password_confirm(request):
    """
    Confirm password reset with OTP
    Uses the new generic OTP service with verification attempt tracking
    """
    from services.otp_service import otp_service
    
    serializer = PasswordResetConfirmSerializer(data=request.data)
    if serializer.is_valid():
        username = serializer.validated_data['username']
        otp = serializer.validated_data['otp']
        new_password = serializer.validated_data['new_password']
        
        try:
            user = User.objects.filter(username=username).first()
            if not user:
                return Response({'error': 'اسم المستخدم غير صحيح'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Verify OTP using new service
            verification_result = otp_service.verify_otp(
                phone_number=username,
                otp_code=otp,
                purpose='password_reset',
                mark_as_used=True
            )
            
            if not verification_result['success']:
                return Response({
                    'error': verification_result['error'],
                    'error_code': verification_result.get('error_code'),
                    'remaining_attempts': verification_result.get('remaining_attempts')
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # OTP verified, reset password
            user.set_password(new_password)
            user.save()
            
            return Response({
                'success': True,
                'message': 'تم إعادة تعيين كلمة المرور بنجاح'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({'error': 'حدث خطأ، يرجى المحاولة لاحقًا.'}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def resend_password_reset_otp(request):
    """
    Resend OTP for password reset (with 120-second rate limit)
    
    POST /accounts/password-reset/resend-otp/
    {
        "username": "01234567890"
    }
    """
    from services.otp_service import otp_service
    
    username = request.data.get('username')
    if not username:
        return Response({'error': 'رقم الهاتف مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if user exists
    user = User.objects.filter(username=username).first()
    if not user:
        return Response({'error': 'المستخدم غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Send OTP
    otp_result = otp_service.send_otp(
        phone_number=username,
        purpose='password_reset',
        user=user
    )
    
    if otp_result['success']:
        return Response({
            'success': True,
            'message': otp_result['message'],
            'expires_in_minutes': otp_result['expires_in_minutes']
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            'error': otp_result.get('error', 'فشل إرسال رمز التحقق'),
            'wait_time': otp_result.get('wait_time'),
            'max_attempts_reached': otp_result.get('max_attempts_reached', False)
        }, status=status.HTTP_400_BAD_REQUEST)



class UpdateUserData(generics.UpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Prevent students from changing their username
        if instance.user_type == 'student' and 'username' in request.data:
            if request.data['username'] != instance.username:
                return Response({'error': 'لا يمكن للطلاب تغيير اسم المستخدم'}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

class GetUserData(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserOrdersView(generics.ListAPIView):
    serializer_class = UserOrderSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        return (
            Pill.objects.filter(user=self.request.user)
            .select_related('coupon')
            .prefetch_related(
                Prefetch(
                    'items',
                    queryset=PillItem.objects.select_related('product', 'product__teacher')
                )
            )
            .order_by('-date_added')
        )


class DeleteAccountView(APIView):
    """Allow an authenticated student to permanently delete their account."""
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user

        if user.is_staff or user.is_superuser:
            return Response({'error': 'لا يمكن حذف حسابات المدير عبر هذا المسار.'}, status=status.HTTP_400_BAD_REQUEST)

        username = user.username
        user.delete()
        return Response(
            {
            'message': 'تم حذف الحساب بنجاح.',
            'username': username
            },
            status=status.HTTP_200_OK
        )
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data)
    
    if serializer.is_valid():
        user = request.user
        old_password = serializer.validated_data['old_password']
        new_password = serializer.validated_data['new_password']
        
        # Verify old password
        if not user.check_password(old_password):
            return Response({'error': 'كلمة المرور القديمة غير صحيحة'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Set new password
        user.set_password(new_password)
        user.save()
        
        # Update session to prevent logout
        update_session_auth_hash(request, user)
        
        return Response(
            {'message': 'تم تحديث كلمة المرور بنجاح'}, 
            status=status.HTTP_200_OK
        )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#^ ---------------------------------------------------- Dashboard ---------------------------- ^#

@api_view(['POST'])
@permission_classes([IsAdminUser])
def create_admin_user(request):
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save(is_staff=True, is_superuser=True)
        refresh = RefreshToken.for_user(user)
        # Return a compact admin-shaped user object in the response
        from .serializers import AdminListUserSerializer
        user_data = AdminListUserSerializer(user, context={'request': request}).data
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': user_data
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserUpdateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, username):  # Changed from pk to username
        try:
            user = User.objects.get(username=username)  # Changed to use username
        except User.DoesNotExist:
            return Response({'error': 'المستخدم غير موجود'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserDeleteAPIView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'المستخدم غير موجود'}, status=status.HTTP_404_NOT_FOUND)
        
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class UserProfileImageListCreateView(generics.ListCreateAPIView):
    queryset = UserProfileImage.objects.all()
    filter_backends = [OrderingFilter]
    ordering_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return [AllowAny()]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return UserProfileImageCreateSerializer
        return UserProfileImageSerializer

class UserProfileImageRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = UserProfileImage.objects.all()
    serializer_class = UserProfileImageSerializer
    permission_classes = [IsAdminUser]


# user analysis

class AdminUserFilter(filters.FilterSet):
    """Reusable filter that supports 'government' as an IN filter (comma-separated)."""
    government = filters.BaseInFilter(field_name='government', lookup_expr='in')

    class Meta:
        model = User
        fields = ['is_staff', 'is_superuser', 'year', 'division', 'government']


class AdminsListView(generics.ListAPIView):
    """Return users who are admins (is_staff OR is_superuser)."""
    serializer_class = None
    permission_classes = [IsAdminUser]
    filter_backends = [SearchFilter, OrderingFilter, DjangoFilterBackend]
    ordering_fields = ['id', 'created_at', 'username', 'name', 'email']
    ordering = ['-created_at']
    search_fields = ['username', 'name', 'email', 'government']
    filterset_class = AdminUserFilter

    def get_queryset(self):
        return User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).order_by('-created_at')

    def get_serializer_class(self):
        from .serializers import AdminListUserSerializer
        return AdminListUserSerializer


class UsersListView(generics.ListAPIView):
    """Return non-admin users (exclude is_staff and is_superuser)."""
    serializer_class = None
    permission_classes = [IsAdminUser]
    filter_backends = [SearchFilter, OrderingFilter, DjangoFilterBackend]
    ordering_fields = ['id', 'created_at', 'username', 'name', 'email', 'year', 'division']
    ordering = ['-created_at']
    search_fields = ['username', 'name', 'email', 'government']
    filterset_class = AdminUserFilter

    def get_queryset(self):
        return User.objects.filter(is_staff=False, is_superuser=False).order_by('-created_at')

    def get_serializer_class(self):
        from .serializers import PublicUserSerializer
        return PublicUserSerializer


class AdminUserDetailView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]
    queryset = User.objects.all()
    lookup_field = 'pk'


# ============== Device Management Views (Admin) ==============

class StudentDeviceListView(generics.ListAPIView):
    """
    List all students with their devices.
    Admin can see all registered devices for each student.
    """
    serializer_class = StudentDeviceListSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [SearchFilter, OrderingFilter, DjangoFilterBackend]
    search_fields = ['username', 'name']
    ordering_fields = ['id', 'created_at', 'username', 'name', 'max_allowed_devices']
    ordering = ['-created_at']
    
    def get_queryset(self):
        return User.objects.filter(user_type='student', is_staff=False, is_superuser=False).prefetch_related('devices').order_by('-created_at')


class StudentDeviceDetailView(generics.RetrieveAPIView):
    """
    Get detailed device information for a specific student.
    """
    serializer_class = StudentDeviceListSerializer
    permission_classes = [IsAdminUser]
    
    def get_queryset(self):
        return User.objects.filter(user_type='student', is_staff=False, is_superuser=False).prefetch_related('devices')


@api_view(['PATCH'])
@permission_classes([IsAdminUser])
def update_student_max_devices(request, pk):
    """
    Update the maximum number of allowed devices for a specific student.
    Admin can increase or decrease the limit.
    """
    try:
        student = User.objects.get(pk=pk, user_type='student')
    except User.DoesNotExist:
        return Response({'error': 'الطالب غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
    
    serializer = UpdateMaxDevicesSerializer(data=request.data)
    if serializer.is_valid():
        new_max = serializer.validated_data['max_allowed_devices']
        student.max_allowed_devices = new_max
        student.save(update_fields=['max_allowed_devices'])
        
        # If new max is less than current active devices, deactivate oldest ones
        active_devices = UserDevice.objects.filter(user=student, is_active=True).order_by('last_used_at')
        active_count = active_devices.count()
        
        if active_count > new_max:
            # Deactivate oldest devices to match new limit
            devices_to_deactivate = active_devices[:active_count - new_max]
            for device in devices_to_deactivate:
                device.is_active = False
                device.save(update_fields=['is_active'])
        
        return Response({
            'message': f'تم تحديث الحد الأقصى للأجهزة إلى {new_max}',
            'max_allowed_devices': new_max,
            'active_devices_count': UserDevice.objects.filter(user=student, is_active=True).count()
        })
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def remove_student_device(request, pk, device_id):
    """
    Remove (delete) a specific device from a student.
    This will log out that device immediately (next API call will fail).
    The student can login again from this device if they want.
    """
    try:
        student = User.objects.get(pk=pk, user_type='student')
    except User.DoesNotExist:
        return Response({'error': 'الطالب غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        device = UserDevice.objects.get(pk=device_id, user=student)
    except UserDevice.DoesNotExist:
        return Response({'error': 'الجهاز غير موجود لهذا الطالب'}, status=status.HTTP_400_BAD_REQUEST)
    
    device_name = device.device_name
    
    # Simply delete the device - this will invalidate all tokens with this device_token
    # The authentication middleware will reject any requests with this device_token
    device.delete()
    
    return Response({
        'message': f'تم حذف الجهاز "{device_name}"',
        'active_devices_count': UserDevice.objects.filter(user=student, is_active=True).count()
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def remove_all_student_devices(request, pk):
    """
    Remove all devices from a student, forcing them to login again.
    Also blacklists all refresh tokens to invalidate access tokens.
    """
    try:
        student = User.objects.get(pk=pk, user_type='student')
    except User.DoesNotExist:
        return Response({'error': 'الطالب غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
    
    deleted_count = UserDevice.objects.filter(user=student).delete()[0]
    
    # Delete all outstanding refresh tokens for this user
    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        
        tokens_deleted = OutstandingToken.objects.filter(user=student).delete()[0]
        
        message = f'تم حذف {deleted_count} جهاز و{tokens_deleted} رمز وصول'
    except (ImportError, AttributeError):
        # Token blacklist not enabled or not properly configured
        message = f'تم حذف {deleted_count} جهاز. تحذير: ميزة إدارة الرموز غير مفعلة'
    
    return Response({
        'message': message,
        'active_devices_count': 0
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_devices(request):
    """
    Get current user's registered devices (for students to see their own devices).
    """
    user = request.user
    
    if user.user_type != 'student':
        return Response({'message': 'تتبع الأجهزة متاح للطلاب فقط'}, status=status.HTTP_200_OK)
    
    devices = UserDevice.objects.filter(user=user, is_active=True)
    serializer = UserDeviceSerializer(devices, many=True)
    
    return Response({
        'max_allowed_devices': user.max_allowed_devices,
        'active_devices_count': devices.count(),
        'devices': serializer.data
    })


# ============================================
# Ban/Unban User and Device Endpoints
# ============================================

@api_view(['POST'])
@permission_classes([IsAdminUser])
def ban_student(request, pk):
    """
    Ban a student - logs them out from all devices and prevents login
    
    POST /accounts/dashboard/students/<pk>/ban/
    {
        "reason": "Optional reason for ban"
    }
    """
    try:
        student = User.objects.get(pk=pk, user_type='student')
    except User.DoesNotExist:
        return Response({'error': 'الطالب غير موجود'}, status=status.HTTP_404_NOT_FOUND)
    
    if student.is_banned:
        return Response({'error': 'الطالب محظور بالفعل'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Ban the user
    student.is_banned = True
    student.banned_at = timezone.now()
    student.ban_reason = request.data.get('reason', '')
    student.save(update_fields=['is_banned', 'banned_at', 'ban_reason'])
    
    # Deactivate all devices
    UserDevice.objects.filter(user=student).update(is_active=False)
    
    return Response({
        'message': f'تم حظر الطالب "{student.name}" بنجاح',
        'banned_at': student.banned_at
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def unban_student(request, pk):
    """
    Unban a student - allows them to login again
    
    POST /accounts/dashboard/students/<pk>/unban/
    """
    try:
        student = User.objects.get(pk=pk, user_type='student')
    except User.DoesNotExist:
        return Response({'error': 'الطالب غير موجود'}, status=status.HTTP_404_NOT_FOUND)
    
    if not student.is_banned:
        return Response({'error': 'الطالب غير محظور'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Unban the user
    student.is_banned = False
    student.banned_at = None
    student.ban_reason = None
    student.save(update_fields=['is_banned', 'banned_at', 'ban_reason'])
    
    return Response({
        'message': f'تم إلغاء حظر الطالب "{student.name}" بنجاح'
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def ban_device(request, pk, device_id):
    """
    Ban a specific device - logs it out and prevents login from that device
    
    POST /accounts/dashboard/students/<pk>/devices/<device_id>/ban/
    {
        "reason": "Optional reason for ban"
    }
    """
    try:
        student = User.objects.get(pk=pk, user_type='student')
    except User.DoesNotExist:
        return Response({'error': 'الطالب غير موجود'}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        device = UserDevice.objects.get(pk=device_id, user=student)
    except UserDevice.DoesNotExist:
        return Response({'error': 'الجهاز غير موجود لهذا الطالب'}, status=status.HTTP_404_NOT_FOUND)
    
    if device.is_banned:
        return Response({'error': 'الجهاز محظور بالفعل'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Ban the device
    device.is_banned = True
    device.is_active = False
    device.banned_at = timezone.now()
    device.ban_reason = request.data.get('reason', '')
    device.save(update_fields=['is_banned', 'is_active', 'banned_at', 'ban_reason'])
    
    return Response({
        'message': f'تم حظر الجهاز "{device.device_name}" بنجاح',
        'banned_at': device.banned_at
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def unban_device(request, pk, device_id):
    """
    Unban a device - allows login from that device again
    
    POST /accounts/dashboard/students/<pk>/devices/<device_id>/unban/
    """
    try:
        student = User.objects.get(pk=pk, user_type='student')
    except User.DoesNotExist:
        return Response({'error': 'الطالب غير موجود'}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        device = UserDevice.objects.get(pk=device_id, user=student)
    except UserDevice.DoesNotExist:
        return Response({'error': 'الجهاز غير موجود لهذا الطالب'}, status=status.HTTP_404_NOT_FOUND)
    
    if not device.is_banned:
        return Response({'error': 'الجهاز غير محظور'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Unban the device
    device.is_banned = False
    device.is_active = True
    device.banned_at = None
    device.ban_reason = None
    device.save(update_fields=['is_banned', 'is_active', 'banned_at', 'ban_reason'])
    
    return Response({
        'message': f'تم إلغاء حظر الجهاز "{device.device_name}" بنجاح'
    })
