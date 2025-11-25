"""
API authentication views and decorators.
"""

from functools import wraps
from django.http import JsonResponse

from ...models import Driver, Session


def api_token_required(view_func):
    """
    Decorator for API views that require token authentication.

    Validates the Authorization header contains a valid API token and
    sets request.user to the authenticated user.

    Usage:
        @api_token_required
        def my_api_view(request):
            # request.user is now the authenticated user
            ...

    Returns 401 JSON response if authentication fails.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check for token in Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        if not auth_header.startswith('Token '):
            return JsonResponse({
                'error': 'Missing or invalid Authorization header'
            }, status=401)

        token_key = auth_header.replace('Token ', '').strip()

        # Validate token format (UUIDs are at least 32 chars)
        if not token_key or len(token_key) < 32:
            return JsonResponse({
                'error': 'Invalid token format'
            }, status=401)

        # Find driver by API token
        try:
            driver_profile = Driver.objects.select_related('user').get(api_token=token_key)
            # Set the authenticated user on the request
            request.user = driver_profile.user
        except Driver.DoesNotExist:
            return JsonResponse({
                'error': 'Invalid API token'
            }, status=401)

        # Call the original view function
        return view_func(request, *args, **kwargs)

    return wrapper


@api_token_required
def api_auth_test(request):
    """
    API endpoint to test authentication.
    Returns basic user info if authenticated with valid API token.

    Requires: Authorization: Token <api_token> header
    """
    # Authentication handled by @api_token_required decorator
    # request.user is the authenticated user
    return JsonResponse({
        'authenticated': True,
        'username': request.user.username,
        'email': request.user.email,
        'sessions_count': Session.objects.filter(driver=request.user).count(),
        'server_url': f"{request.scheme}://{request.get_host()}"
    })
