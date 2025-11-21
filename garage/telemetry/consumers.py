"""
WebSocket consumers for real-time telemetry processing updates and live streaming.
"""

import json
import logging
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.core.cache import cache

from .services.live_telemetry import LiveTelemetrySession, get_session_metadata_from_iracing
from .models import Session

logger = logging.getLogger(__name__)


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




class LiveTelemetryConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for receiving live telemetry from iRacing client (.NET).

    Handles incoming telemetry at 60Hz, processes lap detection,
    saves to database, and broadcasts to web viewers.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        self.live_session = None
        self.driver = None
        self.client_id = None

    async def connect(self):
        """Handle WebSocket connection from .NET client."""
        # For now, accept the connection
        # Authentication should be added here (token-based auth)
        await self.accept()

        logger.info("Live telemetry client connected")

        # Send acknowledgment
        await self.send(text_data=json.dumps({
            'type': 'connected',
            'message': 'Ready to receive telemetry data'
        }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Remove from connected clients list
        if self.client_id:
            await self._remove_connected_client()

        # Finish the session if one was created
        if self.live_session:
            await self._finish_session()

        logger.info(f"Live telemetry client disconnected: {close_code}")

    async def receive(self, text_data):
        """
        Receive message from .NET client.

        Expected message types:
        1. Client connected (sent immediately on connection):
           {
               'type': 'client_connected',
               'api_token': 'abc123...'
           }

        2. Session initialization:
           {
               'type': 'session_init',
               'session_info': {...metadata...}
           }

        3. Telemetry data:
           {
               'type': 'telemetry',
               'data': {...telemetry sample...}
           }
        """
        try:
            message = json.loads(text_data)
            message_type = message.get('type')

            if message_type == 'client_connected':
                await self._handle_client_connected(message)

            elif message_type == 'session_init':
                await self._handle_session_init(message)

            elif message_type == 'telemetry':
                await self._handle_telemetry(message)

            else:
                logger.warning(f"Unknown message type: {message_type}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def _handle_client_connected(self, message):
        """Handle initial client connection before iRacing starts."""
        api_token = message.get('api_token')

        if not api_token:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'API token is required'
            }))
            await self.close()
            return

        # Authenticate user by token
        self.driver = await self._get_driver_by_token(api_token)

        if not self.driver:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid API token'
            }))
            await self.close()
            return

        # Track this connected client in Redis as "waiting"
        self.client_id = f"driver_{self.driver.id}"
        await self._add_connected_client(self.driver.id, self.driver.username)

        logger.info(f"Client connected: {self.driver.username} (waiting for iRacing)")

        # Send success message
        await self.send(text_data=json.dumps({
            'type': 'authenticated',
            'message': f'Authenticated as {self.driver.username}'
        }))

    async def _handle_session_init(self, message):
        """Handle session initialization from client."""
        session_info_raw = message.get('session_info', {})

        # Ensure client is authenticated
        if not self.driver:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Not authenticated. Send client_connected message first.'
            }))
            return

        # Extract session metadata
        session_info = get_session_metadata_from_iracing(session_info_raw)

        # Create live session
        self.live_session = await self._create_live_session(
            self.driver,
            session_info
        )

        # Notify client
        await self.send(text_data=json.dumps({
            'type': 'session_created',
            'session_id': self.live_session.session.id,
            'message': f'Session created for {session_info["track_name"]}'
        }))

        logger.info(f"Session {self.live_session.session.id} initialized for driver {self.driver.username}")

    async def _handle_telemetry(self, message):
        """Handle incoming telemetry data."""
        if not self.live_session:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'No active session. Send session_init first.'
            }))
            return

        telemetry_data = message.get('data', {})

        # Update client status to "streaming" in cache
        if self.client_id:
            await self._update_client_status('streaming')

        # Process telemetry
        result = await self._process_telemetry(telemetry_data)

        # Broadcast to web viewers
        await self.channel_layer.group_send(
            f'live_session_{self.live_session.session.id}',
            {
                'type': 'telemetry_update',
                'session_id': self.live_session.session.id,
                'telemetry': telemetry_data,
                'events': result.get('events', [])
            }
        )

        # Send events back to client if any (lap completed, etc.)
        if result.get('events'):
            await self.send(text_data=json.dumps({
                'type': 'events',
                'events': result['events']
            }))

    @database_sync_to_async
    def _get_driver_by_token(self, api_token):
        """Get driver from database by API token."""
        from .models import Driver
        try:
            driver_profile = Driver.objects.select_related('user').get(api_token=api_token)
            return driver_profile.user
        except Driver.DoesNotExist:
            return None

    @database_sync_to_async
    def _create_live_session(self, driver, session_info):
        """Create live telemetry session."""
        return LiveTelemetrySession.create_or_get_session(
            driver=driver,
            session_info=session_info
        )

    @database_sync_to_async
    def _process_telemetry(self, telemetry_data):
        """Process telemetry data."""
        return self.live_session.process_telemetry_update(telemetry_data)

    @database_sync_to_async
    def _finish_session(self):
        """Finish the live session."""
        self.live_session.finish_session()

    async def _add_connected_client(self, driver_id, driver_name):
        """Add connected client to Redis cache."""
        client_data = {
            'driver_id': driver_id,
            'driver_name': driver_name,
            'connected_at': time.time(),
            'status': 'waiting_for_data'
        }
        # Store client info in cache with 5 minute timeout (refreshed on telemetry)
        await database_sync_to_async(cache.set)(
            f'live_client_{self.client_id}',
            client_data,
            timeout=300
        )
        # Also add to a set for easy retrieval
        await database_sync_to_async(self._add_to_client_set)(self.client_id)

    async def _remove_connected_client(self):
        """Remove connected client from Redis cache."""
        await database_sync_to_async(cache.delete)(
            f'live_client_{self.client_id}'
        )
        # Also remove from set
        await database_sync_to_async(self._remove_from_client_set)(self.client_id)

    async def _update_client_status(self, status):
        """Update client status in cache."""
        client_data = await database_sync_to_async(cache.get)(
            f'live_client_{self.client_id}'
        )
        if client_data:
            client_data['status'] = status
            await database_sync_to_async(cache.set)(
                f'live_client_{self.client_id}',
                client_data,
                timeout=300
            )

    def _add_to_client_set(self, client_id):
        """Add client ID to the set of connected clients."""
        # Get current set
        client_set = cache.get('live_clients_set', set())
        client_set.add(client_id)
        cache.set('live_clients_set', client_set, timeout=None)

    def _remove_from_client_set(self, client_id):
        """Remove client ID from the set of connected clients."""
        client_set = cache.get('live_clients_set', set())
        client_set.discard(client_id)
        cache.set('live_clients_set', client_set, timeout=None)


class LiveSessionViewerConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for web clients viewing live telemetry.

    Broadcasts real-time telemetry updates to web dashboard.
    """

    async def connect(self):
        """Handle WebSocket connection from web viewer."""
        # Get session ID from URL route
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.room_group_name = f'live_session_{self.session_id}'

        # Verify session exists and is live
        is_live = await self._is_session_live(self.session_id)

        if not is_live:
            await self.close(code=4004)
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        logger.info(f"Web viewer connected to live session {self.session_id}")

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

        logger.info(f"Web viewer disconnected from session {self.session_id}")

    async def receive(self, text_data):
        """Receive message from web client (not used, but required)."""
        pass

    async def telemetry_update(self, event):
        """
        Receive telemetry update from channel layer and send to web client.

        Event structure:
        {
            'type': 'telemetry_update',
            'session_id': 123,
            'telemetry': {...telemetry data...},
            'events': [...]
        }
        """
        # Send telemetry to web client
        await self.send(text_data=json.dumps({
            'type': 'telemetry',
            'session_id': event['session_id'],
            'data': event['telemetry'],
            'events': event.get('events', [])
        }))

    @database_sync_to_async
    def _is_session_live(self, session_id):
        """Check if session is currently live."""
        try:
            session = Session.objects.get(id=session_id)
            return session.is_live
        except Session.DoesNotExist:
            return False
