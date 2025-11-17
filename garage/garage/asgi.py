"""
ASGI config for garage project.

It exposes the ASGI callable as a module-level variable named ``application``.

This configuration supports both HTTP and WebSocket connections using Django Channels.
HTTP requests are routed to Django, WebSocket requests to Channels consumers.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'garage.settings')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# Import routing after Django is initialized to avoid AppRegistryNotReady error
# This import will be available after we create the telemetry app
# from telemetry.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    # Django's ASGI application to handle traditional HTTP requests
    "http": django_asgi_app,

    # WebSocket handler (will be configured after telemetry app is created)
    # "websocket": AllowedHostsOriginValidator(
    #     AuthMiddlewareStack(
    #         URLRouter(
    #             websocket_urlpatterns
    #         )
    #     )
    # ),
})
