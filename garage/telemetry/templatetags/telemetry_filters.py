"""
Custom template filters for telemetry data display.
"""
from django import template

register = template.Library()


@register.filter
def format_laptime(seconds):
    """
    Format lap time from seconds to human-readable format.

    Examples:
        59.234 -> "59.234s"
        111.167 -> "1:51.167"
        3661.5 -> "1:01:01.500"
    """
    if seconds is None:
        return "N/A"

    try:
        total_seconds = float(seconds)

        # Calculate hours, minutes, seconds
        hours = int(total_seconds // 3600)
        remaining = total_seconds % 3600
        minutes = int(remaining // 60)
        secs = remaining % 60

        # Format based on duration
        if hours > 0:
            # Format: h:mm:ss.mmm
            return f"{hours}:{minutes:02d}:{secs:06.3f}"
        elif minutes > 0:
            # Format: m:ss.mmm
            return f"{minutes}:{secs:06.3f}"
        else:
            # Format: ss.mmms
            return f"{secs:.3f}s"

    except (ValueError, TypeError):
        return str(seconds)
