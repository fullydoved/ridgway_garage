"""
Django management command to export filtered telemetry data.

Used by the db_backup.sh script for partial backups.
"""

import sys
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from django.db import connection


class Command(BaseCommand):
    help = 'Export telemetry data with optional filters (outputs SQL to stdout)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            help='Only export sessions from the last N days',
        )
        parser.add_argument(
            '--session',
            type=int,
            help='Only export a specific session ID (and related data)',
        )
        parser.add_argument(
            '--lap',
            type=int,
            help='Only export a specific lap ID (and related data)',
        )

    def handle(self, *args, **options):
        from telemetry.models import Session, Lap, TelemetryData, Track, Car, Team

        days = options.get('days')
        session_id = options.get('session')
        lap_id = options.get('lap')

        # Build the filter
        if lap_id:
            # Export specific lap
            laps = Lap.objects.filter(id=lap_id)
            sessions = Session.objects.filter(laps__in=laps).distinct()
            self.stderr.write(f"Exporting lap {lap_id}...")
        elif session_id:
            # Export specific session
            sessions = Session.objects.filter(id=session_id)
            laps = Lap.objects.filter(session__in=sessions)
            self.stderr.write(f"Exporting session {session_id}...")
        elif days:
            # Export last N days
            cutoff = timezone.now() - timedelta(days=days)
            sessions = Session.objects.filter(created_at__gte=cutoff)
            laps = Lap.objects.filter(session__in=sessions)
            self.stderr.write(f"Exporting last {days} days ({sessions.count()} sessions)...")
        else:
            self.stderr.write(self.style.ERROR('No filter specified. Use --days, --session, or --lap'))
            sys.exit(1)

        # Get related objects
        session_ids = list(sessions.values_list('id', flat=True))
        lap_ids = list(laps.values_list('id', flat=True))

        # Get tracks and cars used by these sessions
        track_ids = list(sessions.values_list('track_id', flat=True).distinct())
        car_ids = list(sessions.values_list('car_id', flat=True).distinct())
        team_ids = list(sessions.values_list('team_id', flat=True).distinct())
        driver_ids = list(sessions.values_list('driver_id', flat=True).distinct())

        # Remove None values
        track_ids = [t for t in track_ids if t]
        car_ids = [c for c in car_ids if c]
        team_ids = [t for t in team_ids if t]
        driver_ids = [d for d in driver_ids if d]

        self.stderr.write(f"  Sessions: {len(session_ids)}")
        self.stderr.write(f"  Laps: {len(lap_ids)}")
        self.stderr.write(f"  Tracks: {len(track_ids)}")
        self.stderr.write(f"  Cars: {len(car_ids)}")

        # Generate SQL statements
        # We output raw SQL for pg_restore compatibility

        with connection.cursor() as cursor:
            # Export tracks
            if track_ids:
                self._export_table(cursor, 'telemetry_track', 'id', track_ids)

            # Export cars
            if car_ids:
                self._export_table(cursor, 'telemetry_car', 'id', car_ids)

            # Export teams (if any)
            if team_ids:
                self._export_table(cursor, 'telemetry_team', 'id', team_ids)

            # Export users (drivers)
            if driver_ids:
                self._export_table(cursor, 'auth_user', 'id', driver_ids)

            # Export sessions
            if session_ids:
                self._export_table(cursor, 'telemetry_session', 'id', session_ids)

            # Export laps
            if lap_ids:
                self._export_table(cursor, 'telemetry_lap', 'id', lap_ids)

            # Export telemetry data
            if lap_ids:
                self._export_table(cursor, 'telemetry_telemetrydata', 'lap_id', lap_ids)

        self.stderr.write(self.style.SUCCESS('Export complete'))

    def _export_table(self, cursor, table_name, id_column, ids):
        """Export rows from a table as INSERT statements."""
        if not ids:
            return

        # Get column names
        cursor.execute(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, [table_name])
        columns = [row[0] for row in cursor.fetchall()]

        # Build placeholders for IN clause
        placeholders = ','.join(['%s'] * len(ids))

        # Fetch rows
        cursor.execute(f"""
            SELECT * FROM {table_name}
            WHERE {id_column} IN ({placeholders})
        """, ids)

        rows = cursor.fetchall()

        if not rows:
            return

        self.stderr.write(f"  Exporting {len(rows)} rows from {table_name}")

        # Output INSERT statements
        col_names = ', '.join(f'"{c}"' for c in columns)

        for row in rows:
            values = []
            for val in row:
                if val is None:
                    values.append('NULL')
                elif isinstance(val, bool):
                    values.append('TRUE' if val else 'FALSE')
                elif isinstance(val, (int, float)):
                    values.append(str(val))
                elif isinstance(val, dict):
                    # JSON fields - escape and quote
                    import json
                    json_str = json.dumps(val).replace("'", "''")
                    values.append(f"'{json_str}'")
                else:
                    # String - escape single quotes
                    escaped = str(val).replace("'", "''")
                    values.append(f"'{escaped}'")

            values_str = ', '.join(values)
            print(f'INSERT INTO {table_name} ({col_names}) VALUES ({values_str}) ON CONFLICT DO NOTHING;')
