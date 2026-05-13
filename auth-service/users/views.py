from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings
from django.core.cache import cache
from rest_framework import generics, status, permissions, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenObtainPairView


from .models import User, Address, UserProfile, UserActivity, TemporaryOTP, DeviceSession, _get_client_ip
from .serializers import (
    UserRegistrationSerializer, UserSerializer, AddressSerializer,
    UserActivitySerializer, UserLoginSerializer, UserUpdateSerializer,
    AddressCreateSerializer, PasswordChangeSerializer, CustomTokenObtainPairSerializer
)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _issue_jwt_pair(user):
    """Return a dict with access + refresh tokens for the given user."""
    refresh = RefreshToken.for_user(user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }


def _log_activity(user, activity_type, description, request, device_id=''):
    UserActivity.objects.create(
        user=user,
        activity_type=activity_type,
        description=description,
        ip_address=_get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        device_id=device_id or request.META.get('HTTP_X_DEVICE_ID', ''),
    )


def _send_otp_email(user, otp_code):
    try:
        send_mail(
            subject='Verify Your Email',
            message=(
                f'Your verification code is: {otp_code}\n\n'
                'This code expires in 10 minutes.\n'
                'If you did not request this, please ignore this email.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True
    except Exception:
        return False


# ── Registration & OTP ────────────────────────────────────────────────────────

class UserRegistrationView(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    def create(self, request):
        """POST /api/users/signup/"""
        serializer = UserRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = serializer.save()
            UserProfile.objects.create(user=user)
            user.update_profile_completion()

            otp_record = TemporaryOTP.create_otp(user.email)
            sent = _send_otp_email(user, otp_record.otp)

            _log_activity(user, 'profile_update', 'User registered, OTP sent', request)

        return Response({
            'message': 'Registration successful. Check your email for the verification code.',
            'user_id': user.id,
            'email': user.email,
            'otp_sent': sent,
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def verify_otp(self, request):
        """POST /api/users/verify-otp/"""
        email = request.data.get('email', '').strip()
        otp = request.data.get('otp', '').strip()

        if not email or not otp:
            return Response({'error': 'Email and OTP are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        is_valid, message = TemporaryOTP.verify_otp(email, otp)
        if not is_valid:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

        user.is_verified = True
        user.is_email_verified = True
        user.save(update_fields=['is_verified', 'is_email_verified'])

        # Record device session
        DeviceSession.record(user, request)

        tokens = _issue_jwt_pair(user)
        _log_activity(user, 'otp_verification', 'Email verified successfully', request)

        return Response({
            'message': 'Email verified successfully.',
            'verified': True,
            'user': UserSerializer(user).data,
            **tokens,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def resend_otp(self, request):
        """POST /api/users/resend-otp/"""
        email = request.data.get('email', '').strip()
        if not email:
            return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        otp_record = TemporaryOTP.create_otp(user.email)
        sent = _send_otp_email(user, otp_record.otp)
        _log_activity(user, 'otp_resend', 'OTP resent', request)

        if not sent:
            return Response({'error': 'Failed to send OTP email.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'message': 'New OTP sent to your email.', 'otp_sent': True})


# ── Login ─────────────────────────────────────────────────────────────────────

class UserLoginView(generics.GenericAPIView):
    """POST /api/users/login/"""
    serializer_class = UserLoginSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        if user.account_status == 'banned':
            return Response({'error': 'Your account has been suspended.'}, status=status.HTTP_403_FORBIDDEN)

        # Record device session
        DeviceSession.record(user, request)

        tokens = _issue_jwt_pair(user)
        _log_activity(user, 'login', 'User logged in', request)

        return Response({
            'message': 'Login successful.',
            'user': UserSerializer(user).data,
            **tokens,
        })


# ── Profile ───────────────────────────────────────────────────────────────────

class UserProfileView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/users/profile/"""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        user = self.request.user
        user.update_profile_completion()
        return user

    def retrieve(self, request, *args, **kwargs):
        cache_key = f'profile:{request.user.id}'
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        user = self.get_object()
        data = UserSerializer(user).data
        cache.set(cache_key, data, 600)  # 10 min TTL
        return Response(data)

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            serializer.save()
            cache.delete(f'profile:{user.id}')
            _log_activity(user, 'profile_update', 'Profile updated', request)

        return Response({
            'success': True,
            'message': 'Profile updated successfully.',
            'data': UserSerializer(user).data,
        })


# ── Addresses ─────────────────────────────────────────────────────────────────

class AddressListView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        return AddressCreateSerializer if self.request.method == 'POST' else AddressSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            address = serializer.save()
            _log_activity(request.user, 'address_added', f'Added {address.address_type} address', request)

        return Response({
            'success': True,
            'message': 'Address added successfully.',
            'data': AddressSerializer(address).data,
        }, status=status.HTTP_201_CREATED)


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        return AddressCreateSerializer if self.request.method in ('PUT', 'PATCH') else AddressSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            address = serializer.save()
            _log_activity(request.user, 'profile_update', f'Updated {address.address_type} address', request)

        return Response({'success': True, 'message': 'Address updated.', 'data': AddressSerializer(address).data})

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        with transaction.atomic():
            _log_activity(request.user, 'profile_update', f'Deleted {instance.address_type} address', request)
            instance.delete()
        return Response({'success': True, 'message': 'Address deleted.'}, status=status.HTTP_200_OK)


# ── Activity ──────────────────────────────────────────────────────────────────

class UserActivityListView(generics.ListAPIView):
    serializer_class = UserActivitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return UserActivity.objects.filter(user=self.request.user)


# ── Auth actions ──────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def change_password(request):
    """POST /api/users/change-password/"""
    serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)

    user = request.user
    user.set_password(serializer.validated_data['new_password'])
    user.save()
    cache.delete(f'profile:{user.id}')
    _log_activity(user, 'password_change', 'Password changed', request)

    return Response({'success': True, 'message': 'Password changed successfully.'})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout(request):
    """POST /api/users/logout/ — blacklists the provided refresh token."""
    refresh_token = request.data.get('refresh')
    if refresh_token:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            pass  # Already blacklisted or invalid — treat as success

    # Deactivate device session
    device_id = request.META.get('HTTP_X_DEVICE_ID', '')
    if device_id:
        DeviceSession.objects.filter(user=request.user, device_id=device_id).update(is_active=False)

    _log_activity(request.user, 'logout', 'User logged out', request)
    return Response({'message': 'Logout successful.'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def initiate_password_reset(request):
    """POST /api/users/initiate-password-reset/"""
    email = request.data.get('email', '').strip()
    if not email:
        return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        # Return success anyway to prevent user enumeration
        return Response({'message': 'If that email exists, a reset code has been sent.'})

    otp_record = TemporaryOTP.create_otp(email)
    try:
        send_mail(
            subject='Password Reset Code',
            message=(
                f'Your password reset code is: {otp_record.otp}\n\n'
                'This code expires in 10 minutes.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:
        pass  # Don't expose email-sending failures

    _log_activity(user, 'password_reset', 'Password reset OTP requested', request)
    return Response({'message': 'If that email exists, a reset code has been sent.'})


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def reset_password(request):
    """POST /api/users/reset-password/"""
    email = request.data.get('email', '').strip()
    otp = request.data.get('otp', '').strip()
    new_password = request.data.get('new_password', '')

    if not all([email, otp, new_password]):
        return Response({'error': 'Email, OTP, and new_password are required.'}, status=status.HTTP_400_BAD_REQUEST)

    if len(new_password) < 8:
        return Response({'error': 'Password must be at least 8 characters.'}, status=status.HTTP_400_BAD_REQUEST)

    is_valid, message = TemporaryOTP.verify_otp(email, otp)
    if not is_valid:
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    user.set_password(new_password)
    user.save()
    _log_activity(user, 'password_reset', 'Password reset successfully', request)

    return Response({'message': 'Password reset successfully.'})

class CustomTokenObtainPairView(TokenObtainPairView):
    """JWT login endpoint that embeds RBAC claims in the token payload."""
    serializer_class = CustomTokenObtainPairSerializer
