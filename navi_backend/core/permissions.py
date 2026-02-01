from rest_framework.permissions import SAFE_METHODS
from rest_framework.permissions import BasePermission


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
        action_permissions = getattr(view, "action_permissions", None)

        if request.user and request.user.is_staff:
            return True

        if action_permissions and action in action_permissions:
            perms = action_permissions[action]
            return all(p().has_permission(request, view) for p in perms)

        if not request.user or not request.user.is_authenticated:
            return False

        return False


class IsOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        user_field = getattr(view, "user_field", "user")
        return getattr(obj, user_field, None) == request.user


class ReadOnly(BasePermission):
    def has_permission(self, request, _view):
        return request.method in SAFE_METHODS
