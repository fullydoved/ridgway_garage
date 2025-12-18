# Generated migration to populate display_name from username for existing users

from django.db import migrations


def populate_display_names(apps, schema_editor):
    """Copy username to display_name for all Driver records where display_name is empty."""
    Driver = apps.get_model('telemetry', 'Driver')
    for driver in Driver.objects.filter(display_name=''):
        driver.display_name = driver.user.username
        driver.save(update_fields=['display_name'])


def reverse_populate_display_names(apps, schema_editor):
    """Reverse migration - clear display_names that match username."""
    # This is a no-op since we don't want to lose display_name data on reverse
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('telemetry', '0019_joinrequest_teaminvitation_team_is_default_team_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_display_names, reverse_populate_display_names),
    ]
