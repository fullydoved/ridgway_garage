"""
WebSocket consumers for real-time telemetry processing updates.
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer


class TelemetryProcessingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time telemetry processing updates.

    Clients connect to this consumer to receive progress updates
    for IBT file parsing and processing.
    """

    async def connect(self):
        """Handle WebSocket connection."""
        # Get session ID from URL route
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.room_group_name = f'telemetry_processing_{self.session_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Receive message from WebSocket (not used, but required)."""
        pass

    async def processing_update(self, event):
        """
        Receive processing update from channel layer and send to WebSocket.

        Event structure:
        {
            'type': 'processing_update',
            'status': 'processing' | 'completed' | 'failed',
            'progress': 0-100,
            'message': 'Status message',
            'current_step': 'Current operation',
        }
        """
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'status': event['status'],
            'progress': event.get('progress', 0),
            'message': event.get('message', ''),
            'current_step': event.get('current_step', ''),
        }))


class SystemUpdateConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time system update progress.

    Clients connect to this consumer to receive progress updates
    during system updates.
    """

    async def connect(self):
        """Handle WebSocket connection."""
        self.room_group_name = 'system_update'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Receive message from WebSocket (not used, but required)."""
        pass

    async def update_progress(self, event):
        """
        Receive update progress from channel layer and send to WebSocket.

        Event structure:
        {
            'type': 'update_progress',
            'update_id': 123,
            'status': 'running' | 'success' | 'failed',
            'progress': 0-100,
            'message': 'Status message',
        }
        """
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'update_id': event.get('update_id'),
            'status': event['status'],
            'progress': event.get('progress', 0),
            'message': event.get('message', ''),
        }))
