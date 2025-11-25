#!/usr/bin/env python
"""Debug script to check lap ownership and team memberships."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'garage.settings')
django.setup()

from telemetry.models import Lap, Team

lap = Lap.objects.select_related('session__driver').get(id=4469)
print(f'Lap 4469 owner: {lap.session.driver.username}')

print('\nTeams and members:')
for team in Team.objects.prefetch_related('members').all():
    members = [m.username for m in team.members.all()]
    print(f'  {team.name}: {members}')
