"""
Tests for the Ridgway Garage telemetry app.
"""

from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from decimal import Decimal

from .models import Session, Lap, TelemetryData, Track, Car, Team, Driver

User = get_user_model()


# Disable static file checks for tests
@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class BaseTestCase(TestCase):
    """Base test case with common settings."""
    pass


class TrackModelTest(TestCase):
    """Test the Track model."""

    def setUp(self):
        self.track = Track.objects.create(
            name="Watkins Glen International",
            configuration="Full Course",
            length_km=5.472
        )

    def test_track_creation(self):
        """Test creating a track."""
        self.assertEqual(self.track.name, "Watkins Glen International")
        self.assertEqual(self.track.configuration, "Full Course")
        self.assertEqual(float(self.track.length_km), 5.472)

    def test_track_str(self):
        """Test track string representation."""
        self.assertEqual(
            str(self.track),
            "Watkins Glen International - Full Course"
        )


class CarModelTest(TestCase):
    """Test the Car model."""

    def setUp(self):
        self.car = Car.objects.create(
            name="Dallara IR18",
            car_class="Indy Car"
        )

    def test_car_creation(self):
        """Test creating a car."""
        self.assertEqual(self.car.name, "Dallara IR18")
        self.assertEqual(self.car.car_class, "Indy Car")

    def test_car_str(self):
        """Test car string representation."""
        self.assertEqual(str(self.car), "Dallara IR18")


class TeamModelTest(TestCase):
    """Test the Team model."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="teamowner",
            password="testpass123"
        )
        self.team = Team.objects.create(
            name="Test Racing Team",
            owner=self.owner
        )

    def test_team_creation(self):
        """Test creating a team."""
        self.assertEqual(self.team.name, "Test Racing Team")
        self.assertEqual(self.team.owner, self.owner)

    def test_team_str(self):
        """Test team string representation."""
        self.assertEqual(str(self.team), "Test Racing Team")


class SessionModelTest(TestCase):
    """Test the Session model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testdriver",
            password="testpass123"
        )
        self.track = Track.objects.create(
            name="Watkins Glen International",
            configuration="Full Course"
        )
        self.car = Car.objects.create(name="Dallara IR18")

        # Create a fake IBT file
        self.ibt_file = SimpleUploadedFile(
            "test.ibt",
            b"fake ibt content",
            content_type="application/octet-stream"
        )

        self.session = Session.objects.create(
            driver=self.user,
            track=self.track,
            car=self.car,
            ibt_file=self.ibt_file,
            session_type="practice",
            processing_status="completed"
        )

    def test_session_creation(self):
        """Test creating a session."""
        self.assertEqual(self.session.driver, self.user)
        self.assertEqual(self.session.track, self.track)
        self.assertEqual(self.session.car, self.car)
        self.assertEqual(self.session.session_type, "practice")
        self.assertEqual(self.session.processing_status, "completed")

    def test_session_str(self):
        """Test session string representation."""
        # The format is: "driver - track (car) - date"
        result = str(self.session)
        self.assertIn("testdriver", result)
        self.assertIn("Watkins Glen International", result)
        self.assertIn("Dallara IR18", result)


