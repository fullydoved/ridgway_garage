"""
Telemetry Data Models for Ridgway Garage

These models store iRacing telemetry data including sessions, laps, and detailed
telemetry information for analysis and comparison.
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid


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
        indexes = [
            models.Index(fields=['iracing_id']),  # Frequently queried for driver lookups
            # Note: api_token already has index via unique=True constraint
        ]

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
    is_default_team = models.BooleanField(default=False, help_text="Default team for new users (only one allowed)")

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
        indexes = [
            models.Index(fields=['is_public']),  # For filtering public teams
            models.Index(fields=['owner']),  # For owner's team listings
            models.Index(fields=['is_default_team']),  # For finding default team
            # Note: name already has index via unique=True constraint
        ]

    def __str__(self):
        return self.name

    def clean(self):
        """Validate that only one team can be the default team."""
        if self.is_default_team:
            # Check if another team is already the default
            existing_default = Team.objects.filter(is_default_team=True).exclude(pk=self.pk).first()
            if existing_default:
                raise ValidationError({
                    'is_default_team': f'Team "{existing_default.name}" is already set as the default team. '
                                      'Only one team can be the default.'
                })

    def save(self, *args, **kwargs):
        """Override save to run validation."""
        self.clean()
        super().save(*args, **kwargs)

    def is_user_member(self, user):
        """Check if a user is a member of this team."""
        if not user.is_authenticated:
            return False
        return self.members.filter(pk=user.pk).exists()

    def get_user_role(self, user):
        """Get user's role in this team, or None if not a member."""
        if not user.is_authenticated:
            return None
        membership = TeamMembership.objects.filter(team=self, user=user).first()
        return membership.role if membership else None

    def is_user_admin(self, user):
        """Check if user has admin privileges (owner or admin role)."""
        if not user.is_authenticated:
            return False
        role = self.get_user_role(user)
        return role in ['owner', 'admin']

    def can_user_request_join(self, user):
        """Check if a user can request to join this team."""
        if not user.is_authenticated:
            return False
        if self.is_user_member(user):
            return False
        if not self.allow_join_requests:
            return False
        # Check if user already has a pending request
        if hasattr(self, 'join_requests'):  # Will be available after JoinRequest model is created
            from telemetry.models import JoinRequest  # Import here to avoid circular import
            if JoinRequest.objects.filter(team=self, user=user, status='pending').exists():
                return False
        return True

    def has_pending_request(self, user):
        """Check if user has a pending join request for this team."""
        if not user.is_authenticated:
            return False
        try:
            from telemetry.models import JoinRequest
            return JoinRequest.objects.filter(team=self, user=user, status='pending').exists()
        except (ImportError, AttributeError):
            # JoinRequest model doesn't exist yet
            return False


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
        indexes = [
            models.Index(fields=['user', 'role']),  # For querying user's teams by role
            models.Index(fields=['team', 'role']),  # For querying team members by role
            # Note: unique_together already creates index on ['team', 'user']
        ]

    def __str__(self):
        return f"{self.user.username} - {self.team.name} ({self.role})"


class JoinRequest(models.Model):
    """
    Join request from a user to join a team.
    Requires approval from team owner or admin.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='join_requests')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='team_join_requests')
    message = models.TextField(
        blank=True,
        help_text="Optional message from user explaining why they want to join"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_join_requests'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['team', 'status']),  # For filtering pending requests
            models.Index(fields=['user', 'status']),  # For user's request history
        ]
        # Constraint: one pending request per user per team
        constraints = [
            models.UniqueConstraint(
                fields=['team', 'user'],
                condition=models.Q(status='pending'),
                name='unique_pending_join_request'
            )
        ]

    def __str__(self):
        return f"{self.user.username} → {self.team.name} ({self.status})"

    def approve(self, approved_by):
        """Approve the join request and add user to team."""
        self.status = 'approved'
        self.reviewed_at = timezone.now()
        self.reviewed_by = approved_by
        self.save()

        # Create team membership
        TeamMembership.objects.create(
            team=self.team,
            user=self.user,
            role='member'
        )

    def reject(self, rejected_by):
        """Reject the join request."""
        self.status = 'rejected'
        self.reviewed_at = timezone.now()
        self.reviewed_by = rejected_by
        self.save()


class TeamInvitation(models.Model):
    """
    Invitation from team owner/admin to user to join the team.
    Uses token-based system for secure invitations.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    ]

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='invitations')
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_team_invitations')
    email = models.EmailField(help_text="Email of invited user")
    invited_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='team_invitations',
        help_text="User object if they exist in the system"
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    message = models.TextField(blank=True, help_text="Optional message from the inviter")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="Invitation expires after 7 days")
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['team', 'status']),  # For filtering pending invitations
            models.Index(fields=['email', 'status']),  # For user's invitation lookup
            models.Index(fields=['token']),  # For token-based lookup
        ]

    def __str__(self):
        return f"{self.team.name} → {self.email} ({self.status})"

    def save(self, *args, **kwargs):
        """Set expiration date if not set."""
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=7)

        # If email matches a user, link the invitation
        if not self.invited_user and self.email:
            try:
                self.invited_user = User.objects.get(email=self.email)
            except User.DoesNotExist:
                pass

        super().save(*args, **kwargs)

    def is_expired(self):
        """Check if invitation has expired."""
        return timezone.now() > self.expires_at

    def accept(self, user):
        """Accept the invitation and add user to team."""
        if self.is_expired():
            self.status = 'expired'
            self.save()
            raise ValidationError("This invitation has expired.")

        if self.status != 'pending':
            raise ValidationError("This invitation has already been processed.")

        self.status = 'accepted'
        self.accepted_at = timezone.now()
        self.invited_user = user
        self.save()

        # Create team membership
        TeamMembership.objects.get_or_create(
            team=self.team,
            user=user,
            defaults={'role': 'member'}
        )

    def decline(self):
        """Decline the invitation."""
        self.status = 'declined'
        self.save()


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

    # Visual assets
    background_image_url = models.URLField(max_length=500, blank=True, null=True, help_text="URL to track background image")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'configuration']
        unique_together = ['name', 'configuration']
        indexes = [
            # Note: unique_together already creates index on ['name', 'configuration']
            models.Index(fields=['name']),  # For partial name searches/lookups
        ]

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

    # Visual assets
    image_url = models.URLField(max_length=500, blank=True, null=True, help_text="URL to car image/silhouette")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['car_class']),  # For filtering by car class
            # Note: name already has index via unique=True constraint
        ]

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
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        help_text="SHA256 hash of uploaded IBT file for duplicate detection"
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

    # Car setup information (extracted from IBT)
    setup_name = models.CharField(max_length=255, blank=True, help_text="Setup filename used during this session")

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
            models.Index(fields=['driver', 'file_hash']),  # Fast duplicate detection
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
            models.Index(fields=['is_personal_best']),  # For querying personal best laps
            models.Index(fields=['is_valid', 'is_personal_best', 'lap_time']),  # Compound index for PB queries
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



