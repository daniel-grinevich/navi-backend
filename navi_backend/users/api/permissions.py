from rest_framework import permissions


class IsSelfOrAdmin(permissions.BasePermission):
    """
    Object-level permission: allow access if the requester is staff or the object
    is the requester.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        return bool(user and (user.is_staff or obj.pk == user.pk))
