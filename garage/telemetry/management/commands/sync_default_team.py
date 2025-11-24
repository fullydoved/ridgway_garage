"""
Management command to sync all existing users into the default team.

This is useful for adding existing users who registered before the default team
feature was implemented.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from telemetry.models import Team, TeamMembership


class Command(BaseCommand):
    help = 'Sync all existing users into the default team'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Find the default team
        try:
            default_team = Team.objects.get(is_default_team=True)
        except Team.DoesNotExist:
            self.stdout.write(self.style.ERROR('No default team found. Please mark a team as default first.'))
            return
        except Team.MultipleObjectsReturned:
            self.stdout.write(self.style.ERROR('Multiple default teams found! Only one team should be marked as default.'))
            return

        self.stdout.write(self.style.SUCCESS(f'Default team: {default_team.name}'))

        # Get all users who are NOT already members of the default team
        existing_member_ids = default_team.members.values_list('id', flat=True)
        users_to_add = User.objects.exclude(id__in=existing_member_ids)

        if not users_to_add.exists():
            self.stdout.write(self.style.SUCCESS('All users are already members of the default team!'))
            return

        self.stdout.write(f'Found {users_to_add.count()} user(s) to add to the default team:')

        added_count = 0
        for user in users_to_add:
            self.stdout.write(f'  - {user.username}')

            if not dry_run:
                TeamMembership.objects.get_or_create(
                    team=default_team,
                    user=user,
                    defaults={'role': 'member'}
                )
                added_count += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(f'\nDRY RUN: Would have added {users_to_add.count()} user(s) to "{default_team.name}"'))
            self.stdout.write(self.style.WARNING('Run without --dry-run to apply changes'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nSuccessfully added {added_count} user(s) to "{default_team.name}"!'))
