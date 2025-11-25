"""
Model tests for the Ridgway Garage telemetry app.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from telemetry.models import Session, Lap, TelemetryData, Track, Car, Team, Driver

User = get_user_model()


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

    def test_track_without_configuration(self):
        """Test track with empty configuration."""
        track = Track.objects.create(name="Monza")
        self.assertEqual(str(track), "Monza")


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

    def test_owner_can_add_members(self):
        """Test that team owner can add members."""
        member = User.objects.create_user(username="member", password="testpass123")
        self.team.members.add(member)
        self.assertIn(member, self.team.members.all())


class DriverModelTest(TestCase):
    """Test the Driver model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testdriver",
            password="testpass123"
        )
        # Driver is auto-created by signal, just get and update it
        self.driver = Driver.objects.get(user=self.user)
        self.driver.display_name = "Test Driver"
        self.driver.save()

    def test_driver_creation(self):
        """Test creating a driver profile."""
        self.assertEqual(self.driver.user, self.user)
        self.assertEqual(self.driver.display_name, "Test Driver")

    def test_api_token_generation(self):
        """Test generating API token."""
        token = self.driver.generate_api_token()
        self.assertIsNotNone(token)
        self.assertGreater(len(token), 30)  # Token has sufficient length

    def test_api_token_persistence(self):
        """Test that API token persists after generation."""
        token = self.driver.generate_api_token()
        self.driver.refresh_from_db()
        self.assertEqual(str(self.driver.api_token), token)


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

    def test_telemetry_data_retrieval(self):
        """Test that telemetry data can be retrieved correctly."""
        retrieved = TelemetryData.objects.get(lap=self.lap)
        self.assertEqual(retrieved.data['Speed'], [100, 110, 120])
        self.assertEqual(retrieved.data['Throttle'], [0.8, 0.9, 1.0])