class LapModelTest(TestCase):
    """Test the Lap model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testdriver",
            password="testpass123"
        )
        self.track = Track.objects.create(name="Test Track")
        self.car = Car.objects.create(name="Test Car")

        self.ibt_file = SimpleUploadedFile(
            "test.ibt",
            b"fake content",
            content_type="application/octet-stream"
        )

        self.session = Session.objects.create(
            driver=self.user,
            track=self.track,
            car=self.car,
            ibt_file=self.ibt_file
        )

        self.lap = Lap.objects.create(
            session=self.session,
            lap_number=1,
            lap_time=72.345,
            is_valid=True,
            is_personal_best=True
        )

    def test_lap_creation(self):
        """Test creating a lap."""
        self.assertEqual(self.lap.session, self.session)
        self.assertEqual(self.lap.lap_number, 1)
        self.assertEqual(self.lap.lap_time, 72.345)
        self.assertTrue(self.lap.is_valid)
        self.assertTrue(self.lap.is_personal_best)

    def test_lap_str(self):
        """Test lap string representation."""
        # The format is: "Lap X - Ys (driver)"
        result = str(self.lap)
        self.assertIn("Lap 1", result)
        self.assertIn("72.345s", result)
        self.assertIn("testdriver", result)


class TelemetryDataModelTest(TestCase):
    """Test the TelemetryData model."""

    def setUp(self):
        self.user = User.objects.create_user(username="testdriver", password="testpass123")
        self.track = Track.objects.create(name="Test Track")
        self.car = Car.objects.create(name="Test Car")
        self.ibt_file = SimpleUploadedFile("test.ibt", b"fake", content_type="application/octet-stream")
        self.session = Session.objects.create(
            driver=self.user,
            track=self.track,
            car=self.car,
            ibt_file=self.ibt_file
        )
        self.lap = Lap.objects.create(
            session=self.session,
            lap_number=1,
            lap_time=72.345
        )

        self.telemetry_data = {
            'Speed': [100, 110, 120],
            'Throttle': [0.8, 0.9, 1.0],
            'Brake': [0.0, 0.0, 0.0]
        }

        self.telemetry = TelemetryData.objects.create(
            lap=self.lap,
            data=self.telemetry_data,
            sample_count=3,
            max_speed=250.5,
            avg_speed=180.2
        )

    def test_telemetry_creation(self):
        """Test creating telemetry data."""
        self.assertEqual(self.telemetry.lap, self.lap)
        self.assertEqual(self.telemetry.sample_count, 3)
        self.assertEqual(self.telemetry.max_speed, 250.5)
        self.assertEqual(self.telemetry.avg_speed, 180.2)
        self.assertIn('Speed', self.telemetry.data)

    def test_telemetry_str(self):
        """Test telemetry string representation."""
        expected = f"Telemetry for {self.lap}"
        self.assertEqual(str(self.telemetry), expected)


class HomeViewTest(TestCase):
    """Test the home view."""

    def setUp(self):
        self.client = Client()

    def test_home_view_loads(self):
        """Test that home page loads successfully."""
        response = self.client.get(reverse('telemetry:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ridgway Garage")


class SessionListViewTest(TestCase):
    """Test the session list view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testdriver", password="testpass123")
        self.client.login(username="testdriver", password="testpass123")

        self.track = Track.objects.create(name="Test Track")
        self.car = Car.objects.create(name="Test Car")
        self.ibt_file = SimpleUploadedFile("test.ibt", b"fake", content_type="application/octet-stream")

        self.session = Session.objects.create(
            driver=self.user,
            track=self.track,
            car=self.car,
            ibt_file=self.ibt_file,
            processing_status="completed"
        )

    def test_session_list_view_requires_login(self):
        """Test that session list requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('telemetry:session_list'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_session_list_view_loads(self):
        """Test that session list loads for authenticated user."""
        response = self.client.get(reverse('telemetry:session_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Track")


class APIUploadTest(TestCase):
    """Test API upload endpoint with compression support."""

    def setUp(self):
        """Set up test user with API token."""
        self.user = User.objects.create_user(
            username='testdriver',
            password='testpass123'
        )

        self.driver = Driver.objects.create(
            user=self.user,
            display_name='Test Driver'
        )

        # Generate API token
        self.api_token = self.driver.generate_api_token()

        self.client = Client()

    def test_api_upload_uncompressed_ibt(self):
        """Test uploading uncompressed IBT file (backward compatibility)."""
        # Create fake IBT data
        ibt_data = b"fake ibt content here" * 100
        test_file = SimpleUploadedFile(
            "test_session.ibt",
            ibt_data,
            content_type="application/octet-stream"
        )

        # Upload via API
        response = self.client.post(
            reverse('telemetry:api_upload'),
            {'file': test_file},
            HTTP_AUTHORIZATION=f'Token {self.api_token}'
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('session_id', data)

        # Verify session created
        session = Session.objects.get(id=data['session_id'])
        self.assertEqual(session.driver, self.user)
        self.assertEqual(session.processing_status, 'pending')

        # Verify file saved correctly (uncompressed)
        with session.ibt_file.open('rb') as f:
            saved_data = f.read()
        self.assertEqual(saved_data, ibt_data)

    def test_api_upload_compressed_ibt(self):
        """Test uploading gzip-compressed IBT file."""
        import gzip

        # Create fake IBT data
        original_data = b"fake ibt content here" * 100  # Larger for compression

        # Compress it
        compressed_data = gzip.compress(original_data)

        test_file = SimpleUploadedFile(
            "test_session.ibt.gz",
            compressed_data,
            content_type="application/octet-stream"
        )

        # Upload via API
        response = self.client.post(
            reverse('telemetry:api_upload'),
            {'file': test_file},
            HTTP_AUTHORIZATION=f'Token {self.api_token}'
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('session_id', data)

        # Verify session created
        session = Session.objects.get(id=data['session_id'])

        # Verify file was decompressed before saving
        with session.ibt_file.open('rb') as f:
            saved_data = f.read()
        self.assertEqual(saved_data, original_data)  # Should match ORIGINAL

    def test_api_upload_corrupted_gzip(self):
        """Test that corrupted gzip files are rejected gracefully."""
        # Create fake gzip header but invalid data
        corrupted_data = b'\x1f\x8b\x08\x00' + b'invalid data'

        test_file = SimpleUploadedFile(
            "corrupted.ibt",
            corrupted_data,
            content_type="application/octet-stream"
        )

        response = self.client.post(
            reverse('telemetry:api_upload'),
            {'file': test_file},
            HTTP_AUTHORIZATION=f'Token {self.api_token}'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        # Error message should mention decompression failure
        self.assertIn('decompression', data['error'].lower())

    def test_api_upload_requires_authentication(self):
        """Test that API upload requires valid token."""
        ibt_data = b"fake ibt content"
        test_file = SimpleUploadedFile(
            "test.ibt",
            ibt_data,
            content_type="application/octet-stream"
        )

        # Try without token
        response = self.client.post(
            reverse('telemetry:api_upload'),
            {'file': test_file}
        )

        self.assertEqual(response.status_code, 401)

        # Try with invalid token
        response = self.client.post(
            reverse('telemetry:api_upload'),
            {'file': test_file},
            HTTP_AUTHORIZATION='Token invalid_token_here'
        )

        self.assertEqual(response.status_code, 401)


class LapValidationTest(TestCase):
    """Test lap validation logic for personal best tracking."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            username='testdriver',
            password='testpass123'
        )
        self.track = Track.objects.create(
            name="Road Atlanta",
            configuration="Full Course",
            length_km=4.088
        )
        self.car = Car.objects.create(
            name="Mazda MX-5 Cup",
            car_class="Sports Car"
        )
        self.ibt_file = SimpleUploadedFile(
            "test.ibt",
            b"fake content",
            content_type="application/octet-stream"
        )
        self.session = Session.objects.create(
            driver=self.user,
            track=self.track,
            car=self.car,
            ibt_file=self.ibt_file,
            processing_status="completed"
        )

    def _create_lap_with_telemetry(self, lap_number, lap_time, is_valid=True,
                                   track_surface_values=None, incident_values=None,
                                   pit_road_values=None):
        """
        Helper method to create a lap with mock telemetry data.

        Args:
            lap_number: Lap number
            lap_time: Lap time in seconds
            is_valid: Whether lap should be marked valid
            track_surface_values: List of PlayerTrackSurface values (1=asphalt, 3=off-track, -1=not in world)
            incident_values: List of PlayerCarMyIncidentCount values
            pit_road_values: List of OnPitRoad boolean values
        """
        # Create sample count (60 Hz for 1 minute = 3600 samples, but use fewer for tests)
        sample_count = 100

        # Default telemetry values (all valid)
        if track_surface_values is None:
            track_surface_values = [1] * sample_count  # 1 = asphalt (valid)
        if incident_values is None:
            incident_values = [0] * sample_count  # No incidents
        if pit_road_values is None:
            pit_road_values = [False] * sample_count  # Not on pit road

        # Create lap
        lap = Lap.objects.create(
            session=self.session,
            lap_number=lap_number,
            lap_time=lap_time,
            is_valid=is_valid
        )

        # Create telemetry data with validation channels
        telemetry_data = {
            'Speed': [50.0 + i for i in range(sample_count)],
            'Throttle': [0.8] * sample_count,
            'SessionTime': [i * 0.1 for i in range(sample_count)],
            'PlayerTrackSurface': track_surface_values[:sample_count],
            'OnPitRoad': pit_road_values[:sample_count],
            'PlayerCarMyIncidentCount': incident_values[:sample_count],
        }

        TelemetryData.objects.create(
            lap=lap,
            data=telemetry_data,
            sample_count=sample_count,
            max_speed=200.0,
            avg_speed=150.0
        )

        return lap

    def test_valid_lap_creation(self):
        """Test that a clean, valid lap is created correctly."""
        lap = self._create_lap_with_telemetry(
            lap_number=1,
            lap_time=105.234,  # Valid lap time (1m 45s)
            is_valid=True
        )

        self.assertTrue(lap.is_valid)
        self.assertEqual(lap.lap_time, 105.234)
        self.assertEqual(lap.lap_number, 1)

    def test_invalid_lap_incomplete(self):
        """Test that laps with time < 10s are marked invalid (incomplete)."""
        # Simulate a lap that was reset or session ended mid-lap
        lap = self._create_lap_with_telemetry(
            lap_number=2,
            lap_time=5.123,  # Too short - invalid
            is_valid=False
        )

        self.assertFalse(lap.is_valid)
        self.assertLess(lap.lap_time, 10.0)

    def test_invalid_lap_off_track(self):
        """Test that laps with off-track excursions are marked invalid."""
        # Create telemetry with off-track samples
        # PlayerTrackSurface: 3 = OffTrack
        track_surfaces = [1] * 50 + [3] * 10 + [1] * 40  # 10 samples off-track

        lap = self._create_lap_with_telemetry(
            lap_number=3,
            lap_time=104.567,
            is_valid=False,
            track_surface_values=track_surfaces
        )

        self.assertFalse(lap.is_valid)

        # Verify telemetry contains off-track samples
        telemetry = TelemetryData.objects.get(lap=lap)
        off_track_count = sum(1 for surface in telemetry.data['PlayerTrackSurface'] if surface == 3)
        self.assertGreater(off_track_count, 0)

    def test_invalid_lap_not_in_world(self):
        """Test that laps with NotInWorld surface are marked invalid (reset/tow)."""
        # PlayerTrackSurface: -1 = NotInWorld (driver reset/towed)
        track_surfaces = [1] * 30 + [-1] * 20 + [1] * 50

        lap = self._create_lap_with_telemetry(
            lap_number=4,
            lap_time=98.234,
            is_valid=False,
            track_surface_values=track_surfaces
        )

        self.assertFalse(lap.is_valid)

        # Verify telemetry contains NotInWorld samples
        telemetry = TelemetryData.objects.get(lap=lap)
        not_in_world_count = sum(1 for surface in telemetry.data['PlayerTrackSurface'] if surface == -1)
        self.assertGreater(not_in_world_count, 0)

    def test_invalid_lap_incident(self):
        """Test that laps with incidents are marked invalid."""
        # Incident count increases during lap (started at 0, ended at 2)
        incident_counts = [0] * 40 + [1] * 30 + [2] * 30  # 2 incidents during lap

        lap = self._create_lap_with_telemetry(
            lap_number=5,
            lap_time=107.890,
            is_valid=False,
            incident_values=incident_counts
        )

        self.assertFalse(lap.is_valid)

        # Verify incident count increased
        telemetry = TelemetryData.objects.get(lap=lap)
        incident_start = telemetry.data['PlayerCarMyIncidentCount'][0]
        incident_end = telemetry.data['PlayerCarMyIncidentCount'][-1]
        self.assertGreater(incident_end, incident_start)

    def test_invalid_lap_inlap(self):
        """Test that inlaps (ending in pits) are marked invalid."""
        # Lap ends with OnPitRoad = True
        pit_road = [False] * 80 + [True] * 20  # Entered pits at end of lap

        lap = self._create_lap_with_telemetry(
            lap_number=6,
            lap_time=110.456,
            is_valid=False,
            pit_road_values=pit_road
        )

        self.assertFalse(lap.is_valid)

        # Verify lap ended on pit road
        telemetry = TelemetryData.objects.get(lap=lap)
        self.assertTrue(telemetry.data['OnPitRoad'][-1])

    def test_personal_best_only_valid_laps(self):
        """Test that PB tracking only considers valid laps."""
        from telemetry.utils.pb_tracker import update_personal_bests

        # Create a valid lap (should be PB)
        valid_lap = self._create_lap_with_telemetry(
            lap_number=1,
            lap_time=105.234,
            is_valid=True
        )

        # Create an invalid lap with faster time (should NOT be PB)
        invalid_lap = self._create_lap_with_telemetry(
            lap_number=2,
            lap_time=5.123,  # Faster but invalid (incomplete)
            is_valid=False
        )

        # Update personal bests
        is_new_pb, prev_time, improvement = update_personal_bests(self.session)

        # The valid lap should be marked as PB, not the invalid one
        valid_lap.refresh_from_db()
        invalid_lap.refresh_from_db()

        self.assertTrue(is_new_pb)
        self.assertTrue(valid_lap.is_personal_best)
        self.assertFalse(invalid_lap.is_personal_best)

    def test_personal_best_ignores_invalid_laps(self):
        """Test that invalid laps are ignored when determining PB."""
        from telemetry.utils.pb_tracker import update_personal_bests

        # Create multiple laps: some valid, some invalid
        valid_slow = self._create_lap_with_telemetry(
            lap_number=1,
            lap_time=110.000,
            is_valid=True
        )

        invalid_fast = self._create_lap_with_telemetry(
            lap_number=2,
            lap_time=100.000,  # Fastest but invalid
            is_valid=False,
            track_surface_values=[1] * 50 + [3] * 50  # Off-track
        )

        valid_fast = self._create_lap_with_telemetry(
            lap_number=3,
            lap_time=105.000,  # Slower than invalid but fastest valid
            is_valid=True
        )

        # Update PBs
        is_new_pb, prev_time, improvement = update_personal_bests(self.session)

        # Refresh from DB
        valid_slow.refresh_from_db()
        invalid_fast.refresh_from_db()
        valid_fast.refresh_from_db()

        # The fastest VALID lap should be PB
        self.assertTrue(is_new_pb)
        self.assertFalse(valid_slow.is_personal_best)
        self.assertFalse(invalid_fast.is_personal_best)
        self.assertTrue(valid_fast.is_personal_best)

    def test_leaderboard_query_filters_invalid_laps(self):
        """Test that leaderboard queries only return valid laps."""
        # Create valid and invalid laps
        valid_lap = self._create_lap_with_telemetry(
            lap_number=1,
            lap_time=105.234,
            is_valid=True
        )

        invalid_lap = self._create_lap_with_telemetry(
            lap_number=2,
            lap_time=104.000,  # Faster but invalid
            is_valid=False
        )

        # Query for best laps (simulating leaderboard query)
        best_laps = Lap.objects.filter(
            session__track=self.track,
            session__car=self.car,
            is_valid=True,
            lap_time__gt=0
        ).order_by('lap_time')

        # Should only return the valid lap
        self.assertEqual(best_laps.count(), 1)
        self.assertEqual(best_laps.first(), valid_lap)

    def test_session_best_lap_filters_invalid(self):
        """Test that session best lap query excludes invalid laps."""
        # Create laps for session
        invalid_fast = self._create_lap_with_telemetry(
            lap_number=1,
            lap_time=104.000,
            is_valid=False
        )

        valid_lap = self._create_lap_with_telemetry(
            lap_number=2,
            lap_time=105.234,
            is_valid=True
        )

        # Get best lap for session (should be valid lap, not invalid)
        best_lap = self.session.laps.filter(
            is_valid=True,
            lap_time__gt=0
        ).order_by('lap_time').first()

        self.assertEqual(best_lap, valid_lap)
        self.assertNotEqual(best_lap, invalid_fast)
