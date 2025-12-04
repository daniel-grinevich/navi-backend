from rest_framework.permissions import SAFE_METHODS
from rest_framework.permissions import BasePermission


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS
