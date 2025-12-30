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


@api_view(['POST'])
@permission_classes([AllowAny])
def signup(request):
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        
        # Generate device token and register device for students
        device_token = None
        if user.user_type == 'student':
            # Get device info from request body (sent by mobile app)
            device_id = request.data.get('device_id')  # Unique ID from mobile app
            device_name_from_request = request.data.get('device_name')  # e.g., "iPhone 15 Pro", "Samsung Galaxy S24"
            
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
def signin(request):
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(username=username, password=password)
    if not user:
        return Response({'error': 'بيانات الدخول غير صحيحة، من فضلك تحقق.'}, status=status.HTTP_400_BAD_REQUEST)
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
    serializer = PasswordResetRequestSerializer(data=request.data)
    if serializer.is_valid():
        username = serializer.validated_data['username']
        try:
            user = User.objects.filter(username=username).first()
            if not user:
                return Response({'error': 'المستخدم غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
            
            otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            user.otp = otp
            user.otp_created_at = timezone.now()
            user.save()
            
            message = f'Your PIN code is {otp}'
            # Send OTP to username (which is a phone number)
            sms_response = send_beon_sms(phone_numbers=username, message=message)

            if sms_response.get('success'):
                return Response({'message': 'OTP sent to your phone via SMS'})
            else:
                return Response({'error': 'فشل إرسال رمز التحقق عبر الرسائل القصيرة.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': 'حدث خطأ، يرجى المحاولة لاحقًا.'}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password_confirm(request):
    serializer = PasswordResetConfirmSerializer(data=request.data)
    if serializer.is_valid():
        username = serializer.validated_data['username']
        otp = serializer.validated_data['otp']
        new_password = serializer.validated_data['new_password']
        
        try:
            user = User.objects.filter(username=username, otp=otp).first()
            if not user:
                return Response({'error': 'رمز التحقق أو اسم المستخدم غير صحيح'}, status=status.HTTP_400_BAD_REQUEST)
            
            if user.otp_created_at < timezone.now() - timedelta(minutes=10):
                return Response({'error': 'انتهت صلاحية رمز التحقق'}, status=status.HTTP_400_BAD_REQUEST)
            
            user.set_password(new_password)
            user.otp = None
            user.otp_created_at = None
            user.save()
            
            return Response({'message': 'Password reset successful'})
        except Exception as e:
            return Response({'error': 'حدث خطأ، يرجى المحاولة لاحقًا.'}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



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
                'message': 'Account deleted successfully.',
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
            {'message': 'Password updated successfully'}, 
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
            return Response({'error': 'المستخدم غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
        
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
            return Response({'error': 'المستخدم غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
        
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class UserProfileImageListCreateView(generics.ListCreateAPIView):
    queryset = UserProfileImage.objects.all()

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
    ordering_fields = ['created_at']
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
    ordering_fields = ['created_at']
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
    ordering_fields = ['created_at', 'username', 'name']
    
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
            'message': f'Max devices updated to {new_max}',
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
    device.delete()
    
    return Response({
        'message': f'Device "{device_name}" has been removed',
        'active_devices_count': UserDevice.objects.filter(user=student, is_active=True).count()
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def remove_all_student_devices(request, pk):
    """
    Remove all devices from a student, forcing them to login again.
    """
    try:
        student = User.objects.get(pk=pk, user_type='student')
    except User.DoesNotExist:
        return Response({'error': 'الطالب غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
    
    deleted_count = UserDevice.objects.filter(user=student).delete()[0]
    
    return Response({
        'message': f'All {deleted_count} device(s) have been removed',
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
        return Response({'message': 'Device tracking is only for students'}, status=status.HTTP_200_OK)
    
    devices = UserDevice.objects.filter(user=user, is_active=True)
    serializer = UserDeviceSerializer(devices, many=True)
    
    return Response({
        'max_allowed_devices': user.max_allowed_devices,
        'active_devices_count': devices.count(),
        'devices': serializer.data
    })

