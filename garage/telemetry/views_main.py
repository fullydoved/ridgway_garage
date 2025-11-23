"""
Views for the Ridgway Garage telemetry app.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db.models import Count

from .models import Session, Lap, TelemetryData, Track, Car, Team
from .forms import SessionUploadForm


# ============================================================================
# Helper Functions & Decorators
# ============================================================================

def api_token_required(view_func):
    """
    Decorator for API views that require token authentication.

    Validates the Authorization header contains a valid API token and
    sets request.user to the authenticated user.

    Usage:
        @api_token_required
        def my_api_view(request):
            # request.user is now the authenticated user
            ...

    Returns 401 JSON response if authentication fails.
    """
    from functools import wraps
    from django.http import JsonResponse
    from .models import Driver

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check for token in Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        if not auth_header.startswith('Token '):
            return JsonResponse({
                'error': 'Missing or invalid Authorization header'
            }, status=401)

        token_key = auth_header.replace('Token ', '').strip()

        # Validate token format (UUIDs are at least 32 chars)
        if not token_key or len(token_key) < 32:
            return JsonResponse({
                'error': 'Invalid token format'
            }, status=401)

        # Find driver by API token
        try:
            driver_profile = Driver.objects.select_related('user').get(api_token=token_key)
            # Set the authenticated user on the request
            request.user = driver_profile.user
        except Driver.DoesNotExist:
            return JsonResponse({
                'error': 'Invalid API token'
            }, status=401)

        # Call the original view function
        return view_func(request, *args, **kwargs)

    return wrapper


def build_lap_export_data(lap, telemetry):
    """
    Build standardized export data structure for a lap with telemetry.

    Args:
        lap: Lap model instance
        telemetry: TelemetryData model instance

    Returns:
        dict: Export data structure with lap, session, driver, and telemetry data
    """
    from datetime import datetime

    export_data = {
        'format_version': '1.0',
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'lap': {
            'lap_number': lap.lap_number,
            'lap_time': float(lap.lap_time),
            'sector1_time': float(lap.sector1_time) if lap.sector1_time else None,
            'sector2_time': float(lap.sector2_time) if lap.sector2_time else None,
            'sector3_time': float(lap.sector3_time) if lap.sector3_time else None,
            'is_valid': lap.is_valid,
        },
        'session': {
            'track_name': lap.session.track.name if lap.session.track else 'Unknown Track',
            'track_config': lap.session.track.configuration if lap.session.track else '',
            'car_name': lap.session.car.name if lap.session.car else 'Unknown Car',
            'session_type': lap.session.session_type,
            'session_date': lap.session.session_date.isoformat(),
            'air_temp': float(lap.session.air_temp) if lap.session.air_temp else None,
            'track_temp': float(lap.session.track_temp) if lap.session.track_temp else None,
            'weather_type': lap.session.weather_type or '',
        },
        'driver': {
            'display_name': lap.session.driver_name or lap.session.driver.username,
        },
        'telemetry': {
            'sample_count': telemetry.sample_count,
            'max_speed': float(telemetry.max_speed) if telemetry.max_speed else None,
            'avg_speed': float(telemetry.avg_speed) if telemetry.avg_speed else None,
            'data': telemetry.data,
        }
    }

    return export_data


def compress_lap_export_data(export_data):
    """
    Convert export data to JSON and compress with gzip.

    Args:
        export_data: Dictionary containing lap export data

    Returns:
        bytes: Gzip-compressed JSON data
    """
    import json
    import gzip

    json_data = json.dumps(export_data, indent=2)
    compressed_data = gzip.compress(json_data.encode('utf-8'))

    return compressed_data


def import_lap_from_data(data, user):
    """
    Import a lap from parsed export data structure.

    Creates Session, Lap, and TelemetryData objects from the standardized
    export format. Used by both file upload and protocol import.

    Args:
        data: Dictionary containing lap export data (format_version 1.0)
        user: Django User who is importing the lap

    Returns:
        Lap: The created Lap object

    Raises:
        ValueError: If data format is invalid or missing required fields
    """
    from django.utils.dateparse import parse_datetime
    from django.utils import timezone
    from decimal import Decimal

    # Validate format version
    if data.get('format_version') != '1.0':
        raise ValueError(f"Unsupported format version: {data.get('format_version')}")

    # Validate required fields
    required_fields = ['lap', 'session', 'driver', 'telemetry']
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Invalid data format: missing '{field}' field")

    # Get or create Track
    track_name = data['session'].get('track_name', 'Unknown Track')
    track_config = data['session'].get('track_config', '')
    track, _ = Track.objects.get_or_create(
        name=track_name,
        configuration=track_config,
        defaults={'name': track_name, 'configuration': track_config, 'background_image_url': ''}
    )

    # Get or create Car
    car_name = data['session'].get('car_name', 'Unknown Car')
    car, _ = Car.objects.get_or_create(
        name=car_name,
        defaults={'name': car_name, 'image_url': ''}
    )

    # Parse session date
    try:
        session_date = parse_datetime(data['session']['session_date'])
        if not session_date:
            session_date = timezone.now()
    except:
        session_date = timezone.now()

    # Create Session
    session = Session.objects.create(
        driver=user,
        team=user.driver_profile.default_team if hasattr(user, 'driver_profile') else None,
        track=track,
        car=car,
        session_type='imported',
        session_date=session_date,
        processing_status='completed',
        air_temp=Decimal(str(data['session']['air_temp'])) if data['session'].get('air_temp') is not None else None,
        track_temp=Decimal(str(data['session']['track_temp'])) if data['session'].get('track_temp') is not None else None,
        weather_type=data['session'].get('weather_type', ''),
        is_public=False,
    )

    # Create Lap
    lap_data = data['lap']
    lap = Lap.objects.create(
        session=session,
        lap_number=lap_data.get('lap_number', 1),
        lap_time=Decimal(str(lap_data['lap_time'])),
        sector1_time=Decimal(str(lap_data['sector1_time'])) if lap_data.get('sector1_time') is not None else None,
        sector2_time=Decimal(str(lap_data['sector2_time'])) if lap_data.get('sector2_time') is not None else None,
        sector3_time=Decimal(str(lap_data['sector3_time'])) if lap_data.get('sector3_time') is not None else None,
        is_valid=lap_data.get('is_valid', True),
    )

    # Create TelemetryData
    telemetry_data = data['telemetry']
    TelemetryData.objects.create(
        lap=lap,
        data=telemetry_data['data'],
        sample_count=telemetry_data.get('sample_count', len(telemetry_data['data'].get('Distance', []))),
        max_speed=Decimal(str(telemetry_data['max_speed'])) if telemetry_data.get('max_speed') is not None else None,
        avg_speed=Decimal(str(telemetry_data['avg_speed'])) if telemetry_data.get('avg_speed') is not None else None,
    )

    return lap


# ============================================================================
# Views
# ============================================================================

def home(request):
    """
    Home/Dashboard view showing stats and recent sessions.
    """
    context = {
        'stats': {},
        'recent_sessions': [],
    }

    if request.user.is_authenticated:
        # User stats
        user_sessions = Session.objects.filter(driver=request.user)

        context['stats'] = {
            'total_sessions': user_sessions.count(),
            'total_laps': Lap.objects.filter(session__driver=request.user).count(),
            'best_lap': Lap.objects.filter(
                session__driver=request.user,
                is_valid=True,
                lap_time__gt=0  # Exclude laps with 0 or negative lap times
            ).select_related('session', 'session__track', 'session__car').order_by('lap_time').first(),
            'processing': user_sessions.filter(processing_status='processing').count(),
        }

        # Generate sparkline charts for sessions and laps
        from .utils.charts import create_sessions_sparkline, create_laps_sparkline
        context['sessions_sparkline'] = create_sessions_sparkline(request.user, weeks=12)
        context['laps_sparkline'] = create_laps_sparkline(request.user, weeks=12)

        # Recent sessions (last 5) - exclude sessions with 0 laps
        recent_sessions = user_sessions.select_related(
            'track', 'car', 'team'
        ).prefetch_related('laps').annotate(
            lap_count=Count('laps')
        ).filter(lap_count__gt=0).order_by('-session_date')[:10]  # Get more to filter

        # Add best lap for each session and filter out sessions with no valid laps
        sessions_with_valid_laps = []
        for session in recent_sessions:
            session.best_lap = session.laps.filter(is_valid=True, lap_time__gt=0).order_by('lap_time').first()
            if session.best_lap:  # Only include sessions that have at least one valid lap
                sessions_with_valid_laps.append(session)
            if len(sessions_with_valid_laps) >= 5:  # Stop once we have 5 valid sessions
                break

        context['recent_sessions'] = sessions_with_valid_laps

        # Get lap time progression data for chart (last 20 sessions with laps)
        from .utils.charts import create_lap_time_progression_chart
        sessions_with_laps = user_sessions.select_related('track', 'car').prefetch_related('laps').annotate(
            lap_count=Count('laps')
        ).filter(lap_count__gt=0).order_by('-session_date')[:20]

        progression_data = []
        for session in sessions_with_laps:
            best_lap = session.laps.filter(is_valid=True, lap_time__gt=0).order_by('lap_time').first()
            if best_lap:
                progression_data.append({
                    'session_date': session.session_date,
                    'best_lap_time': float(best_lap.lap_time),
                    'track_name': session.track.name if session.track else 'Unknown',
                    'car_name': session.car.name if session.car else 'Unknown',
                })

        # Reverse to show chronological order (oldest to newest)
        progression_data.reverse()

        if progression_data:
            context['progression_chart'] = create_lap_time_progression_chart(progression_data)
        else:
            context['progression_chart'] = None

    return render(request, 'telemetry/home.html', context)


@login_required
def dashboard_analysis(request):
    """
    ATLAS-style telemetry analysis dashboard with 3-column layout.

    Features:
    - Left: Channel selector (checkboxes for telemetry channels)
    - Middle: Dynamic charts and track map
    - Right: Fastest laps list (user + teammates)

    Default view: Shows best lap from most recent session vs personal best
    """
    print("=" * 80)
    print(f"[DEBUG] dashboard_analysis VIEW CALLED")
    print(f"[DEBUG] Request user: {request.user}")
    print(f"[DEBUG] Is authenticated: {request.user.is_authenticated}")
    print("=" * 80)

    context = {
        'initial_laps': [],
        'tracks': [],
        'cars': [],
        'selected_track': None,
        'selected_car': None,
        'preloaded_lap_id': None,
    }

    if not request.user.is_authenticated:
        return redirect('account_login')

    print(f"[DEBUG] dashboard_analysis called for user: {request.user.username}")

    # Get list of tracks and cars user has driven (for dropdowns)
    context['tracks'] = Track.objects.filter(
        sessions__driver=request.user
    ).distinct().order_by('name')

    context['cars'] = Car.objects.filter(
        sessions__driver=request.user
    ).distinct().order_by('name')

    # Check if a specific lap was requested via query parameter
    lap_id = request.GET.get('lap')
    session_id = request.GET.get('session')

    if lap_id:
        print(f"[DEBUG] Preloading lap ID from query parameter: {lap_id}")
        try:
            preload_lap = Lap.objects.select_related('session', 'session__track', 'session__car').get(
                id=lap_id,
                session__driver=request.user
            )
            context['preloaded_lap_id'] = preload_lap.id
            context['selected_track'] = preload_lap.session.track
            context['selected_car'] = preload_lap.session.car
            print(f"[DEBUG] Successfully preloaded lap {lap_id}")

            # Continue to channel_groups definition at end
            # (we don't return early to avoid duplicating channel_groups dict)

        except Lap.DoesNotExist:
            print(f"[DEBUG] Lap {lap_id} not found or doesn't belong to user")
            # Continue with default behavior
            pass

    elif session_id:
        print(f"[DEBUG] Preloading all laps from session ID: {session_id}")
        try:
            session = Session.objects.select_related('track', 'car').prefetch_related('laps').get(
                id=session_id,
                driver=request.user
            )
            # Get all valid laps from this session ordered by lap number
            valid_laps = session.laps.filter(is_valid=True, lap_time__gt=0).order_by('lap_number')

            if valid_laps.exists():
                # Store lap IDs as comma-separated string for JavaScript
                lap_ids = ','.join(str(lap.id) for lap in valid_laps)
                context['preloaded_session_laps'] = lap_ids
                context['selected_track'] = session.track
                context['selected_car'] = session.car
                print(f"[DEBUG] Successfully preloaded {valid_laps.count()} laps from session {session_id}")
            else:
                print(f"[DEBUG] No valid laps found in session {session_id}")

        except Session.DoesNotExist:
            print(f"[DEBUG] Session {session_id} not found or doesn't belong to user")
            # Continue with default behavior
            pass

    # Only do default lap loading if no lap was preloaded
    if not context['preloaded_lap_id']:
        # Get most recent session with valid laps (lap_time > 0)
        recent_sessions = Session.objects.filter(
            driver=request.user,
            processing_status='completed'
        ).prefetch_related('laps').annotate(
            lap_count=Count('laps')
        ).filter(lap_count__gt=0).order_by('-session_date')[:10]

        recent_session = None
        recent_best_lap = None

        # Find first session with at least one valid lap
        for session in recent_sessions:
            best_lap = session.laps.filter(
                is_valid=True,
                lap_time__gt=0
            ).order_by('lap_time').first()

            if best_lap:
                recent_session = session
                recent_best_lap = best_lap
                break

        print(f"[DEBUG] recent_session: {recent_session}")
        if recent_session:
            print(f"[DEBUG] recent_session ID: {recent_session.id}")
            print(f"[DEBUG] recent_best_lap: {recent_best_lap}")
            if recent_best_lap:
                print(f"[DEBUG] Found best lap ID: {recent_best_lap.id}, time: {recent_best_lap.lap_time}")
                context['selected_track'] = recent_session.track
                context['selected_car'] = recent_session.car
                context['initial_laps'].append(recent_best_lap)
                print(f"[DEBUG] Set selected_track: {context['selected_track']}, selected_car: {context['selected_car']}")

                # Get personal best for this track/car combination
                if recent_session.track and recent_session.car:
                    personal_best = Lap.objects.filter(
                        session__driver=request.user,
                        session__track=recent_session.track,
                        session__car=recent_session.car,
                        is_valid=True,
                        lap_time__gt=0
                    ).exclude(
                        id=recent_best_lap.id  # Don't include the same lap
                    ).order_by('lap_time').first()

                    if personal_best:
                        context['initial_laps'].append(personal_best)

    # DEBUG: Log what we're passing to template
    print(f"[DEBUG] Final context before render:")
    print(f"  initial_laps: {len(context['initial_laps'])} laps")
    if context['initial_laps']:
        print(f"  Lap IDs: {[lap.id for lap in context['initial_laps']]}")
    print(f"  selected_track: {context['selected_track']}")
    print(f"  selected_car: {context['selected_car']}")
    print(f"  tracks count: {context['tracks'].count()}")
    print(f"  cars count: {context['cars'].count()}")
    print("=" * 80)

    # Define available telemetry channels grouped by category
    context['channel_groups'] = {
        'core': {
            'name': 'Core Racing',
            'channels': [
                {'id': 'Speed', 'label': 'Speed', 'default': True},
                {'id': 'Throttle', 'label': 'Throttle', 'default': True},
                {'id': 'Brake', 'label': 'Brake', 'default': True},
                {'id': 'Gear', 'label': 'Gear', 'default': True},
                {'id': 'RPM', 'label': 'RPM', 'default': True},
            ]
        },
        'steering': {
            'name': 'Steering & Inputs',
            'channels': [
                {'id': 'SteeringWheelAngle', 'label': 'Steering Angle', 'default': True},
                {'id': 'Clutch', 'label': 'Clutch', 'default': False},
            ]
        },
        'tires': {
            'name': 'Tire Temperatures',
            'channels': [
                {'id': 'LFtempL', 'label': 'LF Temp (Left)', 'default': False},
                {'id': 'LFtempM', 'label': 'LF Temp (Middle)', 'default': False},
                {'id': 'LFtempR', 'label': 'LF Temp (Right)', 'default': False},
                {'id': 'RFtempL', 'label': 'RF Temp (Left)', 'default': False},
                {'id': 'RFtempM', 'label': 'RF Temp (Middle)', 'default': False},
                {'id': 'RFtempR', 'label': 'RF Temp (Right)', 'default': False},
                {'id': 'LRtempL', 'label': 'LR Temp (Left)', 'default': False},
                {'id': 'LRtempM', 'label': 'LR Temp (Middle)', 'default': False},
                {'id': 'LRtempR', 'label': 'LR Temp (Right)', 'default': False},
                {'id': 'RRtempL', 'label': 'RR Temp (Left)', 'default': False},
                {'id': 'RRtempM', 'label': 'RR Temp (Middle)', 'default': False},
                {'id': 'RRtempR', 'label': 'RR Temp (Right)', 'default': False},
            ]
        },
        'pressure': {
            'name': 'Tire Pressure',
            'channels': [
                {'id': 'LFcoldPressure', 'label': 'LF Pressure', 'default': False},
                {'id': 'RFcoldPressure', 'label': 'RF Pressure', 'default': False},
                {'id': 'LRcoldPressure', 'label': 'LR Pressure', 'default': False},
                {'id': 'RRcoldPressure', 'label': 'RR Pressure', 'default': False},
            ]
        },
        'suspension': {
            'name': 'Suspension & Ride Height',
            'channels': [
                {'id': 'LFrideHeight', 'label': 'LF Ride Height', 'default': False},
                {'id': 'RFrideHeight', 'label': 'RF Ride Height', 'default': False},
                {'id': 'LRrideHeight', 'label': 'LR Ride Height', 'default': False},
                {'id': 'RRrideHeight', 'label': 'RR Ride Height', 'default': False},
                {'id': 'LFshockDefl', 'label': 'LF Shock Deflection', 'default': False},
                {'id': 'RFshockDefl', 'label': 'RF Shock Deflection', 'default': False},
                {'id': 'LRshockDefl', 'label': 'LR Shock Deflection', 'default': False},
                {'id': 'RRshockDefl', 'label': 'RR Shock Deflection', 'default': False},
                {'id': 'LFshockVel', 'label': 'LF Shock Velocity', 'default': False},
                {'id': 'RFshockVel', 'label': 'RF Shock Velocity', 'default': False},
                {'id': 'LRshockVel', 'label': 'LR Shock Velocity', 'default': False},
                {'id': 'RRshockVel', 'label': 'RR Shock Velocity', 'default': False},
            ]
        },
        'acceleration': {
            'name': 'G-Forces',
            'channels': [
                {'id': 'LatAccel', 'label': 'Lateral Acceleration', 'default': False},
                {'id': 'LongAccel', 'label': 'Longitudinal Acceleration', 'default': False},
                {'id': 'VertAccel', 'label': 'Vertical Acceleration', 'default': False},
            ]
        },
        'orientation': {
            'name': 'Orientation',
            'channels': [
                {'id': 'Roll', 'label': 'Roll', 'default': False},
                {'id': 'Pitch', 'label': 'Pitch', 'default': False},
                {'id': 'Yaw', 'label': 'Yaw', 'default': False},
                {'id': 'RollRate', 'label': 'Roll Rate', 'default': False},
                {'id': 'PitchRate', 'label': 'Pitch Rate', 'default': False},
                {'id': 'YawRate', 'label': 'Yaw Rate', 'default': False},
            ]
        },
        'fuel': {
            'name': 'Fuel',
            'channels': [
                {'id': 'FuelLevel', 'label': 'Fuel Level', 'default': False},
                {'id': 'FuelLevelPct', 'label': 'Fuel Level %', 'default': False},
            ]
        },
    }

    return render(request, 'telemetry/dashboard_analysis.html', context)


@login_required
def session_list(request):
    """
    List all sessions for the logged-in user (excluding sessions with 0 laps).
    """
    sessions = Session.objects.filter(
        driver=request.user
    ).select_related('track', 'car', 'team').prefetch_related('laps').annotate(
        lap_count=Count('laps')
    ).filter(lap_count__gt=0).order_by('-session_date')

    # Filter options
    track_filter = request.GET.get('track')
    car_filter = request.GET.get('car')
    status_filter = request.GET.get('status')

    if track_filter:
        sessions = sessions.filter(track_id=track_filter)
    if car_filter:
        sessions = sessions.filter(car_id=car_filter)
    if status_filter:
        sessions = sessions.filter(processing_status=status_filter)

    # Get filter options
    tracks = Track.objects.filter(sessions__driver=request.user).distinct()
    cars = Car.objects.filter(sessions__driver=request.user).distinct()

    # Add best lap and valid laps for each session
    for session in sessions:
        session.valid_laps = session.laps.filter(is_valid=True, lap_time__gt=0).order_by('lap_number')
        session.best_lap = session.valid_laps.order_by('lap_time').first() if session.valid_laps else None

    context = {
        'sessions': sessions,
        'tracks': tracks,
        'cars': cars,
        'current_track': track_filter,
        'current_car': car_filter,
        'current_status': status_filter,
    }

    return render(request, 'telemetry/session_list.html', context)


@login_required
def upload(request):
    """
    Upload IBT telemetry file.
    """
    if request.method == 'POST':
        form = SessionUploadForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            session = form.save(commit=False)
            session.driver = request.user
            session.processing_status = 'pending'
            session.save()

            # Queue Celery task for processing
            from .tasks import parse_ibt_file
            parse_ibt_file.delay(session.id)

            messages.success(
                request,
                'File uploaded successfully! Your telemetry is being processed. '
                'Track, car, and session details will be extracted automatically.'
            )
            return redirect('telemetry:home')
    else:
        form = SessionUploadForm(user=request.user)

    context = {
        'form': form,
    }

    return render(request, 'telemetry/upload.html', context)


@login_required
@require_POST
def session_delete(request, pk):
    """
    Delete a session and all associated data.
    """
    session = get_object_or_404(Session, pk=pk, driver=request.user)
    track_name = session.track.name

    # Delete the file
    if session.ibt_file:
        session.ibt_file.delete()

    session.delete()

    messages.success(request, f'Session for {track_name} deleted successfully.')
    return redirect('telemetry:session_list')


# ================================
# Team Management Views
# ================================
# MOVED TO: views/teams.py
# Team views have been refactored into a separate module for better organization.
# Import them via: from .views import team_list, team_create, etc.


# ================================
# Lap Export/Import Views
# ================================

@login_required
def lap_export(request, pk):
    """
    Export a lap as a compressed JSON file (.lap.gz).
    Includes lap data, session metadata, and full telemetry.
    """
    from django.http import HttpResponse

    lap = get_object_or_404(
        Lap.objects.select_related(
            'session', 'session__track', 'session__car', 'session__driver', 'telemetry'
        ),
        pk=pk
    )

    # Check permissions
    if lap.session.driver != request.user:
        messages.error(request, "You don't have permission to export this lap.")
        return redirect('telemetry:session_list')

    # Get telemetry data
    try:
        telemetry = lap.telemetry
    except TelemetryData.DoesNotExist:
        messages.error(request, "No telemetry data available for this lap.")
        return redirect('telemetry:lap_detail', pk=pk)

    # Build export data structure using helper function
    export_data = build_lap_export_data(lap, telemetry)

    # Compress using helper function
    compressed_data = compress_lap_export_data(export_data)

    # Generate filename
    track_name = (lap.session.track.name if lap.session.track else 'Unknown').replace(' ', '_')
    car_name = (lap.session.car.name if lap.session.car else 'Unknown').replace(' ', '_')
    lap_time_str = f"{lap.lap_time:.3f}".replace('.', '_')
    filename = f"{track_name}_{car_name}_{lap_time_str}.lap.gz"

    # Create HTTP response
    response = HttpResponse(compressed_data, content_type='application/gzip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Content-Length'] = len(compressed_data)

    return response


# ================================
# Discord Sharing Views
# ================================

@login_required
def lap_share_to_discord(request, pk, team_id):
    """
    Share a lap to team's Discord channel via webhook.
    Uploads .lap.gz file and posts formatted message with import links.
    """
    import base64
    import requests
    from django.conf import settings

    lap = get_object_or_404(
        Lap.objects.select_related(
            'session', 'session__track', 'session__car', 'session__driver', 'telemetry'
        ),
        pk=pk
    )

    # Check permissions
    if lap.session.driver != request.user:
        messages.error(request, "You don't have permission to share this lap.")
        return redirect('telemetry:lap_detail', pk=pk)

    # Get the team and check membership
    team = get_object_or_404(Team, pk=team_id)

    # Check if user is a member of this team
    if request.user not in team.members.all():
        messages.error(request, f"You are not a member of {team.name}.")
        return redirect('telemetry:lap_detail', pk=pk)

    # Check if team has Discord webhook configured
    if not team.discord_webhook_url:
        messages.error(request, f"{team.name} doesn't have a Discord webhook configured.")
        return redirect('telemetry:lap_detail', pk=pk)

    # Get telemetry data
    try:
        telemetry = lap.telemetry
    except TelemetryData.DoesNotExist:
        messages.error(request, "No telemetry data available for this lap.")
        return redirect('telemetry:lap_detail', pk=pk)

    # Build export data using helper function
    export_data = build_lap_export_data(lap, telemetry)

    # Compress using helper function
    compressed_data = compress_lap_export_data(export_data)

    # Generate filename
    track_name = (lap.session.track.name if lap.session.track else 'Unknown').replace(' ', '_')
    car_name = (lap.session.car.name if lap.session.car else 'Unknown').replace(' ', '_')
    lap_time_str = f"{lap.lap_time:.3f}".replace('.', '_')
    filename = f"{track_name}_{car_name}_{lap_time_str}.lap.gz"

    # Get driver display name from iRacing (not website username)
    driver_name = lap.session.driver_name or lap.session.driver.username

    # Format Discord message
    track_display = lap.session.track.name if lap.session.track else 'Unknown Track'
    if lap.session.track and lap.session.track.configuration:
        track_display += f" - {lap.session.track.configuration}"

    car_display = lap.session.car.name if lap.session.car else 'Unknown Car'
    lap_status = "Valid" if lap.is_valid else "Invalid"
    session_date = lap.session.session_date.strftime("%b %d, %Y %H:%M")

    weather_info = ""
    if lap.session.air_temp:
        weather_info = f"\n**Weather:** {lap.session.weather_type or 'Clear'}, {lap.session.air_temp}°C"

    # Get optional notes from POST data
    notes = request.POST.get('notes', '').strip()
    notes_section = ""
    if notes:
        notes_section = f"\n\n**Notes:**\n> {notes}\n"

    # Format lap time as mm:ss.mmm
    total_seconds = float(lap.lap_time)
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    if minutes > 0:
        formatted_time = f"{minutes}:{seconds:06.3f}"
    else:
        formatted_time = f"{seconds:.3f}s"

    discord_message = f"""**New Lap Shared to Team**
