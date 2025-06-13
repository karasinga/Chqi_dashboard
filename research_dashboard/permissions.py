from rest_framework import permissions

class HasRole(permissions.BasePermission):
    """
    Check if the user has any of the required roles.
    """
    def __init__(self, allowed_roles):
        self.allowed_roles = allowed_roles
        
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
            
        # Get user's roles from their profile
        user_roles = set(role.name for role in request.user.userprofile.roles.all())
        
        # Check if user has any of the allowed roles
        return any(role in self.allowed_roles for role in user_roles)
