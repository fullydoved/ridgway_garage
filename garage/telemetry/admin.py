"""
Django Admin configuration for Telemetry models.
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import Driver, Team, TeamMembership, JoinRequest, TeamInvitation, Track, Car, Session, Lap, TelemetryData


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ['user', 'display_name', 'iracing_id', 'default_team', 'created_at']
    list_filter = ['created_at', 'default_team']
    search_fields = ['user__username', 'display_name', 'iracing_id']
    raw_id_fields = ['user', 'default_team']


class TeamMembershipInline(admin.TabularInline):
    model = TeamMembership
    extra = 1
    raw_id_fields = ['user']


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'is_public', 'allow_join_requests', 'is_default_team', 'created_at']
    list_filter = ['is_public', 'allow_join_requests', 'is_default_team', 'created_at']
    search_fields = ['name', 'description', 'owner__username']
    raw_id_fields = ['owner']
    inlines = [TeamMembershipInline]


@admin.register(JoinRequest)
class JoinRequestAdmin(admin.ModelAdmin):
    list_display = ['user', 'team', 'status', 'created_at', 'reviewed_by', 'reviewed_at']
    list_filter = ['status', 'created_at', 'reviewed_at']
    search_fields = ['user__username', 'team__name', 'message']
    raw_id_fields = ['user', 'team', 'reviewed_by']
    readonly_fields = ['created_at', 'reviewed_at']


@admin.register(TeamInvitation)
class TeamInvitationAdmin(admin.ModelAdmin):
    list_display = ['team', 'email', 'invited_by', 'status', 'created_at', 'expires_at']
    list_filter = ['status', 'created_at', 'expires_at']
    search_fields = ['email', 'team__name', 'invited_by__username']
    raw_id_fields = ['team', 'invited_by', 'invited_user']
    readonly_fields = ['token', 'created_at', 'accepted_at']


@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ['name', 'configuration', 'length_km', 'turn_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'configuration']


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = ['name', 'car_class', 'created_at']
    list_filter = ['car_class', 'created_at']
    search_fields = ['name', 'car_class']


class LapInline(admin.TabularInline):
    model = Lap
    extra = 0
    fields = ['lap_number', 'lap_time', 'is_valid', 'is_personal_best']
    readonly_fields = ['lap_number', 'lap_time']


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ['driver', 'track_display', 'car_display', 'session_type', 'session_date',
                    'status_display', 'lap_count', 'created_at']
    list_filter = ['session_type', 'processing_status', 'is_public', 'session_date', 'created_at']
    search_fields = ['driver__username', 'track__name', 'car__name']
    raw_id_fields = ['driver', 'team', 'track', 'car']
    readonly_fields = ['processing_started_at', 'processing_completed_at']
    inlines = [LapInline]

    def track_display(self, obj):
        """Display track name or 'Processing...' if not yet detected."""
        if obj.track:
            return str(obj.track)
        elif obj.processing_status == 'completed':
            return '(Unknown)'
        else:
            return 'Processing...'
    track_display.short_description = 'Track'
    track_display.admin_order_field = 'track__name'

    def car_display(self, obj):
        """Display car name or 'Processing...' if not yet detected."""
        if obj.car:
            return str(obj.car)
        elif obj.processing_status == 'completed':
            return '(Unknown)'
        else:
            return 'Processing...'
    car_display.short_description = 'Car'
    car_display.admin_order_field = 'car__name'

    def status_display(self, obj):
        """Display processing status with color coding."""
        colors = {
            'pending': 'orange',
            'processing': 'blue',
            'completed': 'green',
            'failed': 'red',
        }
        color = colors.get(obj.processing_status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_processing_status_display()
        )
    status_display.short_description = 'Status'
    status_display.admin_order_field = 'processing_status'

    def lap_count(self, obj):
        """Display number of laps in the session."""
        count = obj.laps.count()
        if count > 0:
            fastest = obj.laps.filter(is_personal_best=True).first()
            if fastest:
                return f'{count} laps (best: {fastest.lap_time:.3f}s)'
            return f'{count} laps'
        return '-'
    lap_count.short_description = 'Laps'

    fieldsets = (
        ('Session Information', {
            'fields': ('driver', 'team', 'track', 'car', 'session_type', 'session_date')
        }),
        ('File', {
            'fields': ('ibt_file',)
        }),
        ('Processing Status', {
            'fields': ('processing_status', 'processing_started_at', 'processing_completed_at', 'processing_error')
        }),
        ('Environmental Conditions', {
            'fields': ('air_temp', 'track_temp', 'weather_type'),
            'classes': ('collapse',)
        }),
        ('Privacy', {
            'fields': ('is_public',)
        }),
    )


@admin.register(Lap)
class LapAdmin(admin.ModelAdmin):
    list_display = ['session', 'lap_number', 'lap_time', 'is_valid', 'is_personal_best', 'created_at']
    list_filter = ['is_valid', 'is_personal_best', 'created_at']
    search_fields = ['session__driver__username', 'session__track__name']
    raw_id_fields = ['session']


@admin.register(TelemetryData)
class TelemetryDataAdmin(admin.ModelAdmin):
    list_display = ['lap', 'sample_count', 'max_speed', 'avg_speed', 'created_at']
    list_filter = ['created_at']
    search_fields = ['lap__session__driver__username']
    raw_id_fields = ['lap']
    readonly_fields = ['sample_count', 'max_speed', 'avg_speed']

    fieldsets = (
        ('Lap Reference', {
            'fields': ('lap',)
        }),
        ('Summary Statistics', {
            'fields': ('sample_count', 'max_speed', 'avg_speed')
        }),
        ('Telemetry Data', {
            'fields': ('data',),
            'description': 'JSON data containing all telemetry channels'
        }),
    )
