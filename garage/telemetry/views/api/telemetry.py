"""
API endpoints for telemetry data access and chart generation.
"""

import json
import logging

import numpy as np
import plotly.graph_objects as go
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from plotly.subplots import make_subplots

from ...models import Lap, Team

logger = logging.getLogger(__name__)


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
    # Debug: Log that we entered the view
    logger.info("api_lap_telemetry called: lap_id=%s, user=%s, authenticated=%s",
                lap_id, request.user, request.user.is_authenticated)

    try:
        lap = get_object_or_404(Lap, id=lap_id)

        # Check if user has permission to view this lap
        # Allow if: user owns the session, or user shares a team with the session's driver
        if lap.session.driver != request.user:
            # Check if user and driver share any team membership
            # Get team IDs for both users and check for intersection
            user_team_ids = set(Team.objects.filter(members=request.user).values_list('id', flat=True))
            driver_team_ids = set(Team.objects.filter(members=lap.session.driver).values_list('id', flat=True))
            shared_teams = user_team_ids & driver_team_ids
            driver_in_user_teams = len(shared_teams) > 0

            logger.info(
                "Permission check for lap %s: user=%s, driver=%s, shared_teams=%s",
                lap_id, request.user.username, lap.session.driver.username, shared_teams
            )

            if not driver_in_user_teams:
                logger.warning(
                    "Permission DENIED for lap %s: user=%s has no shared teams with driver=%s",
                    lap_id, request.user.username, lap.session.driver.username
                )
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
        logger.exception("Error fetching lap telemetry: %s", e)
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

    except ValueError as e:
        return JsonResponse({
            'error': f'Invalid parameter: {e}'
        }, status=400)
    except Exception as e:
        logger.exception("Error fetching fastest laps: %s", e)
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
    try:
        # Parse request body
        body = json.loads(request.body)
        lap_ids = body.get('lap_ids', [])
        lap_colors = body.get('lap_colors', [])  # Color assignments from client
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

            # Check permissions - allow if user owns session or shares a team with driver
            if lap.session.driver != request.user:
                user_team_ids = set(Team.objects.filter(members=request.user).values_list('id', flat=True))
                driver_team_ids = set(Team.objects.filter(members=lap.session.driver).values_list('id', flat=True))
                if not (user_team_ids & driver_team_ids):
                    continue

            laps.append(lap)

        if not laps:
            return JsonResponse({'error': 'No valid laps found'}, status=404)

        # Color palette (hot to cold: Red, Orange, Yellow, Green, Blue)
        default_colors = ['#FF0000', '#FF8C00', '#FFD700', '#00FF00', '#00BFFF']

        # Extract telemetry data
        lap_data = []
        for i, lap in enumerate(laps):
            telemetry = lap.telemetry
            if telemetry and telemetry.data:
                # Use client-provided color if available, otherwise use default palette
                if lap_colors and i < len(lap_colors):
                    color = lap_colors[i]
                else:
                    color = default_colors[i % len(default_colors)]

                lap_data.append({
                    'lap': lap,
                    'data': telemetry.data,
                    'color': color,
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
                    except (ValueError, IndexError) as e:
                        logger.warning("Error calculating delta: %s", e)

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
                    except (KeyError, TypeError) as e:
                        logger.warning("Error adding trace for %s: %s", subplot_type, e)

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
        logger.exception("Error generating chart: %s", e)
        return JsonResponse({'error': str(e)}, status=500)
