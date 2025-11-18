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

# Custom origin validator that allows all origins (for machine-to-machine connections)
class AllowAllOriginsValidator(OriginValidator):
    """Allow connections from any origin - used for .NET client WebSocket connections"""
    def __init__(self, application):
        # Pass empty list for allowed_origins since we override valid_origin anyway
        super().__init__(application, allowed_origins=[])

    def valid_origin(self, parsed_origin):
        return True

# WebSocket URL patterns
websocket_urlpatterns = [
    # Unauthenticated route for .NET client (machine-to-machine, no auth required)
    re_path(r'ws/telemetry/live/$', AllowAllOriginsValidator(consumers.LiveTelemetryConsumer.as_asgi())),

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
