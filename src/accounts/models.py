from django.contrib.auth.models import AbstractUser
from django.db import models

# Import security models
from .security_models import SecurityBlock, AuthenticationAttempt

GOVERNMENT_CHOICES = [
    ('1', 'Cairo'),
    ('2', 'Alexandria'),
    ('3', 'Kafr El Sheikh'),
    ('4', 'Dakahleya'),
    ('5', 'Sharkeya'),
    ('6', 'Gharbeya'),
    ('7', 'Monefeya'),
    ('8', 'Qalyubia'),
    ('9', 'Giza'),
    ('10', 'Bani-Sweif'),
    ('11', 'Fayoum'),
    ('12', 'Menya'),
    ('13', 'Assiut'),
    ('14', 'Sohag'),
    ('15', 'Qena'),
    ('16', 'Luxor'),
    ('17', 'Aswan'),
    ('18', 'Red Sea'),
    ('19', 'Behera'),
    ('20', 'Ismailia'),
    ('21', 'Suez'),
    ('22', 'Port-Said'),
    ('23', 'Damietta'),
    ('24', 'Marsa Matrouh'),
    ('25', 'Al-Wadi Al-Gadid'),
    ('26', 'North Sinai'),
    ('27', 'South Sinai'),
]

USER_TYPE_CHOICES = [
        ('student', 'Student'),
        ('parent', 'Parent'),
        ('teacher', 'Teacher'),
        ('store', 'Store'),
        ('admin', 'Admin'),
    ]
    
YEAR_CHOICES = [
        ('first-secondary', 'First Secondary'),
        ('second-secondary', 'Second Secondary'),
        ('third-secondary', 'Third Secondary'),
    ]

DIVISION_CHOICES = [
    ('عام', 'عام'),
    ('علمى', 'علمى'),
    ('أدبي', 'أدبي'),
    ('علمى علوم', 'علمى علوم'),
    ('علمى رياضة', 'علمى رياضة'),

]

class UserProfileImage(models.Model):
    image = models.ImageField(upload_to='profile_images/')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile Image {self.id}"
    
    class Meta:
        ordering = ['-created_at'] 


class User(AbstractUser):
    name = models.CharField(max_length=100)
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_created_at = models.DateTimeField(null=True, blank=True)
    email = models.EmailField(blank=True, null=True, max_length=254)
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES)
    parent_phone = models.CharField(max_length=20, null=True, blank=True, help_text="Only applicable for students")
    year = models.CharField(
        max_length=20,
        choices=YEAR_CHOICES,
        null=True,
        blank=True,
        help_text="Only applicable for students"
    )
    division = models.CharField(
        max_length=20,
        choices=DIVISION_CHOICES,
        null=True,
        blank=True
    )
    government = models.CharField(choices=GOVERNMENT_CHOICES, max_length=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True,null=True, blank=True)
    
    # Multi-device login control for students
    max_allowed_devices = models.PositiveIntegerField(
        default=2,
        help_text="Maximum number of devices allowed for this student (admin can adjust per student)"
    )
    
    # Ban control
    is_banned = models.BooleanField(
        default=False,
        help_text="Whether this user is banned from logging in"
    )
    banned_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this user was banned"
    )
    ban_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Reason for banning this user"
    )

    def __str__(self):
        return self.name if self.name else self.username
    
    def save(self, *args, **kwargs):
        """Auto-set admin type for staff/superusers and validate teacher name"""
        # Automatically set user_type to 'admin' for superusers or staff
        if self.is_superuser or self.is_staff:
            self.user_type = 'admin'
        
        self.validate_teacher_name_unique()
        super().save(*args, **kwargs)
    
    def validate_teacher_name_unique(self):
        """Ensure teacher names are unique among users with user_type='teacher'"""
        from django.core.exceptions import ValidationError
        
        if self.user_type == 'teacher':
            # Build query to check for duplicate teacher names
            query = User.objects.filter(
                user_type='teacher',
                name=self.name
            )
            
            # Exclude current instance if updating
            if self.pk:
                query = query.exclude(pk=self.pk)
            
            # Check if duplicate exists
            if query.exists():
                raise ValidationError({
                    'name': f"A teacher with the name '{self.name}' already exists. Teacher names must be unique."
                })
    
    class Meta:
        ordering = ['-created_at']


