"""
Management command to backfill file_hash for existing Session records.

Usage:
    python manage.py backfill_file_hashes [--dry-run]

This command calculates SHA256 hashes for all Session records that have
an ibt_file but no file_hash. This ensures duplicate detection works for
both new and existing sessions.
"""
import hashlib
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from telemetry.models import Session


class Command(BaseCommand):
    help = 'Backfill file_hash for existing Session records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Find sessions without file_hash
        sessions_without_hash = Session.objects.filter(
            ibt_file__isnull=False,
            file_hash__isnull=True
        ).exclude(ibt_file='')

        total_count = sessions_without_hash.count()

        if total_count == 0:
            self.stdout.write(self.style.SUCCESS('No sessions need hash backfill!'))
            return

        self.stdout.write(f'Found {total_count} sessions without file_hash')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be made'))

        updated_count = 0
        skipped_count = 0
        error_count = 0

        for i, session in enumerate(sessions_without_hash, 1):
            try:
                # Check if file exists
                if not session.ibt_file:
                    self.stdout.write(self.style.WARNING(
                        f'  [{i}/{total_count}] Session {session.id}: No file reference, skipping'
                    ))
                    skipped_count += 1
                    continue

                file_path = session.ibt_file.path
                if not os.path.exists(file_path):
                    self.stdout.write(self.style.WARNING(
                        f'  [{i}/{total_count}] Session {session.id}: File not found at {file_path}, skipping'
                    ))
                    skipped_count += 1
                    continue

                # Calculate hash
                hash_obj = hashlib.sha256()
                with open(file_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(8192), b''):
                        hash_obj.update(chunk)
                file_hash = hash_obj.hexdigest()

                if dry_run:
                    self.stdout.write(
                        f'  [{i}/{total_count}] Session {session.id}: Would set hash to {file_hash[:16]}...'
                    )
                else:
                    session.file_hash = file_hash
                    session.save(update_fields=['file_hash'])
                    self.stdout.write(
                        f'  [{i}/{total_count}] Session {session.id}: Hash set to {file_hash[:16]}...'
                    )

                updated_count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'  [{i}/{total_count}] Session {session.id}: Error - {str(e)}'
                ))
                error_count += 1
                continue

        # Summary
        self.stdout.write('\n' + '='*60)
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'DRY RUN SUMMARY:'))
            self.stdout.write(f'  Would update: {updated_count}')
        else:
            self.stdout.write(self.style.SUCCESS(f'BACKFILL COMPLETE:'))
            self.stdout.write(f'  Updated: {updated_count}')
        self.stdout.write(f'  Skipped: {skipped_count}')
        self.stdout.write(f'  Errors: {error_count}')
        self.stdout.write('='*60)

        if not dry_run and updated_count > 0:
            self.stdout.write(self.style.SUCCESS(
                f'\nSuccessfully backfilled {updated_count} session hashes!'
            ))
