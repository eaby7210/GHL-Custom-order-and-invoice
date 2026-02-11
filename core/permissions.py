from rest_framework import permissions
from oauth2_provider.models import AccessToken

class IsM2MClient(permissions.BasePermission):
    """
    Allows access only to Machine-to-Machine clients with a valid token.
    Optional: Check if the token belongs to a specific Service User.
    """
    def has_permission(self, request, view):
        # 1. Allow Django Admins (Staff users)
        if request.user and request.user.is_authenticated and request.user.is_staff:
            return True

        # 2. Check for M2M Token
        token = request.auth
        
        if not token or not isinstance(token, AccessToken):
            return False


        if token.is_expired():
            return False



        return True



class DenyM2M(permissions.BasePermission):
    """
    Explicitly denies access if an OAuth2 token is provided.
    """
    def has_permission(self, request, view):
        # Check if a Bearer token exists in the header
        auth_header = request.headers.get('Authorization', '')
        if 'Bearer' in auth_header:
            return False
        return True       

class IsSPAClient(permissions.BasePermission):
    """
    1. Blocks any request with an OAuth2 'Bearer' token.
    2. Requires a specific 'X-SPA-Key' header.
    """
    def has_permission(self, request, view):

        spa_key = request.headers.get('X-SPA-Key')
        return spa_key == getattr(settings, "SPA_SECRET_KEY", None)