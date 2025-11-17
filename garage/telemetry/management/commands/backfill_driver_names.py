"""
Management command to backfill driver_name field from existing IBT files.
"""
from django.core.management.base import BaseCommand
from telemetry.models import Session
import irsdk
import yaml


class Command(BaseCommand):
    help = 'Backfill driver_name field from existing IBT files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Find sessions without driver_name that have IBT files
        sessions = Session.objects.filter(
            driver_name='',
            ibt_file__isnull=False
        ).exclude(ibt_file='')

        self.stdout.write(
            self.style.SUCCESS(f'Found {sessions.count()} sessions to process')
        )

        updated_count = 0
        error_count = 0

        for session in sessions:
            try:
                # Open the IBT file
                ibt = irsdk.IBT()
                ibt.open(session.ibt_file.path)

                # Extract session info
                try:
                    from yaml.cyaml import CSafeLoader as YamlSafeLoader
                except ImportError:
                    from yaml import SafeLoader as YamlSafeLoader

                YAML_CODE_PAGE = 'cp1252'
                header = ibt._header
                session_info_offset = header.session_info_offset
                session_info_len = header.session_info_len

                # Extract and parse YAML session info
                session_info_yaml = ibt._shared_mem[session_info_offset:session_info_offset + session_info_len]
                session_info_yaml = session_info_yaml.rstrip(b'\x00').decode(YAML_CODE_PAGE)
                session_info = yaml.load(session_info_yaml, Loader=YamlSafeLoader)

                if session_info and 'DriverInfo' in session_info:
                    drivers = session_info['DriverInfo'].get('Drivers', [])
                    if drivers:
                        driver_info = drivers[0]
                        driver_name = driver_info.get('UserName', '').strip()

                        if driver_name:
                            if dry_run:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Would update session {session.id}: "{driver_name}"'
                                    )
                                )
                            else:
                                session.driver_name = driver_name
                                session.save(update_fields=['driver_name'])
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f'Updated session {session.id}: "{driver_name}"'
                                    )
                                )
                            updated_count += 1
                        else:
                            self.stdout.write(
                                self.style.WARNING(
                                    f'Session {session.id}: No driver name found in IBT'
                                )
                            )

                ibt.close()

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'Error processing session {session.id}: {str(e)}'
                    )
                )

        self.stdout.write('')
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Dry run complete. Would update {updated_count} sessions.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Updated {updated_count} sessions with {error_count} errors.'
                )
            )