class UserDevice(models.Model):
    """
    Tracks registered devices for students to enforce multi-device login limits.
    Each device gets a unique token that must be included in JWT for authentication.
    
    Device identification priority:
    1. device_id (from mobile app) - Most reliable, stays constant
    2. ip_address (fallback) - Used if device_id not provided
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='devices'
    )
    device_token = models.CharField(
        max_length=64,
        unique=True,
        help_text="Unique token identifying this device session"
    )
    device_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Unique device identifier from mobile app (Android ID / iOS identifierForVendor)"
    )
    device_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Auto-detected device type (e.g., 'iPhone', 'Android Device', 'Windows PC')"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the device (used as fallback if device_id not provided)"
    )
    user_agent = models.TextField(
        blank=True,
        null=True,
        help_text="Browser/App User-Agent string"
    )
    device_info = models.JSONField(
        blank=True,
        null=True,
        help_text="Additional device information (legacy field, kept for compatibility)"
    )
    logged_in_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this device was first logged in"
    )
    last_used_at = models.DateTimeField(
        auto_now=True,
        help_text="Last time this device made an API request"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this device is currently active (can be disabled by admin)"
    )
    
    # Ban control
    is_banned = models.BooleanField(
        default=False,
        help_text="Whether this device is banned from logging in"
    )
    banned_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this device was banned"
    )
    ban_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Reason for banning this device"
    )

    class Meta:
        ordering = ['-last_used_at']
        verbose_name = 'User Device'
        verbose_name_plural = 'User Devices'
        indexes = [
            models.Index(fields=['user', 'device_id', 'is_active']),
            models.Index(fields=['user', 'ip_address', 'is_active']),
        ]

    def __str__(self):
        identifier = self.device_id[:20] if self.device_id else self.ip_address or 'No ID'
        return f"{self.user.username} - {self.device_name or 'Unknown'} ({identifier})"


class OTP(models.Model):
    """
    One-Time Password model for phone verification
    Used for: signup verification, password reset, phone verification, etc.
    """
    OTP_PURPOSE_CHOICES = [
        ('signup', 'Signup Verification'),
        ('password_reset', 'Password Reset'),
        ('phone_verification', 'Phone Verification'),
        ('other', 'Other'),
    ]
    
    phone_number = models.CharField(
        max_length=20,
        help_text="Phone number to send OTP to"
    )
    otp_code = models.CharField(
        max_length=6,
        help_text="6-digit OTP code"
    )
    purpose = models.CharField(
        max_length=30,
        choices=OTP_PURPOSE_CHOICES,
        default='signup',
        help_text="Purpose of this OTP"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='otps',
        help_text="Associated user (if any)"
    )
    
    # Tracking fields
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When OTP was generated"
    )
    expires_at = models.DateTimeField(
        help_text="When OTP expires"
    )
    
    # Verification fields
    is_verified = models.BooleanField(
        default=False,
        help_text="Whether OTP was successfully verified"
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When OTP was verified"
    )
    is_used = models.BooleanField(
        default=False,
        help_text="Whether OTP has been used (prevents reuse)"
    )
    
    # Security fields
    verification_attempts = models.PositiveIntegerField(
        default=0,
        help_text="Number of failed verification attempts"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'OTP'
        verbose_name_plural = 'OTPs'
        indexes = [
            models.Index(fields=['phone_number', 'purpose', '-created_at']),
            models.Index(fields=['phone_number', 'is_used', 'is_verified']),
        ]
    
    def __str__(self):
        return f"{self.phone_number} - {self.purpose} - {self.otp_code[:2]}****"
    
    def is_expired(self):
        """Check if OTP is expired"""
        from django.utils import timezone
        return timezone.now() > self.expires_at


class DeletedUserArchive(models.Model):
    """
    Archive for deleted user accounts to maintain audit trail.
    Stores user data and their purchased books before deletion.
    """
    # Original user data
    original_user_id = models.IntegerField(help_text="Original user ID before deletion")
    username = models.CharField(max_length=150, help_text="Phone number used as username")
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES)
    parent_phone = models.CharField(max_length=20, null=True, blank=True)
    year = models.CharField(max_length=20, choices=YEAR_CHOICES, null=True, blank=True)
    division = models.CharField(max_length=20, choices=DIVISION_CHOICES, null=True, blank=True)
    government = models.CharField(choices=GOVERNMENT_CHOICES, max_length=2, null=True, blank=True)
    max_allowed_devices = models.PositiveIntegerField(default=2)
    
    # Ban information if user was banned
    was_banned = models.BooleanField(default=False)
    ban_reason = models.TextField(blank=True, null=True)
    
    # Original timestamps
    original_created_at = models.DateTimeField(null=True, blank=True, help_text="When the user account was originally created")
    
    # Deletion metadata
    deleted_at = models.DateTimeField(auto_now_add=True, help_text="When the user was deleted")
    deleted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deleted_users',
        help_text="Admin who deleted this user"
    )
    deletion_reason = models.TextField(blank=True, null=True, help_text="Reason for deletion")
    
    # Purchased books data (stored as JSON)
    purchased_books_data = models.JSONField(
        default=list,
        help_text="List of purchased books with product details"
    )
    
    # Full user data snapshot (for complete restoration if needed)
    user_data_snapshot = models.JSONField(
        default=dict,
        help_text="Complete snapshot of user data at deletion time"
    )
    
    class Meta:
        ordering = ['-deleted_at']
        verbose_name = 'Deleted User Archive'
        verbose_name_plural = 'Deleted Users Archive'
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['original_user_id']),
            models.Index(fields=['-deleted_at']),
        ]
    
    def __str__(self):
        return f"Deleted: {self.name} ({self.username}) - {self.deleted_at.strftime('%Y-%m-%d')}"
