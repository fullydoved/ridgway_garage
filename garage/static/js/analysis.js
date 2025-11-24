// ============================================================================
// Ridgway Garage - Analysis Dashboard JavaScript
// ============================================================================

// ============================================================================
// Global State Management
// ============================================================================
const state = {
    activeLaps: [], // Array of {id, color, data}
    selectedTrackId: null,
    selectedCarId: null,
    includeTeam: true,
    colors: ['#FF0000', '#FF8C00', '#FFD700', '#00FF00', '#00BFFF'], // Hot to cold: Red, Orange, Yellow, Green, Blue
    map: null,
    mapTileLayer: null,
    mapMarkers: [],
    hoverMarkers: [], // Markers for hover position on map
    clickMarker: null, // Marker for clicked position on map
    preloadedLapId: null, // Will be set from template if lap parameter exists
    preloadedSessionLaps: null, // Will be set from template if session parameter exists (array of lap IDs)
    userLaps: [], // Stored user laps data for re-rendering
    teammateLaps: [] // Stored teammate laps data for re-rendering
};

// Format lap time (seconds to MM:SS.mmm)
function formatLapTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(3);
    return `${minutes}:${secs.padStart(6, '0')}`;
}

// Get next available color
function getNextColor() {
    const usedColors = state.activeLaps.map(lap => lap.color);
    for (const color of state.colors) {
        if (!usedColors.includes(color)) {
            return color;
        }
    }
    return state.colors[0]; // Fallback
}

// Generate hot-to-cold gradient colors for session laps
// Fastest lap = Red, Slowest lap = Blue
function generateGradientColors(count) {
    // Define color stops: Red -> Orange -> Yellow -> Green -> Blue
    const colorStops = [
        [255, 0, 0],      // Red (fastest)
        [255, 140, 0],    // Orange
        [255, 215, 0],    // Yellow
        [0, 255, 0],      // Green
        [0, 191, 255]     // Blue (slowest)
    ];

    const colors = [];
    for (let i = 0; i < count; i++) {
        const t = i / (count - 1); // Normalized position (0 to 1)
        const scaledT = t * (colorStops.length - 1); // Scale to color stops
        const index = Math.floor(scaledT);
        const localT = scaledT - index;

        // Handle edge case (last color)
        if (index >= colorStops.length - 1) {
            const [r, g, b] = colorStops[colorStops.length - 1];
            colors.push(`rgb(${r}, ${g}, ${b})`);
            continue;
        }

        // Interpolate between two adjacent color stops
        const [r1, g1, b1] = colorStops[index];
        const [r2, g2, b2] = colorStops[index + 1];
        const r = Math.round(r1 + (r2 - r1) * localT);
        const g = Math.round(g1 + (g2 - g1) * localT);
        const b = Math.round(b1 + (b2 - b1) * localT);

        colors.push(`rgb(${r}, ${g}, ${b})`);
    }
    return colors;
}

// Get color based on speed (heatmap)
function getSpeedColor(speed, minSpeed, maxSpeed) {
    // Normalize speed to 0-1 range
    const normalized = (speed - minSpeed) / (maxSpeed - minSpeed);

    // Create color gradient: blue (slow) -> cyan -> green -> yellow -> orange -> red (fast)
    if (normalized < 0.2) {
        // Blue to cyan
        const t = normalized / 0.2;
        return `rgb(${Math.round(0 * (1-t) + 0 * t)}, ${Math.round(0 * (1-t) + 212 * t)}, ${Math.round(255 * (1-t) + 255 * t)})`;
    } else if (normalized < 0.4) {
        // Cyan to green
        const t = (normalized - 0.2) / 0.2;
        return `rgb(0, ${Math.round(212 * (1-t) + 255 * t)}, ${Math.round(255 * (1-t) + 0 * t)})`;
    } else if (normalized < 0.6) {
        // Green to yellow
        const t = (normalized - 0.4) / 0.2;
        return `rgb(${Math.round(0 * (1-t) + 255 * t)}, 255, 0)`;
    } else if (normalized < 0.8) {
        // Yellow to orange
        const t = (normalized - 0.6) / 0.2;
        return `rgb(255, ${Math.round(255 * (1-t) + 165 * t)}, 0)`;
    } else {
        // Orange to red
        const t = (normalized - 0.8) / 0.2;
        return `rgb(255, ${Math.round(165 * (1-t) + 0 * t)}, 0)`;
    }
}

