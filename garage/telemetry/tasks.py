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
        if not session.track and 'WeekendInfo' in session_info:
            track_name = (session_info['WeekendInfo'].get('TrackDisplayName') or '').strip()
            track_config = (session_info['WeekendInfo'].get('TrackConfigName') or '').strip()

            if track_name:
                track_length = session_info['WeekendInfo'].get('TrackLength') or ''
                track_length_clean = track_length.replace(' km', '') if track_length else None
                track, created = Track.objects.get_or_create(
                    name=track_name,
                    configuration=track_config if track_config else '',
                    defaults={
                        'length_km': track_length_clean
                    }
                )
                session.track = track
                logger.info(f"Auto-detected track: {track_name} {track_config}")

        # Auto-detect car and driver name if not specified
        if 'DriverInfo' in session_info:
            drivers = session_info['DriverInfo'].get('Drivers', [])
            if drivers:
                # Get the user's info (index 0 is typically the player)
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
            from telemetry.services.discord_notifications import send_pb_notification

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
        except:
            pass

        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


def send_update_progress(update_id, status, progress, message=''):
    """
    Send system update progress via WebSocket to connected clients.

    Args:
        update_id: ID of the SystemUpdate object
        status: 'running', 'success', 'failed', or 'rolled_back'
        progress: Integer 0-100 representing completion percentage
        message: Optional status message
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'system_update',
        {
            'type': 'update_progress',
            'update_id': update_id,
            'status': status,
            'progress': progress,
            'message': message,
        }
    )


@shared_task(bind=True)
def execute_system_update(self, update_id, user_id):
    """
    Execute the system update script and monitor its progress.

    This task runs the update.sh script in the background and monitors
    the update_status.json file for progress updates.

    Args:
        update_id: Primary key of the SystemUpdate object
        user_id: ID of the user who triggered the update
    """
    from .models import SystemUpdate
    from django.contrib.auth.models import User
    import subprocess
    import os
    import json
    import time
    from pathlib import Path

    try:
        # Get the update record
        update = SystemUpdate.objects.get(id=update_id)
        user = User.objects.get(id=user_id)

        # Update status to running
        update.status = 'running'
        update.started_at = timezone.now()
        update.save()

        logger.info(f"Starting system update {update_id} triggered by {user.username}")

        # Send initial progress update
        send_update_progress(update_id, 'running', 0, 'Starting update process...')

        # Path to the update script
        project_dir = Path(__file__).resolve().parent.parent.parent.parent
        update_script = project_dir / 'update.sh'
        status_file = project_dir / 'update_status.json'
        log_file = project_dir / 'update.log'

        if not update_script.exists():
            raise FileNotFoundError(f"Update script not found: {update_script}")

        # Remove old status file if it exists
        if status_file.exists():
            status_file.unlink()

        # Execute the update script in the background
        # The script runs on the host, not inside the container
        # We use subprocess.Popen to run it asynchronously
        process = subprocess.Popen(
            [str(update_script)],
            cwd=str(project_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        logger.info(f"Update script started with PID {process.pid}")

        # Monitor the status file for progress updates
        last_progress = 0
        last_status = 'running'
        timeout_counter = 0
        max_timeout = 600  # 10 minutes maximum

        while True:
            # Check if process is still running
            poll = process.poll()

            # Try to read status file
            if status_file.exists():
                try:
                    with open(status_file, 'r') as f:
                        status_data = json.load(f)

                    current_status = status_data.get('status', 'running')
                    current_progress = status_data.get('progress', 0)
                    current_message = status_data.get('message', '')

                    # Update database if progress changed
                    if current_progress != last_progress or current_status != last_status:
                        update.status = current_status
                        update.progress = current_progress
                        update.status_message = current_message
                        update.save()

                        # Send WebSocket update
                        send_update_progress(
                            update_id,
                            current_status,
                            current_progress,
                            current_message
                        )

                        last_progress = current_progress
                        last_status = current_status

                        logger.info(f"Update progress: {current_progress}% - {current_message}")

                    # Check if update completed
                    if current_status in ['success', 'failed', 'error']:
                        break

                except (json.JSONDecodeError, IOError) as e:
                    logger.debug(f"Could not read status file: {e}")

            # Check if process finished
            if poll is not None:
                # Process finished
                stdout, stderr = process.communicate()

                if poll == 0:
                    # Success
                    logger.info("Update script completed successfully")

                    # Read final version
                    version_file = project_dir / 'VERSION'
                    if version_file.exists():
                        with open(version_file, 'r') as f:
                            new_version = f.read().strip()
                            update.new_version = new_version

                    update.status = 'success'
                    update.progress = 100
                    update.status_message = 'Update completed successfully'
                    update.completed_at = timezone.now()
                    update.log_file = str(log_file)
                    update.save()

                    send_update_progress(
                        update_id,
                        'success',
                        100,
                        'Update completed successfully! Please refresh your browser.'
                    )

                    return {
                        'status': 'success',
                        'update_id': update_id,
                        'new_version': update.new_version
                    }
                else:
                    # Failed
                    error_msg = stderr if stderr else 'Update script failed'
                    logger.error(f"Update script failed with exit code {poll}: {error_msg}")

                    update.status = 'failed'
                    update.status_message = f'Update failed: {error_msg[:200]}'
                    update.completed_at = timezone.now()
                    update.log_file = str(log_file)
                    update.save()

                    send_update_progress(
                        update_id,
                        'failed',
                        0,
                        f'Update failed: {error_msg[:100]}'
                    )

                    raise Exception(f"Update script failed: {error_msg}")

            # Timeout check
            timeout_counter += 1
            if timeout_counter > max_timeout:
                logger.error("Update timed out after 10 minutes")
                process.kill()

                update.status = 'failed'
                update.status_message = 'Update timed out after 10 minutes'
                update.completed_at = timezone.now()
                update.save()

                send_update_progress(update_id, 'failed', 0, 'Update timed out')
                raise Exception("Update timed out")

            # Wait before next check
            time.sleep(1)

    except ObjectDoesNotExist as e:
        logger.error(f"Update record {update_id} or user {user_id} does not exist")
        raise

    except Exception as e:
        logger.error(f"Error executing system update: {str(e)}", exc_info=True)

        # Update database with error
        try:
            update = SystemUpdate.objects.get(id=update_id)
            update.status = 'failed'
            update.status_message = f'Error: {str(e)[:200]}'
            update.completed_at = timezone.now()
            update.save()

            send_update_progress(
                update_id,
                'failed',
                0,
                f'Update failed: {str(e)[:100]}'
            )
        except:
            pass

        raise
