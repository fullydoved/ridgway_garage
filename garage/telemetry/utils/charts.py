"""
Plotly chart generation utilities for telemetry visualization.
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import math


def create_speed_chart(telemetry_data):
    """
    Create an interactive speed vs distance chart.

    Args:
        telemetry_data: Dictionary containing telemetry channels

    Returns:
        HTML string for embedding in template
    """
    if 'Speed' not in telemetry_data or 'LapDist' not in telemetry_data:
        return None

    # Convert m/s to km/h (multiply by 3.6)
    speed_kmh = [s * 3.6 for s in telemetry_data['Speed']]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=telemetry_data['LapDist'],
        y=speed_kmh,
        mode='lines',
        name='Speed',
        line=dict(color='#00d4ff', width=2),
        hovertemplate='<b>Distance:</b> %{x:.0f}m<br><b>Speed:</b> %{y:.1f} km/h<extra></extra>'
    ))

    fig.update_layout(
        title='Speed vs Distance',
        xaxis_title='Distance (m)',
        yaxis_title='Speed (km/h)',
        template='plotly_dark',
        hovermode='x unified',
        height=450,
        margin=dict(l=60, r=60, t=50, b=50),
        dragmode='zoom'  # Enable box select zoom by default
    )

    return fig.to_html(div_id='speed-chart', include_plotlyjs=False, config={
        'displayModeBar': True,
        'modeBarButtonsToAdd': ['select2d', 'lasso2d'],
        'modeBarButtonsToRemove': ['toImage']
    })


def create_inputs_chart(telemetry_data):
    """
    Create an overlay chart showing throttle, brake, and clutch inputs.

    Args:
        telemetry_data: Dictionary containing telemetry channels

    Returns:
        HTML string for embedding in template
    """
    if 'LapDist' not in telemetry_data:
        return None

    fig = go.Figure()

    # Throttle (green)
    if 'Throttle' in telemetry_data:
        fig.add_trace(go.Scatter(
            x=telemetry_data['LapDist'],
            y=[t * 100 for t in telemetry_data['Throttle']],  # Convert to percentage
            mode='lines',
            name='Throttle',
            line=dict(color='#00ff00', width=2),
            fill='tozeroy',
            fillcolor='rgba(0, 255, 0, 0.2)',
            hovertemplate='<b>Throttle:</b> %{y:.1f}%<extra></extra>'
        ))

    # Brake (red)
    if 'Brake' in telemetry_data:
        fig.add_trace(go.Scatter(
            x=telemetry_data['LapDist'],
            y=[b * 100 for b in telemetry_data['Brake']],  # Convert to percentage
            mode='lines',
            name='Brake',
            line=dict(color='#ff0000', width=2),
            fill='tozeroy',
            fillcolor='rgba(255, 0, 0, 0.2)',
            hovertemplate='<b>Brake:</b> %{y:.1f}%<extra></extra>'
        ))

    # Clutch (blue, optional)
    if 'Clutch' in telemetry_data:
        fig.add_trace(go.Scatter(
            x=telemetry_data['LapDist'],
            y=[c * 100 for c in telemetry_data['Clutch']],  # Convert to percentage
            mode='lines',
            name='Clutch',
            line=dict(color='#0088ff', width=1),
            hovertemplate='<b>Clutch:</b> %{y:.1f}%<extra></extra>'
        ))

    fig.update_layout(
        title='Driver Inputs (Throttle, Brake, Clutch)',
        xaxis_title='Distance (m)',
        yaxis_title='Input (%)',
        yaxis=dict(range=[0, 105]),
        template='plotly_dark',
        hovermode='x unified',
        height=450,
        margin=dict(l=60, r=60, t=50, b=50),
        dragmode='zoom'
    )

    return fig.to_html(div_id='inputs-chart', include_plotlyjs=False, config={
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['toImage']
    })


def create_steering_chart(telemetry_data):
    """
    Create a steering angle chart.

    Args:
        telemetry_data: Dictionary containing telemetry channels

    Returns:
        HTML string for embedding in template
    """
    if 'SteeringWheelAngle' not in telemetry_data or 'LapDist' not in telemetry_data:
        return None

    fig = go.Figure()

    # Convert radians to degrees for better readability
    import math
    steering_degrees = [angle * (180 / math.pi) for angle in telemetry_data['SteeringWheelAngle']]

    fig.add_trace(go.Scatter(
        x=telemetry_data['LapDist'],
        y=steering_degrees,
        mode='lines',
        name='Steering Angle',
        line=dict(color='#ff6b00', width=2),
        hovertemplate='<b>Steering:</b> %{y:.1f}°<extra></extra>'
    ))

    # Add zero line for reference
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

    fig.update_layout(
        title='Steering Wheel Angle',
        xaxis_title='Distance (m)',
        yaxis_title='Angle (degrees)',
        template='plotly_dark',
        hovermode='x unified',
        height=450,
        margin=dict(l=60, r=60, t=50, b=50),
        dragmode='zoom'
    )

    return fig.to_html(div_id='steering-chart', include_plotlyjs=False, config={
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['toImage']
    })


def create_rpm_gear_chart(telemetry_data):
    """
    Create a dual-axis chart showing RPM and gear.

    Args:
        telemetry_data: Dictionary containing telemetry channels

    Returns:
        HTML string for embedding in template
    """
    if 'LapDist' not in telemetry_data:
        return None

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # RPM on primary axis
    if 'RPM' in telemetry_data:
        fig.add_trace(
            go.Scatter(
                x=telemetry_data['LapDist'],
                y=telemetry_data['RPM'],
                mode='lines',
                name='RPM',
                line=dict(color='#ffaa00', width=2),
                hovertemplate='<b>RPM:</b> %{y:.0f}<extra></extra>'
            ),
            secondary_y=False
        )

    # Gear on secondary axis
    if 'Gear' in telemetry_data:
        fig.add_trace(
            go.Scatter(
                x=telemetry_data['LapDist'],
                y=telemetry_data['Gear'],
                mode='lines',
                name='Gear',
                line=dict(color='#00ffaa', width=2, shape='hv'),
                hovertemplate='<b>Gear:</b> %{y}<extra></extra>'
            ),
            secondary_y=True
        )

    fig.update_xaxes(title_text="Distance (m)")
    fig.update_yaxes(title_text="RPM", secondary_y=False)
    fig.update_yaxes(title_text="Gear", range=[0, 10], secondary_y=True)

    fig.update_layout(
        title='RPM and Gear',
        template='plotly_dark',
        hovermode='x unified',
        height=450,
        margin=dict(l=60, r=60, t=50, b=50),
        dragmode='zoom'
    )

    return fig.to_html(div_id='rpm-gear-chart', include_plotlyjs=False, config={
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['toImage']
    })


def create_tire_temp_chart(telemetry_data):
    """
    Create a chart showing tire temperatures for all four tires (3 zones each).

    Args:
        telemetry_data: Dictionary containing telemetry channels

    Returns:
        HTML string for embedding in template
    """
    if 'LapDist' not in telemetry_data:
        return None

    # Check if we have tire surface temp data (these change more dynamically)
    tire_channels = {
        'LF': ['LFtempL', 'LFtempM', 'LFtempR'],
        'RF': ['RFtempL', 'RFtempM', 'RFtempR'],
        'LR': ['LRtempL', 'LRtempM', 'LRtempR'],
        'RR': ['RRtempL', 'RRtempM', 'RRtempR']
    }

    has_tire_data = any(
        all(channel in telemetry_data for channel in channels)
        for channels in tire_channels.values()
    )

    if not has_tire_data:
        return None

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Left Front', 'Right Front', 'Left Rear', 'Right Rear')
    )

    tire_positions = [
        ('LF', 1, 1),
        ('RF', 1, 2),
        ('LR', 2, 1),
        ('RR', 2, 2)
    ]

    colors = {'L': '#0088ff', 'M': '#ff8800', 'R': '#ff0088'}
    zone_names = {'L': 'Left', 'M': 'Middle', 'R': 'Right'}

    for tire, row, col in tire_positions:
        for zone in ['L', 'M', 'R']:
            # Use surface temps (without 'C') - these change more dynamically
            channel = f'{tire}temp{zone}'
            if channel in telemetry_data:
                fig.add_trace(
                    go.Scatter(
                        x=telemetry_data['LapDist'],
                        y=telemetry_data[channel],
                        mode='lines',
                        name=zone_names[zone],
                        line=dict(color=colors[zone], width=2),
                        showlegend=(row == 1 and col == 1),  # Only show legend once
                        hovertemplate=f'<b>{zone_names[zone]}:</b> %{{y:.1f}}°C<extra></extra>'
                    ),
                    row=row, col=col
                )

    fig.update_xaxes(title_text="Distance (m)", row=2, col=1)
    fig.update_xaxes(title_text="Distance (m)", row=2, col=2)
    fig.update_yaxes(title_text="Temp (°C)", row=1, col=1)
    fig.update_yaxes(title_text="Temp (°C)", row=2, col=1)

    fig.update_layout(
        title='Tire Surface Temperatures (3 Zones per Tire)',
        template='plotly_dark',
        hovermode='x unified',
        height=650,
        margin=dict(l=60, r=60, t=80, b=50),
        dragmode='zoom'
    )

    return fig.to_html(div_id='tire-temp-chart', include_plotlyjs=False, config={
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['toImage']
    })


def prepare_gps_data(telemetry_data):
    """
    Prepare GPS data for the Leaflet track map.

    Args:
        telemetry_data: Dictionary containing telemetry channels

    Returns:
        Dictionary with GPS coordinates, speed, and distance data for the map
    """
    if 'Lat' not in telemetry_data or 'Lon' not in telemetry_data:
        return None

    # Combine lat, lon, speed, and distance data
    gps_data = {
        'coordinates': [],
        'speeds': [],
        'distances': []
    }

    speeds = telemetry_data.get('Speed', [0] * len(telemetry_data['Lat']))
    distances = telemetry_data.get('LapDist', list(range(len(telemetry_data['Lat']))))

    for lat, lon, speed, distance in zip(telemetry_data['Lat'], telemetry_data['Lon'], speeds, distances):
        # Filter out invalid GPS coordinates (0, 0)
        if lat != 0 or lon != 0:
            gps_data['coordinates'].append([lat, lon])
            # Convert m/s to km/h (multiply by 3.6)
            gps_data['speeds'].append(speed * 3.6)
            gps_data['distances'].append(distance)

    if not gps_data['coordinates']:
        return None

    return gps_data


def create_combined_telemetry_chart(telemetry_data):
    """
    Create a single combined chart with all telemetry data in synchronized subplots.
    This approach uses Plotly's native subplot sharing to synchronize zoom/pan.

    Args:
        telemetry_data: Dictionary containing telemetry channels

    Returns:
        HTML string for embedding in template
    """
    if 'LapDist' not in telemetry_data:
        return None

    # Determine which charts we can create based on available data
    has_speed = 'Speed' in telemetry_data
    has_inputs = 'Throttle' in telemetry_data or 'Brake' in telemetry_data
    has_steering = 'SteeringWheelAngle' in telemetry_data
    has_rpm = 'RPM' in telemetry_data or 'Gear' in telemetry_data

    # Check which tires have temperature data
    tire_names = {'LF': 'Left Front', 'RF': 'Right Front', 'LR': 'Left Rear', 'RR': 'Right Rear'}
    tires_with_data = []
    for tire in ['LF', 'RF', 'LR', 'RR']:
        if any(f'{tire}temp{zone}' in telemetry_data for zone in ['L', 'M', 'R']):
            tires_with_data.append(tire)

    # Count how many subplots we need (one per tire with data)
    subplot_count = sum([has_speed, has_inputs, has_steering, has_rpm]) + len(tires_with_data)
    if subplot_count == 0:
        return None

    # Create subplot titles
    subplot_titles = []
    if has_speed:
        subplot_titles.append('Speed vs Distance')
    if has_inputs:
        subplot_titles.append('Driver Inputs - Green: Throttle | Red: Brake | Blue: Clutch')
    if has_steering:
        subplot_titles.append('Steering Wheel Angle')
    if has_rpm:
        subplot_titles.append('RPM (Orange) and Gear (Cyan)')
    # Add one title per tire
    for tire in tires_with_data:
        subplot_titles.append(f'{tire_names[tire]} Tire Temps - Blue: Left | Orange: Middle | Pink: Right')

    # Create subplot specs - RPM chart needs secondary_y for the gear overlay
    specs = []
    for i, title in enumerate(subplot_titles):
        if 'RPM' in title:
            specs.append([{"secondary_y": True}])
        else:
            specs.append([{"secondary_y": False}])

    # Create subplots with shared x-axis
    fig = make_subplots(
        rows=subplot_count, cols=1,
        shared_xaxes=True,  # This enables automatic zoom/pan synchronization!
        vertical_spacing=0.03,  # Compact spacing between charts
        subplot_titles=subplot_titles,
        specs=specs,
        row_heights=[1] * subplot_count  # Equal height for all subplots
    )

    current_row = 1
    legend_group = 1  # Track which legend group each trace belongs to

    # Add Speed chart
    if has_speed:
        speed_kmh = [s * 3.6 for s in telemetry_data['Speed']]
        fig.add_trace(
            go.Scatter(
                x=telemetry_data['LapDist'],
                y=speed_kmh,
                mode='lines',
                name='Speed',
                line=dict(color='#00d4ff', width=2),
                hovertemplate='<b>Speed:</b> %{y:.1f} km/h<extra></extra>',
                showlegend=False,
                legendgroup=f'group{legend_group}'
            ),
            row=current_row, col=1
        )
        fig.update_yaxes(title_text="Speed (km/h)", row=current_row, col=1)
        current_row += 1
        legend_group += 1

    # Add Inputs chart
    if has_inputs:
        if 'Throttle' in telemetry_data:
            fig.add_trace(
                go.Scatter(
                    x=telemetry_data['LapDist'],
                    y=[t * 100 for t in telemetry_data['Throttle']],
                    mode='lines',
                    name='Throttle',
                    line=dict(color='#00ff00', width=2),
                    fill='tozeroy',
                    fillcolor='rgba(0, 255, 0, 0.2)',
                    hovertemplate='<b>Throttle:</b> %{y:.1f}%<extra></extra>'
                ),
                row=current_row, col=1
            )

        if 'Brake' in telemetry_data:
            fig.add_trace(
                go.Scatter(
                    x=telemetry_data['LapDist'],
                    y=[b * 100 for b in telemetry_data['Brake']],
                    mode='lines',
                    name='Brake',
                    line=dict(color='#ff0000', width=2),
                    fill='tozeroy',
                    fillcolor='rgba(255, 0, 0, 0.2)',
                    hovertemplate='<b>Brake:</b> %{y:.1f}%<extra></extra>'
                ),
                row=current_row, col=1
            )

        if 'Clutch' in telemetry_data:
            fig.add_trace(
                go.Scatter(
                    x=telemetry_data['LapDist'],
                    y=[c * 100 for c in telemetry_data['Clutch']],
                    mode='lines',
                    name='Clutch',
                    line=dict(color='#0088ff', width=1),
                    hovertemplate='<b>Clutch:</b> %{y:.1f}%<extra></extra>'
                ),
                row=current_row, col=1
            )

        fig.update_yaxes(title_text="Input (%)", range=[0, 105], row=current_row, col=1)
        current_row += 1
        legend_group += 1

    # Add Steering chart
    if has_steering:
        steering_degrees = [angle * (180 / math.pi) for angle in telemetry_data['SteeringWheelAngle']]
        fig.add_trace(
            go.Scatter(
                x=telemetry_data['LapDist'],
                y=steering_degrees,
                mode='lines',
                name='Steering Angle',
                line=dict(color='#ff6b00', width=2),
                hovertemplate='<b>Steering:</b> %{y:.1f}°<extra></extra>',
                showlegend=False,
                legendgroup=f'group{legend_group}'
            ),
            row=current_row, col=1
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=current_row, col=1)
        fig.update_yaxes(title_text="Angle (degrees)", row=current_row, col=1)
        current_row += 1
        legend_group += 1

    # Add RPM and Gear chart
    if has_rpm:
        if 'RPM' in telemetry_data:
            fig.add_trace(
                go.Scatter(
                    x=telemetry_data['LapDist'],
                    y=telemetry_data['RPM'],
                    mode='lines',
                    name='RPM',
                    line=dict(color='#ffaa00', width=2),
                    hovertemplate='<b>RPM:</b> %{y:.0f}<extra></extra>'
                ),
                row=current_row, col=1, secondary_y=False
            )

        if 'Gear' in telemetry_data:
            fig.add_trace(
                go.Scatter(
                    x=telemetry_data['LapDist'],
                    y=telemetry_data['Gear'],
                    mode='lines',
                    name='Gear',
                    line=dict(color='#00ffaa', width=2, shape='hv'),
                    hovertemplate='<b>Gear:</b> %{y}<extra></extra>'
                ),
                row=current_row, col=1, secondary_y=True
            )

        fig.update_yaxes(title_text="RPM", row=current_row, col=1, secondary_y=False)
        fig.update_yaxes(title_text="Gear", range=[0, 10], row=current_row, col=1, secondary_y=True)
        current_row += 1
        legend_group += 1

    # Add Tire Temperature charts (one per tire)
    if tires_with_data:
        colors = {'L': '#0088ff', 'M': '#ff8800', 'R': '#ff0088'}
        zone_names = {'L': 'Left', 'M': 'Middle', 'R': 'Right'}

        for tire in tires_with_data:
            # Add one subplot for this tire
            for zone in ['L', 'M', 'R']:
                channel = f'{tire}temp{zone}'
                if channel in telemetry_data:
                    fig.add_trace(
                        go.Scatter(
                            x=telemetry_data['LapDist'],
                            y=telemetry_data[channel],
                            mode='lines',
                            name=zone_names[zone],
                            line=dict(color=colors[zone], width=2),
                            hovertemplate=f'<b>{zone_names[zone]}:</b> %{{y:.1f}}°C<extra></extra>'
                        ),
                        row=current_row, col=1
                    )

            fig.update_yaxes(title_text="Temp (°C)", row=current_row, col=1)
            current_row += 1
            legend_group += 1

    # Update overall layout
    fig.update_layout(
        template='plotly_dark',
        hovermode='x',  # Show hover on all subplots at same x-position
        height=280 * subplot_count,  # More compact - 280px per subplot
        margin=dict(l=60, r=60, t=40, b=60),  # Reduced top margin
        dragmode='zoom',
        showlegend=False  # Hide legend - rely on titles and hover info instead
    )

    # Update x-axis for the bottom subplot only (shows "Distance (m)")
    fig.update_xaxes(title_text="Distance (m)", row=subplot_count, col=1)

    # Make subplot titles more prominent with better styling
    for annotation in fig.layout.annotations:
        annotation.font.size = 15  # Larger font
        annotation.font.color = '#00d4ff'  # Bright cyan color
        annotation.font.family = 'Arial, sans-serif'
        annotation.xanchor = 'left'
        annotation.x = 0  # Align to left
        annotation.yanchor = 'bottom'

    return fig.to_html(div_id='combined-telemetry-chart', include_plotlyjs=False, config={
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['toImage']
    })


def create_comparison_chart(laps):
    """
    Create comparison charts overlaying multiple laps.

    Args:
        laps: QuerySet or list of Lap objects to compare

    Returns:
        HTML string for embedding in template, or None if not enough data
    """
    if not laps or len(laps) < 2:
        return None

    # Color palette for different laps
    colors = [
        '#00d4ff',  # Cyan
        '#ff6b00',  # Orange
        '#00ff00',  # Green
        '#ff0088',  # Pink
        '#ffaa00',  # Yellow
        '#8800ff',  # Purple
        '#00ffaa',  # Teal
        '#ff0000',  # Red
    ]

    # Extract telemetry data from all laps
    lap_data = []
    for lap in laps:
        try:
            telemetry = lap.telemetry
            if telemetry and telemetry.data:
                lap_data.append({
                    'lap': lap,
                    'data': telemetry.data,
                    'color': colors[len(lap_data) % len(colors)]
                })
        except:
            pass

    if len(lap_data) < 2:
        return None

    # Sort by lap time to find the fastest (baseline for delta)
    lap_data_sorted = sorted(lap_data, key=lambda x: x['lap'].lap_time)
    fastest_lap = lap_data_sorted[0]

    # Determine which charts we can create (based on first lap's data)
    first_data = lap_data[0]['data']
    has_delta = 'SessionTime' in first_data and 'LapDist' in first_data
    has_speed = 'Speed' in first_data and 'LapDist' in first_data
    has_inputs = 'Throttle' in first_data or 'Brake' in first_data
    has_steering = 'SteeringWheelAngle' in first_data
    has_rpm = 'RPM' in first_data or 'Gear' in first_data

    # Check which tires have temperature data
    tire_names = {'LF': 'Left Front', 'RF': 'Right Front', 'LR': 'Left Rear', 'RR': 'Right Rear'}
    tires_with_data = []
    for tire in ['LF', 'RF', 'LR', 'RR']:
        if any(f'{tire}temp{zone}' in first_data for zone in ['L', 'M', 'R']):
            tires_with_data.append(tire)

    # Count subplots (including delta and tire temps)
    subplot_count = sum([has_delta, has_speed, has_inputs, has_steering, has_rpm]) + len(tires_with_data)
    if subplot_count == 0:
        return None

    # Create subplot titles
    subplot_titles = []
    if has_delta:
        subplot_titles.append('Time Delta vs Fastest Lap')
    if has_speed:
        subplot_titles.append('Speed Comparison')
    if has_inputs:
        subplot_titles.append('Throttle and Brake Comparison')
    if has_steering:
        subplot_titles.append('Steering Angle Comparison')
    if has_rpm:
        subplot_titles.append('RPM and Gear Comparison')
    # Add one title per tire
    for tire in tires_with_data:
        subplot_titles.append(f'{tire_names[tire]} Tire Temps')

    # Create subplot specs - RPM chart needs secondary_y for gear
    specs = []
    for i, title in enumerate(subplot_titles):
        if 'RPM and Gear' in title:
            specs.append([{"secondary_y": True}])
        else:
            specs.append([{"secondary_y": False}])

    # Create subplots with shared x-axis
    fig = make_subplots(
        rows=subplot_count, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=subplot_titles,
        specs=specs,
        row_heights=[1] * subplot_count
    )

    current_row = 1

    # Add Time Delta comparison (first subplot)
    if has_delta:
        import numpy as np

        for i, lap_info in enumerate(lap_data):
            lap = lap_info['lap']
            data = lap_info['data']

            # Skip the fastest lap (it's the 0 line)
            if lap == fastest_lap['lap']:
                continue

            try:
                # Get distance and time arrays for this lap
                lap_distance = np.array(data['LapDist'])
                lap_time = np.array(data['SessionTime'])

                # Get distance and time arrays for fastest lap
                fastest_distance = np.array(fastest_lap['data']['LapDist'])
                fastest_time = np.array(fastest_lap['data']['SessionTime'])

                # Normalize both to start at 0
                lap_time = lap_time - lap_time[0]
                fastest_time = fastest_time - fastest_time[0]

                # Find common distance range
                min_dist = max(lap_distance[0], fastest_distance[0])
                max_dist = min(lap_distance[-1], fastest_distance[-1])

                # Create common distance array for comparison (every 10 meters)
                common_distance = np.arange(min_dist, max_dist, 10)

                # Interpolate both laps' times to the common distance points
                lap_time_interp = np.interp(common_distance, lap_distance, lap_time)
                fastest_time_interp = np.interp(common_distance, fastest_distance, fastest_time)

                # Calculate delta (positive = slower, negative = faster)
                time_delta = lap_time_interp - fastest_time_interp

                fig.add_trace(
                    go.Scatter(
                        x=common_distance,
                        y=time_delta,
                        mode='lines',
                        name=f'Lap {lap.lap_number} (+{lap.lap_time - fastest_lap["lap"].lap_time:.3f}s)',
                        line=dict(color=lap_info['color'], width=2),
                        hovertemplate='<b>%{fullData.name}</b><br>Distance: %{x:.0f}m<br>Delta: %{y:+.3f}s<extra></extra>',
                        showlegend=False,
                        fill='tozeroy',
                        fillcolor=f'rgba({int(lap_info["color"][1:3], 16)}, {int(lap_info["color"][3:5], 16)}, {int(lap_info["color"][5:7], 16)}, 0.1)'
                    ),
                    row=current_row, col=1
                )
            except Exception as e:
                # Skip this lap if interpolation fails
                continue

        # Add zero reference line (fastest lap baseline)
        fig.add_hline(
            y=0,
            line_dash="solid",
            line_color=fastest_lap['color'],
            line_width=2,
            row=current_row, col=1
        )
        fig.update_yaxes(title_text="Delta (s)", row=current_row, col=1)
        current_row += 1

    # Add Speed comparison
    if has_speed:
        for i, lap_info in enumerate(lap_data):
            data = lap_info['data']
            if 'Speed' in data and 'LapDist' in data:
                speed_kmh = [s * 3.6 for s in data['Speed']]
                lap = lap_info['lap']
                fig.add_trace(
                    go.Scatter(
                        x=data['LapDist'],
                        y=speed_kmh,
                        mode='lines',
                        name=f'Lap {lap.lap_number} ({lap.lap_time:.3f}s)',
                        line=dict(color=lap_info['color'], width=2),
                        hovertemplate='<b>%{fullData.name}</b><br>Speed: %{y:.1f} km/h<extra></extra>',
                        showlegend=True
                    ),
                    row=current_row, col=1
                )
        fig.update_yaxes(title_text="Speed (km/h)", row=current_row, col=1)
        current_row += 1

    # Add Inputs comparison (Throttle and Brake overlaid)
    if has_inputs:
        for i, lap_info in enumerate(lap_data):
            data = lap_info['data']
            lap = lap_info['lap']

            # Throttle (solid line)
            if 'Throttle' in data and 'LapDist' in data:
                fig.add_trace(
                    go.Scatter(
                        x=data['LapDist'],
                        y=[t * 100 for t in data['Throttle']],
                        mode='lines',
                        name=f'Lap {lap.lap_number} Throttle',
                        line=dict(color=lap_info['color'], width=2),
                        hovertemplate='<b>Lap %{fullData.name}</b><br>Throttle: %{y:.1f}%<extra></extra>',
                        showlegend=False
                    ),
                    row=current_row, col=1
                )

            # Brake (dashed line)
            if 'Brake' in data and 'LapDist' in data:
                fig.add_trace(
                    go.Scatter(
                        x=data['LapDist'],
                        y=[b * 100 for b in data['Brake']],
                        mode='lines',
                        name=f'Lap {lap.lap_number} Brake',
                        line=dict(color=lap_info['color'], width=2, dash='dash'),
                        hovertemplate='<b>Lap %{fullData.name}</b><br>Brake: %{y:.1f}%<extra></extra>',
                        showlegend=False
                    ),
                    row=current_row, col=1
                )

        fig.update_yaxes(title_text="Input (%)", range=[0, 105], row=current_row, col=1)
        current_row += 1

    # Add Steering comparison
    if has_steering:
        for i, lap_info in enumerate(lap_data):
            data = lap_info['data']
            if 'SteeringWheelAngle' in data and 'LapDist' in data:
                steering_degrees = [angle * (180 / math.pi) for angle in data['SteeringWheelAngle']]
                lap = lap_info['lap']
                fig.add_trace(
                    go.Scatter(
                        x=data['LapDist'],
                        y=steering_degrees,
                        mode='lines',
                        name=f'Lap {lap.lap_number}',
                        line=dict(color=lap_info['color'], width=2),
                        hovertemplate='<b>%{fullData.name}</b><br>Steering: %{y:.1f}°<extra></extra>',
                        showlegend=False
                    ),
                    row=current_row, col=1
                )
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=current_row, col=1)
        fig.update_yaxes(title_text="Angle (degrees)", row=current_row, col=1)
        current_row += 1

    # Add RPM and Gear comparison
    if has_rpm:
        for i, lap_info in enumerate(lap_data):
            data = lap_info['data']
            lap = lap_info['lap']

            # Add RPM on primary y-axis
            if 'RPM' in data and 'LapDist' in data:
                fig.add_trace(
                    go.Scatter(
                        x=data['LapDist'],
                        y=data['RPM'],
                        mode='lines',
                        name=f'Lap {lap.lap_number} RPM',
                        line=dict(color=lap_info['color'], width=2),
                        hovertemplate='<b>%{fullData.name}</b><br>RPM: %{y:.0f}<extra></extra>',
                        showlegend=False
                    ),
                    row=current_row, col=1, secondary_y=False
                )

            # Add Gear on secondary y-axis with gear=0 filtered out
            if 'Gear' in data and 'LapDist' in data:
                # Filter out gear=0 (neutral during shifts) - replace with previous gear
                gears = data['Gear']
                filtered_gears = []
                last_valid_gear = 1  # Start with 1st gear as default

                for gear in gears:
                    if gear == 0:
                        # Keep the previous gear during shifts
                        filtered_gears.append(last_valid_gear)
                    else:
                        filtered_gears.append(gear)
                        last_valid_gear = gear

                fig.add_trace(
                    go.Scatter(
                        x=data['LapDist'],
                        y=filtered_gears,
                        mode='lines',
                        name=f'Lap {lap.lap_number} Gear',
                        line=dict(color=lap_info['color'], width=2, shape='hv', dash='dot'),
                        hovertemplate='<b>%{fullData.name}</b><br>Gear: %{y}<extra></extra>',
                        showlegend=False
                    ),
                    row=current_row, col=1, secondary_y=True
                )

        fig.update_yaxes(title_text="RPM", row=current_row, col=1, secondary_y=False)
        fig.update_yaxes(title_text="Gear", range=[0, 10], row=current_row, col=1, secondary_y=True)
        current_row += 1

    # Add Tire Temperature comparisons (one subplot per tire)
    if tires_with_data:
        zone_colors = {'L': '#0088ff', 'M': '#ff8800', 'R': '#ff0088'}
        zone_names = {'L': 'Left', 'M': 'Middle', 'R': 'Right'}

        for tire in tires_with_data:
            # For each tire, add all laps' data
            for zone in ['L', 'M', 'R']:
                channel = f'{tire}temp{zone}'
                for i, lap_info in enumerate(lap_data):
                    data = lap_info['data']
                    if channel in data and 'LapDist' in data:
                        lap = lap_info['lap']
                        # Use lap color with zone-based line style
                        line_style = {'L': 'solid', 'M': 'dash', 'R': 'dot'}[zone]
                        fig.add_trace(
                            go.Scatter(
                                x=data['LapDist'],
                                y=data[channel],
                                mode='lines',
                                name=f'Lap {lap.lap_number} {zone_names[zone]}',
                                line=dict(color=lap_info['color'], width=2, dash=line_style),
                                hovertemplate=f'<b>Lap {lap.lap_number} {zone_names[zone]}</b><br>Temp: %{{y:.1f}}°C<extra></extra>',
                                showlegend=False
                            ),
                            row=current_row, col=1
                        )

            fig.update_yaxes(title_text="Temp (°C)", row=current_row, col=1)
            current_row += 1

    # Update overall layout
    fig.update_layout(
        template='plotly_dark',
        hovermode='x',
        height=350 * subplot_count,  # Slightly taller for comparison charts
        margin=dict(l=60, r=60, t=60, b=60),
        dragmode='zoom',
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0
        )
    )

    # Update x-axis for the bottom subplot only
    fig.update_xaxes(title_text="Distance (m)", row=subplot_count, col=1)

    # Make subplot titles more prominent
    for annotation in fig.layout.annotations:
        annotation.font.size = 15
        annotation.font.color = '#00d4ff'
        annotation.font.family = 'Arial, sans-serif'
        annotation.xanchor = 'left'
        annotation.x = 0
        annotation.yanchor = 'bottom'

    return fig.to_html(div_id='comparison-chart', include_plotlyjs=False, config={
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['toImage']
    })


def prepare_comparison_gps_data(laps):
    """
    Prepare GPS data for multiple laps to overlay on track map.

    Args:
        laps: QuerySet or list of Lap objects to compare

    Returns:
        List of dictionaries with GPS data for each lap, or None if not enough data
    """
    if not laps or len(laps) < 1:
        return None

    # Color palette for different laps (same as comparison charts)
    colors = [
        '#00d4ff',  # Cyan
        '#ff6b00',  # Orange
        '#00ff00',  # Green
        '#ff0088',  # Pink
        '#ffaa00',  # Yellow
        '#8800ff',  # Purple
        '#00ffaa',  # Teal
        '#ff0000',  # Red
    ]

    laps_gps_data = []

    for i, lap in enumerate(laps):
        try:
            telemetry = lap.telemetry
            if telemetry and telemetry.data:
                data = telemetry.data
                if 'Lat' in data and 'Lon' in data:
                    gps_data = {
                        'lap_number': lap.lap_number,
                        'lap_time': float(lap.lap_time),  # Ensure it's a float, not Decimal
                        'color': colors[i % len(colors)],
                        'coordinates': [],
                        'speeds': [],
                        'distances': []
                    }

                    speeds = data.get('Speed', [0] * len(data['Lat']))
                    distances = data.get('LapDist', list(range(len(data['Lat']))))

                    for lat, lon, speed, distance in zip(data['Lat'], data['Lon'], speeds, distances):
                        # Filter out invalid GPS coordinates (0, 0)
                        if lat != 0 or lon != 0:
                            gps_data['coordinates'].append([lat, lon])
                            # Convert m/s to km/h (multiply by 3.6)
                            gps_data['speeds'].append(speed * 3.6)
                            gps_data['distances'].append(distance)

                    if gps_data['coordinates']:
                        laps_gps_data.append(gps_data)
        except:
            pass

    if not laps_gps_data:
        return None

    return laps_gps_data


def create_time_delta_chart(laps):
    """
    Create a time delta chart showing time gained/lost vs the fastest lap.

    The fastest lap is set as the baseline (0 line). Positive values mean
    the lap is slower (losing time), negative values mean faster (gaining time).

    Args:
        laps: QuerySet or list of Lap objects to compare

    Returns:
        HTML string for embedding in template, or None if not enough data
    """
    if not laps or len(laps) < 2:
        return None

    # Color palette for different laps
    colors = [
        '#00d4ff',  # Cyan
        '#ff6b00',  # Orange
        '#00ff00',  # Green
        '#ff0088',  # Pink
        '#ffaa00',  # Yellow
        '#8800ff',  # Purple
        '#00ffaa',  # Teal
        '#ff0000',  # Red
    ]

    # Extract telemetry data from all laps
    lap_data = []
    for lap in laps:
        try:
            telemetry = lap.telemetry
            if telemetry and telemetry.data:
                if 'SessionTime' in telemetry.data and 'LapDist' in telemetry.data:
                    lap_data.append({
                        'lap': lap,
                        'data': telemetry.data,
                        'color': colors[len(lap_data) % len(colors)]
                    })
        except:
            pass

    if len(lap_data) < 2:
        return None

    # Sort by lap time to find the fastest (baseline)
    lap_data.sort(key=lambda x: x['lap'].lap_time)
    fastest = lap_data[0]

    # Import numpy for interpolation
    import numpy as np

    fig = go.Figure()

    # Process each lap (skip the fastest since it's the baseline)
    for i, lap_info in enumerate(lap_data):
        lap = lap_info['lap']
        data = lap_info['data']

        # Skip the fastest lap (it's the 0 line)
        if lap == fastest['lap']:
            continue

        try:
            # Get distance and time arrays for this lap
            lap_distance = np.array(data['LapDist'])
            lap_time = np.array(data['SessionTime'])

            # Get distance and time arrays for fastest lap
            fastest_distance = np.array(fastest['data']['LapDist'])
            fastest_time = np.array(fastest['data']['SessionTime'])

            # Normalize both to start at 0
            lap_time = lap_time - lap_time[0]
            fastest_time = fastest_time - fastest_time[0]

            # Find common distance range
            min_dist = max(lap_distance[0], fastest_distance[0])
            max_dist = min(lap_distance[-1], fastest_distance[-1])

            # Create common distance array for comparison (every 10 meters)
            common_distance = np.arange(min_dist, max_dist, 10)

            # Interpolate both laps' times to the common distance points
            lap_time_interp = np.interp(common_distance, lap_distance, lap_time)
            fastest_time_interp = np.interp(common_distance, fastest_distance, fastest_time)

            # Calculate delta (positive = slower, negative = faster)
            time_delta = lap_time_interp - fastest_time_interp

            fig.add_trace(go.Scatter(
                x=common_distance,
                y=time_delta,
                mode='lines',
                name=f'Lap {lap.lap_number} ({lap.lap_time:.3f}s, +{lap.lap_time - fastest["lap"].lap_time:.3f}s)',
                line=dict(color=lap_info['color'], width=2),
                hovertemplate='<b>%{fullData.name}</b><br>Distance: %{x:.0f}m<br>Delta: %{y:+.3f}s<extra></extra>',
                fill='tozeroy',
                fillcolor=f'rgba({int(lap_info["color"][1:3], 16)}, {int(lap_info["color"][3:5], 16)}, {int(lap_info["color"][5:7], 16)}, 0.1)'
            ))

        except Exception as e:
            # Skip this lap if interpolation fails
            continue

    # Add zero reference line (fastest lap baseline)
    fig.add_hline(
        y=0,
        line_dash="solid",
        line_color=fastest['color'],
        line_width=3,
        annotation_text=f"Fastest Lap {fastest['lap'].lap_number} ({fastest['lap'].lap_time:.3f}s)",
        annotation_position="top right",
        annotation_font_color=fastest['color']
    )

    fig.update_layout(
        title='Time Delta vs Fastest Lap',
        xaxis_title='Distance (m)',
        yaxis_title='Time Delta (seconds)',
        yaxis_zeroline=True,
        yaxis_zerolinewidth=2,
        yaxis_zerolinecolor='gray',
        template='plotly_dark',
        hovermode='x unified',
        height=450,
        margin=dict(l=60, r=60, t=80, b=50),
        dragmode='zoom',
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor='rgba(0, 0, 0, 0.5)'
        )
    )

    # Add annotations to help interpret the chart
    fig.add_annotation(
        text="<i>Positive = Losing time | Negative = Gaining time</i>",
        xref="paper", yref="paper",
        x=0.5, y=-0.15,
        showarrow=False,
        font=dict(size=12, color='gray'),
        xanchor='center'
    )

    return fig.to_html(div_id='delta-chart', include_plotlyjs=False, config={
        'displayModeBar': True,
        'modeBarButtonsToRemove': ['toImage']
    })
