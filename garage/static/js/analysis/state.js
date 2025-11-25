/**
 * Ridgway Garage - Analysis Dashboard State Management
 *
 * Central state store for the analysis dashboard.
 */

export const state = {
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

export default state;
