from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

from .models import User, Address, UserProfile, UserActivity, UserPreferences, Role, AppPermission


# ── RBAC ──────────────────────────────────────────────────────────────────────

class AppPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppPermission
        fields = ['id', 'name', 'codename', 'description']


class RoleSerializer(serializers.ModelSerializer):
    permissions = AppPermissionSerializer(many=True, read_only=True)

    class Meta:
        model = Role
        fields = ['id', 'name', 'description', 'permissions']


# ── JWT ───────────────────────────────────────────────────────────────────────

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Extends the standard JWT pair with RBAC claims embedded in the payload.

    Flutter's JwtDecoder reads these claims directly from the access token,
    so the client always has up-to-date roles and permissions without an
    extra profile request.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Identity claims
        token['email'] = user.email
        token['role'] = user.role  # primary role label

        # RBAC claims — list of role names and aggregated permission codenames
        token['roles'] = user.get_role_names()
        token['permissions'] = user.get_all_permissions_codenames()

        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        # Append user payload to the response body (for the Flutter AuthResponse model)
        data['user'] = UserSerializer(user).data
        return data


# ── Profile / User ────────────────────────────────────────────────────────────

class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            'id', 'address_type', 'address_line1', 'address_line2',
            'city', 'state', 'postal_code', 'country', 'is_default',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['bio', 'preferences', 'created_at', 'updated_at']


class UserActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivity
        fields = ['activity_type', 'description', 'ip_address', 'user_agent', 'device_id', 'created_at']
        read_only_fields = ['ip_address', 'user_agent', 'device_id', 'created_at']


class UserPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        fields = ['receive_notifications', 'dark_mode', 'language']


class UserSerializer(serializers.ModelSerializer):
    addresses = AddressSerializer(many=True, read_only=True)
    profile = UserProfileSerializer(read_only=True)
    roles = RoleSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone',
            'role', 'roles', 'is_verified', 'date_of_birth', 'gender',
            'nationality', 'city', 'country', 'is_phone_verified',
            'is_email_verified', 'profile_completion', 'account_status',
            'is_active', 'date_joined', 'last_login', 'addresses', 'profile',
        ]
        read_only_fields = ['id', 'date_joined', 'last_login', 'is_active']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Flatten into the format the Flutter User.fromJson() expects
        return {
            'id': data['id'],
            'email': data['email'],
            'first_name': data['first_name'],
            'last_name': data['last_name'],
            'phone': data['phone'],
            'role': data['role'],
            'roles': data['roles'],
            'gender': data.get('gender'),
            'date_of_birth': data.get('date_of_birth'),
            'nationality': data.get('nationality'),
            'city': data.get('city'),
            'country': data.get('country'),
            'is_phone_verified': data['is_phone_verified'],
            'is_email_verified': data['is_email_verified'],
            'profile_completion': data['profile_completion'],
            'account_status': data['account_status'],
            'addresses': data.get('addresses', []),
        }


# ── Auth input serializers ────────────────────────────────────────────────────

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, required=False)
    username = serializers.CharField(required=False)

    class Meta:
        model = User
        fields = ['email', 'username', 'first_name', 'last_name', 'phone', 'password', 'password_confirm']

    def validate(self, attrs):
        if 'password_confirm' not in attrs or not attrs['password_confirm']:
            attrs['password_confirm'] = attrs['password']
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password': "Passwords don't match."})
        if 'username' not in attrs or not attrs['username']:
            attrs['username'] = attrs['email']
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        return User.objects.create_user(**validated_data)


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({'email': 'Invalid email or password.'})

        if not user.check_password(password):
            raise serializers.ValidationError({'password': 'Invalid email or password.'})
        if not user.is_active:
            raise serializers.ValidationError({'email': 'User account is disabled.'})

        attrs['user'] = user
        return attrs


class AddressCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            'address_type', 'address_line1', 'address_line2',
            'city', 'state', 'postal_code', 'country', 'is_default',
        ]

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'date_of_birth', 'gender', 'nationality', 'city', 'country']

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        instance.update_profile_completion()
        return instance


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(min_length=8)
    new_password_confirm = serializers.CharField()

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Old password is incorrect.')
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({'new_password': "New passwords don't match."})
        return attrs
