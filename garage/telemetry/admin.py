"""
Django Admin configuration for Telemetry models.
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import Driver, Team, TeamMembership, Track, Car, Session, Lap, TelemetryData, Analysis, SystemUpdate


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
    list_display = ['name', 'owner', 'is_public', 'allow_join_requests', 'created_at']
    list_filter = ['is_public', 'allow_join_requests', 'created_at']
    search_fields = ['name', 'description', 'owner__username']
    raw_id_fields = ['owner']
    inlines = [TeamMembershipInline]


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


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ['name', 'driver', 'lap_count_display', 'track', 'car', 'is_public', 'updated_at']
    list_filter = ['is_public', 'track', 'car', 'created_at', 'updated_at']
    search_fields = ['name', 'description', 'driver__username']
    raw_id_fields = ['driver', 'team', 'track', 'car']
    filter_horizontal = ['laps']

    def lap_count_display(self, obj):
        """Display number of laps in analysis."""
        count = obj.lap_count()
        fastest = obj.fastest_lap()
        if fastest:
            return f'{count} laps (fastest: {fastest.lap_time:.3f}s)'
        return f'{count} laps'
    lap_count_display.short_description = 'Laps'

    fieldsets = (
        ('Analysis Information', {
            'fields': ('name', 'description', 'driver', 'team')
        }),
        ('Context (Optional)', {
            'fields': ('track', 'car'),
            'description': 'Track and car for filtering (optional)'
        }),
        ('Laps', {
            'fields': ('laps',),
            'description': 'Select laps to include in this analysis'
        }),
        ('Privacy', {
            'fields': ('is_public',)
        }),
    )


@admin.register(SystemUpdate)
class SystemUpdateAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'status_display', 'old_version', 'new_version', 'triggered_by', 'progress_display', 'duration_display']
    list_filter = ['status', 'created_at']
    search_fields = ['old_version', 'new_version', 'status_message']
    readonly_fields = ['created_at', 'updated_at', 'started_at', 'completed_at', 'old_commit', 'new_commit', 'duration_display']
    raw_id_fields = ['triggered_by']

    def status_display(self, obj):
        """Display status with color coding."""
        colors = {
            'pending': 'orange',
            'running': 'blue',
            'success': 'green',
            'failed': 'red',
            'rolled_back': 'purple',
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    status_display.admin_order_field = 'status'

    def progress_display(self, obj):
        """Display progress bar."""
        if obj.status == 'running':
            return format_html(
                '<div style="width: 100px; background-color: #f0f0f0; border-radius: 3px;">'
                '<div style="width: {}px; background-color: #4CAF50; height: 20px; border-radius: 3px; text-align: center; color: white; line-height: 20px;">{} %</div>'
                '</div>',
                obj.progress,
                obj.progress
            )
        return f'{obj.progress}%'
    progress_display.short_description = 'Progress'

    def duration_display(self, obj):
        """Display update duration."""
        duration = obj.duration
        if duration:
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            return f'{minutes}m {seconds}s'
        return '-'
    duration_display.short_description = 'Duration'

    fieldsets = (
        ('Update Information', {
            'fields': ('triggered_by', 'old_version', 'new_version', 'old_commit', 'new_commit')
        }),
        ('Status', {
            'fields': ('status', 'status_message', 'progress')
        }),
        ('Timing', {
            'fields': ('created_at', 'started_at', 'completed_at', 'duration_display')
        }),
        ('Logs', {
            'fields': ('log_file',),
            'classes': ('collapse',)
        }),
    )
