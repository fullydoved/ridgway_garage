/**
 * Ridgway Garage - Analysis Dashboard Lap Management Module
 *
 * Handles loading, adding, removing laps and updating the sidebar display.
 */

import { state } from './state.js';
import { formatLapTime } from './utils.js';
import { updateCharts } from './charts.js';
import { clearMapHoverMarkers } from './map.js';

/**
 * Reassign colors based on lap time order (fastest = red, slowest = blue)
 */
export function reassignLapColors() {
    if (state.activeLaps.length === 0) return;

    // Sort laps by lap time (fastest first)
    const sortedLaps = [...state.activeLaps].sort((a, b) => a.data.lap_time - b.data.lap_time);

    // Assign colors based on sorted order
    sortedLaps.forEach((lap, index) => {
        lap.color = state.colors[index % state.colors.length];
    });

    console.log(`Reassigned colors based on lap times`);
}

/**
 * Add a lap to the analysis view
 * @param {number} lapId - Lap ID to add
 * @param {string|null} customColor - Optional custom color
 */
export async function addLapToView(lapId, customColor = null) {
    console.log(`addLapToView(${lapId}, ${customColor}) called`);

    // Check if lap already loaded - if so, REMOVE it (toggle behavior)
    const existingLap = state.activeLaps.find(l => l.id === lapId);
    if (existingLap) {
        console.log(`Lap ${lapId} already loaded, removing it (toggle)`);
        removeLapFromView(lapId);
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

        // Add lap to state (color will be assigned by reassignLapColors)
        console.log(`Adding lap ${lapId} to state`);
        state.activeLaps.push({
            id: lapId,
            color: '#FFFFFF', // Temporary, will be reassigned
            data: data.lap,
            telemetry: data.telemetry
        });

        console.log(`State now has ${state.activeLaps.length} laps`);

        // Reassign colors based on lap times (fastest = red, slowest = blue)
        reassignLapColors();

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

/**
 * Remove a lap from the analysis view
 * @param {number} lapId - Lap ID to remove
 */
export function removeLapFromView(lapId) {
    state.activeLaps = state.activeLaps.filter(lap => lap.id !== lapId);

    // Reassign colors for remaining laps
    reassignLapColors();

    refreshLapsSidebar(); // Update sidebar to remove colored borders
    updateCharts();
}

/**
 * Clear all laps from the analysis view
 */
export function clearAllLaps() {
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

/**
 * Load fastest laps for current track/car combination
 */
export async function loadFastestLaps() {
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

/**
 * Render a list of laps in a container
 * @param {Array} laps - Array of lap objects
 * @param {string} containerId - DOM element ID
 * @param {boolean} isUserLaps - Whether these are user laps
 */
export function renderLapsList(laps, containerId, isUserLaps) {
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
            <div class="glass-card p-3 cursor-pointer hover:shadow-neon-cyan transition-all duration-300 mb-2" style="${borderStyle}" onclick="window.addLapToView(${lap.id})">
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

/**
 * Refresh the laps sidebar without re-fetching data
 */
export function refreshLapsSidebar() {
    // Re-render user laps
    renderLapsList(state.userLaps, 'myLapsContainer', true);

    // Re-render teammate laps
    if (state.includeTeam) {
        renderLapsList(state.teammateLaps, 'teamLapsContainer', false);
    }
}

/**
 * Handle filter change event
 */
export function onFilterChange() {
    state.selectedTrackId = document.getElementById('trackFilter').value || null;
    state.selectedCarId = document.getElementById('carFilter').value || null;
    state.includeTeam = document.getElementById('includeTeamFilter').checked;

    loadFastestLaps();
}