// ============================================================================
// Initialization
// ============================================================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('Analysis Dashboard initialized');

    // Check if we have a preloaded lap ID from query parameter
    if (state.preloadedLapId) {
        console.log(`Preloading lap ${state.preloadedLapId} from query parameter`);
        addLapToView(state.preloadedLapId);
    }
    // Check if we have preloaded session laps (multiple laps from same session)
    else if (state.preloadedSessionLaps && state.preloadedSessionLaps.length > 0) {
        console.log(`Preloading ${state.preloadedSessionLaps.length} laps from session`);
        const gradientColors = generateGradientColors(state.preloadedSessionLaps.length);

        // Load all laps with gradient colors (blue -> red)
        state.preloadedSessionLaps.forEach((lapId, index) => {
            console.log(`Loading lap ${lapId} with color ${gradientColors[index]}`);
            addLapToView(lapId, gradientColors[index]);
        });
    }

    // Load fastest laps
    console.log('Loading fastest laps...');
    loadFastestLaps();

    // Event listeners
    document.getElementById('trackFilter').addEventListener('change', onFilterChange);
    document.getElementById('carFilter').addEventListener('change', onFilterChange);
    document.getElementById('includeTeamFilter').addEventListener('change', onFilterChange);
    document.getElementById('updateChartsBtn').addEventListener('click', updateCharts);
    document.getElementById('clearAllLaps').addEventListener('click', clearAllLaps);
    document.getElementById('toggleMapBackground').addEventListener('click', toggleMapBackground);

    // Sidebar collapse/expand
    document.getElementById('toggleLeftSidebar').addEventListener('click', toggleLeftSidebar);
    document.getElementById('toggleRightSidebar').addEventListener('click', toggleRightSidebar);
    document.getElementById('toggleLeftFloating').addEventListener('click', toggleLeftSidebar);
    document.getElementById('toggleRightFloating').addEventListener('click', toggleRightSidebar);

    // Channel selector: All/None buttons
    document.querySelectorAll('.select-all').forEach(btn => {
        btn.addEventListener('click', function() {
            const group = this.dataset.group;
            document.querySelectorAll(`.channel-input[data-group="${group}"]`).forEach(checkbox => {
                checkbox.checked = true;
            });
        });
    });

    document.querySelectorAll('.select-none').forEach(btn => {
        btn.addEventListener('click', function() {
            const group = this.dataset.group;
            document.querySelectorAll(`.channel-input[data-group="${group}"]`).forEach(checkbox => {
                checkbox.checked = false;
            });
        });
    });
});

// ============================================================================
// Lap Loading and Management
// ============================================================================
async function addLapToView(lapId, customColor = null) {
    console.log(`addLapToView(${lapId}, ${customColor}) called`);

    // Check if lap already loaded
    if (state.activeLaps.find(l => l.id === lapId)) {
        console.log(`Lap ${lapId} already loaded, skipping`);
        return;
    }

    // Check lap limit (max 5 laps)
    if (state.activeLaps.length >= 5) {
        alert('Maximum 5 laps can be compared at once');
        return;
    }

    try {
        // Fetch lap telemetry data
        console.log(`Fetching telemetry for lap ${lapId}...`);
        const response = await fetch(`/api/laps/${lapId}/telemetry/`);
        const data = await response.json();
        console.log(`Received response for lap ${lapId}:`, data);

        if (!data.success) {
            alert(data.error || 'Failed to load lap data');
            return;
        }

        // Add lap to state
        const color = customColor || getNextColor();
        console.log(`Adding lap ${lapId} to state with color ${color}`);
        state.activeLaps.push({
            id: lapId,
            color: color,
            data: data.lap,
            telemetry: data.telemetry
        });

        console.log(`State now has ${state.activeLaps.length} laps`);

        // If this is the first lap, auto-fill track and car filters
        if (state.activeLaps.length === 1 && data.lap.track_id && data.lap.car_id) {
            console.log(`Auto-filling filters: track=${data.lap.track_id}, car=${data.lap.car_id}`);
            document.getElementById('trackFilter').value = data.lap.track_id;
            document.getElementById('carFilter').value = data.lap.car_id;
            state.selectedTrackId = data.lap.track_id;
            state.selectedCarId = data.lap.car_id;
            // Reload fastest laps with new filters
            loadFastestLaps();
        }

        // Update UI
        refreshLapsSidebar(); // Update sidebar to show colored borders
        updateCharts();

    } catch (error) {
        console.error('Error loading lap:', error);
        alert('Failed to load lap data');
    }
}

