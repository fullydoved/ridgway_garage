"""
Management command to backfill setup_name for existing Session records.

Usage:
    python manage.py backfill_setup_names [--dry-run] [--force]

This command re-parses IBT files to extract setup names for sessions that
don't currently have setup_name populated. Uses the same extraction logic
as the main IBT parser.
"""
import yaml
import os
from django.core.management.base import BaseCommand
from telemetry.models import Session

# Constants from tasks.py
YAML_CODE_PAGE = 'cp1252'

# Use the same YAML loader as tasks.py
try:
    from yaml.cyaml import CSafeLoader as YamlSafeLoader
except ImportError:
    from yaml import SafeLoader as YamlSafeLoader


class Command(BaseCommand):
    help = 'Backfill setup_name for existing Session records by re-parsing IBT files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-extract setup names even for sessions that already have one',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']

        # Find sessions to process
        if force:
            sessions_to_process = Session.objects.filter(
                ibt_file__isnull=False,
                processing_status='completed'
            ).exclude(ibt_file='')
            self.stdout.write(f'Found {sessions_to_process.count()} completed sessions (--force mode)')
        else:
            sessions_to_process = Session.objects.filter(
                ibt_file__isnull=False,
                processing_status='completed',
                setup_name=''
            ).exclude(ibt_file='')
            self.stdout.write(f'Found {sessions_to_process.count()} sessions without setup_name')

        total_count = sessions_to_process.count()

        if total_count == 0:
            self.stdout.write(self.style.SUCCESS('No sessions need setup name backfill!'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be made'))

        updated_count = 0
        skipped_count = 0
        error_count = 0
        no_setup_count = 0

        for i, session in enumerate(sessions_to_process, 1):
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

                # Parse IBT file to extract setup name
                import irsdk
                ibt = irsdk.IBT()
                ibt.open(file_path)

                # Get session info YAML from header
                header = ibt._header
                session_info_offset = header.session_info_offset
                session_info_len = header.session_info_len

                # Extract and parse YAML session info
                session_info_yaml = ibt._shared_mem[session_info_offset:session_info_offset + session_info_len]
                session_info_yaml = session_info_yaml.rstrip(b'\x00').decode(YAML_CODE_PAGE)
                session_info = yaml.load(session_info_yaml, Loader=YamlSafeLoader)

                if not session_info:
                    self.stdout.write(self.style.ERROR(
                        f'  [{i}/{total_count}] Session {session.id}: Could not read session info from IBT file'
                    ))
                    error_count += 1
                    continue

                # Extract setup name from DriverInfo section (not individual driver)
                setup_name = ''
                if 'DriverInfo' in session_info and session_info['DriverInfo']:
                    driver_info_section = session_info['DriverInfo']
                    # Setup name is at the DriverInfo section level, not in Drivers array
                    setup_name = (driver_info_section.get('DriverSetupName') or '').strip()

                if not setup_name:
                    self.stdout.write(
                        f'  [{i}/{total_count}] Session {session.id}: No setup name found in IBT file'
                    )
                    no_setup_count += 1
                    continue

                if dry_run:
                    self.stdout.write(self.style.SUCCESS(
                        f'  [{i}/{total_count}] Session {session.id}: Would set setup_name to "{setup_name}"'
                    ))
                else:
                    old_setup = session.setup_name or '(empty)'
                    session.setup_name = setup_name
                    session.save(update_fields=['setup_name'])
                    self.stdout.write(self.style.SUCCESS(
                        f'  [{i}/{total_count}] Session {session.id}: Updated setup_name from "{old_setup}" to "{setup_name}"'
                    ))

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
        self.stdout.write(f'  No setup in file: {no_setup_count}')
        self.stdout.write(f'  Skipped: {skipped_count}')
        self.stdout.write(f'  Errors: {error_count}')
        self.stdout.write('='*60)

        if not dry_run and updated_count > 0:
            self.stdout.write(self.style.SUCCESS(
                f'\nSuccessfully backfilled {updated_count} setup names!'
            ))