━━━━━━━━━━━━━━━━━━━━━
**Driver:** {driver_name}
**Track:** {track_display}
**Car:** {car_display}
**Time:** {formatted_time} ({lap_status})
**Date:** {session_date}{weather_info}{notes_section}

Download the .lap.gz attachment below to import
"""

    try:
        # Post to Discord webhook
        files = {
            'file': (filename, compressed_data, 'application/gzip')
        }
        payload = {
            'content': discord_message
        }

        response = requests.post(
            team.discord_webhook_url,
            data=payload,
            files=files,
            timeout=10
        )

        if response.status_code in [200, 204]:
            messages.success(request, f'Lap shared to {team.name} Discord channel!')
        else:
            messages.error(request, f'Failed to share to Discord: {response.status_code} - {response.text}')

    except requests.exceptions.RequestException as e:
        messages.error(request, f'Error connecting to Discord: {str(e)}')
    except Exception as e:
        messages.error(request, f'Error sharing lap: {str(e)}')

    return redirect('telemetry:lap_detail', pk=pk)


@login_required
def user_settings(request):
    """
    User profile and settings page.
    Handles profile settings, password changes, and API token management.
    """
    from .models import Driver
    from .forms import UserSettingsForm, CustomPasswordChangeForm

    # Get or create driver profile
    driver_profile, created = Driver.objects.get_or_create(
        user=request.user,
        defaults={'display_name': request.user.username}
    )

    # Determine which form was submitted based on the submit button name
    if request.method == 'POST':
        # Handle API token generation
        if 'generate_token' in request.POST:
            driver_profile.generate_api_token()
            messages.success(request, 'New API token generated successfully!')
            return redirect('telemetry:user_settings')

        # Handle profile settings form
        elif 'save_settings' in request.POST:
            settings_form = UserSettingsForm(request.POST, instance=driver_profile, user=request.user)
            if settings_form.is_valid():
                settings_form.save()
                messages.success(request, 'Settings saved successfully!')
                return redirect('telemetry:user_settings')
            else:
                # Re-instantiate other forms for display
                password_form = CustomPasswordChangeForm(user=request.user)

        # Handle password change form
        elif 'change_password' in request.POST:
            password_form = CustomPasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                # Update session to prevent logout
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, password_form.user)
                messages.success(request, 'Password changed successfully!')
                return redirect('telemetry:user_settings')
            else:
                # Re-instantiate other forms for display
                settings_form = UserSettingsForm(instance=driver_profile, user=request.user)
        else:
            # Unknown form submission, re-instantiate all forms
            settings_form = UserSettingsForm(instance=driver_profile, user=request.user)
            password_form = CustomPasswordChangeForm(user=request.user)
    else:
        # GET request - instantiate all forms
        settings_form = UserSettingsForm(instance=driver_profile, user=request.user)
        password_form = CustomPasswordChangeForm(user=request.user)

    context = {
        'driver_profile': driver_profile,
        'settings_form': settings_form,
        'password_form': password_form,
        'has_token': bool(driver_profile.api_token),
    }

    return render(request, 'telemetry/user_settings.html', context)


def leaderboards(request):
    """
    Display global leaderboards showing best lap times for each track/car combination.
    Grouped and sortable with search functionality.
    """
    from django.db.models import Min, Count, Q

    # Get filter parameters
    track_filter = request.GET.get('track', '')
    car_filter = request.GET.get('car', '')
    search = request.GET.get('search', '')

    # Build base query for best laps per track/car/driver combination
    # We want the fastest lap for each driver on each track/car combo
    leaderboard_entries = []

    # Only show data if at least one filter (track or car) is selected
    if track_filter or car_filter:
        # Get all track/car combinations that have laps
        combinations = Lap.objects.filter(
            is_valid=True,
            lap_time__gt=0  # Exclude laps with 0 or negative lap times
        ).values('session__track', 'session__car').annotate(
            lap_count=Count('id')
        ).filter(lap_count__gt=0)

        # Apply filters
        if track_filter:
            combinations = combinations.filter(session__track__id=track_filter)
        if car_filter:
            combinations = combinations.filter(session__car__id=car_filter)

        # For each combination, get the best lap for each driver
        for combo in combinations:
            track_id = combo['session__track']
            car_id = combo['session__car']

            if not track_id or not car_id:
                continue

            # Get best lap for each driver for this track/car combo
            best_laps = Lap.objects.filter(
                session__track_id=track_id,
                session__car_id=car_id,
                is_valid=True,
                lap_time__gt=0  # Exclude laps with 0 or negative lap times
            ).select_related(
                'session__driver',
                'session__track',
                'session__car',
                'session__team'
            ).values(
                'session__driver',
                'session__driver__username',
                'session__track__name',
                'session__track__configuration',
                'session__car__name'
            ).annotate(
                best_time=Min('lap_time')
            ).order_by('best_time')

            # Apply search filter
            if search:
                best_laps = best_laps.filter(
                    Q(session__driver__username__icontains=search) |
                    Q(session__track__name__icontains=search) |
                    Q(session__car__name__icontains=search)
                )

            for lap_data in best_laps:
                # Get the actual lap object for the link
                actual_lap = Lap.objects.filter(
                    session__driver_id=lap_data['session__driver'],
                    session__track_id=track_id,
                    session__car_id=car_id,
                    lap_time=lap_data['best_time'],
                    is_valid=True
                ).select_related('session').first()

                if actual_lap:
                    track_name = lap_data['session__track__name']
                    if lap_data['session__track__configuration']:
                        track_name += f" - {lap_data['session__track__configuration']}"

                    leaderboard_entries.append({
                        'driver': lap_data['session__driver__username'],
                        'track': track_name,
                        'car': lap_data['session__car__name'],
                        'lap_time': lap_data['best_time'],
                        'lap': actual_lap,
                    })

    # Get unique tracks and cars for filters
    tracks = Track.objects.filter(
        id__in=Session.objects.filter(laps__isnull=False).values_list('track_id', flat=True).distinct()
    ).order_by('name')

    cars = Car.objects.filter(
        id__in=Session.objects.filter(laps__isnull=False).values_list('car_id', flat=True).distinct()
    ).order_by('name')

    context = {
        'leaderboard_entries': leaderboard_entries,
        'tracks': tracks,
        'cars': cars,
        'selected_track': track_filter,
        'selected_car': car_filter,
        'search': search,
    }

    return render(request, 'telemetry/leaderboards.html', context)


@api_token_required
def api_auth_test(request):
    """
    API endpoint to test authentication.
    Returns basic user info if authenticated with valid API token.

    Requires: Authorization: Token <api_token> header
    """
    from django.http import JsonResponse

    # Authentication handled by @api_token_required decorator
    # request.user is the authenticated user
    return JsonResponse({
        'authenticated': True,
        'username': request.user.username,
        'email': request.user.email,
        'sessions_count': Session.objects.filter(driver=request.user).count(),
        'server_url': f"{request.scheme}://{request.get_host()}"
    })


from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@api_token_required
def api_upload(request):
    """
    API endpoint for uploading telemetry files with API token authentication.

    Security Notes:
    - CSRF exempt because this is a token-authenticated API endpoint
    - Authentication handled by @api_token_required decorator
    - TODO: Add rate limiting to prevent abuse (use django-ratelimit)
    - File validation includes extension and size checks

    Requires: Authorization: Token <api_token> header
    """
    from django.http import JsonResponse
    from django.conf import settings

    # Only accept POST
    if request.method != 'POST':
        return JsonResponse({
            'error': 'Only POST method is allowed'
        }, status=405)

    # Authentication handled by @api_token_required decorator
    # request.user is the authenticated user

    # Check if file was uploaded
    if 'file' not in request.FILES:
        return JsonResponse({
            'error': 'No file provided'
        }, status=400)

    uploaded_file = request.FILES['file']

    # Validate file extension
    if not uploaded_file.name.lower().endswith('.ibt') and not uploaded_file.name.lower().endswith('.ibt.gz'):
        return JsonResponse({
            'error': 'Only .ibt files are allowed'
        }, status=400)

    # Detect and decompress gzipped files
    import gzip
    from django.core.files.uploadedfile import InMemoryUploadedFile
    from io import BytesIO

    # Check if file is gzipped by reading magic bytes
    file_start = uploaded_file.read(2)
    uploaded_file.seek(0)  # Reset to beginning

    if file_start == b'\x1f\x8b':  # Gzip magic number
        try:
            # Read and decompress the entire file
            compressed_data = uploaded_file.read()
            decompressed_data = gzip.decompress(compressed_data)

            # Create new in-memory file with decompressed data
            decompressed_file = InMemoryUploadedFile(
                file=BytesIO(decompressed_data),
                field_name='file',
                name=uploaded_file.name.replace('.gz', ''),  # Remove .gz extension if present
                content_type='application/octet-stream',
                size=len(decompressed_data),
                charset=None
            )
            uploaded_file = decompressed_file

        except gzip.BadGzipFile:
            return JsonResponse({
                'error': 'File appears corrupted - invalid gzip format'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'error': f'Decompression error: {str(e)}'
            }, status=400)

    # Validate file size (check against MAX_UPLOAD_SIZE from settings)
    max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 2147483648)  # 2GB default
    if uploaded_file.size > max_size:
        return JsonResponse({
            'error': f'File size exceeds maximum allowed size ({max_size / (1024**3):.1f} GB)'
        }, status=400)

    # Validate minimum file size (IBT files are typically > 1KB)
    if uploaded_file.size < 1024:
        return JsonResponse({
            'error': 'File appears to be too small to be a valid IBT file'
        }, status=400)

    # Create session
    session = Session(
        driver=request.user,
        ibt_file=uploaded_file,
        processing_status='pending'
    )

    # Try to extract original file modification time from header
    original_mtime = request.META.get('HTTP_X_ORIGINAL_MTIME')
    if original_mtime:
        from django.utils.dateparse import parse_datetime
        parsed_mtime = parse_datetime(original_mtime)
        if parsed_mtime:
            session.session_date = parsed_mtime

    session.save()

    # Queue Celery task for processing
    from .tasks import parse_ibt_file
    parse_ibt_file.delay(session.id)

    return JsonResponse({
        'success': True,
        'session_id': session.id,
        'filename': uploaded_file.name,
        'message': 'File uploaded successfully and queued for processing'
    }, status=201)


# ============================================================================
# Dashboard Analysis API Endpoints
# ============================================================================

@login_required
def api_lap_telemetry(request, lap_id):
    """
    API endpoint to get telemetry data for a specific lap.
    Returns JSON with all telemetry channels for dynamic chart rendering.

    Args:
        lap_id: The ID of the lap to fetch telemetry for

    Returns:
        JSON with lap metadata and telemetry data
    """
    from django.http import JsonResponse

    try:
        lap = get_object_or_404(Lap, id=lap_id)

        # Check if user has permission to view this lap
        # Allow if: user owns the session, or it's a teammate's lap and team allows sharing
        if lap.session.driver != request.user:
            if not lap.session.team or not lap.session.team.members.filter(id=request.user.id).exists():
                return JsonResponse({
                    'error': 'You do not have permission to view this lap'
                }, status=403)

        # Get telemetry data
        telemetry = lap.telemetry
        if not telemetry:
            return JsonResponse({
                'error': 'No telemetry data available for this lap'
            }, status=404)

        return JsonResponse({
            'success': True,
            'lap': {
                'id': lap.id,
                'lap_number': lap.lap_number,
                'lap_time': lap.lap_time,
                'driver': lap.session.driver.username,
                'track': lap.session.track.name if lap.session.track else 'Unknown',
                'track_id': lap.session.track.id if lap.session.track else None,
                'car': lap.session.car.name if lap.session.car else 'Unknown',
                'car_id': lap.session.car.id if lap.session.car else None,
                'session_date': lap.session.session_date.isoformat() if lap.session.session_date else None,
            },
            'telemetry': telemetry.data,  # All channel data
        })

    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
def api_fastest_laps(request):
    """
    API endpoint to get fastest laps for a specific track/car combination.

    Query parameters:
        track_id: Track ID (required)
        car_id: Car ID (required)
        include_team: Whether to include teammate laps (default: true)
        limit: Number of laps to return per category (default: 10)

    Returns:
        JSON with user's fastest laps and teammates' fastest laps
    """
    from django.http import JsonResponse

    try:
        track_id = request.GET.get('track_id')
        car_id = request.GET.get('car_id')
        include_team = request.GET.get('include_team', 'true').lower() == 'true'
        limit = int(request.GET.get('limit', 10))

        if not track_id or not car_id:
            return JsonResponse({
                'error': 'track_id and car_id are required'
            }, status=400)

        # Get user's fastest laps (exclude incomplete laps with lap_time=0)
        user_laps = Lap.objects.filter(
            session__driver=request.user,
            session__track_id=track_id,
            session__car_id=car_id,
            is_valid=True,
            lap_time__gt=0  # Exclude incomplete laps
        ).select_related(
            'session', 'session__track', 'session__car', 'session__driver'
        ).order_by('lap_time')[:limit]

        user_laps_data = [{
            'id': lap.id,
            'lap_number': lap.lap_number,
            'lap_time': lap.lap_time,
            'session_id': lap.session.id,
            'session_type': lap.session.session_type or 'Unknown',
            'session_date': lap.session.session_date.isoformat() if lap.session.session_date else None,
            'is_personal_best': lap.is_personal_best,
        } for lap in user_laps]

        # Get teammates' fastest laps if requested
        teammate_laps_data = []
        if include_team:
            # Find teams user belongs to
            user_teams = Team.objects.filter(members=request.user)

            if user_teams.exists():
                # Get teammates (excluding current user)
                from django.contrib.auth import get_user_model
                User = get_user_model()
                teammates = User.objects.filter(
                    teams__in=user_teams
                ).exclude(id=request.user.id).distinct()

                # Get each teammate's best lap for this track/car
                for teammate in teammates:
                    best_lap = Lap.objects.filter(
                        session__driver=teammate,
                        session__track_id=track_id,
                        session__car_id=car_id,
                        is_valid=True,
                        lap_time__gt=0  # Exclude incomplete laps
                    ).select_related(
                        'session', 'session__track', 'session__car', 'session__driver'
                    ).order_by('lap_time').first()

                    if best_lap:
                        teammate_laps_data.append({
                            'id': best_lap.id,
                            'lap_number': best_lap.lap_number,
                            'lap_time': best_lap.lap_time,
                            'driver': teammate.username,
                            'session_id': best_lap.session.id,
                            'session_type': best_lap.session.session_type or 'Unknown',
                            'session_date': best_lap.session.session_date.isoformat() if best_lap.session.session_date else None,
                        })

                # Sort by lap time
                teammate_laps_data.sort(key=lambda x: x['lap_time'])

        return JsonResponse({
            'success': True,
            'track_id': int(track_id),
            'car_id': int(car_id),
            'user_laps': user_laps_data,
            'teammate_laps': teammate_laps_data,
        })

    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
def api_generate_chart(request):
    """
    API endpoint to generate dynamic telemetry charts based on selected laps and channels.

    POST body (JSON):
        lap_ids: List of lap IDs to compare
        channels: List of channel names to display

    Returns:
        JSON with chart HTML
    """
    from django.http import JsonResponse
    import json
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go
    import numpy as np

    try:
        # Parse request body
        body = json.loads(request.body)
        lap_ids = body.get('lap_ids', [])
        selected_channels = body.get('channels', [])

        if not lap_ids:
            return JsonResponse({'error': 'No laps provided'}, status=400)

        if not selected_channels:
            return JsonResponse({'error': 'No channels selected'}, status=400)

        # Fetch laps
        laps = []
        for lap_id in lap_ids:
            lap = Lap.objects.filter(id=lap_id).select_related(
                'session', 'session__driver', 'session__track', 'session__car', 'telemetry'
            ).first()

            if not lap:
                continue

            # Check permissions
            if lap.session.driver != request.user:
                if not lap.session.team or not lap.session.team.members.filter(id=request.user.id).exists():
                    continue

            laps.append(lap)

        if not laps:
            return JsonResponse({'error': 'No valid laps found'}, status=404)

        # Color palette
        colors = ['#00d1b2', '#ff6b6b', '#4ecdc4', '#ffe66d', '#a8dadc', '#f1fa8c', '#ff79c6', '#bd93f9']

        # Extract telemetry data
        lap_data = []
        for i, lap in enumerate(laps):
            telemetry = lap.telemetry
            if telemetry and telemetry.data:
                lap_data.append({
                    'lap': lap,
                    'data': telemetry.data,
                    'color': colors[i % len(colors)],
                    'name': f"{lap.session.driver.username} - {lap.lap_time:.3f}s"
                })

        if not lap_data:
            return JsonResponse({'error': 'No telemetry data available'}, status=404)

        # Group channels by subplot
        channel_groups = {
            'delta': ['LapDist', 'SessionTime'],  # For time delta calculation
            'Speed': ['Speed', 'LapDist'],
            'Throttle': ['Throttle', 'LapDist'],
            'Brake': ['Brake', 'LapDist'],
            'Clutch': ['Clutch', 'LapDist'],
            'Gear': ['Gear', 'LapDist'],
            'RPM': ['RPM', 'LapDist'],
            'SteeringWheelAngle': ['SteeringWheelAngle', 'LapDist'],
            # Tire Temperatures
            'LFtempL': ['LFtempL', 'LapDist'],
            'LFtempM': ['LFtempM', 'LapDist'],
            'LFtempR': ['LFtempR', 'LapDist'],
            'RFtempL': ['RFtempL', 'LapDist'],
            'RFtempM': ['RFtempM', 'LapDist'],
            'RFtempR': ['RFtempR', 'LapDist'],
            'LRtempL': ['LRtempL', 'LapDist'],
            'LRtempM': ['LRtempM', 'LapDist'],
            'LRtempR': ['LRtempR', 'LapDist'],
            'RRtempL': ['RRtempL', 'LapDist'],
            'RRtempM': ['RRtempM', 'LapDist'],
            'RRtempR': ['RRtempR', 'LapDist'],
            # Tire Pressures
            'LFcoldPressure': ['LFcoldPressure', 'LapDist'],
            'RFcoldPressure': ['RFcoldPressure', 'LapDist'],
            'LRcoldPressure': ['LRcoldPressure', 'LapDist'],
            'RRcoldPressure': ['RRcoldPressure', 'LapDist'],
            # Suspension - Ride Heights
            'LFrideHeight': ['LFrideHeight', 'LapDist'],
            'RFrideHeight': ['RFrideHeight', 'LapDist'],
            'LRrideHeight': ['LRrideHeight', 'LapDist'],
            'RRrideHeight': ['RRrideHeight', 'LapDist'],
            # Suspension - Shock Deflection
            'LFshockDefl': ['LFshockDefl', 'LapDist'],
            'RFshockDefl': ['RFshockDefl', 'LapDist'],
            'LRshockDefl': ['LRshockDefl', 'LapDist'],
            'RRshockDefl': ['RRshockDefl', 'LapDist'],
            # Suspension - Shock Velocity
            'LFshockVel': ['LFshockVel', 'LapDist'],
            'RFshockVel': ['RFshockVel', 'LapDist'],
            'LRshockVel': ['LRshockVel', 'LapDist'],
            'RRshockVel': ['RRshockVel', 'LapDist'],
            # Acceleration / G-Forces
            'LatAccel': ['LatAccel', 'LapDist'],
            'LongAccel': ['LongAccel', 'LapDist'],
            'VertAccel': ['VertAccel', 'LapDist'],
            # Orientation
            'Roll': ['Roll', 'LapDist'],
            'Pitch': ['Pitch', 'LapDist'],
            'Yaw': ['Yaw', 'LapDist'],
            'RollRate': ['RollRate', 'LapDist'],
            'PitchRate': ['PitchRate', 'LapDist'],
            'YawRate': ['YawRate', 'LapDist'],
            # Fuel
            'FuelLevel': ['FuelLevel', 'LapDist'],
            'FuelLevelPct': ['FuelLevelPct', 'LapDist'],
        }

        # Determine subplots to create
        subplots = []
        subplot_titles = []

        # Always include delta if comparing multiple laps
        if len(lap_data) > 1:
            subplots.append('delta')
            subplot_titles.append('Time Delta vs Fastest Lap')

        # Add selected channels
        for channel in selected_channels:
            if channel in channel_groups:
                # Check if first lap has this channel
                if all(req in lap_data[0]['data'] for req in channel_groups[channel]):
                    subplots.append(channel)
                    # Format channel name for display
                    display_name = channel.replace('Wheel', ' Wheel').replace('Accel', ' Accel')
                    subplot_titles.append(display_name)

        if not subplots:
            return JsonResponse({'error': 'No valid channels to display'}, status=400)

        # Create subplots (no titles to save space - lap info shown above in UI)
        fig = make_subplots(
            rows=len(subplots),
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.02,
            subplot_titles=[],  # Remove titles to save space
            row_heights=[350] * len(subplots)
        )

        # Sort laps by lap time for delta calculation
        fastest_lap = min(lap_data, key=lambda x: x['lap'].lap_time)

        # Add traces for each subplot
        for row_idx, subplot_type in enumerate(subplots, start=1):
            if subplot_type == 'delta' and len(lap_data) > 1:
                # Calculate time delta for each lap vs fastest
                for lap_info in lap_data:
                    try:
                        # Get distance and time arrays
                        distance = np.array(lap_info['data'].get('LapDist', []))
                        time = np.array(lap_info['data'].get('SessionTime', []))
                        fastest_distance = np.array(fastest_lap['data'].get('LapDist', []))
                        fastest_time = np.array(fastest_lap['data'].get('SessionTime', []))

                        if len(distance) == 0 or len(fastest_distance) == 0:
                            continue

                        # Normalize time to start from 0 for each lap (relative lap time)
                        time = time - time[0]
                        fastest_time = fastest_time - fastest_time[0]

                        # Interpolate to common distance points
                        common_distance = np.linspace(0, min(distance.max(), fastest_distance.max()), 500)
                        interp_time = np.interp(common_distance, distance, time)
                        interp_fastest_time = np.interp(common_distance, fastest_distance, fastest_time)

                        # Calculate delta (positive = slower, negative = faster)
                        delta = interp_time - interp_fastest_time

                        # Choose line style based on whether this is the fastest lap
                        line_style = dict(color=lap_info['color'], width=2)
                        if lap_info == fastest_lap:
                            # Fastest lap shows as baseline (delta = 0)
                            line_style['dash'] = 'dot'

                        fig.add_trace(
                            go.Scatter(
                                x=common_distance,
                                y=delta,
                                name=lap_info['name'],
                                line=line_style,
                                hovertemplate='Distance: %{x:.1f}m<br>Delta: %{y:+.3f}s<extra></extra>'
                            ),
                            row=row_idx,
                            col=1
                        )
                    except Exception as e:
                        print(f"Error calculating delta: {e}")

                # Update y-axis for delta
                fig.update_yaxes(title_text="Time Delta (s)", row=row_idx, col=1)

            else:
                # Regular channel subplot
                required_channels = channel_groups.get(subplot_type, [])

                for lap_info in lap_data:
                    try:
                        # Check if lap has required channels
                        if not all(ch in lap_info['data'] for ch in required_channels):
                            continue

                        x_data = lap_info['data'].get('LapDist', [])
                        y_data = lap_info['data'].get(subplot_type, [])

                        if len(x_data) == 0 or len(y_data) == 0:
                            continue

                        # Truncate to shortest length
                        min_len = min(len(x_data), len(y_data))
                        x_data = x_data[:min_len]
                        y_data = y_data[:min_len]

                        # Convert units for better readability
                        if subplot_type == 'Speed':
                            # Convert Speed from m/s to km/h
                            y_data = [v * 3.6 for v in y_data]
                        elif subplot_type in ['Throttle', 'Brake', 'Clutch']:
                            # Convert from 0-1 to 0-100%
                            y_data = [v * 100 for v in y_data]
                        elif subplot_type == 'Gear':
                            # Filter out gear 0 (neutral) for cleaner display
                            y_data = [v if v > 0 else None for v in y_data]

                        fig.add_trace(
                            go.Scatter(
                                x=x_data,
                                y=y_data,
                                name=lap_info['name'],
                                line=dict(color=lap_info['color'], width=2),
                                hovertemplate=f'Distance: %{{x:.1f}}m<br>{subplot_type}: %{{y:.2f}}<extra></extra>',
                                connectgaps=True  # Connect line segments even with None values (for Gear)
                            ),
                            row=row_idx,
                            col=1
                        )
                    except Exception as e:
                        print(f"Error adding trace for {subplot_type}: {e}")

                # Update y-axis label with proper units
                y_label = subplot_type
                if subplot_type == 'Speed':
                    y_label = 'Speed (km/h)'
                elif subplot_type in ['Throttle', 'Brake', 'Clutch']:
                    y_label = f'{subplot_type} (%)'
                    # Set fixed range for percentage inputs (0-100%)
                    fig.update_yaxes(title_text=y_label, range=[0, 100], row=row_idx, col=1)
                    continue  # Skip the default update below

                fig.update_yaxes(title_text=y_label, row=row_idx, col=1)

        # Update x-axis (only bottom subplot)
        fig.update_xaxes(title_text="Distance (m)", row=len(subplots), col=1)

        # Update layout
        fig.update_layout(
            height=350 * len(subplots),
            hovermode='x unified',
            template='plotly_dark',
            showlegend=False,  # Hide legend - lap info shown above in UI
            margin=dict(l=60, r=20, t=20, b=60)  # Reduced top margin since no titles/legend
        )

        # Convert to JSON for client-side rendering
        chart_json = fig.to_json()

        return JsonResponse({
            'success': True,
            'chart_json': chart_json,
            'lap_count': len(lap_data),
            'subplot_count': len(subplots)
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
