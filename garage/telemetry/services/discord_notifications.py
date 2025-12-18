"""
Discord notification services.

Handles sending notifications to Discord webhooks for various events.
"""
import logging
import requests
from decimal import Decimal
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def send_pb_notification(session, lap, is_improvement=False, previous_time=None, improvement=None):
    """
    Send a Discord notification when a personal best is set.

    Uses the team's Discord webhook URL to send the notification.
    Only sends if:
    - Driver has a default team
    - Team has a Discord webhook configured
    - Driver has PB notifications enabled (if preference exists)
    - Session is less than 24 hours old (to prevent spam on bulk imports)

    Args:
        session: Session object where the PB was set
        lap: Lap object that is the new PB
        is_improvement: Boolean indicating if this improved an existing PB
        previous_time: Previous PB time (Decimal), if this was an improvement
        improvement: Time improvement in seconds (Decimal), if applicable

    Returns:
        bool: True if notification was sent successfully, False otherwise
    """
    user = session.driver  # session.driver is a User object

    # Get driver profile (if it exists)
    try:
        driver_profile = user.driver_profile
    except AttributeError:
        logger.debug(f"Driver {user.username} has no driver profile, skipping PB notification")
        return False

    # Check if driver has a default team
    if not driver_profile.default_team:
        logger.debug(f"Driver {user.username} has no default team, skipping PB notification")
        return False

    team = driver_profile.default_team

    # Check if team has Discord webhook configured
    if not team.discord_webhook_url:
        logger.debug(f"Team {team.name} has no Discord webhook, skipping PB notification")
        return False

    # Check if driver has PB notifications enabled
    if not driver_profile.enable_pb_notifications:
        logger.debug(f"Driver {user.username} has PB notifications disabled")
        return False

    # Only notify for recent sessions (last 24 hours) to prevent spam
    session_age_hours = (datetime.now(timezone.utc) - session.session_date).total_seconds() / 3600
    if session_age_hours > 24:
        logger.debug(
            f"Session {session.id} is {session_age_hours:.1f} hours old, "
            f"skipping PB notification (only notify for sessions < 24h)"
        )
        return False

    # Can't send notification without track and car information
    if not session.track or not session.car:
        logger.debug(f"Session {session.id} missing track or car information, skipping PB notification")
        return False

    # Build the Discord message
    try:
        # Format track name
        track_display = session.track.name
        if session.track.configuration:
            track_display += f" - {session.track.configuration}"

        # Format lap time
        from telemetry.utils.pb_tracker import format_lap_time
        lap_time_str = format_lap_time(lap.lap_time)

        # Build title and description based on whether this is an improvement or first PB
        if is_improvement and previous_time:
            improvement_str = format_lap_time(improvement)
            previous_time_str = format_lap_time(previous_time)

            title = "🏆 PERSONAL BEST IMPROVED! 🏆"
            description = (
                f"**{driver_profile.display_name or user.username}** just improved their PB!\n\n"
                f"**Track:** {track_display}\n"
                f"**Car:** {session.car.name}\n"
                f"**New Time:** {lap_time_str}\n"
                f"**Previous PB:** {previous_time_str}\n"
                f"**Improvement:** -{improvement_str} ({float(improvement):.3f}s faster)\n\n"
                f"Great driving! 🎉"
            )
            color = 0xFFD700  # Gold
        else:
            title = "🏆 NEW PERSONAL BEST! 🏆"
            description = (
                f"**{driver_profile.display_name or user.username}** set their first PB!\n\n"
                f"**Track:** {track_display}\n"
                f"**Car:** {session.car.name}\n"
                f"**Time:** {lap_time_str}\n\n"
                f"First PB for this track/car combination! 🎉"
            )
            color = 0x00FF00  # Green

        # Build Discord embed payload
        payload = {
            "embeds": [{
                "title": title,
                "description": description,
                "color": color,
                "timestamp": session.session_date.isoformat(),
                "footer": {
                    "text": f"Session: {session.session_type.replace('_', ' ').title()}"
                }
            }]
        }

        # Send to Discord webhook
        response = requests.post(
            team.discord_webhook_url,
            json=payload,
            timeout=10
        )

        if response.status_code in [200, 204]:
            logger.info(
                f"PB notification sent to Discord for {user.username} "
                f"({session.track.name} / {session.car.name})"
            )
            return True
        else:
            logger.error(
                f"Discord webhook returned status {response.status_code} "
                f"for PB notification: {response.text}"
            )
            return False

    except Exception as e:
        logger.error(f"Error sending PB Discord notification: {e}", exc_info=True)
        return False


