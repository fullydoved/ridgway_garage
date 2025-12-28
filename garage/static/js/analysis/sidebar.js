/**
 * Ridgway Garage - Analysis Dashboard Sidebar Module
 *
 * Handles sidebar collapse/expand functionality.
 */

import { state } from './state.js';

/**
 * Toggle the left sidebar (channel selector)
 */
export function toggleLeftSidebar() {
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

    // Resize chart and map after sidebar animation completes
    setTimeout(() => {
        const chartDiv = document.getElementById('telemetryChart');
        if (chartDiv && typeof Plotly !== 'undefined') {
            Plotly.Plots.resize(chartDiv);
        }
        // Also resize map if visible
        if (state.map) {
            state.map.invalidateSize();
        }
    }, 300);
}

/**
 * Toggle the right sidebar (laps list)
 */
export function toggleRightSidebar() {
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

    // Resize chart and map after sidebar animation completes
    setTimeout(() => {
        const chartDiv = document.getElementById('telemetryChart');
        if (chartDiv && typeof Plotly !== 'undefined') {
            Plotly.Plots.resize(chartDiv);
        }
        // Also resize map if visible
        if (state.map) {
            state.map.invalidateSize();
        }
    }, 300);
}
