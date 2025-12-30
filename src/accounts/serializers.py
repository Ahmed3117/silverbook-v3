from django.db.models import Count, Sum, F
from rest_framework import serializers
from rest_framework.fields import ImageField
from django.conf import settings

from .models import User, UserProfileImage, UserDevice
from products.models import Pill, PillItem, Product
from django.db.models import Count, Sum, Case, When, Value, FloatField
from django.db.models.functions import Coalesce


def get_full_file_url(file_field, request=None):
    """
    Get the full URL for a file/image field.
    Returns the complete URL including domain.
    """
    if not file_field:
        return None
    
    # Get the file path/name
    file_path = file_field.name if hasattr(file_field, 'name') else str(file_field)
    
    if not file_path:
        return None
    
    # If already a full URL, return as-is
    if file_path.startswith('http://') or file_path.startswith('https://'):
        return file_path
    
    # Build full URL using S3 custom domain or request
    custom_domain = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', None)
    
    if custom_domain:
        # Use S3/R2 custom domain
        return f"https://{custom_domain}/{file_path}"
    elif request:
        # Use request to build absolute URI
        return request.build_absolute_uri(f"{settings.MEDIA_URL}{file_path}")
    else:
        # Fallback to MEDIA_URL
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        if media_url.startswith('http'):
            return f"{media_url.rstrip('/')}/{file_path}"
        return f"{media_url}{file_path}"


class UserProfileImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = UserProfileImage
        fields = ['id', 'image', 'created_at', 'updated_at']

    def get_image(self, obj):
        return get_full_file_url(obj.image, self.context.get('request'))

class UserProfileImageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfileImage
        fields = ['image']
        
class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)  # Make password optional for updates
    # user_profile_image removed per request

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'password', 'name','government',
            'is_staff', 'is_superuser', 'user_type', 'parent_phone',
            'year', 'division',
            'created_at'
        )
        extra_kwargs = {
            'is_staff': {'read_only': True},
            'is_superuser': {'read_only': True},
            'email': {'required': False, 'allow_null': True, 'allow_blank': True},
            'user_type': {'required': False, 'allow_null': True},
            'parent_phone': {'required': False, 'allow_null': True, 'allow_blank': True},
            'year': {'required': False, 'allow_null': True},
            'division': {'required': False, 'allow_null': True},
            'password': {'required': False},  # Make password optional for updates
        }
    
    def validate_username(self, value):
        """Validate that username is a valid Egyptian phone number for students only"""
        # Skip validation during updates if user_type is not being changed
        # We'll validate in the validate() method where we have access to all fields
        return value.strip()
    
    def validate(self, data):
        """Validate username format based on user_type and teacher name uniqueness"""
        import re
        
        username = data.get('username')
        user_type = data.get('user_type')
        name = data.get('name')
        
        # For updates, get the current user_type if not provided
        if self.instance and not user_type:
            user_type = self.instance.user_type
        
        # Only validate phone format for students
        if user_type == 'student' and username:
            # Check if it matches Egyptian phone pattern (starts with 01 and has 11 digits)
            if not re.match(r'^01[0-2,5]{1}[0-9]{8}$', username):
                raise serializers.ValidationError({
                    'username': 'For students, username must be a valid Egyptian phone number (e.g., 01012345678)'
                })
        
        # Validate unique teacher names
        if user_type == 'teacher' and name:
            query = User.objects.filter(
                user_type='teacher',
                name=name
            )
            
            # Exclude current instance if updating
            if self.instance:
                query = query.exclude(pk=self.instance.pk)
            
            # Check if duplicate exists
            if query.exists():
                raise serializers.ValidationError({
                    'name': f"A teacher with the name '{name}' already exists. Teacher names must be unique."
                })
        
        return data
    
    def update(self, instance, validated_data):
        """
        Handle user updates with proper password hashing
        """
        # Extract password from validated_data
        password = validated_data.pop('password', None)
        
        # Update all other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Handle password separately to ensure proper hashing
        if password:
            instance.set_password(password)  # This properly hashes the password
        
        instance.save()
        return instance

    def create(self, validated_data):
        """
        Handle user creation with proper password hashing
        """
        email = validated_data.get('email', None)
        user = User.objects.create_user(
            username=validated_data['username'],
            email=email,
            password=validated_data['password'],
            name=validated_data.get('name', ''),
            is_staff=validated_data.get('is_staff', False),
            is_superuser=validated_data.get('is_superuser', False),
            user_type=validated_data.get('user_type', None),
            parent_phone=validated_data.get('parent_phone', None),
            year=validated_data.get('year', None),
            division=validated_data.get('division', None),
            government=validated_data.get('government', None),
        )
        return user


