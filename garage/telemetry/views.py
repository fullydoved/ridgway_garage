"""
Views for the Ridgway Garage telemetry app.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.views.decorators.http import require_POST

from .models import Session, Lap, TelemetryData, Analysis, Track, Car
from .forms import SessionUploadForm, AnalysisForm


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
                is_valid=True
            ).order_by('lap_time').first(),
            'processing': user_sessions.filter(processing_status='processing').count(),
        }

        # Recent sessions (last 5)
        recent_sessions = user_sessions.select_related(
            'track', 'car', 'team'
        ).prefetch_related('laps').order_by('-session_date')[:5]

        # Add best lap for each session
        for session in recent_sessions:
            session.best_lap = session.laps.filter(is_valid=True).order_by('lap_time').first()

        context['recent_sessions'] = recent_sessions

    return render(request, 'telemetry/home.html', context)


@login_required
def session_list(request):
    """
    List all sessions for the logged-in user.
    """
    sessions = Session.objects.filter(
        driver=request.user
    ).select_related('track', 'car', 'team').order_by('-session_date')

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
def session_detail(request, pk):
    """
    Detail view for a single session showing all laps.
    """
    session = get_object_or_404(
        Session.objects.select_related('track', 'car', 'driver', 'team'),
        pk=pk
    )

    # Check permissions
    if session.driver != request.user:
        # TODO: Check if user has team access
        messages.error(request, "You don't have permission to view this session.")
        return redirect('telemetry:session_list')

    laps = session.laps.all().order_by('lap_number').prefetch_related('analyses')

    # Get user's analyses for the "Add to Analysis" dropdown
    user_analyses = Analysis.objects.filter(driver=request.user).order_by('-updated_at')

    # For each lap, get the analyses it belongs to and annotate user_analyses
    for lap in laps:
        lap.user_analyses = lap.analyses.filter(driver=request.user)

        # Get IDs of analyses this lap is already in
        lap_analysis_ids = set(lap.analyses.values_list('id', flat=True))

        # Annotate each user analysis with whether it contains this lap
        lap.analyses_with_flag = []
        for analysis in user_analyses:
            analysis_copy = type('obj', (object,), {
                'id': analysis.id,
                'pk': analysis.pk,
                'name': analysis.name,
                'contains_this_lap': analysis.id in lap_analysis_ids
            })()
            lap.analyses_with_flag.append(analysis_copy)

    context = {
        'session': session,
        'laps': laps,
        'best_lap': laps.filter(is_valid=True).order_by('lap_time').first(),
        'user_analyses': user_analyses,
    }

    return render(request, 'telemetry/session_detail.html', context)


@login_required
def lap_detail(request, pk):
    """
    Detail view for a single lap with telemetry visualization.
    """
    from .utils.charts import (
        create_combined_telemetry_chart, prepare_gps_data
    )
    import json

    lap = get_object_or_404(
        Lap.objects.select_related(
            'session', 'session__track', 'session__car', 'session__driver'
        ),
        pk=pk
    )

    # Check permissions
    if lap.session.driver != request.user:
        messages.error(request, "You don't have permission to view this lap.")
        return redirect('telemetry:session_list')

    # Get telemetry data
    try:
        telemetry = lap.telemetry
        telemetry_data = telemetry.data
    except TelemetryData.DoesNotExist:
        telemetry = None
        telemetry_data = None
        messages.warning(request, "Telemetry data not available for this lap.")

    # Generate combined chart and GPS data if telemetry data is available
    combined_chart = None
    gps_data_json = None

    if telemetry_data:
        combined_chart = create_combined_telemetry_chart(telemetry_data)

        # Prepare GPS data for the track map
        gps_data = prepare_gps_data(telemetry_data)
        if gps_data:
            # Convert to JSON for JavaScript
            gps_data_json = json.dumps(gps_data)

    # Get user's analyses for the "Add to Analysis" dropdown
    # Annotate which analyses already contain this lap
    user_analyses = Analysis.objects.filter(driver=request.user).order_by('-updated_at')

    # Check which analyses this lap is already in
    lap_analyses = set(lap.analyses.values_list('id', flat=True))
    for analysis in user_analyses:
        analysis.contains_this_lap = analysis.id in lap_analyses

    context = {
        'lap': lap,
        'session': lap.session,
        'telemetry': telemetry,
        'combined_chart': combined_chart,
        'gps_data_json': gps_data_json,
        'user_analyses': user_analyses,
    }

    return render(request, 'telemetry/lap_detail.html', context)


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
            return redirect('telemetry:session_detail', pk=session.id)
    else:
        form = SessionUploadForm(user=request.user)

    context = {
        'form': form,
    }

    return render(request, 'telemetry/upload.html', context)


@login_required
def lap_compare(request):
    """
    Compare multiple laps side-by-side.
    """
    lap_ids = request.GET.getlist('laps')

    if not lap_ids:
        messages.info(request, "Select laps to compare from the session view.")
        return redirect('telemetry:session_list')

    laps = Lap.objects.filter(
        id__in=lap_ids,
        session__driver=request.user
    ).select_related('session', 'session__track', 'session__car').prefetch_related('telemetry')

    if not laps.exists():
        messages.error(request, "No laps found to compare.")
        return redirect('telemetry:session_list')

    context = {
        'laps': laps,
    }

    return render(request, 'telemetry/lap_compare.html', context)


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


# ============================================================================
# Analysis Views (Lap Comparison)
# ============================================================================

@login_required
def analysis_list(request):
    """
    List all analyses for the logged-in user.
    """
    analyses = Analysis.objects.filter(driver=request.user).prefetch_related('laps', 'track', 'car')

    context = {
        'analyses': analyses,
    }

    return render(request, 'telemetry/analysis_list.html', context)


@login_required
def analysis_create(request):
    """
    Create a new analysis.
    Optionally accepts a lap_id to add that lap to the analysis on creation.
    """
    # Get optional lap_id from query params
    lap_id = request.GET.get('lap_id') or request.POST.get('lap_id')
    initial_lap = None

    if lap_id:
        initial_lap = get_object_or_404(Lap, pk=lap_id, session__driver=request.user)

    if request.method == 'POST':
        form = AnalysisForm(request.POST, user=request.user)
        if form.is_valid():
            analysis = form.save(commit=False)
            analysis.driver = request.user
            analysis.save()

            # Add the initial lap if provided
            if initial_lap:
                analysis.laps.add(initial_lap)
                messages.success(request, f'Analysis "{analysis.name}" created with Lap {initial_lap.lap_number}!')
            else:
                messages.success(request, f'Analysis "{analysis.name}" created successfully!')

            return redirect('telemetry:analysis_detail', pk=analysis.pk)
    else:
        form = AnalysisForm(user=request.user)

    context = {
        'form': form,
        'initial_lap': initial_lap,
    }

    return render(request, 'telemetry/analysis_form.html', context)


@login_required
def analysis_detail(request, pk):
    """
    View an analysis with comparison charts.
    """
    from .utils.charts import create_comparison_chart, prepare_comparison_gps_data
    import json

    analysis = get_object_or_404(
        Analysis.objects.prefetch_related(
            'laps__session__track',
            'laps__session__car',
            'laps__telemetry'
        ),
        pk=pk
    )

    # Check permissions
    if analysis.driver != request.user:
        # TODO: Check if user has team access
        messages.error(request, "You don't have permission to view this analysis.")
        return redirect('telemetry:analysis_list')

    laps = analysis.laps.all().order_by('lap_time')

    # Generate comparison charts if we have at least 2 laps
    # (includes time delta as first subplot)
    comparison_chart = None
    if laps.count() >= 2:
        comparison_chart = create_comparison_chart(laps)

    # Prepare GPS data for track overlay
    comparison_gps_data = None
    if laps.count() >= 1:
        gps_data = prepare_comparison_gps_data(laps)
        if gps_data:
            comparison_gps_data = json.dumps(gps_data)

    context = {
        'analysis': analysis,
        'laps': laps,
        'comparison_chart': comparison_chart,
        'comparison_gps_data': comparison_gps_data,
    }

    return render(request, 'telemetry/analysis_detail.html', context)


@login_required
def analysis_edit(request, pk):
    """
    Edit an existing analysis.
    """
    analysis = get_object_or_404(Analysis, pk=pk, driver=request.user)

    if request.method == 'POST':
        form = AnalysisForm(request.POST, instance=analysis, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Analysis "{analysis.name}" updated successfully!')
            return redirect('telemetry:analysis_detail', pk=analysis.pk)
    else:
        form = AnalysisForm(instance=analysis, user=request.user)

    context = {
        'form': form,
        'analysis': analysis,
    }

    return render(request, 'telemetry/analysis_form.html', context)


@login_required
@require_POST
def analysis_delete(request, pk):
    """
    Delete an analysis.
    """
    analysis = get_object_or_404(Analysis, pk=pk, driver=request.user)
    name = analysis.name
    analysis.delete()

    messages.success(request, f'Analysis "{name}" deleted successfully.')
    return redirect('telemetry:analysis_list')


@login_required
@require_POST
def analysis_add_lap(request, pk, lap_id):
    """
    Add a lap to an analysis.
    Prevents duplicate laps from being added.
    """
    analysis = get_object_or_404(Analysis, pk=pk, driver=request.user)
    lap = get_object_or_404(Lap, pk=lap_id, session__driver=request.user)

    # Check if lap is already in the analysis
    if analysis.laps.filter(pk=lap_id).exists():
        messages.warning(request, f'Lap {lap.lap_number} is already in "{analysis.name}"')
    else:
        analysis.laps.add(lap)
        messages.success(request, f'Lap {lap.lap_number} added to "{analysis.name}"')

    # Redirect back to the referring page if available, otherwise to analysis detail
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('telemetry:analysis_detail', pk=analysis.pk)


@login_required
@require_POST
def analysis_remove_lap(request, pk, lap_id):
    """
    Remove a lap from an analysis.
    """
    analysis = get_object_or_404(Analysis, pk=pk, driver=request.user)
    lap = get_object_or_404(Lap, pk=lap_id)

    analysis.laps.remove(lap)
    messages.success(request, f'Lap {lap.lap_number} removed from "{analysis.name}"')

    return redirect('telemetry:analysis_detail', pk=analysis.pk)


# ================================
# Team Management Views
# ================================

@login_required
def team_list(request):
    """
    List teams the user belongs to and public teams.
    """
    # Teams the user is a member of
    user_teams = Team.objects.filter(members=request.user).prefetch_related('members')

    # Public teams
    public_teams = Team.objects.filter(is_public=True).exclude(members=request.user)

    context = {
        'user_teams': user_teams,
        'public_teams': public_teams,
    }

    return render(request, 'telemetry/team_list.html', context)


@login_required
def team_create(request):
    """
    Create a new team.
    """
    from .forms import TeamForm

    if request.method == 'POST':
        form = TeamForm(request.POST)
        if form.is_valid():
            team = form.save(commit=False)
            team.owner = request.user
            team.save()

            # Add creator as team member with owner role
            from .models import TeamMembership
            TeamMembership.objects.create(
                team=team,
                user=request.user,
                role='owner'
            )

            messages.success(request, f'Team "{team.name}" created successfully!')
            return redirect('telemetry:team_detail', pk=team.pk)
    else:
        form = TeamForm()

    context = {
        'form': form,
        'page_title': 'Create Team',
    }

    return render(request, 'telemetry/team_form.html', context)


@login_required
def team_detail(request, pk):
    """
    View team details and members.
    """
    team = get_object_or_404(Team.objects.prefetch_related('members'), pk=pk)

    # Check if user is a member
    is_member = request.user in team.members.all()

    # Get user's role if they're a member
    user_role = None
    if is_member:
        try:
            membership = team.teammembership_set.get(user=request.user)
            user_role = membership.role
        except:
            pass

    # Get team members with roles
    memberships = team.teammembership_set.select_related('user').order_by('role', 'joined_at')

    context = {
        'team': team,
        'is_member': is_member,
        'user_role': user_role,
        'memberships': memberships,
        'is_owner': user_role == 'owner',
    }

    return render(request, 'telemetry/team_detail.html', context)


@login_required
def team_edit(request, pk):
    """
    Edit team settings (owner only).
    """
    from .forms import TeamForm

    team = get_object_or_404(Team, pk=pk)

    # Check if user is the owner
    if team.owner != request.user:
        messages.error(request, "Only the team owner can edit team settings.")
        return redirect('telemetry:team_detail', pk=pk)

    if request.method == 'POST':
        form = TeamForm(request.POST, instance=team)
        if form.is_valid():
            form.save()
            messages.success(request, f'Team "{team.name}" updated successfully!')
            return redirect('telemetry:team_detail', pk=pk)
    else:
        form = TeamForm(instance=team)

    context = {
        'form': form,
        'team': team,
        'page_title': f'Edit {team.name}',
    }

    return render(request, 'telemetry/team_form.html', context)


@login_required
@require_POST
def team_delete(request, pk):
    """
    Delete a team (owner only).
    """
    team = get_object_or_404(Team, pk=pk, owner=request.user)
    team_name = team.name
    team.delete()

    messages.success(request, f'Team "{team_name}" deleted successfully.')
    return redirect('telemetry:team_list')


# ================================
# Lap Export/Import Views
# ================================

@login_required
def lap_export(request, pk):
    """
    Export a lap as a compressed JSON file (.lap.gz).
    Includes lap data, session metadata, and full telemetry.
    """
    import gzip
    import json
    from django.http import HttpResponse
    from datetime import datetime

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

    # Build export data structure
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
            'display_name': lap.session.driver.driver_profile.display_name if hasattr(lap.session.driver, 'driver_profile') and lap.session.driver.driver_profile.display_name else lap.session.driver.username,
        },
        'telemetry': {
            'sample_count': telemetry.sample_count,
            'max_speed': float(telemetry.max_speed) if telemetry.max_speed else None,
            'avg_speed': float(telemetry.avg_speed) if telemetry.avg_speed else None,
            'data': telemetry.data,
        }
    }

    # Convert to JSON
    json_data = json.dumps(export_data, indent=2)

    # Compress with gzip
    compressed_data = gzip.compress(json_data.encode('utf-8'))

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


@login_required
def lap_import(request):
    """
    Import a lap from a compressed JSON file (.lap.gz).
    Creates a new Session with type 'imported' and associated Lap and TelemetryData.
    """
    import gzip
    import json
    from django.utils.dateparse import parse_datetime
    from decimal import Decimal

    if request.method == 'POST':
        uploaded_file = request.FILES.get('lap_file')

        if not uploaded_file:
            messages.error(request, 'Please select a file to import.')
            return redirect('telemetry:lap_import')

        # Check file extension
        if not uploaded_file.name.endswith('.lap.gz'):
            messages.error(request, 'Invalid file format. Please upload a .lap.gz file.')
            return redirect('telemetry:lap_import')

        # Check file size (max 50MB compressed, should be plenty)
        if uploaded_file.size > 50 * 1024 * 1024:
            messages.error(request, 'File too large. Maximum size is 50MB.')
            return redirect('telemetry:lap_import')

        try:
            # Decompress and parse JSON
            compressed_data = uploaded_file.read()
            json_data = gzip.decompress(compressed_data).decode('utf-8')
            data = json.loads(json_data)

            # Validate format version
            if data.get('format_version') != '1.0':
                messages.error(request, f"Unsupported format version: {data.get('format_version')}")
                return redirect('telemetry:lap_import')

            # Validate required fields
            required_fields = ['lap', 'session', 'driver', 'telemetry']
            for field in required_fields:
                if field not in data:
                    messages.error(request, f"Invalid file format: missing '{field}' field.")
                    return redirect('telemetry:lap_import')

            # Get or create Track
            track_name = data['session'].get('track_name', 'Unknown Track')
            track_config = data['session'].get('track_config', '')
            track, _ = Track.objects.get_or_create(
                name=track_name,
                configuration=track_config,
                defaults={'name': track_name, 'configuration': track_config}
            )

            # Get or create Car
            car_name = data['session'].get('car_name', 'Unknown Car')
            car, _ = Car.objects.get_or_create(
                name=car_name,
                defaults={'name': car_name}
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
                driver=request.user,
                team=request.user.driver_profile.default_team if hasattr(request.user, 'driver_profile') else None,
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

            # Get driver display name from imported data
            imported_driver_name = data['driver'].get('display_name', 'Unknown Driver')

            messages.success(
                request,
                f"Lap imported successfully! {imported_driver_name}'s lap on {track_name} ({car_name}) - {lap.lap_time}s"
            )

            # Redirect to lap detail or suggest creating an analysis
            return redirect('telemetry:lap_detail', pk=lap.pk)

        except gzip.BadGzipFile:
            messages.error(request, 'Invalid file format. File is not a valid gzip file.')
            return redirect('telemetry:lap_import')
        except json.JSONDecodeError as e:
            messages.error(request, f'Invalid JSON format: {str(e)}')
            return redirect('telemetry:lap_import')
        except Exception as e:
            messages.error(request, f'Error importing lap: {str(e)}')
            return redirect('telemetry:lap_import')

    # GET request - show import form
    context = {
        'page_title': 'Import Lap',
    }
    return render(request, 'telemetry/lap_import.html', context)


# ================================
# Discord Sharing Views
# ================================

@login_required
def lap_share_to_discord(request, pk):
    """
    Share a lap to team's Discord channel via webhook.
    Uploads .lap.gz file and posts formatted message with import links.
    """
    import gzip
    import json
    import base64
    import requests
    from datetime import datetime
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

    # Check if user has a team with Discord webhook configured
    try:
        driver_profile = request.user.driver_profile
        team = driver_profile.default_team
        if not team or not team.discord_webhook_url:
            messages.error(request, "No Discord webhook configured for your team. Contact your team admin.")
            return redirect('telemetry:lap_detail', pk=pk)
    except:
        messages.error(request, "You need to join a team and configure Discord integration first.")
        return redirect('telemetry:lap_detail', pk=pk)

    # Get telemetry data
    try:
        telemetry = lap.telemetry
    except TelemetryData.DoesNotExist:
        messages.error(request, "No telemetry data available for this lap.")
        return redirect('telemetry:lap_detail', pk=pk)

    # Build export data (same as export view)
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
            'display_name': lap.session.driver.driver_profile.display_name if hasattr(lap.session.driver, 'driver_profile') and lap.session.driver.driver_profile.display_name else lap.session.driver.username,
        },
        'telemetry': {
            'sample_count': telemetry.sample_count,
            'max_speed': float(telemetry.max_speed) if telemetry.max_speed else None,
            'avg_speed': float(telemetry.avg_speed) if telemetry.avg_speed else None,
            'data': telemetry.data,
        }
    }

    # Convert to JSON and compress
    json_data = json.dumps(export_data, indent=2)
    compressed_data = gzip.compress(json_data.encode('utf-8'))

    # Create base64-encoded data for protocol URL (uncompressed for smaller URL)
    # Limit data to prevent huge URLs
    protocol_data = {
        'format_version': export_data['format_version'],
        'exported_at': export_data['exported_at'],
        'lap': export_data['lap'],
        'session': export_data['session'],
        'driver': export_data['driver'],
        'telemetry': {
            'sample_count': export_data['telemetry']['sample_count'],
            'max_speed': export_data['telemetry']['max_speed'],
            'avg_speed': export_data['telemetry']['avg_speed'],
            'data': export_data['telemetry']['data'],
        }
    }
    protocol_json = json.dumps(protocol_data)
    base64_data = base64.urlsafe_b64encode(protocol_json.encode('utf-8')).decode('utf-8')

    # Generate filename
    track_name = (lap.session.track.name if lap.session.track else 'Unknown').replace(' ', '_')
    car_name = (lap.session.car.name if lap.session.car else 'Unknown').replace(' ', '_')
    lap_time_str = f"{lap.lap_time:.3f}".replace('.', '_')
    filename = f"{track_name}_{car_name}_{lap_time_str}.lap.gz"

    # Get driver display name
    driver_name = lap.session.driver.driver_profile.display_name if hasattr(lap.session.driver, 'driver_profile') and lap.session.driver.driver_profile.display_name else lap.session.driver.username

    # Format Discord message
    track_display = lap.session.track.name if lap.session.track else 'Unknown Track'
    if lap.session.track and lap.session.track.configuration:
        track_display += f" - {lap.session.track.configuration}"

    car_display = lap.session.car.name if lap.session.car else 'Unknown Car'
    lap_status = "Valid" if lap.is_valid else "Invalid"
    session_date = lap.session.session_date.strftime("%b %d, %Y %H:%M")

    weather_info = ""
    if lap.session.air_temp:
        weather_info = f"\n🌡️ Weather: {lap.session.weather_type or 'Clear'}, {lap.session.air_temp}°C"

    # Build import URLs
    protocol_url = f"ridgway://import/{base64_data[:100]}"  # Truncate if too long
    http_url = f"http://localhost:8000/laps/import/protocol/{base64_data[:100]}/"

    discord_message = f"""📊 **New Lap Shared to Team**
