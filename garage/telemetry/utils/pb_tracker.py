"""
Personal Best tracking utilities.

This module handles the logic for tracking and updating personal bests
across all sessions for a given driver/track/car combination.
"""
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def update_personal_bests(session):
    """
    Update personal best tracking for a session.

    Compares the fastest lap in this session against all previous laps
    for this driver/track/car combination to determine if a new PB was set.

    Args:
        session: Session object to check for personal bests

    Returns:
        tuple: (is_new_pb, previous_best_time, improvement)
            - is_new_pb (bool): True if a new PB was set
            - previous_best_time (Decimal): Previous PB time, or None if first PB
            - improvement (Decimal): Time improvement in seconds, or None if first PB
    """
    from telemetry.models import Lap

    driver = session.driver
    track = session.track
    car = session.car

    # Can't track PBs without track and car information
    if not track or not car:
        logger.debug(f"Session {session.id} missing track or car information, skipping PB check")
        return False, None, None

    # Get fastest valid lap from this session (exclude lap 0 and invalid laps)
    session_best = session.laps.filter(
        lap_time__gt=0,
        is_valid=True
    ).exclude(
        lap_number=0
    ).order_by('lap_time').first()

    if not session_best:
        logger.debug(f"No valid laps found in session {session.id}")
        return False, None, None

    # Get all-time best lap for this driver/track/car combo across ALL sessions
    # Exclude the current session to find the previous PB
    all_time_best = Lap.objects.filter(
        session__driver=driver,
        session__track=track,
        session__car=car,
        lap_time__gt=0,
        is_valid=True
    ).exclude(
        session=session
    ).order_by('lap_time').first()

    is_new_pb = False
    previous_time = None
    improvement = None

    if not all_time_best:
        # This is the first PB for this driver/track/car combination
        logger.info(
            f"First PB for {driver.username}: {track.name} / {car.name} - "
            f"{session_best.lap_time}s"
        )
        is_new_pb = True
        session_best.is_personal_best = True
        session_best.save(update_fields=['is_personal_best'])

    elif session_best.lap_time < all_time_best.lap_time:
        # New PB! This lap is faster than the previous best
        previous_time = all_time_best.lap_time
        improvement = previous_time - session_best.lap_time

        logger.info(
            f"New PB for {driver.username}: {track.name} / {car.name} - "
            f"{session_best.lap_time}s (improved by {improvement}s)"
        )

        is_new_pb = True

        # Clear the old PB flag
        all_time_best.is_personal_best = False
        all_time_best.save(update_fields=['is_personal_best'])

        # Set the new PB flag
        session_best.is_personal_best = True
        session_best.save(update_fields=['is_personal_best'])

    else:
        # Not a PB - the session best is slower than the all-time best
        logger.debug(
            f"Not a PB for {driver.username}: {track.name} / {car.name} - "
            f"session best {session_best.lap_time}s vs all-time {all_time_best.lap_time}s"
        )

    return is_new_pb, previous_time, improvement


def format_lap_time(lap_time_seconds):
    """
    Format lap time in seconds to MM:SS.mmm format.

    Args:
        lap_time_seconds: Lap time in seconds (Decimal or float)

    Returns:
        str: Formatted lap time (e.g., "1:23.456" or "59.123")
    """
    lap_time = float(lap_time_seconds)
    minutes = int(lap_time // 60)
    seconds = lap_time % 60

    if minutes > 0:
        return f"{minutes}:{seconds:06.3f}"
    else:
        return f"{seconds:.3f}"
