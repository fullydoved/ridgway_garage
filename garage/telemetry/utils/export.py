"""
Lap export and import utilities.

Provides standardized functions for exporting laps with telemetry data
and importing them back into the system.
"""

import gzip
import json
import logging
from datetime import datetime
from decimal import Decimal

from django.utils.dateparse import parse_datetime
from django.utils import timezone

logger = logging.getLogger(__name__)


def build_lap_export_data(lap, telemetry):
    """
    Build standardized export data structure for a lap with telemetry.

    Args:
        lap: Lap model instance
        telemetry: TelemetryData model instance

    Returns:
        dict: Export data structure with lap, session, driver, and telemetry data
    """
    export_data = {
        'format_version': '1.0',
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'lap': {
            'lap_number': lap.lap_number,
            'lap_time': float(lap.lap_time),
            'sector1_time': float(lap.sector1_time) if lap.sector1_time else None,
            'sector2_time': float(lap.sector2_time) if lap.sector2_time else None,
            'sector3_time': float(lap.sector3_time) if lap.sector3_time else None,
            'is_valid': lap.is_valid,
        },
        'session': {
            'track_name': lap.session.track.name if lap.session.track else 'Unknown Track',
            'track_config': lap.session.track.configuration if lap.session.track else '',
            'car_name': lap.session.car.name if lap.session.car else 'Unknown Car',
            'session_type': lap.session.session_type,
            'session_date': lap.session.session_date.isoformat(),
            'air_temp': float(lap.session.air_temp) if lap.session.air_temp else None,
            'track_temp': float(lap.session.track_temp) if lap.session.track_temp else None,
            'weather_type': lap.session.weather_type or '',
        },
        'driver': {
            'display_name': lap.session.driver_name or lap.session.driver.username,
        },
        'telemetry': {
            'sample_count': telemetry.sample_count,
            'max_speed': float(telemetry.max_speed) if telemetry.max_speed else None,
            'avg_speed': float(telemetry.avg_speed) if telemetry.avg_speed else None,
            'data': telemetry.data,
        }
    }

    return export_data


def compress_lap_export_data(export_data):
    """
    Convert export data to JSON and compress with gzip.

    Args:
        export_data: Dictionary containing lap export data

    Returns:
        bytes: Gzip-compressed JSON data
    """
    json_data = json.dumps(export_data, indent=2)
    compressed_data = gzip.compress(json_data.encode('utf-8'))

    return compressed_data


def import_lap_from_data(data, user):
    """
    Import a lap from parsed export data structure.

    Creates Session, Lap, and TelemetryData objects from the standardized
    export format. Used by both file upload and protocol import.

    Args:
        data: Dictionary containing lap export data (format_version 1.0)
        user: Django User who is importing the lap

    Returns:
        Lap: The created Lap object

    Raises:
        ValueError: If data format is invalid or missing required fields
    """
    # Import models here to avoid circular imports
    from ..models import Session, Lap, TelemetryData, Track, Car

    # Validate format version
    if data.get('format_version') != '1.0':
        raise ValueError(f"Unsupported format version: {data.get('format_version')}")

    # Validate required fields
    required_fields = ['lap', 'session', 'driver', 'telemetry']
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Invalid data format: missing '{field}' field")

    # Get or create Track
    track_name = data['session'].get('track_name', 'Unknown Track')
    track_config = data['session'].get('track_config', '')
    track, _ = Track.objects.get_or_create(
        name=track_name,
        configuration=track_config,
        defaults={'name': track_name, 'configuration': track_config, 'background_image_url': ''}
    )

    # Get or create Car
    car_name = data['session'].get('car_name', 'Unknown Car')
    car, _ = Car.objects.get_or_create(
        name=car_name,
        defaults={'name': car_name, 'image_url': ''}
    )

    # Parse session date
    try:
        session_date = parse_datetime(data['session']['session_date'])
        if not session_date:
            session_date = timezone.now()
    except (KeyError, TypeError, ValueError) as e:
        logger.debug("Could not parse session date, using current time: %s", e)
        session_date = timezone.now()

    # Create Session
    session = Session.objects.create(
        driver=user,
        team=user.driver_profile.default_team if hasattr(user, 'driver_profile') else None,
        track=track,
        car=car,
        session_type='imported',
        session_date=session_date,
        processing_status='completed',
        air_temp=Decimal(str(data['session']['air_temp'])) if data['session'].get('air_temp') is not None else None,
        track_temp=Decimal(str(data['session']['track_temp'])) if data['session'].get('track_temp') is not None else None,
        weather_type=data['session'].get('weather_type', ''),
        is_public=False,
    )

    # Create Lap
    lap_data = data['lap']
    lap = Lap.objects.create(
        session=session,
        lap_number=lap_data.get('lap_number', 1),
        lap_time=Decimal(str(lap_data['lap_time'])),
        sector1_time=Decimal(str(lap_data['sector1_time'])) if lap_data.get('sector1_time') is not None else None,
        sector2_time=Decimal(str(lap_data['sector2_time'])) if lap_data.get('sector2_time') is not None else None,
        sector3_time=Decimal(str(lap_data['sector3_time'])) if lap_data.get('sector3_time') is not None else None,
        is_valid=lap_data.get('is_valid', True),
    )

    # Create TelemetryData
    telemetry_data = data['telemetry']
    TelemetryData.objects.create(
        lap=lap,
        data=telemetry_data['data'],
        sample_count=telemetry_data.get('sample_count', len(telemetry_data['data'].get('Distance', []))),
        max_speed=Decimal(str(telemetry_data['max_speed'])) if telemetry_data.get('max_speed') is not None else None,
        avg_speed=Decimal(str(telemetry_data['avg_speed'])) if telemetry_data.get('avg_speed') is not None else None,
    )

    return lap
