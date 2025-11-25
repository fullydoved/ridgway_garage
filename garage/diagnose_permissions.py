#!/usr/bin/env python
"""Diagnose teammate lap permission issue."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'garage.settings')
django.setup()

from django.contrib.auth import get_user_model
from telemetry.models import Team, Lap

User = get_user_model()

# Change these to match your production scenario
REQUESTING_USER = 'mike'  # User trying to view the lap
LAP_ID = 4469  # The lap they can't view

print("=" * 60)
print("DIAGNOSING LAP PERMISSION ISSUE")
print("=" * 60)

try:
    user = User.objects.get(username=REQUESTING_USER)
    print(f"\nRequesting user: {user.username} (id={user.id})")
except User.DoesNotExist:
    print(f"\nERROR: User '{REQUESTING_USER}' not found!")
    exit(1)

try:
    lap = Lap.objects.select_related('session__driver').get(id=LAP_ID)
    driver = lap.session.driver
    print(f"Lap {LAP_ID} owner: {driver.username} (id={driver.id})")
except Lap.DoesNotExist:
    print(f"\nERROR: Lap {LAP_ID} not found!")
    exit(1)

print("\n" + "-" * 60)
print("TEAM MEMBERSHIPS")
print("-" * 60)

user_teams = Team.objects.filter(members=user)
driver_teams = Team.objects.filter(members=driver)

print(f"\n{user.username}'s teams:")
for t in user_teams:
    members = list(t.members.values_list('username', flat=True))
    print(f"  - {t.name} (id={t.id}): {members}")

print(f"\n{driver.username}'s teams:")
for t in driver_teams:
    members = list(t.members.values_list('username', flat=True))
    print(f"  - {t.name} (id={t.id}): {members}")

print("\n" + "-" * 60)
print("PERMISSION CHECK")
print("-" * 60)

user_team_ids = set(user_teams.values_list('id', flat=True))
driver_team_ids = set(driver_teams.values_list('id', flat=True))
shared_teams = user_team_ids & driver_team_ids

print(f"\n{user.username}'s team IDs: {user_team_ids}")
print(f"{driver.username}'s team IDs: {driver_team_ids}")
print(f"Shared team IDs: {shared_teams}")
print(f"\nHas shared teams: {len(shared_teams) > 0}")

if len(shared_teams) > 0:
    print("\n>>> RESULT: Permission SHOULD be GRANTED <<<")
    print("If you're still getting 403, the deployed code may be different.")
else:
    print("\n>>> RESULT: Permission DENIED (no shared teams) <<<")
    print("Users need to be in at least one common team.")
