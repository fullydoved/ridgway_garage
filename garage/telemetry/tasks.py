"""
Celery tasks for processing telemetry data.
"""

from celery import shared_task
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def parse_ibt_file(self, session_id):
    """
    Parse an IBT telemetry file and extract session, lap, and telemetry data.

    This task runs in the background via Celery to avoid blocking the web server
    while processing large IBT files (which can be 100MB+).

    Args:
        session_id: Primary key of the Session object to process
    """
    from .models import Session, Lap, TelemetryData, Track, Car
    import irsdk

    try:
        # Get the session
        session = Session.objects.get(id=session_id)

        # Update status
        session.processing_status = 'processing'
        session.processing_started_at = timezone.now()
        session.save()

        logger.info(f"Starting IBT file processing for session {session_id}")

        # Open the IBT file
        ibt = irsdk.IBT()
        ibt.open(session.ibt_file.path)

        # Extract session info from the YAML section in the IBT file
        # The session info is stored in the header as YAML data
        import yaml
        try:
            from yaml.cyaml import CSafeLoader as YamlSafeLoader
        except ImportError:
            from yaml import SafeLoader as YamlSafeLoader

        YAML_CODE_PAGE = 'cp1252'
        header = ibt._header
        session_info_offset = header.session_info_offset
        session_info_len = header.session_info_len

        # Extract and parse YAML session info
        session_info_yaml = ibt._shared_mem[session_info_offset:session_info_offset + session_info_len]
        session_info_yaml = session_info_yaml.rstrip(b'\x00').decode(YAML_CODE_PAGE)
        session_info = yaml.load(session_info_yaml, Loader=YamlSafeLoader)

        if not session_info:
            raise ValueError("Could not read session info from IBT file")

        # Auto-detect track if not specified
        if not session.track and 'WeekendInfo' in session_info:
            track_name = session_info['WeekendInfo'].get('TrackDisplayName', '').strip()
            track_config = session_info['WeekendInfo'].get('TrackConfigName', '').strip()

            if track_name:
                track, created = Track.objects.get_or_create(
                    name=track_name,
                    configuration=track_config if track_config else '',
                    defaults={
                        'length_km': session_info['WeekendInfo'].get('TrackLength', '').replace(' km', '') or None
                    }
                )
                session.track = track
                logger.info(f"Auto-detected track: {track_name} {track_config}")

        # Auto-detect car if not specified
        if not session.car and 'DriverInfo' in session_info:
            drivers = session_info['DriverInfo'].get('Drivers', [])
            if drivers:
                # Get the user's car (index 0 is typically the player)
                car_name = drivers[0].get('CarScreenName', '').strip()
                if car_name:
                    car_class = drivers[0].get('CarClassShortName') or ''
                    car, created = Car.objects.get_or_create(
                        name=car_name,
                        defaults={
                            'car_class': car_class
                        }
                    )
                    session.car = car
                    logger.info(f"Auto-detected car: {car_name}")

        # Extract session type
        if 'SessionInfo' in session_info and 'Sessions' in session_info['SessionInfo']:
            sessions = session_info['SessionInfo']['Sessions']
            # Find the session that has telemetry data (usually the last one)
            for sess in sessions:
                sess_type = sess.get('SessionType', '').lower()
                if 'race' in sess_type:
                    session.session_type = 'race'
                    break
                elif 'qualify' in sess_type or 'qual' in sess_type:
                    session.session_type = 'qualifying'
                    break
                elif 'practice' in sess_type:
                    session.session_type = 'practice'
                    break
                elif 'time' in sess_type and 'trial' in sess_type:
                    session.session_type = 'time_trial'
                    break

        # Extract environmental conditions
        if 'WeekendInfo' in session_info:
            weekend_info = session_info['WeekendInfo']
            session.air_temp = weekend_info.get('TrackAirTemp', '').replace(' C', '') or None
            session.track_temp = weekend_info.get('TrackSurfaceTemp', '').replace(' C', '') or None
            session.weather_type = weekend_info.get('TrackWeatherType', '')

        session.save()

        # Get telemetry data
        # Common telemetry channels we want to extract
        channels = [
            'Lap', 'LapDist', 'LapDistPct', 'SessionTime', 'Speed',
            'Throttle', 'Brake', 'Clutch', 'Gear', 'RPM', 'SteeringWheelAngle',
            'Lat', 'Lon', 'Alt',  # GPS data
            # Tire surface temps (these change dynamically during the lap)
            'LFtempL', 'LFtempM', 'LFtempR',  # Left Front tire surface temps
            'RFtempL', 'RFtempM', 'RFtempR',  # Right Front tire surface temps
            'LRtempL', 'LRtempM', 'LRtempR',  # Left Rear tire surface temps
            'RRtempL', 'RRtempM', 'RRtempR',  # Right Rear tire surface temps
            # Tire carcass temps (for reference - change more slowly)
            'LFtempCL', 'LFtempCM', 'LFtempCR',  # Left Front tire carcass temps
            'RFtempCL', 'RFtempCM', 'RFtempCR',  # Right Front tire carcass temps
            'LRtempCL', 'LRtempCM', 'LRtempCR',  # Left Rear tire carcass temps
            'RRtempCL', 'RRtempCM', 'RRtempCR',  # Right Rear tire carcass temps
            'LFcoldPressure', 'RFcoldPressure', 'LRcoldPressure', 'RRcoldPressure',
            'FuelLevel', 'FuelLevelPct',
        ]

        # Extract data for each channel using get_all(key)
        # get_all() returns a list of all values for the channel across all telemetry samples
        telemetry_data = {}
        for channel in channels:
            try:
                data = ibt.get_all(channel)
                if data is not None:
                    # Data is already a list, no need to convert
                    telemetry_data[channel] = data
            except (KeyError, AttributeError, Exception) as e:
                # Channel not available in this telemetry file
                logger.debug(f"Channel {channel} not available: {e}")
                pass

        # Process laps using the 'Lap' channel for segmentation
        if telemetry_data and 'Lap' in telemetry_data:
            lap_numbers = telemetry_data['Lap']  # Array of lap numbers for each sample

            # Find unique lap numbers and their boundaries
            import numpy as np
            lap_array = np.array(lap_numbers)
            unique_laps = np.unique(lap_array)

            logger.info(f"Found {len(unique_laps)} laps in session")

            # Process each lap
            for lap_number in unique_laps:
                # Skip lap 0 (outlap/warmup)
                if lap_number == 0:
                    continue

                # Find indices for this lap
                lap_indices = np.where(lap_array == lap_number)[0]
                if len(lap_indices) == 0:
                    continue

                start_idx = lap_indices[0]
                end_idx = lap_indices[-1] + 1  # +1 for inclusive slicing

                # Extract telemetry for this lap only
                lap_telemetry = {}
                for channel, data in telemetry_data.items():
                    if isinstance(data, list) and len(data) > end_idx:
                        lap_telemetry[channel] = data[start_idx:end_idx]

                # Calculate lap time from SessionTime difference
                if 'SessionTime' in lap_telemetry and len(lap_telemetry['SessionTime']) > 1:
                    lap_time = lap_telemetry['SessionTime'][-1] - lap_telemetry['SessionTime'][0]
                else:
                    lap_time = 0.0

                # Calculate statistics
                # Convert speed from m/s to km/h (multiply by 3.6)
                if 'Speed' in lap_telemetry and lap_telemetry['Speed']:
                    speeds = lap_telemetry['Speed']
                    max_speed = max(speeds) * 3.6 if speeds else 0
                    avg_speed = (sum(speeds) / len(speeds)) * 3.6 if speeds else 0
                else:
                    max_speed = 0
                    avg_speed = 0

                # Create lap object
                lap = Lap.objects.create(
                    session=session,
                    lap_number=int(lap_number),
                    lap_time=round(lap_time, 4),
                    is_valid=True  # TODO: Check track limits/off-track flags
                )

                # Create telemetry data for this lap
                TelemetryData.objects.create(
                    lap=lap,
                    data=lap_telemetry,
                    sample_count=len(lap_indices),
                    max_speed=round(max_speed, 2),
                    avg_speed=round(avg_speed, 2)
                )

                logger.info(f"Created lap {lap_number}: {lap_time:.3f}s, {len(lap_indices)} samples")

            # Mark the fastest lap as personal best (exclude lap 0 and laps with 0 time)
            fastest_lap = session.laps.exclude(lap_number=0).filter(lap_time__gt=0).order_by('lap_time').first()
            if fastest_lap:
                fastest_lap.is_personal_best = True
                fastest_lap.save()
                logger.info(f"Fastest lap: #{fastest_lap.lap_number} ({fastest_lap.lap_time}s)")

        elif telemetry_data:
            # Fallback: Create single lap if Lap channel not available
            logger.warning("Lap channel not found, creating single lap with all data")
            lap = Lap.objects.create(
                session=session,
                lap_number=1,
                lap_time=0.0,
                is_valid=True
            )

            # Convert speed from m/s to km/h (multiply by 3.6)
            if 'Speed' in telemetry_data and telemetry_data['Speed']:
                speeds = telemetry_data['Speed']
                max_speed = max(speeds) * 3.6 if speeds else 0
                avg_speed = (sum(speeds) / len(speeds)) * 3.6 if speeds else 0
            else:
                max_speed = 0
                avg_speed = 0

            TelemetryData.objects.create(
                lap=lap,
                data=telemetry_data,
                sample_count=len(telemetry_data.get('SessionTime', [])),
                max_speed=max_speed,
                avg_speed=avg_speed
            )

        # Close the IBT file
        ibt.close()

        # Mark as completed
        session.processing_status = 'completed'
        session.processing_completed_at = timezone.now()
        session.save()

        logger.info(f"Successfully processed session {session_id}")

        # TODO: Send WebSocket notification to user

        return {
            'status': 'completed',
            'session_id': session_id,
            'laps_created': session.laps.count()
        }

    except ObjectDoesNotExist:
        logger.error(f"Session {session_id} does not exist")
        raise

    except Exception as e:
        logger.error(f"Error processing session {session_id}: {str(e)}", exc_info=True)

        # Update session with error
        try:
            session = Session.objects.get(id=session_id)
            session.processing_status = 'failed'
            session.processing_error = str(e)[:500]  # Limit error message length
            session.processing_completed_at = timezone.now()
            session.save()
        except:
            pass

        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