class AdminListUserSerializer(serializers.ModelSerializer):
    """Serializer for admin listing (admins only)."""
    # user_profile_image removed from admin listing

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'name', 'is_staff', 'is_superuser',
            'created_at'
        )


class PublicUserSerializer(serializers.ModelSerializer):
    """Serializer for non-admin users listing."""
    # user_profile_image removed from public listing

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'name', 'government', 'user_type',
            'parent_phone', 'year', 'division',
            'created_at'
        )


class PasswordResetRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    
    def validate_username(self, value):
        """Validate that username exists and is a valid phone number for students"""
        import re
        from .models import User
        
        # Remove any whitespace
        value = value.strip()
        
        # Check if user exists
        try:
            user = User.objects.get(username=value)
            # Only validate phone format for students
            if user.user_type == 'student':
                if not re.match(r'^01[0-2,5]{1}[0-9]{8}$', value):
                    raise serializers.ValidationError(
                        'For students, username must be a valid Egyptian phone number (e.g., 01012345678)'
                    )
        except User.DoesNotExist:
            # Don't reveal whether user exists or not for security
            pass
        
        return value

class PasswordResetConfirmSerializer(serializers.Serializer):
    username = serializers.CharField()
    otp = serializers.CharField()
    new_password = serializers.CharField()
    
    def validate_username(self, value):
        """Validate that username is a valid phone number for students"""
        import re
        from .models import User
        
        # Remove any whitespace
        value = value.strip()
        
        # Check if user exists
        try:
            user = User.objects.get(username=value)
            # Only validate phone format for students
            if user.user_type == 'student':
                if not re.match(r'^01[0-2,5]{1}[0-9]{8}$', value):
                    raise serializers.ValidationError(
                        'For students, username must be a valid Egyptian phone number (e.g., 01012345678)'
                    )
        except User.DoesNotExist:
            # Don't reveal whether user exists or not for security
            pass
        
        return value

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, min_length=8)


class UserOrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source='product.id', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_number = serializers.CharField(source='product.product_number', read_only=True)
    teacher_name = serializers.CharField(source='product.teacher.name', read_only=True)
    product_image = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = PillItem
        fields = [
            'id', 'status', 'status_display', 'price_at_sale', 'date_added',
            'product_id', 'product_name', 'product_number', 'teacher_name',
            'product_image'
        ]

    def get_product_image(self, obj):
        product = getattr(obj, 'product', None)
        if not product:
            return None

        image = product.base_image or product.main_image()
        if not image or not hasattr(image, 'url'):
            return None

        request = self.context.get('request')
        url = image.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class UserOrderSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    subtotal = serializers.SerializerMethodField()
    final_total = serializers.SerializerMethodField()
    coupon_code = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = Pill
        fields = [
            'id', 'pill_number', 'status', 'status_display', 'payment_gateway',
            'coupon_discount', 'coupon_code', 'items_count', 'subtotal',
            'final_total', 'date_added', 'items'
        ]

    def get_items(self, obj):
        items = obj.items.all()
        return UserOrderItemSerializer(items, many=True, context=self.context).data

    def get_subtotal(self, obj):
        return float(obj.items_subtotal())

    def get_final_total(self, obj):
        return float(obj.final_price())

    def get_coupon_code(self, obj):
        coupon = getattr(obj, 'coupon', None)
        if coupon:
            return coupon.coupon
        return None

    def get_items_count(self, obj):
        return obj.items.count()


# ============== Device Management Serializers ==============

class UserDeviceSerializer(serializers.ModelSerializer):
    """Serializer for viewing device information"""
    class Meta:
        model = UserDevice
        fields = [
            'id', 'device_id', 'device_name', 'ip_address', 'user_agent',
            'logged_in_at', 'last_used_at', 'is_active'
        ]
        read_only_fields = ['logged_in_at', 'last_used_at']


class StudentDeviceListSerializer(serializers.ModelSerializer):
    """Serializer for listing student with their devices"""
    devices = UserDeviceSerializer(many=True, read_only=True)
    active_devices_count = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'name', 'max_allowed_devices',
            'active_devices_count', 'devices'
        ]
    
    def get_active_devices_count(self, obj):
        return obj.devices.filter(is_active=True).count()


class UpdateMaxDevicesSerializer(serializers.Serializer):
    """Serializer for updating max allowed devices for a student"""
    max_allowed_devices = serializers.IntegerField(min_value=1, max_value=10)


class RemoveDeviceSerializer(serializers.Serializer):
    """Serializer for removing a specific device"""
    device_id = serializers.IntegerField()