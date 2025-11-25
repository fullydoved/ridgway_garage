"""
API endpoint tests for the Ridgway Garage telemetry app.
"""

import gzip
import json

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from telemetry.models import Session, Lap, TelemetryData, Track, Car, Team, Driver

User = get_user_model()


class APIAuthTest(TestCase):
    """Test API authentication."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testdriver',
            password='testpass123'
        )
        # Driver is auto-created by signal, just get it
        self.driver = Driver.objects.get(user=self.user)
        self.driver.display_name = 'Test Driver'
        self.driver.save()
        self.api_token = self.driver.generate_api_token()
        self.client = Client()

    def test_api_auth_test_with_valid_token(self):
        """Test authentication endpoint with valid token."""
        response = self.client.get(
            reverse('telemetry:api_auth_test'),
            HTTP_AUTHORIZATION=f'Token {self.api_token}'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['authenticated'])
        self.assertEqual(data['username'], 'testdriver')

    def test_api_auth_test_without_token(self):
        """Test authentication endpoint without token."""
        response = self.client.get(reverse('telemetry:api_auth_test'))
        self.assertEqual(response.status_code, 401)

    def test_api_auth_test_with_invalid_token(self):
        """Test authentication endpoint with invalid token."""
        response = self.client.get(
            reverse('telemetry:api_auth_test'),
            HTTP_AUTHORIZATION='Token invalid_token_12345678901234567890'
        )
        self.assertEqual(response.status_code, 401)

    def test_api_auth_test_with_malformed_header(self):
        """Test authentication endpoint with malformed header."""
        response = self.client.get(
            reverse('telemetry:api_auth_test'),
            HTTP_AUTHORIZATION='Bearer token'  # Wrong format
        )
        self.assertEqual(response.status_code, 401)


class APIUploadTest(TestCase):
    """Test API upload endpoint with compression support."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testdriver',
            password='testpass123'
        )
        # Driver is auto-created by signal, just get it
        self.driver = Driver.objects.get(user=self.user)
        self.driver.display_name = 'Test Driver'
        self.driver.save()
        self.api_token = self.driver.generate_api_token()
        self.client = Client()

    def test_api_upload_uncompressed_ibt(self):
        """Test uploading uncompressed IBT file."""
        ibt_data = b"fake ibt content here" * 100
        test_file = SimpleUploadedFile(
            "test_session.ibt",
            ibt_data,
            content_type="application/octet-stream"
        )

        response = self.client.post(
            reverse('telemetry:api_upload'),
            {'file': test_file},
            HTTP_AUTHORIZATION=f'Token {self.api_token}'
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('session_id', data)

        session = Session.objects.get(id=data['session_id'])
        self.assertEqual(session.driver, self.user)
        self.assertEqual(session.processing_status, 'pending')

    def test_api_upload_compressed_ibt(self):
        """Test uploading gzip-compressed IBT file."""
        original_data = b"fake ibt content here" * 100
        compressed_data = gzip.compress(original_data)

        test_file = SimpleUploadedFile(
            "test_session.ibt.gz",
            compressed_data,
            content_type="application/octet-stream"
        )

        response = self.client.post(
            reverse('telemetry:api_upload'),
            {'file': test_file},
            HTTP_AUTHORIZATION=f'Token {self.api_token}'
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data['success'])

        session = Session.objects.get(id=data['session_id'])
        with session.ibt_file.open('rb') as f:
            saved_data = f.read()
        self.assertEqual(saved_data, original_data)  # Should be decompressed

    def test_api_upload_corrupted_gzip(self):
        """Test that corrupted gzip files are rejected."""
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

    def test_api_upload_duplicate_detection(self):
        """Test that duplicate uploads are detected."""
        ibt_data = b"unique ibt content" * 100
        test_file1 = SimpleUploadedFile(
            "session1.ibt",
            ibt_data,
            content_type="application/octet-stream"
        )

        # First upload
        response1 = self.client.post(
            reverse('telemetry:api_upload'),
            {'file': test_file1},
            HTTP_AUTHORIZATION=f'Token {self.api_token}'
        )
        self.assertEqual(response1.status_code, 201)
        first_session_id = response1.json()['session_id']

        # Second upload with same content
        test_file2 = SimpleUploadedFile(
            "session2.ibt",
            ibt_data,
            content_type="application/octet-stream"
        )

        response2 = self.client.post(
            reverse('telemetry:api_upload'),
            {'file': test_file2},
            HTTP_AUTHORIZATION=f'Token {self.api_token}'
        )

        self.assertEqual(response2.status_code, 200)
        data = response2.json()
        self.assertTrue(data['duplicate'])
        self.assertEqual(data['session_id'], first_session_id)

    def test_api_upload_requires_authentication(self):
        """Test that API upload requires valid token."""
        test_file = SimpleUploadedFile(
            "test.ibt",
            b"fake ibt content",
            content_type="application/octet-stream"
        )

        # Without token
        response = self.client.post(
            reverse('telemetry:api_upload'),
            {'file': test_file}
        )
        self.assertEqual(response.status_code, 401)

    def test_api_upload_rejects_invalid_extension(self):
        """Test that non-IBT files are rejected."""
        test_file = SimpleUploadedFile(
            "test.txt",
            b"not an ibt file",
            content_type="text/plain"
        )

        response = self.client.post(
            reverse('telemetry:api_upload'),
            {'file': test_file},
            HTTP_AUTHORIZATION=f'Token {self.api_token}'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_api_upload_rejects_small_file(self):
        """Test that too-small files are rejected."""
        test_file = SimpleUploadedFile(
            "test.ibt",
            b"tiny",  # Less than 1KB
            content_type="application/octet-stream"
        )

        response = self.client.post(
            reverse('telemetry:api_upload'),
            {'file': test_file},
            HTTP_AUTHORIZATION=f'Token {self.api_token}'
        )

        self.assertEqual(response.status_code, 400)


class APILapTelemetryTest(TestCase):
    """Test API lap telemetry endpoint."""

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
            lap_time=100.0,
            is_valid=True
        )

        self.telemetry = TelemetryData.objects.create(
            lap=self.lap,
            data={'Speed': [100, 110, 120], 'Throttle': [0.8, 0.9, 1.0]},
            sample_count=3
        )

    def test_api_lap_telemetry_returns_data(self):
        """Test that lap telemetry endpoint returns data."""
        response = self.client.get(
            reverse('telemetry:api_lap_telemetry', args=[self.lap.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('telemetry', data)
        self.assertIn('Speed', data['telemetry'])

    def test_api_lap_telemetry_requires_login(self):
        """Test that lap telemetry requires authentication."""
        self.client.logout()
        response = self.client.get(
            reverse('telemetry:api_lap_telemetry', args=[self.lap.id])
        )
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_api_lap_telemetry_access_control(self):
        """Test that users cannot access other users' lap data."""
        other_user = User.objects.create_user(username="other", password="testpass123")
        other_ibt = SimpleUploadedFile("other.ibt", b"fake", content_type="application/octet-stream")
        other_session = Session.objects.create(
            driver=other_user,
            track=self.track,
            car=self.car,
            ibt_file=other_ibt,
            processing_status="completed"
        )
        other_lap = Lap.objects.create(
            session=other_session,
            lap_number=1,
            lap_time=100.0
        )

        response = self.client.get(
            reverse('telemetry:api_lap_telemetry', args=[other_lap.id])
        )
        self.assertEqual(response.status_code, 403)


class APIFastestLapsTest(TestCase):
    """Test API fastest laps endpoint."""

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

        # Create some laps
        for i in range(5):
            Lap.objects.create(
                session=self.session,
                lap_number=i + 1,
                lap_time=100.0 + i,
                is_valid=True
            )

    def test_api_fastest_laps_returns_data(self):
        """Test that fastest laps endpoint returns data."""
        response = self.client.get(
            reverse('telemetry:api_fastest_laps'),
            {'track_id': self.track.id, 'car_id': self.car.id}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('user_laps', data)
        self.assertEqual(len(data['user_laps']), 5)

    def test_api_fastest_laps_requires_track_and_car(self):
        """Test that track_id and car_id are required."""
        response = self.client.get(reverse('telemetry:api_fastest_laps'))
        self.assertEqual(response.status_code, 400)

    def test_api_fastest_laps_sorted_by_time(self):
        """Test that laps are sorted by lap time."""
        response = self.client.get(
            reverse('telemetry:api_fastest_laps'),
            {'track_id': self.track.id, 'car_id': self.car.id}
        )

        data = response.json()
        lap_times = [lap['lap_time'] for lap in data['user_laps']]
        self.assertEqual(lap_times, sorted(lap_times))


class APIGenerateChartTest(TestCase):
    """Test API chart generation endpoint."""

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
            lap_time=100.0,
            is_valid=True
        )

        self.telemetry = TelemetryData.objects.create(
            lap=self.lap,
            data={
                'Speed': [100, 110, 120],
                'Throttle': [0.8, 0.9, 1.0],
                'Brake': [0.0, 0.0, 0.0],
                'LapDist': [0, 100, 200]
            },
            sample_count=3
        )

    def test_api_generate_chart_returns_data(self):
        """Test that chart generation endpoint returns chart data."""
        response = self.client.post(
            reverse('telemetry:api_generate_chart'),
            json.dumps({
                'lap_ids': [self.lap.id],
                'channels': ['Speed']
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('chart_json', data)

    def test_api_generate_chart_requires_laps(self):
        """Test that lap_ids are required."""
        response = self.client.post(
            reverse('telemetry:api_generate_chart'),
            json.dumps({'lap_ids': [], 'channels': ['Speed']}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_api_generate_chart_requires_channels(self):
        """Test that channels are required."""
        response = self.client.post(
            reverse('telemetry:api_generate_chart'),
            json.dumps({'lap_ids': [self.lap.id], 'channels': []}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_api_generate_chart_invalid_json(self):
        """Test error handling for invalid JSON."""
        response = self.client.post(
            reverse('telemetry:api_generate_chart'),
            'not json',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)


class APITeammateLapAccessTest(TestCase):
    """Test teammate lap access permissions - the main bug we're investigating."""

    def setUp(self):
        self.client = Client()

        # Create two users who will be teammates
        self.user1 = User.objects.create_user(username="driver1", password="testpass123")
        self.user2 = User.objects.create_user(username="driver2", password="testpass123")

        # Create a third user who is NOT a teammate
        self.stranger = User.objects.create_user(username="stranger", password="testpass123")

        # Create a team and add both users as members
        self.team = Team.objects.create(name="Test Team", owner=self.user1)
        self.team.members.add(self.user1, self.user2)  # Both are teammates
        # Note: stranger is NOT added to the team

        # Create track and car
        self.track = Track.objects.create(name="Test Track")
        self.car = Car.objects.create(name="Test Car")

        # Create a session for user2 (the teammate whose lap we want to view)
        # Note: session.team is NOT set - this is the key scenario!
        self.ibt_file = SimpleUploadedFile("test.ibt", b"fake", content_type="application/octet-stream")
        self.user2_session = Session.objects.create(
            driver=self.user2,
            track=self.track,
            car=self.car,
            ibt_file=self.ibt_file,
            processing_status="completed",
            team=None  # Session not assigned to any team!
        )

        self.user2_lap = Lap.objects.create(
            session=self.user2_session,
            lap_number=1,
            lap_time=100.0,
            is_valid=True
        )

        self.user2_telemetry = TelemetryData.objects.create(
            lap=self.user2_lap,
            data={
                'Speed': [100, 110, 120],
                'Throttle': [0.8, 0.9, 1.0],
                'Brake': [0.0, 0.0, 0.0],
                'LapDist': [0, 100, 200]
            },
            sample_count=3
        )

    def test_teammate_can_access_lap_telemetry(self):
        """
        User1 should be able to view User2's lap because they share team membership,
        even though the session.team is None.
        """
        self.client.login(username="driver1", password="testpass123")

        response = self.client.get(
            reverse('telemetry:api_lap_telemetry', args=[self.user2_lap.id])
        )

        self.assertEqual(response.status_code, 200,
            f"Teammate should have access. Response: {response.json()}")
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('telemetry', data)

    def test_stranger_cannot_access_lap_telemetry(self):
        """
        Stranger should NOT be able to view User2's lap because they don't share any team.
        """
        self.client.login(username="stranger", password="testpass123")

        response = self.client.get(
            reverse('telemetry:api_lap_telemetry', args=[self.user2_lap.id])
        )

        self.assertEqual(response.status_code, 403,
            "Non-teammate should be denied access")

    def test_owner_can_access_own_lap(self):
        """User2 should always be able to access their own lap."""
        self.client.login(username="driver2", password="testpass123")

        response = self.client.get(
            reverse('telemetry:api_lap_telemetry', args=[self.user2_lap.id])
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    def test_teammate_can_generate_chart_with_teammate_lap(self):
        """
        User1 should be able to generate a chart including User2's lap.
        """
        self.client.login(username="driver1", password="testpass123")

        response = self.client.post(
            reverse('telemetry:api_generate_chart'),
            json.dumps({
                'lap_ids': [self.user2_lap.id],
                'channels': ['Speed']
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200,
            f"Teammate should be able to generate chart. Response: {response.json()}")
        data = response.json()
        self.assertTrue(data['success'])

    def test_stranger_cannot_generate_chart_with_others_lap(self):
        """
        Stranger should NOT be able to generate a chart with User2's lap.
        """
        self.client.login(username="stranger", password="testpass123")

        response = self.client.post(
            reverse('telemetry:api_generate_chart'),
            json.dumps({
                'lap_ids': [self.user2_lap.id],
                'channels': ['Speed']
            }),
            content_type='application/json'
        )

        # Should return 404 because no valid laps found (all filtered out)
        self.assertEqual(response.status_code, 404,
            "Non-teammate's lap should be filtered out")

    def test_api_fastest_laps_shows_teammate_laps(self):
        """
        api_fastest_laps should show User2's lap when User1 requests it,
        since they share team membership.
        """
        self.client.login(username="driver1", password="testpass123")

        response = self.client.get(
            reverse('telemetry:api_fastest_laps'),
            {'track_id': self.track.id, 'car_id': self.car.id}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        # User2's lap should appear in teammate_laps
        teammate_lap_ids = [lap['id'] for lap in data['teammate_laps']]
        self.assertIn(self.user2_lap.id, teammate_lap_ids,
            "Teammate's lap should appear in teammate_laps list")

    def test_api_fastest_laps_excludes_stranger_laps(self):
        """
        api_fastest_laps should NOT show stranger's laps.
        """
        # Create a lap for the stranger
        stranger_ibt = SimpleUploadedFile("stranger.ibt", b"fake", content_type="application/octet-stream")
        stranger_session = Session.objects.create(
            driver=self.stranger,
            track=self.track,
            car=self.car,
            ibt_file=stranger_ibt,
            processing_status="completed"
        )
        stranger_lap = Lap.objects.create(
            session=stranger_session,
            lap_number=1,
            lap_time=95.0,  # Faster than user2
            is_valid=True
        )

        self.client.login(username="driver1", password="testpass123")

        response = self.client.get(
            reverse('telemetry:api_fastest_laps'),
            {'track_id': self.track.id, 'car_id': self.car.id}
        )

        data = response.json()
        teammate_lap_ids = [lap['id'] for lap in data['teammate_laps']]

        # Stranger's lap should NOT appear
        self.assertNotIn(stranger_lap.id, teammate_lap_ids,
            "Stranger's lap should NOT appear in teammate_laps")

    def test_debug_team_membership(self):
        """Debug test to verify team membership is set up correctly."""
        # Verify team exists
        self.assertEqual(Team.objects.count(), 1)

        # Verify both users are members
        team_members = list(self.team.members.all())
        self.assertIn(self.user1, team_members, "user1 should be in team")
        self.assertIn(self.user2, team_members, "user2 should be in team")
        self.assertNotIn(self.stranger, team_members, "stranger should NOT be in team")

        # Verify user1's teams include the test team
        user1_teams = list(Team.objects.filter(members=self.user1))
        self.assertIn(self.team, user1_teams)

        # Verify user1 and user2 share a team
        shared_teams = Team.objects.filter(members=self.user1).filter(members=self.user2)
        self.assertTrue(shared_teams.exists(), "user1 and user2 should share at least one team")

        # This is the exact logic from the permission check
        user_teams = Team.objects.filter(members=self.user1)
        driver_in_user_teams = user_teams.filter(members=self.user2).exists()
        self.assertTrue(driver_in_user_teams,
            "Permission check logic should find that user2 is in user1's teams")
