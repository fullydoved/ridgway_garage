"""
ASGI config for garage project.

It exposes the ASGI callable as a module-level variable named ``application``.

This configuration supports both HTTP and WebSocket connections using Django Channels.
HTTP requests are routed to Django, WebSocket requests to Channels consumers.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
from django.urls import re_path
from django.conf import settings

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'garage.settings')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# Import consumers after Django is initialized
from telemetry import consumers

# Get allowed WebSocket origins from environment (for .NET client connections)
# Format: "localhost,127.0.0.1,your-domain.com" (comma-separated, no protocol)
from decouple import config
WS_ALLOWED_ORIGINS = config(
    'WS_ALLOWED_ORIGINS',
    default='localhost,127.0.0.1',
    cast=lambda v: [s.strip() for s in v.split(',')]
)

# Custom origin validator for machine-to-machine WebSocket connections
class TokenAuthOriginValidator(OriginValidator):
    """
    Validate WebSocket origins against allowed list.

    Security: While this validates origins, the LiveTelemetryConsumer MUST also
    validate API tokens on each message. Origin validation alone is insufficient
    as origins can be spoofed. This is defense-in-depth.

    Allowed origins are configured via WS_ALLOWED_ORIGINS environment variable.
    """
    def __init__(self, application):
        # Build full origin list including protocols for development/production
        allowed_origins = []
        for host in WS_ALLOWED_ORIGINS:
            allowed_origins.append(f'http://{host}')
            allowed_origins.append(f'https://{host}')
            allowed_origins.append(f'http://{host}:42069')  # Development port
            allowed_origins.append(f'https://{host}:42069')

        super().__init__(application, allowed_origins=allowed_origins)

    def valid_origin(self, parsed_origin):
        # Call parent's validation logic
        return super().valid_origin(parsed_origin)

# WebSocket URL patterns
websocket_urlpatterns = [
    # Token-authenticated route for .NET client (validates API token on each message)
    re_path(r'ws/telemetry/live/$', TokenAuthOriginValidator(consumers.LiveTelemetryConsumer.as_asgi())),

    # Authenticated routes for web browsers (require login)
    re_path(r'ws/telemetry/processing/(?P<session_id>\d+)/$', AuthMiddlewareStack(consumers.TelemetryProcessingConsumer.as_asgi())),
    re_path(r'ws/system/update/$', AuthMiddlewareStack(consumers.SystemUpdateConsumer.as_asgi())),
    re_path(r'ws/telemetry/watch/(?P<session_id>\d+)/$', AuthMiddlewareStack(consumers.LiveSessionViewerConsumer.as_asgi())),
]

application = ProtocolTypeRouter({
    # Django's ASGI application to handle traditional HTTP requests
    "http": django_asgi_app,

    # WebSocket handler for real-time updates
    "websocket": URLRouter(websocket_urlpatterns),
})
