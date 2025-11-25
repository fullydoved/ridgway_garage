"""
Views for the Ridgway Garage telemetry app.
"""

import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db.models import Count

from .models import Session, Lap, TelemetryData, Track, Car, Team
from .forms import SessionUploadForm

logger = logging.getLogger(__name__)


# Import helper functions from utils (now extracted)
from .utils.export import build_lap_export_data, compress_lap_export_data, import_lap_from_data


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
        ).filter(lap_count__gt=0).order_by('-session_date').distinct()[:10]  # Get more to filter

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
    logger.debug("dashboard_analysis called - user: %s, authenticated: %s",
                 request.user, request.user.is_authenticated)

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
        logger.debug("Preloading lap ID from query parameter: %s", lap_id)
        try:
            preload_lap = Lap.objects.select_related('session', 'session__track', 'session__car').get(
                id=lap_id,
                session__driver=request.user
            )
            context['preloaded_lap_id'] = preload_lap.id
            context['selected_track'] = preload_lap.session.track
            context['selected_car'] = preload_lap.session.car
            logger.debug("Successfully preloaded lap %s", lap_id)

        except Lap.DoesNotExist:
            logger.debug("Lap %s not found or doesn't belong to user", lap_id)

    elif session_id:
        logger.debug("Preloading top 5 fastest laps from session ID: %s", session_id)
        try:
            session = Session.objects.select_related('track', 'car').prefetch_related('laps').get(
                id=session_id,
                driver=request.user
            )
            # Get top 5 fastest valid laps from this session (ordered fastest to slowest)
            valid_laps = session.laps.filter(is_valid=True, lap_time__gt=0).order_by('lap_time')[:5]

            if valid_laps.exists():
                # Store lap IDs as comma-separated string for JavaScript
                lap_ids = ','.join(str(lap.id) for lap in valid_laps)
                context['preloaded_session_laps'] = lap_ids
                context['selected_track'] = session.track
                context['selected_car'] = session.car
                logger.debug("Successfully preloaded %d laps from session %s",
                            valid_laps.count(), session_id)
            else:
                logger.debug("No valid laps found in session %s", session_id)

        except Session.DoesNotExist:
            logger.debug("Session %s not found or doesn't belong to user", session_id)

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

        if recent_session and recent_best_lap:
            logger.debug("Found recent session %s with best lap %s (time: %s)",
                        recent_session.id, recent_best_lap.id, recent_best_lap.lap_time)
            context['selected_track'] = recent_session.track
            context['selected_car'] = recent_session.car
            context['initial_laps'].append(recent_best_lap)

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

    logger.debug("Rendering dashboard_analysis - initial_laps: %d, track: %s, car: %s",
                len(context['initial_laps']), context['selected_track'], context['selected_car'])

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
    from django.core.paginator import Paginator

    ITEMS_PER_PAGE = 25

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

    # Paginate
    paginator = Paginator(sessions, ITEMS_PER_PAGE)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Add best lap and valid laps for each session in current page
    for session in page_obj:
        session.valid_laps = session.laps.filter(is_valid=True, lap_time__gt=0).order_by('lap_number')
        session.best_lap = session.valid_laps.order_by('lap_time').first() if session.valid_laps else None

    context = {
        'sessions': page_obj,  # Now a Page object, not QuerySet
        'page_obj': page_obj,
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

    # Paginate leaderboard entries
    from django.core.paginator import Paginator
    ITEMS_PER_PAGE = 25

    paginator = Paginator(leaderboard_entries, ITEMS_PER_PAGE)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'leaderboard_entries': page_obj,  # Now a Page object
        'page_obj': page_obj,
        'tracks': tracks,
        'cars': cars,
        'selected_track': track_filter,
        'selected_car': car_filter,
        'search': search,
    }

    return render(request, 'telemetry/leaderboards.html', context)
