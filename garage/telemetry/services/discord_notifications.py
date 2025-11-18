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
    except Exception:
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
