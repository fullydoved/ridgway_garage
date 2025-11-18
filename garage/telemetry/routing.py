"""
WebSocket URL routing for telemetry app.
"""

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/telemetry/processing/(?P<session_id>\d+)/$', consumers.TelemetryProcessingConsumer.as_asgi()),
    re_path(r'ws/system/update/$', consumers.SystemUpdateConsumer.as_asgi()),
    re_path(r'ws/telemetry/live/$', consumers.LiveTelemetryConsumer.as_asgi()),
    re_path(r'ws/telemetry/watch/(?P<session_id>\d+)/$', consumers.LiveSessionViewerConsumer.as_asgi()),
]