function removeLapFromView(lapId) {
    state.activeLaps = state.activeLaps.filter(lap => lap.id !== lapId);
    refreshLapsSidebar(); // Update sidebar to remove colored borders
    updateCharts();
}

function clearAllLaps() {
    state.activeLaps = [];
    clearMapHoverMarkers();
    if (state.clickMarker && state.map) {
        state.map.removeLayer(state.clickMarker);
        state.clickMarker = null;
    }
    refreshLapsSidebar(); // Update sidebar to remove all colored borders
    document.getElementById('chartsContainer').innerHTML = `
        <div class="text-center py-12">
            <svg class="w-16 h-16 text-neon-cyan mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
            </svg>
            <h5 class="text-xl font-bold text-white mb-2">No Laps Selected</h5>
            <p class="text-gray-400">Select laps from the right panel to begin analysis.</p>
        </div>
    `;
    if (state.map) {
        state.map.remove();
        state.map = null;
    }
    document.getElementById('mapContainer').style.display = 'none';
}

// ============================================================================
// Chart Generation
// ============================================================================
async function updateCharts() {
    if (state.activeLaps.length === 0) {
        return;
    }

    // Get selected channels
    const selectedChannels = Array.from(document.querySelectorAll('.channel-input:checked'))
        .map(checkbox => checkbox.value);

    if (selectedChannels.length === 0) {
        alert('Please select at least one channel to display');
        return;
    }

    // Show loading indicator
    document.getElementById('chartsContainer').innerHTML = `
        <div class="text-center py-12">
            <div class="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-neon-cyan"></div>
            <p class="mt-4 text-gray-400">Generating charts...</p>
        </div>
    `;

    try {
        // Get CSRF token
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
                         getCookie('csrftoken');

        // Call API to generate charts with color assignments
        const response = await fetch('/api/generate-chart/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                lap_ids: state.activeLaps.map(lap => lap.id),
                lap_colors: state.activeLaps.map(lap => lap.color), // Pass color assignments
                channels: selectedChannels
            })
        });

        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Failed to generate charts');
        }

        // Render Plotly chart from JSON
        const chartContainer = document.getElementById('chartsContainer');
        chartContainer.innerHTML = '<div id="telemetryChart"></div>';

        const chartData = JSON.parse(data.chart_json);

        // Fix all y-axes to prevent vertical zooming (only allow horizontal zoom)
        if (chartData.layout) {
            // Fix main y-axis
            if (chartData.layout.yaxis) {
                chartData.layout.yaxis.fixedrange = true;
            }
            // Fix all secondary y-axes (yaxis2, yaxis3, etc.)
            Object.keys(chartData.layout).forEach(key => {
                if (key.startsWith('yaxis')) {
                    chartData.layout[key].fixedrange = true;
                }
            });
        }

        Plotly.newPlot('telemetryChart', chartData.data, chartData.layout, {responsive: true});

        // Add hover event to sync with map
        const chartDiv = document.getElementById('telemetryChart');
        chartDiv.on('plotly_hover', function(eventData) {
            if (!state.map || !eventData.points || eventData.points.length === 0) return;

            const point = eventData.points[0];
            const distance = point.x; // Distance along track

            // Update map markers for all active laps
            updateMapHoverMarkers(distance);
        });

        // Clear hover markers when not hovering
        chartDiv.on('plotly_unhover', function() {
            clearMapHoverMarkers();
        });

        // Show map container
        document.getElementById('mapContainer').style.display = 'block';
        initializeMap();

    } catch (error) {
        console.error('Error generating charts:', error);
        document.getElementById('chartsContainer').innerHTML = `
            <div class="glass-card p-6 border-2 border-red-500/50">
                <div class="flex items-center gap-3">
                    <svg class="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                    </svg>
                    <div>
                        <h5 class="text-white font-bold">Failed to Generate Charts</h5>
                        <p class="text-gray-400">${error.message}</p>
                    </div>
                </div>
            </div>
        `;
    }
}

