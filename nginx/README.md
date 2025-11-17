# Nginx Configuration

This directory contains the nginx configuration for Ridgway Garage.

## Features

- **Reverse Proxy**: Proxies requests to Django/Daphne on port 8000
- **Static Files**: Serves static files directly for better performance
- **Media Files**: Serves uploaded media files directly
- **WebSocket Support**: Handles WebSocket connections for Django Channels
- **Caching**: Sets appropriate cache headers for static assets

## File Structure

- `nginx.conf` - Main nginx configuration

## Usage

Nginx is automatically started by Docker Compose and listens on port 42069.
Access the application at: http://localhost:42069

## Configuration Details

- **Max Upload Size**: 2GB (configured for large IBT files like Nurburgring sessions)
- **Static Files**: Served from `/static/` with 30-day cache
- **Media Files**: Served from `/media/` with 30-day cache
- **WebSockets**: Available at `/ws/` with automatic upgrade support
