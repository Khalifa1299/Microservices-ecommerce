from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.utils import timezone
from datetime import timedelta


class AppPermission(models.Model):
    """Fine-grained permission used by the RBAC system.

    Mirrors the Permission enum in the Flutter auth_framework.
    Codenames use snake_case (e.g. 'read_users', 'write_content').
    """
    name = models.CharField(max_length=100, unique=True)
    codename = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['codename']
        verbose_name = 'App Permission'
        verbose_name_plural = 'App Permissions'

    def __str__(self):
        return self.codename


class Role(models.Model):
    """A named role that carries a set of AppPermissions.

    Mirrors the Role model in the Flutter auth_framework.
    """
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(AppPermission, blank=True, related_name='roles')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def permission_codenames(self):
        return list(self.permissions.values_list('codename', flat=True))


class User(AbstractUser):
    """Custom User model with RBAC support and device-aware sessions."""

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    email = models.EmailField(unique=True)
    phone = models.CharField(
        max_length=15,
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
            )
        ],
        blank=True,
        null=True
    )
    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    profile_completion = models.IntegerField(default=0)

    # Simple role label kept for backward-compat API responses.
    role = models.CharField(max_length=50, default='user')

    # Full RBAC roles — drives JWT claims and permission checks.
    roles = models.ManyToManyField(Role, blank=True, related_name='users')

    city = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    gender = models.CharField(
        max_length=10,
        choices=[('male', 'Male'), ('female', 'Female')],
        blank=True, null=True
    )
    nationality = models.CharField(max_length=100, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    account_status = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Active'),
            ('pending', 'Pending'),
            ('banned', 'Banned'),
        ],
        default='active'
    )

    # Override groups and user_permissions to avoid clashes with AbstractUser.
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name='custom_user_set',
        related_query_name='custom_user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name='custom_user_set',
        related_query_name='custom_user',
    )

    def calculate_profile_completion(self):
        fields = [
            self.is_phone_verified,
            self.is_email_verified,
            self.first_name,
            self.last_name,
            self.gender,
            self.date_of_birth,
            self.nationality,
            self.city,
        ]
        filled = sum(1 for f in fields if f)
        return int((filled / len(fields)) * 100)

    def update_profile_completion(self):
        self.profile_completion = self.calculate_profile_completion()
        self.save(update_fields=['profile_completion'])

    def get_all_permissions_codenames(self):
        """Collect every permission codename across all assigned roles."""
        return list(
            AppPermission.objects
            .filter(roles__users=self)
            .values_list('codename', flat=True)
            .distinct()
        )

    def get_role_names(self):
        return list(self.roles.values_list('name', flat=True))

    def __str__(self):
        return self.email


class DeviceSession(models.Model):
    """Records each device that has authenticated as a user.

    Created / updated on login and OTP verification using headers sent
    by the Flutter DeviceInterceptor (X-Device-ID, X-Device-Platform, etc.).
    Used for device-binding validation and audit trails.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='device_sessions')
    device_id = models.CharField(max_length=255, db_index=True)
    device_platform = models.CharField(max_length=50, blank=True)
    device_model = models.CharField(max_length=100, blank=True)
    os_version = models.CharField(max_length=50, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    last_seen = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user', 'device_id')
        ordering = ['-last_seen']

    def __str__(self):
        return f"{self.user.email} | {self.device_platform} | {self.device_id[:12]}…"

    @classmethod
    def record(cls, user, request):
        """Create or refresh the device session from request headers."""
        device_id = request.META.get('HTTP_X_DEVICE_ID', '')
        if not device_id:
            return None

        session, _ = cls.objects.update_or_create(
            user=user,
            device_id=device_id,
            defaults={
                'device_platform': request.META.get('HTTP_X_DEVICE_PLATFORM', ''),
                'device_model': request.META.get('HTTP_X_DEVICE_MODEL', ''),
                'os_version': request.META.get('HTTP_X_OS_VERSION', ''),
                'ip_address': _get_client_ip(request),
                'is_active': True,
            }
        )
        return session


class UserPreferences(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')
    receive_notifications = models.BooleanField(default=True)
    dark_mode = models.BooleanField(default=False)
    language = models.CharField(max_length=10, default='en')


class Address(models.Model):
    ADDRESS_TYPES = [
        ('home', 'Home'),
        ('work', 'Work'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    address_type = models.CharField(max_length=20, choices=ADDRESS_TYPES, default='home')
    address_line1 = models.CharField(max_length=200)
    address_line2 = models.CharField(max_length=200, blank=True, null=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default='Egypt')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_validated = models.BooleanField(default=False)
    validation_score = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['-is_default', '-created_at']
        verbose_name = 'Address'
        verbose_name_plural = 'Addresses'
        indexes = [
            models.Index(fields=['user', 'is_default']),
            models.Index(fields=['city']),
            models.Index(fields=['postal_code']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.address_type} - {self.city}"

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(id=self.id).update(is_default=False)
        super().save(*args, **kwargs)
        if not Address.objects.filter(user=self.user, is_default=True).exists():
            self.is_default = True
            super().save(update_fields=['is_default'])


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True, null=True)
    preferences = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile for {self.user.email}"


class UserActivity(models.Model):
    ACTIVITY_TYPES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('password_change', 'Password Change'),
        ('password_reset', 'Password Reset'),
        ('otp_verification', 'OTP Verification'),
        ('otp_resend', 'OTP Resend'),
        ('profile_update', 'Profile Update'),
        ('order_placed', 'Order Placed'),
        ('review_posted', 'Review Posted'),
        ('address_added', 'Address Added'),
        ('token_refresh', 'Token Refresh'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    device_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'User activities'

    def __str__(self):
        return f"{self.user.email} - {self.activity_type}"


class TemporaryOTP(models.Model):
    """Temporary OTP storage — used for email verification and password reset."""
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def is_expired(self):
        return timezone.now() > self.expires_at

    def is_valid(self):
        return not self.is_used and not self.is_expired()

    @classmethod
    def create_otp(cls, email):
        import random
        import string
        cls.objects.filter(email=email, is_used=False).update(is_used=True)
        otp = ''.join(random.choices(string.digits, k=6))
        return cls.objects.create(
            email=email,
            otp=otp,
            expires_at=timezone.now() + timedelta(minutes=10)
        )

    @classmethod
    def verify_otp(cls, email, otp):
        try:
            record = cls.objects.get(email=email, otp=otp, is_used=False)
            if record.is_expired():
                return False, 'OTP has expired'
            record.is_used = True
            record.save()
            return True, 'OTP verified successfully'
        except cls.DoesNotExist:
            return False, 'Invalid OTP'


# ── Shared helper ─────────────────────────────────────────────────────────────

def _get_client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')