// Helper function to get CSRF cookie
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function initializeMap() {
    // Clear existing map if any
    if (state.map) {
        state.map.remove();
        state.map = null;
        state.mapTileLayer = null;
    }

    // Check if we have GPS data
    if (state.activeLaps.length === 0) return;

    const firstLap = state.activeLaps[0];
    const gpsData = firstLap.telemetry;

    if (!gpsData.Lat || !gpsData.Lon || gpsData.Lat.length === 0) return;

    // Create map centered on first coordinate with higher max zoom
    const centerLat = gpsData.Lat[0];
    const centerLon = gpsData.Lon[0];
    state.map = L.map('map', {
        maxZoom: 22,
        minZoom: 10
    }).setView([centerLat, centerLon], 15);

    // Add tile layer and store reference for toggling
    state.mapTileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(state.map);

    // Add track line for each lap with speed-based coloring
    state.activeLaps.forEach(lap => {
        if (lap.telemetry.Lat && lap.telemetry.Lon && lap.telemetry.Speed) {
            const speeds = lap.telemetry.Speed;
            const minSpeed = Math.min(...speeds);
            const maxSpeed = Math.max(...speeds);

            // Draw line segments with different colors based on speed
            for (let i = 0; i < lap.telemetry.Lat.length - 1; i++) {
                const segment = [
                    [lap.telemetry.Lat[i], lap.telemetry.Lon[i]],
                    [lap.telemetry.Lat[i + 1], lap.telemetry.Lon[i + 1]]
                ];
                const avgSpeed = (speeds[i] + speeds[i + 1]) / 2;
                const color = getSpeedColor(avgSpeed, minSpeed, maxSpeed);

                L.polyline(segment, {
                    color: color,
                    weight: 4,
                    opacity: 0.8
                }).addTo(state.map);
            }
        }
    });

    // Fit map to show all tracks
    if (state.activeLaps.length > 0 && state.activeLaps[0].telemetry.Lat) {
        const allCoordinates = state.activeLaps.flatMap(lap =>
            lap.telemetry.Lat ? lap.telemetry.Lat.map((lat, idx) => [lat, lap.telemetry.Lon[idx]]) : []
        );
        if (allCoordinates.length > 0) {
            state.map.fitBounds(allCoordinates);
        }
    }

    // Add speed legend
    addSpeedLegend();

    // Add map click handler for bidirectional interaction
    state.map.on('click', onMapClick);
    state.map.on('dblclick', clearMapSelection);
}

function addSpeedLegend() {
    if (!state.map) return;

    const legend = L.control({ position: 'bottomright' });

    legend.onAdd = function(map) {
        const div = L.DomUtil.create('div', 'info legend');
        div.style.background = 'rgba(21, 25, 41, 0.95)';
        div.style.padding = '10px';
        div.style.borderRadius = '8px';
        div.style.border = '1px solid rgba(0, 212, 255, 0.3)';
        div.style.color = '#fff';
        div.style.fontSize = '12px';
        div.style.backdropFilter = 'blur(10px)';

        const colors = [
            { label: 'Slow', color: 'rgb(0, 0, 255)' },
            { label: '', color: 'rgb(0, 212, 255)' },
            { label: '', color: 'rgb(0, 255, 0)' },
            { label: '', color: 'rgb(255, 255, 0)' },
            { label: '', color: 'rgb(255, 165, 0)' },
            { label: 'Fast', color: 'rgb(255, 0, 0)' }
        ];

        div.innerHTML = '<strong style="color: #00d4ff; margin-bottom: 5px; display: block;">Speed</strong>';

        colors.forEach(item => {
            div.innerHTML += `
                <div style="display: flex; align-items: center; margin: 2px 0;">
                    <span style="background: ${item.color}; width: 20px; height: 4px; display: inline-block; margin-right: 8px; border-radius: 2px;"></span>
                    <span style="color: #ccc; font-size: 10px;">${item.label}</span>
                </div>
            `;
        });

        return div;
    };

    legend.addTo(state.map);
}

