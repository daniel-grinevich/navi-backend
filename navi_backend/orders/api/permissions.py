from rest_framework.permissions import BasePermission


class CanUpdateOrder(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        if view.action in ["update", "partial_update"] and (obj.order_status != "O"):
            return False
        return obj.user == request.user

    def has_permission(self, request, view):
        if view.action in ["create", "list"]:
            return request.user.is_authenticated
        return True
