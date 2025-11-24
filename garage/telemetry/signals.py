"""
Signals for telemetry app.

Handles automatic actions on model events like user creation.
"""

from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import Driver, Team, TeamMembership


@receiver(post_save, sender=User)
def create_driver_profile(sender, instance, created, **kwargs):
    """
    Create a Driver profile for new users and auto-join them to the default team.
    """
    if created:
        # Create driver profile
        driver, driver_created = Driver.objects.get_or_create(user=instance)

        # Add user to default team if one exists
        try:
            default_team = Team.objects.filter(is_default_team=True).first()
            if default_team and not default_team.is_user_member(instance):
                TeamMembership.objects.create(
                    team=default_team,
                    user=instance,
                    role='member'
                )
        except Exception as e:
            # Log error but don't fail user creation
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to add user {instance.username} to default team: {e}")
