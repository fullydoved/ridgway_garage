"""
Management command to re-parse existing IBT files with updated validation logic.

This command re-processes existing sessions to apply the new lap validation rules
for off-track excursions, incidents, inlaps, and incomplete laps.
"""
from django.core.management.base import BaseCommand
from telemetry.models import Session, Lap, TelemetryData
from telemetry.tasks import parse_ibt_file


class Command(BaseCommand):
    help = 'Re-parse existing IBT files to apply updated lap validation logic'

    def add_arguments(self, parser):
        parser.add_argument(
            '--session-id',
            type=int,
            help='Re-parse a specific session by ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be re-parsed without making changes',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Re-parse all sessions (use with caution)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of sessions to re-parse',
        )
        parser.add_argument(
            '--status',
            type=str,
            default='completed',
            help='Filter by processing status (default: completed)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        session_id = options['session_id']
        reparse_all = options['all']
        limit = options['limit']
        status_filter = options['status']

        # Build query
        if session_id:
            # Re-parse specific session
            sessions = Session.objects.filter(id=session_id)
            if not sessions.exists():
                self.stdout.write(
                    self.style.ERROR(f'Session {session_id} not found')
                )
                return
        elif reparse_all:
            # Re-parse all sessions with IBT files
            sessions = Session.objects.filter(
                ibt_file__isnull=False
            ).exclude(ibt_file='')

            # Apply status filter
            if status_filter:
                sessions = sessions.filter(processing_status=status_filter)

            # Apply limit
            if limit:
                sessions = sessions[:limit]
        else:
            self.stdout.write(
                self.style.ERROR(
                    'Please specify either --session-id or --all to re-parse sessions'
                )
            )
            return

        total_sessions = sessions.count()

        if total_sessions == 0:
            self.stdout.write(
                self.style.WARNING('No sessions found to re-parse')
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f'Found {total_sessions} session(s) to re-parse')
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN - No changes will be made')
            )
            for session in sessions:
                self.stdout.write(
                    f'  Would re-parse: Session {session.id} - '
                    f'{session.driver.username if session.driver else "Unknown"} - '
                    f'{session.track.name if session.track else "Unknown"} - '
                    f'({session.laps.count()} laps)'
                )
            return

        # Re-parse sessions
        success_count = 0
        error_count = 0
        total_laps_before = 0
        total_laps_after = 0
        total_invalid_laps = 0

        for idx, session in enumerate(sessions, 1):
            self.stdout.write(
                self.style.HTTP_INFO(
                    f'\n[{idx}/{total_sessions}] Processing session {session.id}...'
                )
            )

            try:
                # Count laps before re-parse
                laps_before = session.laps.count()
                total_laps_before += laps_before

                # Delete existing laps and telemetry data
                self.stdout.write(
                    f'  Deleting {laps_before} existing laps and telemetry data...'
                )
                TelemetryData.objects.filter(lap__session=session).delete()
                Lap.objects.filter(session=session).delete()

                # Re-parse the IBT file (call task synchronously without .delay())
                self.stdout.write(
                    f'  Re-parsing IBT file: {session.ibt_file.name}...'
                )

                # Call the task function directly (synchronously)
                # Skip notifications to avoid spamming Discord during re-parse
                parse_ibt_file(session.id, skip_notifications=True)

                # Refresh session from DB
                session.refresh_from_db()

                # Count laps after re-parse
                laps_after = session.laps.count()
                invalid_laps = session.laps.filter(is_valid=False).count()
                valid_laps = session.laps.filter(is_valid=True).count()

                total_laps_after += laps_after
                total_invalid_laps += invalid_laps

                success_count += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ Session {session.id} re-parsed successfully\n'
                        f'    Laps: {laps_after} ({valid_laps} valid, {invalid_laps} invalid)'
                    )
                )

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'  ✗ Error re-parsing session {session.id}: {str(e)}'
                    )
                )

        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Re-parse Summary:'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'  Sessions processed: {success_count}/{total_sessions}')
        self.stdout.write(f'  Errors: {error_count}')
        self.stdout.write(f'  Total laps before: {total_laps_before}')
        self.stdout.write(f'  Total laps after: {total_laps_after}')
        self.stdout.write(
            self.style.WARNING(
                f'  Invalid laps detected: {total_invalid_laps} '
                f'({total_invalid_laps / total_laps_after * 100:.1f}% of total)'
            ) if total_laps_after > 0 else ''
        )
        self.stdout.write(self.style.SUCCESS('=' * 60))

        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(
                    f'\n⚠ Completed with {error_count} error(s). '
                    f'Check logs above for details.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ All sessions re-parsed successfully!'
                )
            )
