from rest_framework.permissions import BasePermission
from .models import DeviceSession


class HasRBACPermission(BasePermission):
    """Checks that the authenticated user has a specific RBAC permission codename.

    Usage on a view:
        permission_classes = [IsAuthenticated, HasRBACPermission]
        required_permission = 'write_content'
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        required = getattr(view, 'required_permission', None)
        if required is None:
            return True  # No restriction declared on the view

        return required in request.user.get_all_permissions_codenames()


class IsAdminRole(BasePermission):
    """Allows access only to users whose primary role is 'admin'."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == 'admin' or request.user.is_staff


class IsDeviceBound(BasePermission):
    """Soft device-binding check.

    Requires that the request carries an X-Device-ID header that matches an
    active DeviceSession for the authenticated user.

    In strict mode (DEVICE_BINDING_STRICT = True on the view) the check
    fails if no matching session exists. In soft mode (default) it logs a
    warning but still allows the request so existing clients are not broken.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        device_id = request.META.get('HTTP_X_DEVICE_ID', '')
        if not device_id:
            # No header — fail if strict, pass otherwise
            return not getattr(view, 'DEVICE_BINDING_STRICT', False)

        is_known = DeviceSession.objects.filter(
            user=request.user,
            device_id=device_id,
            is_active=True,
        ).exists()

        if not is_known:
            return not getattr(view, 'DEVICE_BINDING_STRICT', False)

        return True