━━━━━━━━━━━━━━━━━━━━━
👤 **Driver:** {driver_name}
🏁 **Track:** {track_display}
🏎️ **Car:** {car_display}
⏱️ **Time:** {lap.lap_time}s ({lap_status})
📅 **Date:** {session_date}{weather_info}

📥 **Import Options:**
• One-Click: `{protocol_url}`
• Browser: <{http_url}>

💾 Or download the .lap.gz attachment below
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
def protocol_import(request, base64_data):
    """
    Import a lap from base64-encoded protocol URL.
    Handles both ridgway:// and http://localhost:8000/laps/import/protocol/ URLs.
    """
    import base64
    import json
    from decimal import Decimal

    try:
        # Decode base64 data
        json_data = base64.urlsafe_b64decode(base64_data.encode('utf-8')).decode('utf-8')
        data = json.loads(json_data)

        # Validate format version
        if data.get('format_version') != '1.0':
            messages.error(request, f"Unsupported format version: {data.get('format_version')}")
            return redirect('telemetry:lap_import')

        # Validate required fields
        required_fields = ['lap', 'session', 'driver', 'telemetry']
        for field in required_fields:
            if field not in data:
                messages.error(request, f"Invalid data format: missing '{field}' field.")
                return redirect('telemetry:lap_import')

        # Get or create Track
        track_name = data['session'].get('track_name', 'Unknown Track')
        track_config = data['session'].get('track_config', '')
        track, _ = Track.objects.get_or_create(
            name=track_name,
            configuration=track_config,
            defaults={'name': track_name, 'configuration': track_config}
        )

        # Get or create Car
        car_name = data['session'].get('car_name', 'Unknown Car')
        car, _ = Car.objects.get_or_create(
            name=car_name,
            defaults={'name': car_name}
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
            driver=request.user,
            team=request.user.driver_profile.default_team if hasattr(request.user, 'driver_profile') else None,
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

        # Get driver display name from imported data
        imported_driver_name = data['driver'].get('display_name', 'Unknown Driver')

        messages.success(
            request,
            f"Lap imported from Discord! {imported_driver_name}'s lap on {track_name} ({car_name}) - {lap.lap_time}s"
        )

        # Redirect to lap detail
        return redirect('telemetry:lap_detail', pk=lap.pk)

    except base64.binascii.Error:
        messages.error(request, 'Invalid import link: malformed data.')
        return redirect('telemetry:lap_import')
    except json.JSONDecodeError as e:
        messages.error(request, f'Invalid import link: {str(e)}')
        return redirect('telemetry:lap_import')
    except Exception as e:
        messages.error(request, f'Error importing lap: {str(e)}')
        return redirect('telemetry:lap_import')


# ================================
# System Update Views
# ================================

@staff_member_required
def system_update_check(request):
    """
    Check for available updates from GitHub.
    Returns JSON with current version, latest version, and changelog.
    """
    from django.conf import settings
    import requests
    import subprocess
    from django.http import JsonResponse

    try:
        # Get current version and commit
        current_version = getattr(settings, 'VERSION', 'unknown')

        # Get current git commit
        try:
            current_commit = subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'],
                cwd=settings.BASE_DIR.parent,
                text=True
            ).strip()
            current_commit_short = current_commit[:7]
        except:
            current_commit = 'unknown'
            current_commit_short = 'unknown'

        # Get latest commit from GitHub
        try:
            # GitHub API to get latest commit on main branch
            response = requests.get(
                'https://api.github.com/repos/fullydoved/ridgway_garage/commits/main',
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            latest_commit = data['sha']
            latest_commit_short = latest_commit[:7]
            latest_message = data['commit']['message']
            latest_date = data['commit']['author']['date']

            # Check if update available
            update_available = current_commit != latest_commit

            return JsonResponse({
                'success': True,
                'current_version': current_version,
                'current_commit': current_commit_short,
                'latest_commit': latest_commit_short,
                'latest_message': latest_message,
                'latest_date': latest_date,
                'update_available': update_available,
            })

        except requests.RequestException as e:
            return JsonResponse({
                'success': False,
                'error': f'Could not connect to GitHub: {str(e)}',
                'current_version': current_version,
                'current_commit': current_commit_short,
            })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        })


