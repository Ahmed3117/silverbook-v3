from django.contrib.auth.models import AbstractUser
from django.db import models

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
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, null=True, blank=True)
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

    def __str__(self):
        return self.name if self.name else self.username
    
    def save(self, *args, **kwargs):
        """Validate unique name for teachers before saving"""
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