/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './new_templates/**/*.html',
    './templates/**/*.html',  // Main templates directory
    './telemetry/templates/**/*.html',
    './telemetry/**/*.py',  // Include Python files so form widget classes are detected
    './static/src/**/*.js',
    './static/js/**/*.js',  // Include JS files for dynamic classes
  ],
  safelist: [
    'input-neon',
    'btn-neon',
    'form-label',
    'form-error',
    'form-help',
    'session-badge-practice',
    'session-badge-qualifying',
    'session-badge-race',
    'session-badge-time_trial',
    'session-badge-testing',
    'session-badge-imported',
  ],
  theme: {
    extend: {
      colors: {
        // Cyberpunk neon colors
        'neon-cyan': '#00D9FF',
        'neon-pink': '#FF2E97',
        'neon-purple': '#9D4EDD',

        // Logo gradient colors
        'ridgway-red': '#E63946',
        'ridgway-orange': '#FF6B35',
        'ridgway-yellow': '#FFB627',

        // Dark backgrounds
        'cyber-darkest': '#0A0E27',
        'cyber-dark': '#151929',
        'cyber-card': '#1E2139',
        'cyber-border': '#2A2F4A',

        // Accent variants
        'cyber-accent': '#00D9FF',
        'cyber-accent-dim': '#0099CC',
      },
      fontFamily: {
        'mono': ['Courier New', 'monospace'],
        'sans': ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      boxShadow: {
        'neon-cyan': '0 0 10px rgba(0, 217, 255, 0.5), 0 0 20px rgba(0, 217, 255, 0.3)',
        'neon-pink': '0 0 10px rgba(255, 46, 151, 0.5), 0 0 20px rgba(255, 46, 151, 0.3)',
        'neon-orange': '0 0 10px rgba(255, 107, 53, 0.5), 0 0 20px rgba(255, 107, 53, 0.3)',
        'neon-yellow': '0 0 10px rgba(255, 182, 39, 0.5), 0 0 20px rgba(255, 182, 39, 0.3)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'scanline': 'scanline 8s linear infinite',
        'grid-pulse': 'grid-pulse 4s ease-in-out infinite',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(0, 217, 255, 0.5), 0 0 10px rgba(0, 217, 255, 0.3)' },
          '100%': { boxShadow: '0 0 20px rgba(0, 217, 255, 0.8), 0 0 30px rgba(0, 217, 255, 0.5)' },
        },
        scanline: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100%)' },
        },
        'grid-pulse': {
          '0%, 100%': { opacity: '0.3' },
          '50%': { opacity: '0.6' },
        },
      },
      backgroundImage: {
        'grid-pattern': `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%2300D9FF' fill-opacity='0.1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
      },
    },
  },
  plugins: [],
}
