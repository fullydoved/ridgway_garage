/**
 * Ridgway Garage - Analysis Dashboard Map Module
 *
 * Handles Leaflet map initialization, track visualization, and map interactions.
 */

import { state } from './state.js';
import { getSpeedColor } from './utils.js';

/**
 * Initialize the Leaflet map with track visualization
 */
export function initializeMap() {
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

    // Watch for container resize and invalidate map size (for responsive layout)
    const resizeObserver = new ResizeObserver(() => {
        if (state.map) {
            state.map.invalidateSize();
        }
    });
    resizeObserver.observe(document.getElementById('mapContainer'));
}

/**
 * Add speed legend to the map
 */
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

/**
 * Toggle map background tiles on/off
 */
export function toggleMapBackground() {
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

/**
 * Update hover markers on the map at a given track distance
 * @param {number} distance - Distance along track in meters
 */
export function updateMapHoverMarkers(distance) {
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

/**
 * Clear all hover markers from the map
 */
export function clearMapHoverMarkers() {
    state.hoverMarkers.forEach(marker => {
        if (state.map) {
            state.map.removeLayer(marker);
        }
    });
    state.hoverMarkers = [];
}

/**
 * Handle map click to find closest track point
 * @param {Object} e - Leaflet click event
 */
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

/**
 * Draw a vertical line on the chart at a specific distance
 * @param {number} distance - Distance in meters
 */
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

/**
 * Clear map selection marker and chart line
 */
export function clearMapSelection() {
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
