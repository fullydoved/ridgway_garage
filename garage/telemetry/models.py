"""
Telemetry Data Models for Ridgway Garage

These models store iRacing telemetry data including sessions, laps, and detailed
telemetry information for analysis and comparison.
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.utils import timezone


class Driver(models.Model):
    """
    Extended user profile for iRacing drivers.
    One-to-one relationship with Django User model.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='driver_profile')
    iracing_id = models.CharField(max_length=50, blank=True, null=True, help_text="iRacing Member ID")
    display_name = models.CharField(max_length=100, blank=True, help_text="Display name for leaderboards")

    # API Authentication
    api_token = models.CharField(
        max_length=64,
        blank=True,
        unique=True,
        null=True,
        help_text="API token for telemetry client authentication"
    )

    # Settings and preferences
    default_team = models.ForeignKey('Team', on_delete=models.SET_NULL, null=True, blank=True, related_name='default_members')
    timezone = models.CharField(max_length=50, default='UTC')

    # Notification preferences
    enable_pb_notifications = models.BooleanField(
        default=True,
        help_text="Enable Discord notifications when you set a personal best"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['user__username']

    def __str__(self):
        return self.display_name or self.user.username

    def generate_api_token(self):
        """Generate a new API token for this driver."""
        import secrets
        self.api_token = secrets.token_urlsafe(48)
        self.save(update_fields=['api_token'])
        return self.api_token


class Team(models.Model):
    """
    Racing team for sharing and comparing telemetry data.
    Members can view each other's telemetry and leaderboards.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_teams')
    members = models.ManyToManyField(User, through='TeamMembership', related_name='teams')

    # Privacy settings
    is_public = models.BooleanField(default=False, help_text="Allow public viewing of team telemetry")
    allow_join_requests = models.BooleanField(default=True, help_text="Allow users to request to join")

    # Discord integration
    discord_webhook_url = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text="Discord webhook URL for sharing laps to team channel"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class TeamMembership(models.Model):
    """
    Through model for Team-User relationship with roles.
    """
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]

    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['team', 'user']
        ordering = ['team', '-joined_at']

    def __str__(self):
        return f"{self.user.username} - {self.team.name} ({self.role})"


class Track(models.Model):
    """
    iRacing track information including configuration and GPS bounds.
    """
    name = models.CharField(max_length=200, help_text="Track name (e.g., 'Road Atlanta')")
    configuration = models.CharField(max_length=100, blank=True, help_text="Configuration (e.g., 'Full Course')")

    # Track details
    length_km = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True, help_text="Track length in kilometers")
    turn_count = models.IntegerField(null=True, blank=True, help_text="Number of turns")

    # GPS bounds for map display (calculated from telemetry data)
    gps_lat_min = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    gps_lat_max = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    gps_lng_min = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    gps_lng_max = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'configuration']
        unique_together = ['name', 'configuration']

    def __str__(self):
        if self.configuration:
            return f"{self.name} - {self.configuration}"
        return self.name


class Car(models.Model):
    """
    iRacing car/vehicle information.
    """
    name = models.CharField(max_length=200, unique=True, help_text="Car name (e.g., 'Mazda MX-5 Cup')")
    car_class = models.CharField(max_length=100, blank=True, default='', help_text="Car class (e.g., 'Sports Car')")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Session(models.Model):
    """
    A telemetry session from an uploaded IBT file or live stream.
    Contains metadata about the session and references to uploaded files.
    """
    SESSION_TYPE_CHOICES = [
        ('practice', 'Practice'),
        ('qualifying', 'Qualifying'),
        ('race', 'Race'),
        ('time_trial', 'Time Trial'),
        ('testing', 'Testing'),
        ('imported', 'Imported Lap'),
    ]

    PROCESSING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    CONNECTION_STATE_CHOICES = [
        ('disconnected', 'Disconnected'),
        ('connected', 'Connected'),
        ('error', 'Error'),
    ]

    # Relationships
    driver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='sessions', null=True, blank=True)
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name='sessions', null=True, blank=True)

    # Session details
    session_type = models.CharField(max_length=20, choices=SESSION_TYPE_CHOICES, default='practice')
    session_date = models.DateTimeField(default=timezone.now, help_text="When the session occurred")
    driver_name = models.CharField(max_length=100, blank=True, default='', help_text="Driver name from iRacing (not username)")

    # File reference
    ibt_file = models.FileField(
        upload_to='telemetry/%Y/%m/%d/',
        validators=[FileExtensionValidator(['ibt', 'IBT'])],
        help_text="Uploaded IBT telemetry file",
        null=True,
        blank=True
    )

    # Processing status
    processing_status = models.CharField(max_length=20, choices=PROCESSING_STATUS_CHOICES, default='pending')
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_completed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True, help_text="Error message if processing failed")

    # Live streaming status
    is_live = models.BooleanField(default=False, help_text="Currently streaming live telemetry")
    connection_state = models.CharField(
        max_length=20,
        choices=CONNECTION_STATE_CHOICES,
        default='disconnected',
        help_text="Live connection state"
    )
    last_telemetry_update = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of last received telemetry data"
    )

    # Environmental conditions (extracted from IBT)
    air_temp = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Air temperature in Celsius")
    track_temp = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Track temperature in Celsius")
    weather_type = models.CharField(max_length=50, blank=True, help_text="Weather condition")

    # Privacy
    is_public = models.BooleanField(default=False, help_text="Allow public viewing")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-session_date', '-created_at']
        indexes = [
            models.Index(fields=['driver', 'track', 'car']),
            models.Index(fields=['processing_status']),
            models.Index(fields=['-session_date']),
            models.Index(fields=['is_live', '-last_telemetry_update']),
        ]

    def __str__(self):
        track_name = self.track.name if self.track else "Unknown Track"
        car_name = self.car.name if self.car else "Unknown Car"
        return f"{self.driver.username} - {track_name} ({car_name}) - {self.session_date.strftime('%Y-%m-%d')}"


class Lap(models.Model):
    """
    Individual lap within a session with timing data.
    References telemetry data for detailed analysis.
    """
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='laps')
    lap_number = models.IntegerField(help_text="Lap number in the session")

    # Timing data
    lap_time = models.DecimalField(max_digits=10, decimal_places=4, help_text="Lap time in seconds")
    sector1_time = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="Sector 1 time")
    sector2_time = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="Sector 2 time")
    sector3_time = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="Sector 3 time")

    # Lap validity
    is_valid = models.BooleanField(default=True, help_text="Whether lap is clean (no off-tracks)")
    is_personal_best = models.BooleanField(default=False, help_text="Personal best lap for this track/car combo")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['session', 'lap_number']
        unique_together = ['session', 'lap_number']
        indexes = [
            models.Index(fields=['session', 'lap_time']),
            models.Index(fields=['is_valid', 'lap_time']),
        ]

    def __str__(self):
        return f"Lap {self.lap_number} - {self.lap_time}s ({self.session.driver.username})"


class TelemetryData(models.Model):
    """
    Detailed telemetry data for a specific lap.
    Stores arrays of data points (60Hz sampling) as JSON for flexibility.

    Data includes: distance, time, speed, throttle, brake, steering, gear, RPM,
    tire temps/pressure, fuel, GPS coordinates, and 200+ other iRacing data points.
    """
    lap = models.OneToOneField(Lap, on_delete=models.CASCADE, related_name='telemetry')

    # Telemetry data stored as JSON
    # Each key is a telemetry channel name, value is array of samples
    # Example structure:
    # {
    #   "Distance": [0.0, 5.2, 10.5, ...],
    #   "Speed": [0.0, 45.2, 89.3, ...],
    #   "Throttle": [0.0, 0.5, 1.0, ...],
    #   "Brake": [0.0, 0.0, 0.0, ...],
    #   "Steering": [0.0, -0.2, -0.3, ...],
    #   "RPM": [1000, 3500, 5200, ...],
    #   "Gear": [1, 2, 3, ...],
    #   "LFtempCL": [80.2, 82.1, 85.3, ...],  # Left front tire temp
    #   "Lat": [33.123456, 33.123457, ...],
    #   "Lon": [-84.123456, -84.123457, ...],
    #   ... and many more
    # }
    data = models.JSONField(help_text="Telemetry data arrays indexed by channel name")

    # Quick access fields (denormalized for performance)
    sample_count = models.IntegerField(help_text="Number of samples in this lap")
    max_speed = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text="Maximum speed in km/h")
    avg_speed = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text="Average speed in km/h")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Telemetry data"

    def __str__(self):
        return f"Telemetry for {self.lap}"


class Analysis(models.Model):
    """
    A saved lap comparison analysis (similar to Garage 61).
    Users create an analysis, add laps to it, and can view/compare them later.
    """
    # Basic info
    name = models.CharField(max_length=200, help_text="Analysis name (e.g. 'Baseline vs New Setup')")
    description = models.TextField(blank=True, help_text="Optional notes about this analysis")

    # Ownership
    driver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='analyses')
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='analyses',
                            help_text="Optional: share with team")

    # Laps in this analysis (many-to-many)
    laps = models.ManyToManyField(Lap, related_name='analyses', blank=True,
                                 help_text="Laps to compare in this analysis")

    # Filter context (for convenience)
    track = models.ForeignKey(Track, on_delete=models.SET_NULL, null=True, blank=True,
                             help_text="Track these laps are from (optional, for filtering)")
    car = models.ForeignKey(Car, on_delete=models.SET_NULL, null=True, blank=True,
                           help_text="Car these laps are from (optional, for filtering)")

    # Privacy
    is_public = models.BooleanField(default=False, help_text="Allow public viewing")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name_plural = "Analyses"
        indexes = [
            models.Index(fields=['driver', '-updated_at']),
        ]

    def __str__(self):
        return f"{self.name} ({self.driver.username})"

    def lap_count(self):
        """Return number of laps in this analysis"""
        return self.laps.count()

    def fastest_lap(self):
        """Return the fastest lap in this analysis"""
        return self.laps.filter(is_valid=True).order_by('lap_time').first()


class SystemUpdate(models.Model):
    """
    Track system update history and status.
    Records when updates are initiated, their progress, and outcomes.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('rolled_back', 'Rolled Back'),
    ]

    # Update details
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='triggered_updates')
    old_version = models.CharField(max_length=50, help_text="Version before update")
    new_version = models.CharField(max_length=50, blank=True, help_text="Version after update")
    old_commit = models.CharField(max_length=50, blank=True, help_text="Git commit before update")
    new_commit = models.CharField(max_length=50, blank=True, help_text="Git commit after update")

    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    status_message = models.TextField(blank=True, help_text="Current status or error message")
    progress = models.IntegerField(default=0, help_text="Update progress percentage (0-100)")

    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Logs
    log_file = models.TextField(blank=True, help_text="Path to update log file")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Update to {self.new_version or 'pending'} - {self.status} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"

    @property
    def duration(self):
        """Calculate update duration"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
