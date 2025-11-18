# iRacing Telemetry Client for Ridgway Garage

This .NET client streams live telemetry data from iRacing to the Ridgway Garage Django server at 60 Hz.

## Prerequisites

- **Windows** (iRacing only runs on Windows)
- **.NET 8.0 SDK** - Download from https://dotnet.microsoft.com/download/dotnet/8.0
- **iRacing** installed and running

## Installation

### 1. Install .NET 8.0 SDK

1. Download .NET 8.0 SDK from https://dotnet.microsoft.com/download/dotnet/8.0
2. Run the installer
3. Verify installation by opening Command Prompt and running:
   ```cmd
   dotnet --version
   ```
   You should see version 8.0.x

### 2. Restore Dependencies

Open Command Prompt or PowerShell in this directory (`C:\temp\iRacingTelemetryClient`) and run:

```cmd
dotnet restore
```

This will download the required NuGet packages:
- `SVappsLAB.iRacingTelemetrySDK` (v0.9.8.1) - iRacing SDK wrapper
- `System.Text.Json` (v8.0.0) - JSON serialization

## Configuration

Edit `appsettings.json` to configure the client:

```json
{
  "ServerUrl": "ws://localhost:8000/ws/telemetry/live/",
  "DriverId": 1,
  "UpdateRateHz": 60,
  "LogLevel": "Information"
}
```

### Configuration Options

- **ServerUrl**: WebSocket URL of your Django server
  - Local development: `ws://localhost:8000/ws/telemetry/live/`
  - Docker: `ws://<docker-host-ip>:8000/ws/telemetry/live/`
  - Production: `wss://yourdomain.com/ws/telemetry/live/` (use wss:// for SSL)

- **DriverId**: Your user ID from the Django database
  - Log into Django admin to find your user ID
  - Or query: `SELECT id FROM auth_user WHERE username='your_username';`

- **UpdateRateHz**: Telemetry update rate (default: 60)
  - 60 Hz = full fidelity (recommended)
  - 30 Hz = reduced bandwidth
  - 20 Hz = minimal bandwidth

- **LogLevel**: Logging verbosity
  - `Information` - Normal logging
  - `Debug` - Detailed logging
  - `Warning` - Only warnings and errors

## Building the Client

### Option 1: Debug Build (for testing)

```cmd
dotnet build
```

Executable location: `bin\Debug\net8.0\iRacingTelemetryClient.exe`

### Option 2: Release Build (optimized)

```cmd
dotnet build -c Release
```

Executable location: `bin\Release\net8.0\iRacingTelemetryClient.exe`

### Option 3: Self-Contained Executable (recommended for distribution)

This creates a single .exe file with all dependencies included (no .NET runtime required on target machine):

```cmd
dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true
```

Executable location: `bin\Release\net8.0\win-x64\publish\iRacingTelemetryClient.exe`

This single .exe can be copied to any Windows machine and run without installing .NET.

## Running the Client

### Prerequisites Before Running

1. **Start Django Server**: Make sure your Ridgway Garage Django server is running and accessible
   ```bash
   # In WSL/Django directory
   python manage.py runserver 0.0.0.0:8000
   ```

2. **Start iRacing**: Launch iRacing and join a session (practice, qualifying, race, etc.)

### Running the Client

1. Open Command Prompt or PowerShell
2. Navigate to the project directory:
   ```cmd
   cd C:\temp\iRacingTelemetryClient
   ```

3. Run the client:
   ```cmd
   dotnet run
   ```

   Or run the compiled executable directly:
   ```cmd
   bin\Release\net8.0\iRacingTelemetryClient.exe
   ```

### What You Should See

```
iRacing Telemetry Client Starting...
Server URL: ws://localhost:8000/ws/telemetry/live/
Driver ID: 1
Update Rate: 60 Hz
Connecting to ws://localhost:8000/ws/telemetry/live/...
Connected to server
Monitoring for iRacing...
Connected to iRacing!
Session info received
Session initialization sent
Session created: ID 42
Lap 1
Lap 2
Lap 2 completed: 89.234s
Lap 3
...
```

### Stopping the Client

Press `Ctrl+C` to gracefully shut down the client.

## Troubleshooting

### "dotnet: command not found"

- .NET SDK is not installed or not in PATH
- Solution: Install .NET 8.0 SDK from https://dotnet.microsoft.com/download

### "Failed to connect to server"

- Django server is not running or not accessible
- Solution:
  1. Check Django is running: `python manage.py runserver 0.0.0.0:8000`
  2. Check firewall allows connections
  3. If using Docker, update ServerUrl to Docker host IP

### "Server error: Driver with ID X not found"

- DriverId in appsettings.json doesn't match your user ID
- Solution: Find your user ID in Django admin or database

### "No telemetry data"

- iRacing is not running or you're not in a session
- Solution: Launch iRacing and join a practice/race session

### Client connects but no data appears on Django

- Check Django logs for errors
- Verify WebSocket consumer is running (Daphne/Channels)
- Check Redis is running (required for Django Channels)

## How It Works

1. **Connection**: Client connects to Django WebSocket endpoint
2. **iRacing Detection**: Client polls iRacing SDK memory-mapped file
3. **Session Init**: When iRacing session detected, client sends track/car metadata to Django
4. **Live Streaming**: Client sends telemetry at 60 Hz to Django server
5. **Lap Detection**: Django server detects lap completions and saves to database
6. **Broadcasting**: Django broadcasts live data to web viewers

## Data Flow

```
iRacing (60 Hz)
  → Memory-Mapped File
    → .NET Client (SVappsLAB SDK)
      → WebSocket
        → Django Channels Consumer
          → Database (Sessions, Laps, Telemetry)
          → Redis Broadcast → Web Viewers
```

## Telemetry Data Sent

The client sends the following data points at 60 Hz:

**Timing & Position:**
- Session time, lap distance, lap number, current lap time

**Speed & Engine:**
- Speed, RPM, gear

**Driver Inputs:**
- Throttle, brake, steering, clutch

**GPS:**
- Latitude, longitude

**Tire Data:**
- Temperature (all 4 tires)
- Pressure (all 4 tires)

**Fuel:**
- Fuel level, fuel use per hour

**Track Info:**
- Track surface type, pit road status

## Viewing Live Telemetry

Once the client is streaming:

1. Open web browser to Django server: `http://localhost:8000`
2. Navigate to live sessions page
3. Select your active session
4. View real-time charts and data

## Advanced Usage

### Running as Windows Service

To run the client automatically in the background:

1. Use NSSM (Non-Sucking Service Manager): https://nssm.cc/
2. Install as service:
   ```cmd
   nssm install iRacingTelemetry "C:\path\to\iRacingTelemetryClient.exe"
   ```

### Multiple Drivers

Each driver needs their own client with unique DriverId in appsettings.json.

### Remote Server

To connect to a remote server, update ServerUrl:
```json
{
  "ServerUrl": "wss://ridgwaygarage.com/ws/telemetry/live/"
}
```

Note: Use `wss://` (WebSocket Secure) for HTTPS sites.

## Development

To modify the client:

1. Edit `Program.cs`
2. Rebuild: `dotnet build`
3. Test: `dotnet run`

## Support

For issues or questions:
- Check Ridgway Garage documentation
- Review Django server logs
- Check iRacing SDK docs: https://sajax.github.io/irsdkdocs/

## License

Part of the Ridgway Garage project.
