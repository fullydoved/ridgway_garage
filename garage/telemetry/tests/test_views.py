"""
View tests for the Ridgway Garage telemetry app.
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from telemetry.models import Session, Lap, TelemetryData, Track, Car, Team

User = get_user_model()


class HomeViewTest(TestCase):
    """Test the home view."""

    def setUp(self):
        self.client = Client()

    def test_home_view_loads(self):
        """Test that home page loads successfully."""
        response = self.client.get(reverse('telemetry:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ridgway Garage")

    def test_home_shows_stats_for_anonymous(self):
        """Test that home page shows appropriate content for anonymous users."""
        response = self.client.get(reverse('telemetry:home'))
        self.assertEqual(response.status_code, 200)


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

    def test_session_list_pagination_context(self):
        """Test that session list has pagination context."""
        response = self.client.get(reverse('telemetry:session_list'))
        self.assertEqual(response.status_code, 200)
        # Check pagination context is present (even with few sessions)
        self.assertIn('page_obj', response.context)

    def test_session_list_shows_only_user_sessions(self):
        """Test that users only see their own sessions."""
        other_user = User.objects.create_user(username="other", password="testpass123")
        other_ibt = SimpleUploadedFile("other.ibt", b"fake", content_type="application/octet-stream")
        other_session = Session.objects.create(
            driver=other_user,
            track=self.track,
            car=self.car,
            ibt_file=other_ibt,
            processing_status="completed"
        )

        response = self.client.get(reverse('telemetry:session_list'))
        sessions = response.context['page_obj'].object_list
        for session in sessions:
            self.assertEqual(session.driver, self.user)


class LeaderboardViewTest(TestCase):
    """Test the leaderboard view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testdriver", password="testpass123")
        self.track = Track.objects.create(name="Test Track")
        self.car = Car.objects.create(name="Test Car")

    def test_leaderboard_loads_without_login(self):
        """Test that leaderboard is publicly accessible."""
        response = self.client.get(reverse('telemetry:leaderboards'))
        self.assertEqual(response.status_code, 200)

    def test_leaderboard_filters_by_track(self):
        """Test filtering leaderboard by track."""
        response = self.client.get(
            reverse('telemetry:leaderboards'),
            {'track': self.track.id}
        )
        self.assertEqual(response.status_code, 200)
        # Check the filter is reflected in context
        self.assertIn('selected_track', response.context)

    def test_leaderboard_filters_by_car(self):
        """Test filtering leaderboard by car."""
        response = self.client.get(
            reverse('telemetry:leaderboards'),
            {'car': self.car.id}
        )
        self.assertEqual(response.status_code, 200)
        # Check the filter is reflected in context
        self.assertIn('selected_car', response.context)

    def test_leaderboard_pagination(self):
        """Test that leaderboard is paginated."""
        # Create 30 laps to trigger pagination
        ibt = SimpleUploadedFile("test.ibt", b"fake", content_type="application/octet-stream")
        session = Session.objects.create(
            driver=self.user,
            track=self.track,
            car=self.car,
            ibt_file=ibt,
            processing_status="completed"
        )
        for i in range(30):
            Lap.objects.create(
                session=session,
                lap_number=i + 1,
                lap_time=100.0 + i,
                is_valid=True
            )

        response = self.client.get(
            reverse('telemetry:leaderboards'),
            {'track': self.track.id, 'car': self.car.id}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('page_obj', response.context)


class AnalysisDashboardViewTest(TestCase):
    """Test the analysis dashboard view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testdriver", password="testpass123")
        self.client.login(username="testdriver", password="testpass123")

        self.track = Track.objects.create(name="Test Track")
        self.car = Car.objects.create(name="Test Car")

    def test_analysis_requires_login(self):
        """Test that analysis dashboard requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('telemetry:analysis'))
        self.assertEqual(response.status_code, 302)

    def test_analysis_loads(self):
        """Test that analysis dashboard loads for authenticated user."""
        response = self.client.get(reverse('telemetry:analysis'))
        self.assertEqual(response.status_code, 200)

    def test_analysis_with_preloaded_lap(self):
        """Test loading analysis with a lap ID."""
        ibt = SimpleUploadedFile("test.ibt", b"fake", content_type="application/octet-stream")
        session = Session.objects.create(
            driver=self.user,
            track=self.track,
            car=self.car,
            ibt_file=ibt,
            processing_status="completed"
        )
        lap = Lap.objects.create(
            session=session,
            lap_number=1,
            lap_time=100.0,
            is_valid=True
        )

        response = self.client.get(
            reverse('telemetry:analysis'),
            {'lap': lap.id}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['preloaded_lap_id'], lap.id)


class UserSettingsViewTest(TestCase):
    """Test the user settings view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testdriver", password="testpass123")
        self.client.login(username="testdriver", password="testpass123")

    def test_settings_requires_login(self):
        """Test that settings require authentication."""
        self.client.logout()
        response = self.client.get(reverse('telemetry:user_settings'))
        self.assertEqual(response.status_code, 302)

    def test_settings_loads(self):
        """Test that settings page loads for authenticated user."""
        response = self.client.get(reverse('telemetry:user_settings'))
        self.assertEqual(response.status_code, 200)
