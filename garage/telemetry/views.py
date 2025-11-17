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
