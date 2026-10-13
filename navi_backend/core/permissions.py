from rest_framework.permissions import SAFE_METHODS
from rest_framework.permissions import BasePermission

from navi_backend.devices.models import RaspberryPi
from navi_backend.devices.services.events import touch_presence


class ActionBasedPermission(BasePermission):
    action_perm_map = {
        "list": "view",
        "retrieve": "view",
        "create": "add",
        "update": "change",
        "partial_update": "change",
        "destroy": "delete",
    }

    def _permissions_for(self, view):
        action = getattr(view, "action", None)
        action_permissions = getattr(view, "action_permissions", {})
        return action_permissions.get(
            action,
            action_permissions.get("default", []),
        )

    def has_permission(self, request, view):
        if request.user and request.user.is_staff:
            return True

        permissions = self._permissions_for(view)

        if not permissions:
            return False

        return all(p().has_permission(request, view) for p in permissions)

    def has_object_permission(self, request, view, obj):
        # DRF calls has_object_permission on the classes in permission_classes
        # (this class), not on the nested action permissions. Delegate down so
        # object-level checks like IsOwner are actually enforced on detail routes.
        if request.user and request.user.is_staff:
            return True

        permissions = self._permissions_for(view)

        if not permissions:
            return False

        return all(p().has_object_permission(request, view, obj) for p in permissions)


class IsOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        user_field = getattr(view, "user_field", "user")
        return getattr(obj, user_field, None) == request.user


class ReadOnly(BasePermission):
    def has_permission(self, request, _view):
        return request.method in SAFE_METHODS


class IsAdminUserOrReadOnly(BasePermission):
    """Anyone may read; only staff may write."""

    def has_permission(self, request, _view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


class IsMachineAuthenticated(BasePermission):
    def has_permission(self, request, view):
        rpi = RaspberryPi.objects.authenticate(request.headers.get("X-Device-Token"))
        if rpi is None:
            return False
        request.raspberry_pi = rpi
        # Presence heartbeat: any authenticated machine request counts as a
        # check-in. Pis may also report their firmware via a header.
        touch_presence(rpi.pk, request.headers.get("X-Firmware-Version"))
        return True
