/**
 * Ridgway Garage - Analysis Dashboard Main Entry Point
 *
 * This is the main ES6 module that imports all components and initializes the dashboard.
 */

import { state } from './state.js';
import { formatLapTime } from './utils.js';
import { updateCharts } from './charts.js';
import { toggleMapBackground } from './map.js';
import { addLapToView, clearAllLaps, loadFastestLaps, onFilterChange } from './laps.js';
import { toggleLeftSidebar, toggleRightSidebar } from './sidebar.js';

// Expose functions to global scope for inline event handlers in templates
window.addLapToView = addLapToView;
window.clearAllLaps = clearAllLaps;
window.formatLapTime = formatLapTime;

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('Analysis Dashboard initialized (ES6 modules)');

    // Check if we have a preloaded lap ID from query parameter
    if (state.preloadedLapId) {
        console.log(`Preloading lap ${state.preloadedLapId} from query parameter`);
        addLapToView(state.preloadedLapId);
    }
    // Check if we have preloaded session laps (multiple laps from same session)
    else if (state.preloadedSessionLaps && state.preloadedSessionLaps.length > 0) {
        console.log(`Preloading ${state.preloadedSessionLaps.length} laps from session`);

        // Load all laps (colors will be auto-assigned based on lap time)
        state.preloadedSessionLaps.forEach((lapId) => {
            console.log(`Loading lap ${lapId}`);
            addLapToView(lapId);
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

// Export state for template to set preloaded values
export { state };
