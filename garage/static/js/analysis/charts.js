/**
 * Ridgway Garage - Analysis Dashboard Charts Module
 *
 * Handles chart generation using Plotly and chart-map interactions.
 */

import { state } from './state.js';
import { getCookie } from './utils.js';
import { initializeMap, updateMapHoverMarkers, clearMapHoverMarkers } from './map.js';

/**
 * Generate and render telemetry charts based on selected laps and channels
 */
export async function updateCharts() {
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