def check_team_record(session, lap):
    """
    Check if a lap is a new team record for the track/car combination.

    Args:
        session: Session object
        lap: Lap object to check

    Returns:
        tuple: (is_new_record, previous_record_time, previous_holder_name)
               Returns (False, None, None) if not a new record
    """
    from telemetry.models import Lap, Session as SessionModel

    # Must have a team, track, and car
    if not session.team or not session.track or not session.car:
        return False, None, None

    # Get all valid laps for this team/track/car combination (excluding current session)
    previous_best_lap = Lap.objects.filter(
        session__team=session.team,
        session__track=session.track,
        session__car=session.car,
        is_valid=True,
        lap_time__gt=0
    ).exclude(
        session=session
    ).order_by('lap_time').first()

    if previous_best_lap:
        # There's an existing record - check if this lap beats it
        if lap.lap_time < previous_best_lap.lap_time:
            previous_holder = previous_best_lap.session.driver
            holder_name = previous_holder.username
            if hasattr(previous_holder, 'driver_profile') and previous_holder.driver_profile.display_name:
                holder_name = previous_holder.driver_profile.display_name
            return True, previous_best_lap.lap_time, holder_name
        return False, None, None
    else:
        # No previous record exists - this is the first!
        return True, None, None


def send_team_record_notification(session, lap, previous_time=None, previous_holder=None):
    """
    Send a Discord notification when a new team record is set.

    Args:
        session: Session object where the record was set
        lap: Lap object that is the new team record
        previous_time: Previous record time (Decimal), if there was one
        previous_holder: Name of the previous record holder, if there was one

    Returns:
        bool: True if notification was sent successfully, False otherwise
    """
    # Must have a team with Discord webhook configured
    if not session.team or not session.team.discord_webhook_url:
        logger.debug(f"Session {session.id} has no team or team has no Discord webhook")
        return False

    # Only notify for recent sessions (last 24 hours)
    session_age_hours = (datetime.now(timezone.utc) - session.session_date).total_seconds() / 3600
    if session_age_hours > 24:
        logger.debug(f"Session {session.id} too old for team record notification")
        return False

    # Get driver display name
    driver = session.driver
    driver_name = driver.username
    if hasattr(driver, 'driver_profile') and driver.driver_profile.display_name:
        driver_name = driver.driver_profile.display_name

    try:
        # Format track name
        track_display = session.track.name
        if session.track.configuration:
            track_display += f" - {session.track.configuration}"

        # Format lap time
        from telemetry.utils.pb_tracker import format_lap_time
        lap_time_str = format_lap_time(lap.lap_time)

        # Build message based on whether this beat an existing record
        if previous_time:
            previous_time_str = format_lap_time(previous_time)
            improvement = previous_time - lap.lap_time
            improvement_str = format_lap_time(improvement)

            title = "🏅 NEW TEAM RECORD! 🏅"
            description = (
                f"**{driver_name}** just set a new team record!\n\n"
                f"**Track:** {track_display}\n"
                f"**Car:** {session.car.name}\n"
                f"**New Record:** {lap_time_str}\n"
                f"**Previous Record:** {previous_time_str} (held by {previous_holder})\n"
                f"**Improvement:** -{improvement_str}\n\n"
                f"The new benchmark has been set! 🔥"
            )
            color = 0xFF4500  # Orange-red
        else:
            title = "🏅 FIRST TEAM RECORD! 🏅"
            description = (
                f"**{driver_name}** set the first team record!\n\n"
                f"**Track:** {track_display}\n"
                f"**Car:** {session.car.name}\n"
                f"**Time:** {lap_time_str}\n\n"
                f"This is the time to beat! 🎯"
            )
            color = 0x9932CC  # Purple

        # Build Discord embed payload
        payload = {
            "embeds": [{
                "title": title,
                "description": description,
                "color": color,
                "timestamp": session.session_date.isoformat(),
                "footer": {
                    "text": f"Team: {session.team.name}"
                }
            }]
        }

        # Send to Discord webhook
        response = requests.post(
            session.team.discord_webhook_url,
            json=payload,
            timeout=10
        )

        if response.status_code in [200, 204]:
            logger.info(
                f"Team record notification sent to Discord for {driver_name} "
                f"({session.track.name} / {session.car.name}) in team {session.team.name}"
            )
            return True
        else:
            logger.error(
                f"Discord webhook returned status {response.status_code} "
                f"for team record notification: {response.text}"
            )
            return False

    except Exception as e:
        logger.error(f"Error sending team record Discord notification: {e}", exc_info=True)
        return False
