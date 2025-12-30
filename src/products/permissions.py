from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

from products.models import Pill, PillItem

class IsOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Allow users to manage their own ratings
        return obj.user == request.user


class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user
    



class PillItemPermissionMixin:
    """Mixin to ensure pill items belong to the authenticated user"""
    
    def get_queryset(self):
        return PillItem.objects.filter(user=self.request.user)
    
    def check_pill_ownership(self, pill_id):
        """Check if the pill belongs to the authenticated user"""
        try:
            pill = Pill.objects.get(id=pill_id, user=self.request.user)
            return pill
        except Pill.DoesNotExist:
            raise PermissionDenied("You don't have permission to access this pill.")
