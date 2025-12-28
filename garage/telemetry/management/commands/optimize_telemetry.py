"""
Management command to optimize existing telemetry data for storage efficiency.

This command processes existing TelemetryData records to:
1. Remove unused channels (Alt, tire carcass temps)
2. Decimate data from 60Hz to 20Hz
3. Optionally compress JSON data with gzip

Usage:
    python manage.py optimize_telemetry --dry-run  # Preview changes
    python manage.py optimize_telemetry            # Apply optimizations
"""
import gzip
import json
import sys
from django.core.management.base import BaseCommand
from django.db import transaction
from telemetry.models import TelemetryData


# Channels to remove from existing data
CHANNELS_TO_REMOVE = [
    'Alt',  # Altitude - never displayed
    # Tire carcass temps - never displayed
    'LFtempCL', 'LFtempCM', 'LFtempCR',
    'RFtempCL', 'RFtempCM', 'RFtempCR',
    'LRtempCL', 'LRtempCM', 'LRtempCR',
    'RRtempCL', 'RRtempCM', 'RRtempCR',
]

# Decimation factor (60Hz / 3 = 20Hz)
DECIMATION_FACTOR = 3


class Command(BaseCommand):
    help = 'Optimize existing telemetry data for storage efficiency'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be optimized without making changes',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of records to process',
        )
        parser.add_argument(
            '--skip-decimation',
            action='store_true',
            help='Skip sample rate decimation (only remove channels)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of records to process per batch (default: 100)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        skip_decimation = options['skip_decimation']
        batch_size = options['batch_size']

        # Get all telemetry data records
        queryset = TelemetryData.objects.all().order_by('id')

        if limit:
            queryset = queryset[:limit]

        total_records = queryset.count()

        if total_records == 0:
            self.stdout.write(self.style.WARNING('No telemetry data found'))
            return

        self.stdout.write(
            self.style.SUCCESS(f'Found {total_records} telemetry record(s) to optimize')
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))

        # Statistics
        total_bytes_before = 0
        total_bytes_after = 0
        records_processed = 0
        records_modified = 0
        channels_removed_count = 0
        samples_removed_count = 0
        errors = []

        # Process in batches for memory efficiency
        for batch_start in range(0, total_records, batch_size):
            batch_end = min(batch_start + batch_size, total_records)
            batch = list(queryset[batch_start:batch_end])

            self.stdout.write(
                f'Processing batch {batch_start + 1}-{batch_end} of {total_records}...'
            )

            for record in batch:
                try:
                    data = record.data
                    if not data or not isinstance(data, dict):
                        records_processed += 1
                        continue

                    # Measure original size
                    original_json = json.dumps(data)
                    original_size = len(original_json.encode('utf-8'))
                    total_bytes_before += original_size

                    modified = False
                    channels_removed_this_record = 0
                    samples_before = 0
                    samples_after = 0

                    # 1. Remove unused channels
                    for channel in CHANNELS_TO_REMOVE:
                        if channel in data:
                            del data[channel]
                            channels_removed_this_record += 1
                            modified = True

                    channels_removed_count += channels_removed_this_record

                    # 2. Decimate to 20Hz (keep every 3rd sample)
                    if not skip_decimation:
                        for channel, values in data.items():
                            if isinstance(values, list) and len(values) > DECIMATION_FACTOR:
                                samples_before = len(values)
                                data[channel] = values[::DECIMATION_FACTOR]
                                samples_after = len(data[channel])
                                if samples_before != samples_after:
                                    modified = True
                                    samples_removed_count += samples_before - samples_after

                    # Measure new size
                    new_json = json.dumps(data)
                    new_size = len(new_json.encode('utf-8'))
                    total_bytes_after += new_size

                    # Update sample_count field
                    if 'SessionTime' in data:
                        new_sample_count = len(data['SessionTime'])
                    else:
                        # Use any available channel
                        for ch, vals in data.items():
                            if isinstance(vals, list):
                                new_sample_count = len(vals)
                                break
                        else:
                            new_sample_count = record.sample_count

                    # Save if modified
                    if modified and not dry_run:
                        with transaction.atomic():
                            record.data = data
                            record.sample_count = new_sample_count
                            record.save(update_fields=['data', 'sample_count'])
                        records_modified += 1

                    elif modified:
                        records_modified += 1

                    records_processed += 1

                    # Progress indicator
                    if records_processed % 50 == 0:
                        progress_pct = (records_processed / total_records) * 100
                        saved_mb = (total_bytes_before - total_bytes_after) / (1024 * 1024)
                        self.stdout.write(
                            f'  Progress: {records_processed}/{total_records} ({progress_pct:.1f}%) '
                            f'- {saved_mb:.2f} MB saved so far'
                        )

                except Exception as e:
                    errors.append(f'Record {record.id}: {str(e)}')
                    self.stdout.write(
                        self.style.ERROR(f'  Error processing record {record.id}: {e}')
                    )

        # Summary
        saved_bytes = total_bytes_before - total_bytes_after
        saved_mb = saved_bytes / (1024 * 1024)
        original_mb = total_bytes_before / (1024 * 1024)
        new_mb = total_bytes_after / (1024 * 1024)
        reduction_pct = (saved_bytes / total_bytes_before * 100) if total_bytes_before > 0 else 0

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Optimization Summary:'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'  Records processed: {records_processed}')
        self.stdout.write(f'  Records modified: {records_modified}')
        self.stdout.write(f'  Channels removed: {channels_removed_count}')
        if not skip_decimation:
            self.stdout.write(f'  Samples removed (decimation): {samples_removed_count:,}')
        self.stdout.write('')
        self.stdout.write(f'  Original size: {original_mb:.2f} MB')
        self.stdout.write(f'  New size: {new_mb:.2f} MB')
        self.stdout.write(
            self.style.SUCCESS(f'  Space saved: {saved_mb:.2f} MB ({reduction_pct:.1f}%)')
        )
        self.stdout.write(self.style.SUCCESS('=' * 60))

        if errors:
            self.stdout.write(
                self.style.ERROR(f'\n{len(errors)} error(s) occurred during processing')
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '\nThis was a DRY RUN. Run without --dry-run to apply changes.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('\nOptimization complete!')
            )