@staff_member_required
def system_update_page(request):
    """
    Display the system update page with current version,
    available updates, and update history.
    """
    from django.conf import settings
    from .models import SystemUpdate

    # Get current version
    current_version = getattr(settings, 'VERSION', 'unknown')

    # Get recent updates
    recent_updates = SystemUpdate.objects.all()[:10]

    # Check if an update is currently running
    running_update = SystemUpdate.objects.filter(status='running').first()

    context = {
        'current_version': current_version,
        'recent_updates': recent_updates,
        'running_update': running_update,
    }

    return render(request, 'telemetry/system_update.html', context)


@staff_member_required
@require_POST
def system_update_trigger(request):
    """
    Trigger a system update.
    Creates a SystemUpdate record and starts the Celery task.
    """
    from django.conf import settings
    from .models import SystemUpdate
    from .tasks import execute_system_update
    import subprocess

    # Check if an update is already running
    if SystemUpdate.objects.filter(status='running').exists():
        messages.error(request, 'An update is already in progress.')
        return redirect('telemetry:system_update')

    # Get current version and commit
    current_version = getattr(settings, 'VERSION', 'unknown')
    try:
        current_commit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            cwd=settings.BASE_DIR.parent,
            text=True
        ).strip()
    except:
        current_commit = 'unknown'

    # Create update record
    update = SystemUpdate.objects.create(
        triggered_by=request.user,
        old_version=current_version,
        old_commit=current_commit,
        status='pending',
        progress=0,
    )

    # Start Celery task
    execute_system_update.delay(update.id, request.user.id)

    messages.success(request, 'System update started! This page will show progress in real-time.')
    return redirect('telemetry:system_update')


@staff_member_required
def system_update_history(request):
    """
    Display full update history.
    """
    from .models import SystemUpdate

    updates = SystemUpdate.objects.all()

    context = {
        'updates': updates,
    }

    return render(request, 'telemetry/system_update_history.html', context)
