"""
Live telemetry processing service.

Handles real-time telemetry data from iRacing, including:
- Session creation and metadata extraction
- Lap detection and creation
- Telemetry data batching and storage
"""

import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List
from datetime import datetime
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.models import User

from ..models import Session, Lap, TelemetryData, Track, Car, Team

logger = logging.getLogger(__name__)


class LiveTelemetrySession:
    """
    Manages a live telemetry streaming session.

    Handles incoming telemetry data, lap detection, and database persistence.
    """

    def __init__(self, session_id: int):
        """Initialize with existing session ID."""
        self.session = Session.objects.get(id=session_id)
        self.current_lap_number = None
        self.current_lap_data = []  # Accumulate telemetry for current lap
        self.last_lap_distance = 0.0
        self.lap_completed = False

    @classmethod
    def create_or_get_session(
        cls,
        driver: User,
        session_info: Dict[str, Any],
        team: Optional[Team] = None
    ) -> 'LiveTelemetrySession':
        """
        Create a new live session or get existing one.

        Args:
            driver: User who is driving
            session_info: Session metadata from iRacing (track, car, etc.)
            team: Optional team to associate with session

        Returns:
            LiveTelemetrySession instance
        """
        # Extract session metadata
        track_name = session_info.get('track_name', '')
        track_config = session_info.get('track_config', '')
        car_name = session_info.get('car_name', '')
        session_type = session_info.get('session_type', 'practice').lower()

        # Get or create Track
        track, _ = Track.objects.get_or_create(
            name=track_name,
            configuration=track_config,
            defaults={
                'length_km': session_info.get('track_length_km'),
                'background_image_url': ''
            }
        )

        # Get or create Car
        car, _ = Car.objects.get_or_create(
            name=car_name,
            defaults={
                'car_class': session_info.get('car_class', ''),
                'image_url': ''
            }
        )

        # Create new live session
        session = Session.objects.create(
            driver=driver,
            team=team or driver.driver_profile.default_team,
            track=track,
            car=car,
            session_type=session_type,
            session_date=timezone.now(),
            driver_name=session_info.get('driver_name', driver.username),
            air_temp=session_info.get('air_temp'),
            track_temp=session_info.get('track_temp'),
            weather_type=session_info.get('weather_type', ''),
            processing_status='completed',  # Live sessions are "processed" as they stream
            is_live=True,
            connection_state='connected'
        )

        logger.info(f"Created live session {session.id} for {driver.username} at {track_name}")

        return cls(session.id)

    def process_telemetry_update(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming telemetry data point.

        Args:
            telemetry: Single telemetry data point from iRacing at 60Hz

        Returns:
            Dict with processing status and any events (lap completed, etc.)
        """
        result = {
            'status': 'ok',
            'events': []
        }

        # Extract lap number
        lap_number = telemetry.get('lap_number', 1)

        # Check if we're starting a new lap
        if self.current_lap_number is None:
            self.current_lap_number = lap_number
            self.current_lap_data = []

        elif lap_number != self.current_lap_number:
            # Lap changed - save the previous lap
            if self.current_lap_data:
                lap = self._save_lap(self.current_lap_number, self.current_lap_data)
                if lap:
                    result['events'].append({
                        'type': 'lap_completed',
                        'lap_number': self.current_lap_number,
                        'lap_time': float(lap.lap_time),
                        'is_valid': lap.is_valid
                    })

            # Start new lap
            self.current_lap_number = lap_number
            self.current_lap_data = []

        # Add current telemetry to accumulator
        self.current_lap_data.append(telemetry)

        # Update session last update time
        self.session.last_telemetry_update = timezone.now()
        self.session.save(update_fields=['last_telemetry_update'])

        return result

    def _save_lap(self, lap_number: int, telemetry_data: List[Dict[str, Any]]) -> Optional[Lap]:
        """
        Save completed lap to database.

        Args:
            lap_number: Lap number
            telemetry_data: List of telemetry data points for this lap

        Returns:
            Created Lap instance or None if failed
        """
        if not telemetry_data:
            logger.warning(f"No telemetry data for lap {lap_number}")
            return None

        try:
            # Calculate lap time from telemetry
            lap_time = self._calculate_lap_time(telemetry_data)

            # Extract sector times if available
            sector1_time = telemetry_data[-1].get('sector1_time')
            sector2_time = telemetry_data[-1].get('sector2_time')
            sector3_time = telemetry_data[-1].get('sector3_time')

            # Check if lap is valid (no off-track, no pitting, etc.)
            is_valid = self._is_lap_valid(telemetry_data)

            with transaction.atomic():
                # Create Lap
                lap = Lap.objects.create(
                    session=self.session,
                    lap_number=lap_number,
                    lap_time=Decimal(str(lap_time)),
                    sector1_time=Decimal(str(sector1_time)) if sector1_time else None,
                    sector2_time=Decimal(str(sector2_time)) if sector2_time else None,
                    sector3_time=Decimal(str(sector3_time)) if sector3_time else None,
                    is_valid=is_valid
                )

                # Convert telemetry data to channel-based format
                telemetry_channels = self._convert_to_channels(telemetry_data)

                # Calculate statistics
                speeds = telemetry_channels.get('Speed', [])
                max_speed = max(speeds) if speeds else None
                avg_speed = sum(speeds) / len(speeds) if speeds else None

                # Create TelemetryData
                TelemetryData.objects.create(
                    lap=lap,
                    data=telemetry_channels,
                    sample_count=len(telemetry_data),
                    max_speed=Decimal(str(max_speed)) if max_speed else None,
                    avg_speed=Decimal(str(avg_speed)) if avg_speed else None
                )

                logger.info(f"Saved lap {lap_number} for session {self.session.id}: {lap_time:.3f}s")

                return lap

        except Exception as e:
            logger.error(f"Failed to save lap {lap_number}: {e}", exc_info=True)
            return None

    def _calculate_lap_time(self, telemetry_data: List[Dict[str, Any]]) -> float:
        """Calculate lap time from telemetry data."""
        if not telemetry_data:
            return 0.0

        # Option 1: Use lap_time from last sample if available
        if 'lap_time' in telemetry_data[-1]:
            return telemetry_data[-1]['lap_time']

        # Option 2: Calculate from session time difference
        if 'session_time' in telemetry_data[0] and 'session_time' in telemetry_data[-1]:
            return telemetry_data[-1]['session_time'] - telemetry_data[0]['session_time']

        # Option 3: Estimate from sample count (60Hz)
        return len(telemetry_data) / 60.0

    def _is_lap_valid(self, telemetry_data: List[Dict[str, Any]]) -> bool:
        """
        Check if lap is valid (no off-track violations).

        iRacing provides PlayerTrackSurface:
        - NotInWorld = -1
        - UndefinedMaterial = 0
        - Asphalt1Material = 1
        - Asphalt2Material = 2
        - ...
        - OffTrackSurface = 3 (off track)
        """
        for sample in telemetry_data:
            track_surface = sample.get('player_track_surface', 1)

            # Check for off-track (typically value 3 or -1)
            if track_surface == 3 or track_surface == -1:
                return False

        return True

    def _convert_to_channels(self, telemetry_data: List[Dict[str, Any]]) -> Dict[str, List]:
        """
        Convert list of telemetry samples to channel-based format.

        Input: [
            {'speed': 100, 'rpm': 5000, 'throttle': 0.8},
            {'speed': 105, 'rpm': 5200, 'throttle': 0.9},
            ...
        ]

        Output: {
            'Speed': [100, 105, ...],
            'RPM': [5000, 5200, ...],
            'Throttle': [0.8, 0.9, ...]
        }
        """
        if not telemetry_data:
            return {}

        # Get all keys from first sample
        channels = {}

        # Map of lowercase keys to proper channel names
        key_mapping = {
            'speed': 'Speed',
            'rpm': 'RPM',
            'throttle': 'Throttle',
            'brake': 'Brake',
            'steering': 'Steering',
            'gear': 'Gear',
            'clutch': 'Clutch',
            'distance': 'LapDist',
            'lap_distance': 'LapDist',
            'session_time': 'SessionTime',
            'lat': 'Lat',
            'lon': 'Lon',
            'latitude': 'Lat',
            'longitude': 'Lon',
            # Tire temps
            'lf_tire_temp': 'LFtempCL',
            'rf_tire_temp': 'RFtempCL',
            'lr_tire_temp': 'LRtempCL',
            'rr_tire_temp': 'RRtempCL',
            # Tire pressure
            'lf_tire_pressure': 'LFpressure',
            'rf_tire_pressure': 'RFpressure',
            'lr_tire_pressure': 'LRpressure',
            'rr_tire_pressure': 'RRpressure',
            # Other
            'fuel_level': 'FuelLevel',
            'fuel_use_per_hour': 'FuelUsePerHour',
        }

        # Initialize channels
        for key in telemetry_data[0].keys():
            channel_name = key_mapping.get(key.lower(), key)
            channels[channel_name] = []

        # Populate channels
        for sample in telemetry_data:
            for key, value in sample.items():
                channel_name = key_mapping.get(key.lower(), key)
                channels[channel_name].append(value)

        return channels

    def finish_session(self):
        """Mark session as finished and save final lap if needed."""
        # Save current lap if in progress
        if self.current_lap_data:
            self._save_lap(self.current_lap_number, self.current_lap_data)
            self.current_lap_data = []

        # Update session status
        self.session.is_live = False
        self.session.connection_state = 'disconnected'
        self.session.save(update_fields=['is_live', 'connection_state'])

        logger.info(f"Finished live session {self.session.id}")


def get_session_metadata_from_iracing(telemetry_sample: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract session metadata from iRacing telemetry sample.

    This should be called with the first telemetry sample or session info
    to extract track, car, and environmental data.
    """
    return {
        'track_name': telemetry_sample.get('track_name', 'Unknown Track'),
        'track_config': telemetry_sample.get('track_config', ''),
        'track_length_km': telemetry_sample.get('track_length_km'),
        'car_name': telemetry_sample.get('car_name', 'Unknown Car'),
        'car_class': telemetry_sample.get('car_class', ''),
        'driver_name': telemetry_sample.get('driver_name', ''),
        'session_type': telemetry_sample.get('session_type', 'practice'),
        'air_temp': telemetry_sample.get('air_temp'),
        'track_temp': telemetry_sample.get('track_temp'),
        'weather_type': telemetry_sample.get('weather_type', 'Clear'),
    }
