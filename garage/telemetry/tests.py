"""
Tests for the Ridgway Garage telemetry app.
"""

from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from decimal import Decimal

from .models import Session, Lap, TelemetryData, Track, Car, Team, Analysis, Driver

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


class AnalysisModelTest(TestCase):
    """Test the Analysis model."""

    def setUp(self):
        self.user = User.objects.create_user(username="testdriver", password="testpass123")
        self.track = Track.objects.create(name="Test Track")
        self.car = Car.objects.create(name="Test Car")

        self.analysis = Analysis.objects.create(
            name="Baseline vs New Setup",
            description="Comparing different setups",
            driver=self.user,
            track=self.track,
            car=self.car,
            is_public=False
        )

    def test_analysis_creation(self):
        """Test creating an analysis."""
        self.assertEqual(self.analysis.name, "Baseline vs New Setup")
        self.assertEqual(self.analysis.description, "Comparing different setups")
        self.assertEqual(self.analysis.driver, self.user)
        self.assertEqual(self.analysis.track, self.track)
        self.assertEqual(self.analysis.car, self.car)
        self.assertFalse(self.analysis.is_public)

    def test_analysis_str(self):
        """Test analysis string representation."""
        # The format is: "name (driver)"
        result = str(self.analysis)
        self.assertIn("Baseline vs New Setup", result)
        self.assertIn("testdriver", result)


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


class SessionDetailViewTest(TestCase):
    """Test the session detail view."""

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

        self.lap = Lap.objects.create(
            session=self.session,
            lap_number=1,
            lap_time=72.345
        )

    def test_session_detail_view_requires_login(self):
        """Test that session detail requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('telemetry:session_detail', args=[self.session.pk]))
        self.assertEqual(response.status_code, 302)

    def test_session_detail_view_loads(self):
        """Test that session detail loads successfully."""
        response = self.client.get(reverse('telemetry:session_detail', args=[self.session.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Track")
        self.assertContains(response, "72.345s")  # Lap time is displayed

    def test_session_detail_other_user_denied(self):
        """Test that users can't view other users' sessions."""
        other_user = User.objects.create_user(username="otheruser", password="testpass123")
        self.client.login(username="otheruser", password="testpass123")

        response = self.client.get(reverse('telemetry:session_detail', args=[self.session.pk]))
        self.assertEqual(response.status_code, 302)  # Redirect


class AnalysisViewTest(TestCase):
    """Test analysis views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testdriver", password="testpass123")
        self.client.login(username="testdriver", password="testpass123")

        self.track = Track.objects.create(name="Test Track")
        self.car = Car.objects.create(name="Test Car")

        self.analysis = Analysis.objects.create(
            name="Test Analysis",
            driver=self.user,
            track=self.track,
            car=self.car
        )

    def test_analysis_list_requires_login(self):
        """Test that analysis list requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('telemetry:analysis_list'))
        self.assertEqual(response.status_code, 302)

    def test_analysis_list_loads(self):
        """Test that analysis list loads successfully."""
        response = self.client.get(reverse('telemetry:analysis_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Analysis")

    def test_analysis_create_requires_login(self):
        """Test that creating analysis requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('telemetry:analysis_create'))
        self.assertEqual(response.status_code, 302)

    def test_analysis_create_loads(self):
        """Test that analysis creation form loads."""
        response = self.client.get(reverse('telemetry:analysis_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create New Analysis")

    def test_analysis_create_post(self):
        """Test creating an analysis via POST."""
        data = {
            'name': 'New Analysis',
            'description': 'Test description',
            'track': self.track.pk,
            'car': self.car.pk,
            'is_public': False
        }
        response = self.client.post(reverse('telemetry:analysis_create'), data)
        self.assertEqual(response.status_code, 302)  # Redirect on success

        # Verify analysis was created
        analysis = Analysis.objects.get(name='New Analysis')
        self.assertEqual(analysis.driver, self.user)
        self.assertEqual(analysis.description, 'Test description')

    def test_analysis_detail_loads(self):
        """Test that analysis detail loads successfully."""
        response = self.client.get(reverse('telemetry:analysis_detail', args=[self.analysis.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Analysis")


class AnalysisAddLapTest(TestCase):
    """Test adding laps to analyses."""

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
            ibt_file=self.ibt_file
        )

        self.lap = Lap.objects.create(
            session=self.session,
            lap_number=1,
            lap_time=72.345
        )

        self.analysis = Analysis.objects.create(
            name="Test Analysis",
            driver=self.user,
            track=self.track,
            car=self.car
        )

    def test_add_lap_to_analysis(self):
        """Test adding a lap to an analysis."""
        url = reverse('telemetry:analysis_add_lap', args=[self.analysis.pk, self.lap.pk])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)  # Redirect
        self.assertIn(self.lap, self.analysis.laps.all())

    def test_add_duplicate_lap_shows_warning(self):
        """Test that adding the same lap twice shows a warning."""
        url = reverse('telemetry:analysis_add_lap', args=[self.analysis.pk, self.lap.pk])

        # Add lap first time
        self.client.post(url)

        # Try to add again
        response = self.client.post(url, follow=True)

        # Check that warning message appears
        messages_list = list(response.context['messages'])
        self.assertTrue(any('already in' in str(m) for m in messages_list))

    def test_remove_lap_from_analysis(self):
        """Test removing a lap from an analysis."""
        # First add the lap
        self.analysis.laps.add(self.lap)
        self.assertIn(self.lap, self.analysis.laps.all())

        # Now remove it
        url = reverse('telemetry:analysis_remove_lap', args=[self.analysis.pk, self.lap.pk])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertNotIn(self.lap, self.analysis.laps.all())


class AnalysisFormTest(TestCase):
    """Test the AnalysisForm."""

    def setUp(self):
        self.user = User.objects.create_user(username="testdriver", password="testpass123")
        self.track = Track.objects.create(name="Test Track")
        self.car = Car.objects.create(name="Test Car")

    def test_analysis_form_valid(self):
        """Test that valid form data passes validation."""
        from .forms import AnalysisForm

        data = {
            'name': 'Test Analysis',
            'description': 'Test description',
            'track': self.track.pk,
            'car': self.car.pk,
            'is_public': False
        }

        form = AnalysisForm(data=data, user=self.user)
        self.assertTrue(form.is_valid())

    def test_analysis_form_requires_name(self):
        """Test that name field is required."""
        from .forms import AnalysisForm

        data = {
            'description': 'Test description',
            'is_public': False
        }

        form = AnalysisForm(data=data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)


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
