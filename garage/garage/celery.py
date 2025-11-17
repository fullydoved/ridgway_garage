"""
Celery configuration for Ridgway Garage project.

This module configures Celery for background task processing,
particularly for parsing large IBT telemetry files.
"""

import os
from celery import Celery
from decouple import config

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'garage.settings')

# Create Celery app
app = Celery('garage')

# Configure Celery using settings from Django settings.py
# with a 'CELERY_' prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery configuration
app.conf.update(
    # Broker and backend
    broker_url=config('CELERY_BROKER_URL', default='redis://localhost:6379/0'),
    result_backend=config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0'),
    broker_connection_retry_on_startup=True,  # Retry connections on startup (Celery 6.0+ compatibility)

    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Worker settings for better database connection management
    worker_prefetch_multiplier=1,  # Prevent connection hogging
    worker_max_tasks_per_child=1000,  # Recycle workers to prevent memory leaks

    # Task routing (disabled for now - using default queue)
    # task_routes={
    #     'telemetry.tasks.parse_ibt_file': {'queue': 'telemetry'},
    #     'telemetry.tasks.process_live_telemetry': {'queue': 'realtime'},
    # },

    # Task time limits (30 minutes for large files)
    task_time_limit=1800,  # 30 minutes hard limit
    task_soft_time_limit=1500,  # 25 minutes soft limit

    # Result settings
    result_expires=3600,  # Results expire after 1 hour

    # Retry settings
    task_acks_late=True,  # Acknowledge task after completion (for reliability)
    task_reject_on_worker_lost=True,  # Requeue task if worker dies
)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery setup."""
    print(f'Request: {self.request!r}')