function toggleMapBackground() {
    if (!state.map || !state.mapTileLayer) {
        return;
    }

    const btn = document.getElementById('toggleMapBackground');
    if (state.map.hasLayer(state.mapTileLayer)) {
        state.map.removeLayer(state.mapTileLayer);
        btn.textContent = 'Show Background';
    } else {
        state.map.addLayer(state.mapTileLayer);
        btn.textContent = 'Hide Background';
    }
}

function updateMapHoverMarkers(distance) {
    if (!state.map) return;

    // Clear existing hover markers
    clearMapHoverMarkers();

    // Add marker for each active lap at the given distance
    state.activeLaps.forEach(lap => {
        if (!lap.telemetry.LapDist || !lap.telemetry.Lat || !lap.telemetry.Lon) return;

        // Find the index closest to this distance
        const distances = lap.telemetry.LapDist;
        let closestIdx = 0;
        let minDiff = Math.abs(distances[0] - distance);

        for (let i = 1; i < distances.length; i++) {
            const diff = Math.abs(distances[i] - distance);
            if (diff < minDiff) {
                minDiff = diff;
                closestIdx = i;
            }
        }

        // Create marker at this position
        const lat = lap.telemetry.Lat[closestIdx];
        const lon = lap.telemetry.Lon[closestIdx];
        const speed = lap.telemetry.Speed ? lap.telemetry.Speed[closestIdx] : 0;

        const marker = L.circleMarker([lat, lon], {
            radius: 10,
            fillColor: lap.color,
            color: '#ffffff',
            weight: 3,
            opacity: 1,
            fillOpacity: 1,
            zIndexOffset: 1000  // Ensure markers appear on top
        }).addTo(state.map);

        // Add popup with info
        marker.bindTooltip(
            `<strong>${lap.data.driver}</strong><br>` +
            `Speed: ${speed.toFixed(1)} km/h<br>` +
            `Distance: ${distance.toFixed(0)} m`,
            { permanent: false, direction: 'top' }
        ).openTooltip();

        state.hoverMarkers.push(marker);
    });
}

function clearMapHoverMarkers() {
    state.hoverMarkers.forEach(marker => {
        if (state.map) {
            state.map.removeLayer(marker);
        }
    });
    state.hoverMarkers = [];
}

