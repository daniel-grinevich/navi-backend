from rest_framework.permissions import SAFE_METHODS
from rest_framework.permissions import BasePermission

from navi_backend.devices.models import RaspberryPi


class ActionBasedPermission(BasePermission):
    action_perm_map = {
        "list": "view",
        "retrieve": "view",
        "create": "add",
        "update": "change",
        "partial_update": "change",
        "destroy": "delete",
    }

    def has_permission(self, request, view):
        action = getattr(view, "action", None)
        action_permissions = getattr(view, "action_permissions", {})
        action_permissions = getattr(
            view, "action_permissions", action_permissions.get("default", [])
        )

        if request.user and request.user.is_staff:
            return True

        permissions = action_permissions.get(
            action,
            action_permissions.get("default", []),
        )

        if not permissions:
            return False

        return all(p().has_permission(request, view) for p in permissions)


class IsOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        user_field = getattr(view, "user_field", "user")
        return getattr(obj, user_field, None) == request.user


class ReadOnly(BasePermission):
    def has_permission(self, request, _view):
        return request.method in SAFE_METHODS


class IsMachineAuthenticated(BasePermission):
    def has_permission(self, request, view):
        token = request.headers.get("X-Device-Token")
        if not token:
            return False
        rpi = RaspberryPi.objects.filter(device_token=token, is_connected=True).first()
        if rpi:
            request.raspberry_pi = rpi
        return rpi is not None
