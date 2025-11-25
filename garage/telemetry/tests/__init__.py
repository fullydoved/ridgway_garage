"""
Tests package for the Ridgway Garage telemetry app.

Test modules:
- test_models: Model tests (Track, Car, Team, Session, Lap, TelemetryData)
- test_views: View tests (Home, Sessions, Leaderboards)
- test_api: API endpoint tests (Auth, Upload, Telemetry)
- test_utils: Utility function tests (export, charts)
"""

# Import all test classes for test discovery
from .test_models import *
from .test_views import *
from .test_api import *
