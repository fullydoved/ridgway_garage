#!/usr/bin/env python
"""Set up test data to reproduce teammate lap permission issue."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'garage.settings')
django.setup()

from django.contrib.auth import get_user_model
from telemetry.models import Team, Track, Car, Session, Lap, TelemetryData
from django.core.files.base import ContentFile

User = get_user_model()

# Create two users
mike, _ = User.objects.get_or_create(username='mike', defaults={'password': 'testpass123'})
mike.set_password('testpass123')
mike.save()

teammate, _ = User.objects.get_or_create(username='teammate', defaults={'password': 'testpass123'})
teammate.set_password('testpass123')
teammate.save()

print(f"Created users: mike (id={mike.id}), teammate (id={teammate.id})")

# Create a team and add both users
team, _ = Team.objects.get_or_create(name='Test Team', defaults={'owner': mike})
team.members.add(mike, teammate)
print(f"Created team: {team.name} (id={team.id})")
print(f"Team members: {list(team.members.values_list('username', flat=True))}")

# Create track and car
track, _ = Track.objects.get_or_create(name='Test Track')
car, _ = Car.objects.get_or_create(name='Test Car')

# Create a session for teammate (NOT mike)
session, created = Session.objects.get_or_create(
    driver=teammate,
    track=track,
    car=car,
    defaults={
        'processing_status': 'completed',
    }
)
if created:
    session.ibt_file.save('test.ibt', ContentFile(b'fake ibt content'))
print(f"Created session: id={session.id}, driver={session.driver.username}")

# Create a lap for teammate's session
lap, _ = Lap.objects.get_or_create(
    session=session,
    lap_number=1,
    defaults={
        'lap_time': 90.123,
        'is_valid': True,
    }
)
print(f"Created lap: id={lap.id}, driver={lap.session.driver.username}")

# Create telemetry data for the lap
telemetry, _ = TelemetryData.objects.get_or_create(
    lap=lap,
    defaults={
        'data': {
            'Speed': [100, 110, 120],
            'Throttle': [0.8, 0.9, 1.0],
            'Brake': [0.0, 0.0, 0.0],
            'LapDist': [0, 100, 200],
        },
        'sample_count': 3,
    }
)
print(f"Created telemetry for lap {lap.id}")

# Verify team membership
print("\n=== Verification ===")
mike_teams = set(Team.objects.filter(members=mike).values_list('id', flat=True))
teammate_teams = set(Team.objects.filter(members=teammate).values_list('id', flat=True))
shared = mike_teams & teammate_teams

print(f"Mike's teams: {mike_teams}")
print(f"Teammate's teams: {teammate_teams}")
print(f"Shared teams: {shared}")
print(f"Should have access: {len(shared) > 0}")

print(f"\n=== Test URL ===")
print(f"Login as 'mike' with password 'testpass123'")
print(f"Then try: /api/laps/{lap.id}/telemetry/")