function onMapClick(e) {
    if (!state.map || state.activeLaps.length === 0) return;

    const clickedLat = e.latlng.lat;
    const clickedLon = e.latlng.lng;

    // Find the closest point on any lap's track to the clicked location
    let closestDistance = Infinity;
    let closestLapDist = 0;
    let closestPoint = null;

    state.activeLaps.forEach(lap => {
        if (!lap.telemetry.Lat || !lap.telemetry.Lon || !lap.telemetry.LapDist) return;

        for (let i = 0; i < lap.telemetry.Lat.length; i++) {
            const lat = lap.telemetry.Lat[i];
            const lon = lap.telemetry.Lon[i];

            // Calculate distance using Haversine formula (approximate)
            const dLat = (lat - clickedLat) * Math.PI / 180;
            const dLon = (lon - clickedLon) * Math.PI / 180;
            const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                     Math.cos(clickedLat * Math.PI / 180) * Math.cos(lat * Math.PI / 180) *
                     Math.sin(dLon/2) * Math.sin(dLon/2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            const distance = 6371000 * c; // Earth radius in meters

            if (distance < closestDistance) {
                closestDistance = distance;
                closestLapDist = lap.telemetry.LapDist[i];
                closestPoint = [lat, lon];
            }
        }
    });

    if (!closestPoint) return;

    // Remove previous click marker
    if (state.clickMarker) {
        state.map.removeLayer(state.clickMarker);
    }

    // Add marker at clicked position
    state.clickMarker = L.circleMarker(closestPoint, {
        radius: 8,
        fillColor: '#ff00ff',
        color: '#ffffff',
        weight: 3,
        opacity: 1,
        fillOpacity: 0.8,
        zIndexOffset: 2000
    }).addTo(state.map);

    state.clickMarker.bindTooltip(
        `<strong>Selected Point</strong><br>Distance: ${closestLapDist.toFixed(0)} m`,
        { permanent: true, direction: 'top' }
    ).openTooltip();

    // Draw vertical line on chart
    drawChartLineAtDistance(closestLapDist);
}

function drawChartLineAtDistance(distance) {
    const chartDiv = document.getElementById('telemetryChart');
    if (!chartDiv || !chartDiv.data) return;

    // Add a vertical line shape at the specified distance
    const shapes = chartDiv.layout.shapes || [];

    // Remove any existing vertical lines from previous clicks
    const newShapes = shapes.filter(shape => !shape.name || shape.name !== 'click-line');

    // Add new vertical line
    newShapes.push({
        type: 'line',
        name: 'click-line',
        x0: distance,
        x1: distance,
        y0: 0,
        y1: 1,
        yref: 'paper',
        line: {
            color: '#ff00ff',
            width: 2,
            dash: 'dash'
        }
    });

    Plotly.relayout(chartDiv, { shapes: newShapes });
}

function clearMapSelection() {
    // Remove click marker from map
    if (state.clickMarker && state.map) {
        state.map.removeLayer(state.clickMarker);
        state.clickMarker = null;
    }

    // Remove vertical line from chart
    const chartDiv = document.getElementById('telemetryChart');
    if (chartDiv && chartDiv.layout && chartDiv.layout.shapes) {
        const shapes = chartDiv.layout.shapes.filter(shape => !shape.name || shape.name !== 'click-line');
        Plotly.relayout(chartDiv, { shapes: shapes });
    }
}

// ============================================================================
// Sidebar Toggle Functions
// ============================================================================
function toggleLeftSidebar() {
    const sidebar = document.getElementById('channelSidebar');
    const btn = document.getElementById('toggleLeftSidebar');
    const floatingBtn = document.getElementById('toggleLeftFloating');

    sidebar.classList.toggle('collapsed');

    if (sidebar.classList.contains('collapsed')) {
        btn.innerHTML = '→';
        floatingBtn.classList.remove('hidden');
    } else {
        btn.innerHTML = '←';
        floatingBtn.classList.add('hidden');
    }

    // Resize chart after sidebar animation completes
    setTimeout(() => {
        const chartDiv = document.getElementById('telemetryChart');
        if (chartDiv && typeof Plotly !== 'undefined') {
            Plotly.Plots.resize(chartDiv);
        }
    }, 300);
}

function toggleRightSidebar() {
    const sidebar = document.getElementById('lapsSidebar');
    const btn = document.getElementById('toggleRightSidebar');
    const floatingBtn = document.getElementById('toggleRightFloating');

    sidebar.classList.toggle('collapsed');

    if (sidebar.classList.contains('collapsed')) {
        btn.innerHTML = '←';
        floatingBtn.classList.remove('hidden');
    } else {
        btn.innerHTML = '→';
        floatingBtn.classList.add('hidden');
    }

    // Resize chart after sidebar animation completes
    setTimeout(() => {
        const chartDiv = document.getElementById('telemetryChart');
        if (chartDiv && typeof Plotly !== 'undefined') {
            Plotly.Plots.resize(chartDiv);
        }
    }, 300);
}

// ============================================================================
// Fastest Laps Loading
// ============================================================================
async function loadFastestLaps() {
    console.log(`loadFastestLaps() called - track: ${state.selectedTrackId}, car: ${state.selectedCarId}`);

    if (!state.selectedTrackId || !state.selectedCarId) {
        console.log('No track/car selected, showing empty state');
        document.getElementById('myLapsContainer').innerHTML = `
            <div class="text-center text-gray-500 py-4 text-sm">
                Select a track and car to view fastest laps
            </div>
        `;
        document.getElementById('teamLapsContainer').innerHTML = `
            <div class="text-center text-gray-500 py-4 text-sm">
                Select a track and car to view teammates
            </div>
        `;
        return;
    }

    try {
        const url = `/api/fastest-laps/?track_id=${state.selectedTrackId}&car_id=${state.selectedCarId}&include_team=${state.includeTeam}`;
        console.log(`Fetching fastest laps: ${url}`);
        const response = await fetch(url);
        const data = await response.json();
        console.log('Fastest laps response:', data);

        if (!data.success) {
            throw new Error(data.error || 'Failed to load laps');
        }

        // Store data in state for re-rendering
        state.userLaps = data.user_laps || [];
        state.teammateLaps = data.teammate_laps || [];

        // Render user laps
        renderLapsList(state.userLaps, 'myLapsContainer', true);

        // Render teammate laps
        if (state.includeTeam) {
            renderLapsList(state.teammateLaps, 'teamLapsContainer', false);
        } else {
            document.getElementById('teamLapsContainer').innerHTML = `
                <div class="text-center text-gray-500 py-4 text-sm">
                    Enable "Include Teammates" to view team laps
                </div>
            `;
        }

    } catch (error) {
        console.error('Error loading fastest laps:', error);
        document.getElementById('myLapsContainer').innerHTML = `
            <div class="text-center text-red-500 py-4 text-sm">
                <svg class="w-5 h-5 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                </svg>
                Error loading laps
            </div>
        `;
    }
}

function renderLapsList(laps, containerId, isUserLaps) {
    const container = document.getElementById(containerId);

    if (!laps || laps.length === 0) {
        container.innerHTML = `
            <div class="text-center text-gray-500 py-4 text-sm">
                No laps found
            </div>
        `;
        return;
    }

    container.innerHTML = laps.map(lap => {
        const isActive = state.activeLaps.some(l => l.id === lap.id);
        const activeLap = state.activeLaps.find(l => l.id === lap.id);
        const borderStyle = isActive ? `border: 3px solid ${activeLap.color};` : '';

        return `
            <div class="glass-card p-3 corner-brackets cursor-pointer hover:shadow-neon-cyan transition-all duration-300 mb-2" style="${borderStyle}" onclick="addLapToView(${lap.id})">
                ${isActive ? `<span class="inline-block w-3 h-3 rounded-full mb-1" style="background-color: ${activeLap.color};"></span>` : ''}
                <div class="font-mono text-lg font-bold text-neon-cyan">
                    ${formatLapTime(lap.lap_time)}
                    ${lap.is_personal_best ? '<span class="text-xs bg-ridgway-orange text-white px-2 py-1 rounded ml-2">PB</span>' : ''}
                </div>
                <div class="text-sm text-gray-400 mt-1">
                    ${lap.driver ? lap.driver + ' - ' : ''}Lap #${lap.lap_number}
                    ${lap.session_date ? '<br>' + new Date(lap.session_date).toLocaleDateString() : ''}
                </div>
            </div>
        `;
    }).join('');
}

// Refresh the laps sidebar without re-fetching data
function refreshLapsSidebar() {
    // Re-render user laps
    renderLapsList(state.userLaps, 'myLapsContainer', true);

    // Re-render teammate laps
    if (state.includeTeam) {
        renderLapsList(state.teammateLaps, 'teamLapsContainer', false);
    }
}

function onFilterChange() {
    state.selectedTrackId = document.getElementById('trackFilter').value || null;
    state.selectedCarId = document.getElementById('carFilter').value || null;
    state.includeTeam = document.getElementById('includeTeamFilter').checked;

    loadFastestLaps();
}
