/**
 * Ridgway Garage - Analysis Dashboard Utility Functions
 *
 * Helper functions for formatting, color generation, etc.
 */

import { state } from './state.js';

/**
 * Format lap time from seconds to MM:SS.mmm format
 * @param {number} seconds - Lap time in seconds
 * @returns {string} Formatted time string
 */
export function formatLapTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(3);
    return `${minutes}:${secs.padStart(6, '0')}`;
}

/**
 * Get next available color from the palette
 * @returns {string} Hex color code
 */
export function getNextColor() {
    const usedColors = state.activeLaps.map(lap => lap.color);
    for (const color of state.colors) {
        if (!usedColors.includes(color)) {
            return color;
        }
    }
    return state.colors[0]; // Fallback
}

/**
 * Generate hot-to-cold gradient colors for session laps
 * Fastest lap = Red, Slowest lap = Blue
 * @param {number} count - Number of colors to generate
 * @returns {string[]} Array of RGB color strings
 */
export function generateGradientColors(count) {
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

/**
 * Get color based on speed for heatmap visualization
 * @param {number} speed - Current speed
 * @param {number} minSpeed - Minimum speed in range
 * @param {number} maxSpeed - Maximum speed in range
 * @returns {string} RGB color string
 */
export function getSpeedColor(speed, minSpeed, maxSpeed) {
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

/**
 * Get CSRF token from cookie or DOM
 * @param {string} name - Cookie name
 * @returns {string|null} Cookie value
 */
export function getCookie(name) {
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
