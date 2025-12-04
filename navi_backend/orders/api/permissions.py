from rest_framework.permissions import BasePermission

class IsOwnerOrAdmin(BasePermission):
    """
    Custom permission to only allow owners of an object to access or modify it.
    Admin users have unrestricted access.
    """

    def has_object_permission(self, request, view, obj):
        # Allow admin users to access all orders
        if request.user.is_staff:
            return True
        # Allow access to the owner of the order
        if view.action in ["update", "partial_update"] and (obj.status != "O"):
            return False
        return obj.user == request.user

    def has_permission(self, request, view):
        # Allow authenticated users to create orders or access their own orders
        if view.action in ["create", "list"]:
            return request.user.is_authenticated
        return True
