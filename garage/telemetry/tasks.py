"""
Celery tasks for processing telemetry data.
"""

from celery import shared_task
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging

logger = logging.getLogger(__name__)


def send_processing_update(session_id, status, progress, message='', current_step=''):
    """
    Send a processing update via WebSocket to connected clients.

    Args:
        session_id: ID of the session being processed
        status: 'processing', 'completed', or 'failed'
        progress: Integer 0-100 representing completion percentage
        message: Optional status message
        current_step: Current operation being performed
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'telemetry_processing_{session_id}',
        {
            'type': 'processing_update',
            'status': status,
            'progress': progress,
            'message': message,
            'current_step': current_step,
        }
    )


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

        # Send initial progress update
        send_processing_update(
            session_id, 'processing', 0,
            'Starting IBT file processing...',
            'Opening file'
        )

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

        send_processing_update(
            session_id, 'processing', 10,
            'Extracted session metadata',
            'Detecting track and car'
        )

        # Auto-detect track if not specified
        if not session.track and 'WeekendInfo' in session_info and session_info['WeekendInfo']:
            track_name = (session_info['WeekendInfo'].get('TrackDisplayName') or '').strip()
            track_config = (session_info['WeekendInfo'].get('TrackConfigName') or '').strip()

            if track_name:
                track_length = session_info['WeekendInfo'].get('TrackLength') or ''
                track_length_clean = track_length.replace(' km', '') if track_length else None
                track, created = Track.objects.get_or_create(
                    name=track_name,
                    configuration=track_config if track_config else '',
                    defaults={
                        'length_km': track_length_clean,
                        'background_image_url': ''
                    }
                )
                session.track = track
                logger.info(f"Auto-detected track: {track_name} {track_config}")

        # Auto-detect car and driver name if not specified
        if 'DriverInfo' in session_info and session_info['DriverInfo']:
            driver_info_section = session_info['DriverInfo']
            drivers = driver_info_section.get('Drivers', [])

            # Extract setup name from DriverInfo section (not from individual driver)
            setup_name = (driver_info_section.get('DriverSetupName') or '').strip()
            if setup_name:
                session.setup_name = setup_name
                logger.info(f"Extracted setup name: {setup_name}")

            # Get the player's car index to identify which driver is the actual player
            # DriverCarIdx tells us which entry in the Drivers array is the player
            player_car_idx = driver_info_section.get('DriverCarIdx')

            if drivers and player_car_idx is not None:
                # Find the player by matching CarIdx with DriverCarIdx
                driver_info = None
                for driver in drivers:
                    if driver.get('CarIdx') == player_car_idx:
                        driver_info = driver
                        break

                # Fallback to first driver if we couldn't find a match
                if driver_info is None:
                    logger.warning(f"Could not find player driver with CarIdx {player_car_idx}, using first driver as fallback")
                    driver_info = drivers[0]

                # Extract driver name
                driver_name = (driver_info.get('UserName') or '').strip()
                if driver_name:
                    session.driver_name = driver_name
                    logger.info(f"Extracted driver name: {driver_name}")

                # Extract car info
                if not session.car:
                    car_name = (driver_info.get('CarScreenName') or '').strip()
                    if car_name:
                        car_class = driver_info.get('CarClassShortName') or ''
                        car, created = Car.objects.get_or_create(
                            name=car_name,
                            defaults={
                                'car_class': car_class,
                                'image_url': ''
                            }
                        )
                        session.car = car
                        logger.info(f"Auto-detected car: {car_name} (CarIdx: {player_car_idx})")

        # Extract session type
        if 'SessionInfo' in session_info and session_info['SessionInfo'] and 'Sessions' in session_info['SessionInfo']:
            sessions = session_info['SessionInfo']['Sessions']
            # Find the session that has telemetry data (usually the last one)
            if sessions:
                for sess in sessions:
                    sess_type = (sess.get('SessionType') or '').lower()
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
        if 'WeekendInfo' in session_info and session_info['WeekendInfo']:
            weekend_info = session_info['WeekendInfo']
            air_temp_str = weekend_info.get('TrackAirTemp') or ''
            session.air_temp = air_temp_str.replace(' C', '') if air_temp_str else None
            track_temp_str = weekend_info.get('TrackSurfaceTemp') or ''
            session.track_temp = track_temp_str.replace(' C', '') if track_temp_str else None
            session.weather_type = weekend_info.get('TrackWeatherType') or ''

        session.save()

        # Get telemetry data
        # Common telemetry channels we want to extract
        channels = [
            'Lap', 'LapDist', 'LapDistPct', 'SessionTime', 'Speed',
            'LapLastLapTime', 'LapCurrentLapTime',  # Official iRacing lap times
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
            # Suspension - Ride Heights (mm)
            'LFrideHeight', 'RFrideHeight', 'LRrideHeight', 'RRrideHeight',
            # Suspension - Shock Deflection (mm)
            'LFshockDefl', 'RFshockDefl', 'LRshockDefl', 'RRshockDefl',
            # Suspension - Shock Velocity (m/s)
            'LFshockVel', 'RFshockVel', 'LRshockVel', 'RRshockVel',
            # Acceleration / G-Forces (m/s²)
            'LatAccel', 'LongAccel', 'VertAccel',
            # Orientation (radians)
            'Roll', 'Pitch', 'Yaw',
            # Rotation Rates (rad/s)
            'RollRate', 'PitchRate', 'YawRate',
            # Lap validation channels
            'PlayerTrackSurface',  # Track surface type (-1=NotInWorld, 0=Undefined, 1-2=Asphalt, 3=OffTrack)
            'OnPitRoad',  # Boolean indicating if on pit road
            'PlayerCarMyIncidentCount',  # Total incident count for player
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
            except KeyError:
                # Channel not in telemetry data
                logger.debug(f"Channel {channel} not in telemetry data")
            except (AttributeError, TypeError) as e:
                # Data structure issue with channel
                logger.warning(f"Error accessing channel {channel}: {type(e).__name__}: {e}")
            except Exception as e:
                # Unexpected error - log with more detail for debugging
                logger.error(f"Unexpected error processing channel {channel}: {type(e).__name__}: {e}", exc_info=True)

        send_processing_update(
            session_id, 'processing', 30,
            f'Extracted {len(telemetry_data)} telemetry channels',
            'Segmenting laps'
        )

        # Process laps using the 'Lap' channel for segmentation
        if telemetry_data and 'Lap' in telemetry_data:
            lap_numbers = telemetry_data['Lap']  # Array of lap numbers for each sample

            # Find unique lap numbers and their boundaries
            import numpy as np
            lap_array = np.array(lap_numbers)
            unique_laps = np.unique(lap_array)

            logger.info(f"Found {len(unique_laps)} laps in session")

            # Process each lap
            total_laps = len(unique_laps)
            for idx, lap_number in enumerate(unique_laps):
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

                # Get official lap time from iRacing's LapLastLapTime
                # This value is set at the moment you cross the start/finish line,
                # so we look at the first sample of the NEXT lap (or end of current lap)
                lap_time = 0.0
                if 'LapLastLapTime' in telemetry_data:
                    lap_last_times = telemetry_data['LapLastLapTime']
                    # Check the sample right after this lap ends (start of next lap)
                    if end_idx < len(lap_last_times):
                        official_time = lap_last_times[end_idx]
                        if official_time and official_time > 0:
                            lap_time = official_time
                            logger.debug(f"Lap {lap_number}: Using official LapLastLapTime = {lap_time:.4f}s")

                # Fallback: Calculate from SessionTime if LapLastLapTime not available
                if lap_time == 0.0:
                    if 'SessionTime' in lap_telemetry and len(lap_telemetry['SessionTime']) > 1:
                        lap_time = lap_telemetry['SessionTime'][-1] - lap_telemetry['SessionTime'][0]
                        logger.debug(f"Lap {lap_number}: Fallback to calculated time = {lap_time:.4f}s")

                # Calculate statistics
                # Convert speed from m/s to km/h (multiply by 3.6)
                if 'Speed' in lap_telemetry and lap_telemetry['Speed']:
                    speeds = lap_telemetry['Speed']
                    max_speed = max(speeds) * 3.6 if speeds else 0
                    avg_speed = (sum(speeds) / len(speeds)) * 3.6 if speeds else 0
                else:
                    max_speed = 0
                    avg_speed = 0

                # Lap validation logic
                is_valid = True
                invalid_reason = None

                # Check 1: Incomplete lap detection
                # Laps < 10s are incomplete (session ended mid-lap)
                if lap_time < 10.0:
                    is_valid = False
                    invalid_reason = f"Incomplete lap (time: {lap_time:.3f}s)"
                    logger.debug(f"Lap {lap_number} invalid: {invalid_reason}")

                # Check 1b: Reset detection via position teleportation
                # When driver resets, their position jumps 100+ meters instantly
                if is_valid and 'Lat' in lap_telemetry and 'Lon' in lap_telemetry:
                    import math
                    lats = lap_telemetry['Lat']
                    lons = lap_telemetry['Lon']

                    # Calculate max position jump between consecutive samples
                    max_jump = 0
                    for i in range(1, min(len(lats), len(lons))):
                        # Haversine formula for distance
                        R = 6371000  # Earth radius in meters
                        lat1, lon1, lat2, lon2 = map(math.radians, [lats[i-1], lons[i-1], lats[i], lons[i]])
                        dlat = lat2 - lat1
                        dlon = lon2 - lon1
                        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
                        c = 2 * math.asin(math.sqrt(a))
                        dist = R * c
                        if dist > max_jump:
                            max_jump = dist

                    # Position jumps > 100m indicate reset/teleport (normal is ~1m)
                    if max_jump > 100:
                        is_valid = False
                        invalid_reason = f"Reset detected (position jump: {max_jump:.1f}m)"
                        logger.debug(f"Lap {lap_number} invalid: {invalid_reason}")

                # Check 2: Reset/Tow detection
                # PlayerTrackSurface = -1 means NotInWorld (driver reset or was towed)
                if is_valid and 'PlayerTrackSurface' in lap_telemetry:
                    track_surfaces = lap_telemetry['PlayerTrackSurface']
                    not_in_world_samples = sum(1 for surface in track_surfaces if surface == -1)
                    if not_in_world_samples > 0:
                        is_valid = False
                        invalid_reason = f"Reset/tow detected ({not_in_world_samples} samples)"
                        logger.debug(f"Lap {lap_number} invalid: {invalid_reason}")

                # Check 3: Incident detection
                # If incident count increased during the lap, mark as invalid
                # iRacing tracks off-track violations via the incident system
                if is_valid and 'PlayerCarMyIncidentCount' in lap_telemetry:
                    incident_counts = lap_telemetry['PlayerCarMyIncidentCount']
                    if len(incident_counts) > 1:
                        incident_start = incident_counts[0]
                        incident_end = incident_counts[-1]
                        if incident_end > incident_start:
                            incidents_this_lap = incident_end - incident_start
                            is_valid = False
                            invalid_reason = f"Incident during lap ({incidents_this_lap}x)"
                            logger.debug(f"Lap {lap_number} invalid: {invalid_reason}")

                # Check 4: Inlap detection (lap ends in pits)
                # If OnPitRoad is True at the end of the lap, it's an inlap
                if is_valid and 'OnPitRoad' in lap_telemetry:
                    on_pit_road = lap_telemetry['OnPitRoad']
                    if len(on_pit_road) > 0 and on_pit_road[-1]:
                        is_valid = False
                        invalid_reason = "Inlap (ended in pits)"
                        logger.debug(f"Lap {lap_number} invalid: {invalid_reason}")

                # Create lap object
                lap = Lap.objects.create(
                    session=session,
                    lap_number=int(lap_number),
                    lap_time=round(lap_time, 4),
                    is_valid=is_valid
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

                # Send progress update for this lap
                progress = 30 + int((idx / total_laps) * 60)  # 30-90% range for lap processing
                send_processing_update(
                    session_id, 'processing', progress,
                    f'Processing lap {int(lap_number)} of {total_laps}',
                    f'Lap {int(lap_number)}: {lap_time:.3f}s'
                )

            send_processing_update(
                session_id, 'processing', 95,
                'Identifying personal best',
                'Analyzing lap times'
            )

            # Check for personal best using proper global PB tracking
            from telemetry.utils.pb_tracker import update_personal_bests
            from telemetry.services.discord_notifications import (
                send_pb_notification,
                check_team_record,
                send_team_record_notification
            )

            is_new_pb, previous_time, improvement = update_personal_bests(session)

            if is_new_pb:
                # Get the PB lap for logging and notification
                pb_lap = session.laps.filter(is_personal_best=True).first()
                if pb_lap:
                    logger.info(
                        f"New PB detected: #{pb_lap.lap_number} ({pb_lap.lap_time}s)"
                        + (f" - improved by {improvement}s" if improvement else " - first PB")
                    )

                    # Send Discord notification to team channel
                    send_pb_notification(
                        session=session,
                        lap=pb_lap,
                        is_improvement=(previous_time is not None),
                        previous_time=previous_time,
                        improvement=improvement
                    )

            # Check for team record (best lap in session for this team/track/car)
            if session.team:
                best_lap = session.laps.filter(is_valid=True, lap_time__gt=0).order_by('lap_time').first()
                if best_lap:
                    is_team_record, prev_record_time, prev_holder = check_team_record(session, best_lap)
                    if is_team_record:
                        logger.info(
                            f"New team record detected: #{best_lap.lap_number} ({best_lap.lap_time}s) "
                            f"for team {session.team.name}"
                        )
                        send_team_record_notification(
                            session=session,
                            lap=best_lap,
                            previous_time=prev_record_time,
                            previous_holder=prev_holder
                        )

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

        # Send completion notification via WebSocket
        send_processing_update(
            session_id, 'completed', 100,
            f'Processing complete! {session.laps.count()} laps created',
            'Done'
        )

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

        # Send error notification via WebSocket
        send_processing_update(
            session_id, 'failed', 0,
            f'Processing failed: {str(e)[:100]}',
            'Error'
        )

        # Update session with error
        try:
            session = Session.objects.get(id=session_id)
            session.processing_status = 'failed'
            session.processing_error = str(e)[:500]  # Limit error message length
            session.processing_completed_at = timezone.now()
            session.save()
        except Session.DoesNotExist:
            logger.warning("Session %s not found when updating error status", session_id)

        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


