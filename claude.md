# Ridgway Garage - iRacing Telemetry Analysis Platform

## Project Overview

Ridgway Garage is a web-based telemetry analysis platform for iRacing, similar to Garage61. It allows users to upload, analyze, and compare iRacing telemetry data (IBT files) with teammates and the community.

## Core Features

### Current Scope
- **IBT File Upload & Processing**: Upload telemetry files with background processing for large files (100MB+)
- **Lap-by-Lap Analysis**: Detailed telemetry visualization with interactive charts
- **Lap Comparison**: Compare multiple laps side-by-side with delta times
- **Team-Based Privacy**: Users organize into teams with shared telemetry access
- **Leaderboards**: Track + Car combination rankings within teams or publicly
- **Track Maps**: GPS-based racing line visualization on real-world maps
- **Discord Integration**: Share lap times and analysis to team Discord channels via webhooks

### Target Users
- iRacing drivers looking to improve lap times
- Racing teams collaborating on setups and technique
- Coaches analyzing driver performance

## Technology Stack

### Backend
- **Django 5.2.8**: Web framework (LTS version, supported until April 2028)
- **Python 3.10+**: Language runtime
- **PostgreSQL**: Primary database with psycopg3 connection pooling
- **Redis**: Message broker for Celery + channel layer for WebSockets
- **Celery 5.4**: Background task processing for IBT parsing
- **Django Channels 4.3.1**: WebSocket support for real-time features
- **Daphne 4.0**: ASGI server for WebSocket connections

### Frontend
- **Tailwind CSS 3.4.18**: Utility-first CSS framework with custom cyberpunk theme
- **Custom UI Components**: Glass-morphic cards, neon borders, corner brackets, animated effects
- **Plotly.js 2.27.0**: Interactive telemetry charts (speed, throttle, brake, etc.)
- **Leaflet.js**: Map visualization with OpenStreetMap tiles
- **Vanilla JavaScript**: Minimal JS for interactions (no heavy frameworks)

### Data Processing
- **pyirsdk 1.3.5**: iRacing telemetry file (IBT) parsing
- **Pandas**: Data manipulation and analysis
- **NumPy**: Numerical processing

### Authentication
- **Custom Authentication**: Simple username/email/password auth (no third-party dependencies)
- **Django User Model**: Built-in User model with standard authenticate/login
- **No Email Validation**: Streamlined registration flow (username, email, password, confirm)

### File Storage
- **Django Storage Abstraction**: Local filesystem (migration-ready for S3/cloud)
- **django-storages**: S3 integration for future scaling

## Docker Architecture

This project uses **Docker Compose** for development. The following services run in Docker containers:

- **db** (PostgreSQL 16): Database - `ridgway_garage_db`
- **redis** (Redis 7): Cache and message broker - `ridgway_garage_redis`
- **web** (Django/Daphne): Web application - `ridgway_garage_web`
- **nginx**: Reverse proxy - `ridgway_garage_nginx`
- **celery_worker**: Background task processor - `ridgway_garage_celery`
- **celery_beat**: Scheduled tasks - `ridgway_garage_beat`

All containers are connected via the `ridgway_garage_ridgway_network` Docker bridge network.

### Ports

- **42069**: Nginx (exposed to host) - main application access point
- **8000**: Django/Daphne (internal only, accessed via nginx)
- **5432**: PostgreSQL (internal only)
- **6379**: Redis (internal only)

### Development Modes

#### Option 1: Full Docker (Production-like)
All services run in Docker. Access via http://172.28.208.237:42069

#### Option 2: Hybrid Mode (Current Dev Setup)
- Docker: PostgreSQL, Redis, Celery workers, nginx
- Local: Django development server on http://172.28.208.237:42069 OR via Docker nginx

**Note**: You can run Django locally for faster development/debugging while still using Dockerized services.

### Essential Docker Commands

#### Check Container Status
```bash
docker ps -a
# Shows all containers (running and stopped)
```

#### View Logs
```bash
# Last 20 lines from a specific container
docker logs ridgway_garage_nginx --tail 20
docker logs ridgway_garage_web --tail 20
docker logs ridgway_garage_celery --tail 20

# Follow logs in real-time
docker logs -f ridgway_garage_celery
```

#### Container Management
```bash
# Restart a specific container
docker restart ridgway_garage_nginx

# Start all services
cd /home/mike/Code/ridgway_garage && docker-compose up -d

# Stop all services
cd /home/mike/Code/ridgway_garage && docker-compose down

# Rebuild and restart a specific service
cd /home/mike/Code/ridgway_garage && docker-compose up -d --build web
```

#### Inspect Container Details
```bash
# Check which network a container is on
docker inspect ridgway_garage_web -f '{{range $key, $value := .NetworkSettings.Networks}}{{$key}} {{end}}'

# Get container IP address
docker inspect ridgway_garage_web -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```

#### Execute Commands in Containers
```bash
# Access PostgreSQL
docker compose exec db psql -U postgres ridgway_garage

# Access Redis CLI
docker compose exec redis redis-cli

# Django management commands via web container
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

### Docker Troubleshooting

#### Upload Files Hang / Don't Process

**Symptom**: Files upload successfully but never get processed (stuck on processing page)

**Cause**: Celery worker is not running

**Check**:
```bash
docker ps | grep celery
docker logs ridgway_garage_celery --tail 50
```

**Fix**:
```bash
docker restart ridgway_garage_celery
```

#### Nginx Can't Connect to Web Container

**Symptom**: Nginx logs show "host not found in upstream 'web:8000'"

**Cause**: Nginx started before web container was ready, or network issue

**Check**:
```bash
docker ps | grep nginx
docker logs ridgway_garage_nginx --tail 20
```

**Fix**: Restart nginx after web is running
```bash
docker restart ridgway_garage_nginx
```

#### Database Connection Errors

**Symptom**: Django can't connect to PostgreSQL

**Check**:
```bash
docker ps | grep db
docker logs ridgway_garage_db --tail 20
```

**Fix**: Ensure db container is healthy
```bash
docker ps  # Look for "(healthy)" status
docker restart ridgway_garage_db
```

### File Upload Processing Flow

1. User uploads IBT file via Django web interface
2. File is saved to `media/telemetry/` directory
3. Django creates a TelemetrySession record
4. Django queues a Celery task: `process_ibt_file.delay(session_id)`
5. **Celery worker** (running in Docker) picks up the task
6. Celery worker parses IBT file and extracts telemetry data
7. WebSocket sends real-time updates to browser
8. Processing completes, user is redirected

**If uploads hang**: The Celery worker container is likely not running or has crashed.

### Network Architecture

```
Windows Host (172.28.208.1)
    |
    v
WSL2 (172.28.208.237)
    |
    +-- Local Django Server (port 42069) [Optional]
    |
    +-- Docker Network (ridgway_garage_ridgway_network)
            |
            +-- nginx (port 80 -> exposed as 42069)
            +-- web (port 8000)
            +-- db (port 5432)
            +-- redis (port 6379)
            +-- celery_worker
            +-- celery_beat
```

### Common Docker Mistakes to Avoid

1. **Don't assume Django is running locally** - Check `docker ps` first to see if web container is running
2. **Don't assume Celery is running locally** - It's ALWAYS in Docker (`ridgway_garage_celery`)
3. **Remember to check container logs** - Use `docker logs` instead of looking for local log files
4. **Network names matter** - All containers must be on `ridgway_garage_ridgway_network` to communicate

### Docker Quick Reference

| Task | Command |
|------|---------|
| View all containers | `docker ps -a` |
| View nginx logs | `docker logs ridgway_garage_nginx --tail 20` |
| View celery logs | `docker logs ridgway_garage_celery --tail 50` |
| Restart nginx | `docker restart ridgway_garage_nginx` |
| Restart celery | `docker restart ridgway_garage_celery` |
| Start all services | `cd /home/mike/Code/ridgway_garage && docker-compose up -d` |
| Stop all services | `cd /home/mike/Code/ridgway_garage && docker-compose down` |
| Django shell (Docker) | `docker compose exec web python manage.py shell` |
| Check container network | `docker inspect <container> -f '{{range $key, $value := .NetworkSettings.Networks}}{{$key}} {{end}}'` |

## Architecture Decisions

### Why PostgreSQL?
- **Concurrent Access**: Multiple Celery workers need simultaneous database access
- **JSON Support**: Efficient storage of telemetry data arrays
- **Connection Pooling**: psycopg3 native pooling handles worker connections
- **SQLite Limitations**: File-based locking makes concurrent writes problematic

### Why Celery?
- **Large File Processing**: IBT files can be 100MB+ and take minutes to parse
- **Background Tasks**: Don't block web requests during processing
- **Retry Logic**: Automatic retry on failures with exponential backoff
- **Scalability**: Can run multiple workers across machines

### Why Redis?
- **Celery Message Broker**: Powers background task queue for file processing
- **Caching Layer**: Fast access to frequently used data
- **Session Storage**: Can be used for Django sessions in production
- **Scalability**: Shared state across multiple application servers

### Why Plotly for Charts?
- **Interactive**: Zoom, pan, hover tooltips for detailed analysis
- **Multi-Trace**: Overlay multiple laps on same chart for comparison
- **Time-Series Optimized**: Perfect for telemetry data over distance/time
- **Django Integration**: Easy export to HTML templates

### Why Leaflet for Maps?
- **Lightweight**: 42KB vs heavier alternatives
- **Free OSM Tiles**: No API keys required for basic usage
- **GPS Overlay**: Perfect for displaying racing lines from lat/lng data
- **Framework Agnostic**: Works seamlessly with custom CSS

### Why Tailwind CSS?
- **Utility-First**: Rapid UI development with composable classes
- **Custom Theme**: Full control over cyberpunk color palette and design tokens
- **Tree-Shaking**: Only includes CSS classes actually used (final bundle ~24KB)
- **No Runtime**: Pure CSS with no JavaScript framework overhead
- **Developer Experience**: Tailwind config + safelist for Python form widgets

## UI Design System

### Cyberpunk Racing Aesthetic

**Design Philosophy:**
- **Racing/Cyberpunk Theme**: Neon accents, grid patterns, futuristic tech aesthetic
- **Dark Mode First**: Near-black backgrounds with high contrast elements
- **Performance Focused**: Fast loading, minimal JavaScript, optimized assets

### Color Palette

**Primary Colors:**
- **Neon Cyan** (`#00D9FF`): Primary accent, links, buttons, focus states
- **Ridgway Orange** (`#FF6B35`): Secondary accent, from logo gradient
- **Ridgway Yellow** (`#FFB627`): Tertiary accent, from logo gradient
- **Ridgway Red** (`#E63946`): Errors, warnings, race session badges

**Background Colors:**
- **Cyber Darkest** (`#0A0E27`): Page background
- **Cyber Dark** (`#151929`): Card backgrounds, input fields
- **Cyber Card** (`#1E2139`): Elevated cards, modals
- **Cyber Border** (`#2A2F4A`): Borders, dividers

**Additional Accents:**
- **Neon Pink** (`#FF2E97`): Hover states, special highlights
- **Neon Purple** (`#9D4EDD`): Gradients, testing badges

### Component Library

**Custom Components** (defined in `static/src/input.css`):

1. **Glass Cards** (`.glass-card`):
   - Semi-transparent background with backdrop blur
   - Subtle border with inner highlight
   - Used for: session cards, stat cards, content containers

2. **Neon Borders** (`.neon-border`):
   - Gradient border with glow effect on hover
   - Animated glow using CSS transitions
   - Used for: interactive cards, clickable elements

3. **Corner Brackets** (`.corner-brackets`):
   - Decorative cyberpunk UI element
   - 20px corner decorations in neon cyan
   - Used for: modal dialogs, featured content

4. **Neon Buttons** (`.btn-neon`):
   - Gradient background (cyan to purple)
   - Border with glow effect
   - Slide animation on hover (shine effect)
   - Min height 56px for touch targets

5. **Neon Inputs** (`.input-neon`):
   - Dark background with thick borders
   - Cyan glow on focus with box-shadow
   - Auto-fill override (prevents white backgrounds)
   - Min height 56px, 16px font (prevents mobile zoom)

6. **Session Type Badges**:
   - `.session-badge-practice` → Cyan background
   - `.session-badge-qualifying` → Orange background
   - `.session-badge-race` → Red background
   - `.session-badge-time_trial` → Yellow background
   - `.session-badge-testing` → Purple background
   - Small, uppercase, with border

7. **Effects & Animations**:
   - `.cyber-grid-bg` → Animated grid background pattern
   - `.scanline-effect` → Animated scanline overlay
   - `.cyber-divider` → Neon horizontal rule with diamond
   - `.text-neon-glow` → Text with cyan glow shadow
   - `.text-logo-gradient` → Orange to yellow gradient text

### Typography

- **Primary Font**: Inter (Google Fonts) for body text
- **Monospace Font**: Courier New for lap times, data display
- **Font Weights**: 300-700 range for hierarchy
- **Text Shadows**: Neon glow effects on headers and important text

### Layout Patterns

- **Grid System**: Tailwind's responsive grid (1 col mobile, 2 col desktop)
- **Max Width**: 7xl (80rem) container for content
- **Spacing**: Consistent 6/8/12 gap between cards
- **Padding**: Generous padding (p-6 to p-10) for touch targets

### Responsive Design

- **Mobile First**: Base styles for small screens, scale up
- **Breakpoints**: sm (640px), md (768px), lg (1024px)
- **Touch Targets**: Minimum 48px height for buttons/inputs (upgraded to 56px)
- **Navigation**: Hamburger menu on mobile, full nav on desktop

### Build Process

**Tailwind Compilation:**
```bash
npm run build   # Production build (minified)
npm run watch   # Development watch mode
```

**Input:** `static/src/input.css` (Tailwind directives + custom components)
**Output:** `static/dist/output.css` (~24KB minified)
**Config:** `tailwind.config.js` (custom theme + safelist for dynamic classes)

**Safelist Strategy:**
- Form widgets from Python: `input-neon`, `btn-neon`, `form-label`, `form-error`
- Session badges: `session-badge-practice`, `session-badge-qualifying`, etc.
- Dynamic classes that Tailwind can't detect in templates

## Data Model

### Core Entities

**Driver** (extends Django User)
- iRacing member ID
- Display name, preferences
- Team memberships

**Team**
- Name, owner
- Privacy settings (team-only vs public)
- Member list with roles

**Track**
- Name and configuration (e.g., "Road Atlanta - Full Course")
- GPS bounds for map display
- Length, turn count

**Car**
- Name (e.g., "Mazda MX-5 Cup")
- Class (e.g., "Sports Car")

**Session**
- Uploaded IBT file reference
- Track, car, driver, team
- Processing status (pending/processing/completed/failed)
- Environmental conditions (air temp, track temp)
- Session type (practice/qualifying/race)

**Lap**
- Session reference
- Lap number, lap time
- Sector times (S1, S2, S3)
- Valid/invalid flag
- Reference to telemetry data

**TelemetryData**
- Lap reference
- JSON field containing arrays:
  - Distance, time, speed
  - Throttle, brake, steering, clutch
  - RPM, gear
  - Tire temperatures (all 4 corners, surface/inner/middle/outer)
  - Tire pressure, wear
  - Fuel level, fuel usage
  - Position (lat/lng for GPS)
  - And 200+ other iRacing data points

## File Processing Workflow

1. **Upload**: Windows client or web form uploads IBT file via HTTP POST
2. **Compression Detection**: Server checks for gzip magic bytes (`0x1f 0x8b`)
3. **Decompression**: If gzipped, automatically decompress before storage
4. **Storage**: File saved to media directory using Django storage (always uncompressed)
5. **Queue**: Celery task `parse_ibt_file(session_id)` queued
6. **Processing**:
   - pyirsdk opens and parses IBT file
   - Extract session metadata (track, car, conditions)
   - Extract all laps with times and sectors
   - Extract full telemetry data (60 samples/second)
   - Store in database
7. **Visualization**: User can view/compare laps

**Note:** Compression is transparent to the processing pipeline - files are always decompressed before storage, so Celery tasks and file processing code work with standard uncompressed IBT files.

## Development Setup

### Prerequisites
- Python 3.10+
- PostgreSQL 12+
- Redis 6+
- Virtual environment at `../venv`

### Installation
```bash
# Activate virtual environment
source ../venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with database credentials, Discord OAuth keys, etc.

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start Redis (in separate terminal)
redis-server

# Start Celery worker (in separate terminal)
celery -A garage worker --loglevel=info

# Start Django development server
python manage.py runserver
```

### Local Development Server

When running Django locally (not in Docker):
```bash
cd /home/mike/Code/ridgway_garage && source venv/bin/activate && cd garage
python manage.py runserver 172.28.208.237:42069
```

The local Django server can still connect to Dockerized PostgreSQL and Redis because the WSL IP (172.28.208.237) is accessible from both the host and Docker containers.

## Windows Client Build (iRacingTelemetryClient)

The Windows telemetry client monitors the iRacing telemetry folder and automatically uploads new IBT files via HTTP POST with API token authentication. Files are automatically compressed with gzip before upload for 60-80% bandwidth savings.

### Prerequisites
- .NET 8.0 SDK (already installed at `~/.dotnet/`)
- WSL environment for building from Linux

### Building the Client

```bash
# Navigate to client directory
cd /home/mike/Code/ridgway_garage/iRacingTelemetryClient

# Build and publish as single-file executable
export PATH="$HOME/.dotnet:$PATH"
dotnet publish -c Release

# The compiled executable will be at:
# bin/Release/net8.0-windows/win-x64/publish/RidgwayGarageAgent.exe
```

### Deploying to Windows

```bash
# Copy ONLY the executable to the Windows deployment location
# DO NOT copy appsettings.json or other config files (preserves user settings)
cp bin/Release/net8.0-windows/win-x64/publish/RidgwayGarageAgent.exe \
   /mnt/c/Users/fully/Desktop/iRacingClient/

# Alternative deployment location:
# /mnt/c/temp/iRacingTelemetryClient/
```

### Architecture

The client follows a clean, modular architecture to avoid monolithic code files and improve maintainability:

```
iRacingTelemetryClient/
├── Models/
│   └── AppSettings.cs              # Configuration data model
│
├── Services/
│   ├── LoggingService.cs           # Centralized logging with in-memory buffer
│   ├── UploadTracker.cs            # Tracks uploaded files via JSON persistence
│   ├── SettingsService.cs          # Load/save settings from appsettings.json
│   └── WindowsStartupService.cs    # Registry management for auto-start
│
├── UI/
│   └── Forms/
│       ├── LogForm.cs              # Log viewer window
│       ├── StatusForm.cs           # Status display window
│       ├── SettingsForm.cs         # Settings editor window
│       └── DownloadProgressForm.cs # Update download progress window
│
├── Program.cs                      # Entry point and MainForm (920 lines)
├── UpdateChecker.cs                # GitHub Releases API integration
├── appsettings.json                # User settings (runtime)
├── appsettings.default.json        # Default settings template
└── app.ico                         # System tray icon
```

**Design Principles:**
- **Single Responsibility**: Each class has one clear purpose
- **No Monoliths**: No file should exceed ~300 lines (MainForm is an exception at 920 lines)
- **Service Layer**: Business logic separated from UI logic
- **Direct Instantiation**: Services created directly (no DI container complexity)
- **Static Services**: LoggingService and SettingsService are static for simplicity

**Key Components:**

1. **Program.cs / MainForm**
   - Application entry point and main form
   - System tray icon management
   - File system monitoring with FileSystemWatcher
   - Upload orchestration (uses UploadTracker service)
   - Event handlers for tray menu actions

2. **Services Layer**
   - `LoggingService`: Static in-memory logging (max 1000 messages) with event notifications
   - `UploadTracker`: Tracks which IBT files have been uploaded (JSON persistence)
   - `SettingsService`: Static methods to load/save settings from appsettings.json
   - `WindowsStartupService`: Static methods to manage Windows registry for auto-start

3. **UI Layer**
   - All forms separated into individual files under `UI/Forms/`
   - Forms use services via static method calls (LoggingService.Log, etc.)
   - Clean separation between UI and business logic

4. **UpdateChecker.cs**
   - Well-structured class for GitHub Releases API integration
   - Version checking and update notifications
   - Example of good single-file class design

**Runtime Files:**
- **appsettings.json**: User settings (server URL, API token, telemetry folder, auto-upload)
- **uploaded_files.json**: Tracks which files have been uploaded (generated at runtime)
- **crash.log**: Fatal error logging (generated on crashes)

### Configuration
The client stores settings in `appsettings.json` in the same directory as the executable:
```json
{
  "ServerUrl": "https://garage.mapleleafmakers.com",
  "ApiToken": "user-api-token-here",
  "TelemetryFolder": "C:\\Users\\username\\Documents\\iRacing\\telemetry",
  "AutoUpload": true
}
```

### Build Notes
- The project uses `PublishSingleFile=true` to create a standalone executable
- Runtime identifier is `win-x64` (Windows 64-bit)
- Assembly name is `RidgwayGarageAgent` (not `iRacingTelemetryClient`)
- First build generates warnings about nullable fields - these are safe to ignore
- When deploying updates, only copy the .exe to avoid overwriting user settings

### Code Quality Standards

**⚠️ CRITICAL: Avoid Monolithic Files**

This project was refactored in November 2024 to eliminate a 1,669-line monolithic Program.cs file. Future development MUST follow these standards:

**File Size Limits:**
- **Hard limit**: No single file should exceed 500 lines
- **Target limit**: Keep files under 300 lines when possible
- **Forms/UI**: Keep individual forms under 200 lines
- **Services**: Keep service classes under 150 lines

**When a File Gets Too Large:**

If a file approaches 300 lines, immediately refactor:

1. **Extract Services**: Move business logic to `Services/` folder
   ```csharp
   // Bad: Logic in MainForm
   private void SaveSettings() { /* 50 lines */ }

   // Good: Extract to service
   SettingsService.SaveSettings(settings);
   ```

2. **Extract UI Forms**: Move forms to `UI/Forms/` folder
   - Each dialog/window should be its own file
   - Keep form logic focused on UI concerns only

3. **Extract Utilities**: Move helper methods to `Utils/` folder
   - File path detection, crash logging, etc.
   - Static utility classes are acceptable for stateless helpers

4. **Extract Models**: Move data structures to `Models/` folder
   - POCOs, DTOs, configuration classes

**Refactoring Checklist:**

When you notice a file getting large, ask:
- [ ] Can this logic move to a service?
- [ ] Can this form be extracted to UI/Forms/?
- [ ] Can this be a static utility method?
- [ ] Does this class have multiple responsibilities?
- [ ] Would extracting this make the code clearer?

**Good Examples in This Codebase:**
- ✅ `UpdateChecker.cs` (279 lines) - Well-structured, single responsibility
- ✅ `LoggingService.cs` (42 lines) - Focused, simple, reusable
- ✅ `SettingsService.cs` (79 lines) - Clear separation of concerns
- ⚠️ `Program.cs/MainForm` (920 lines) - Still large but acceptable as main orchestrator

**Red Flags:**
- ❌ File over 500 lines - Immediate refactoring required
- ❌ File over 300 lines - Plan refactoring soon
- ❌ Class with 5+ distinct responsibilities - Extract services
- ❌ Copying code between files - Extract to shared service

**Remember:** Smaller, focused files are easier to:
- Understand and maintain
- Test independently
- Reuse across the application
- Review in pull requests
- Debug when issues arise

### Compression Feature

The client automatically compresses IBT files before upload using gzip compression:

**How It Works:**
- Files are compressed in-memory using `GZipStream` before upload
- Server automatically detects gzip via magic bytes (`0x1f 0x8b`) and decompresses
- Fully backward compatible - server handles both compressed and uncompressed files
- No configuration needed - compression is always enabled

**Benefits:**
- **60-80% file size reduction** on typical IBT files
- **70% faster uploads** on typical connections
- Massive savings for endurance races (500MB → 100-200MB)

**Example Compression Ratios:**
- Practice session (10 laps, 10MB): → 3-4MB (70% reduction)
- Race session (30 laps, 100MB): → 20-30MB (75% reduction)
- Endurance race (500MB): → 100-150MB (75% reduction)

**Upload Time Savings (10 Mbps connection):**
- 100MB file: 80 seconds → 24 seconds (**56 seconds saved**)
- 500MB file: 400 seconds → 120 seconds (**4.6 minutes saved**)

**Logging:**
The client logs compression statistics for each upload:
```
Uploading: session.ibt (100.00 MB → 25.00 MB compressed, 75.0% reduction)
```

**Technical Details:**
- Compression: Standard .NET `System.IO.Compression.GZipStream`
- Compression level: Default (optimal balance of speed and size)
- Server decompression: Python `gzip.decompress()`
- File validation: Server validates gzip format and rejects corrupted files

### File Upload Retry Logic

The client includes intelligent retry logic for files being actively written by iRacing:

**How It Works:**
- Waits up to 4 minutes for iRacing to finish writing the file
- Uses file size stability checks (size unchanged for 2 consecutive checks)
- Exponential backoff: starts at 1 second, increases to max 5 seconds
- If timeout occurs, automatically retries when file changes are detected via FileSystemWatcher

**Why This Matters:**
- iRacing can take 2-4 minutes to finalize large IBT files (100MB+)
- Prevents "file locked" errors and stuck uploads
- Users don't need to manually retry failed uploads
- Seamless experience even during active racing sessions

### Release Workflow

**CRITICAL: Version Matching Rule**
- ⚠️ **ALWAYS update the version in `iRacingTelemetryClient.csproj` BEFORE tagging a release**
- The version in `.csproj` MUST match the git tag (e.g., tag `v0.1.7` requires version `0.1.7` in csproj)
- Mismatched versions cause the update checker to detect false updates

**Release Process:**
1. Update version in `iRacingTelemetryClient/iRacingTelemetryClient.csproj`:
   ```xml
   <Version>0.1.7</Version>
   <AssemblyVersion>0.1.7</AssemblyVersion>
   <FileVersion>0.1.7</FileVersion>
   ```

2. Commit changes:
   ```bash
   git add iRacingTelemetryClient/iRacingTelemetryClient.csproj
   git commit -m "Bump version to 0.1.7"
   ```

3. Tag and push (triggers GitHub Actions):
   ```bash
   git tag v0.1.7
   git push origin main --tags
   ```

4. GitHub Actions automatically:
   - Builds the client
   - Creates a GitHub Release
   - Uploads `RidgwayGarageAgent.exe` as a release asset

5. Users with older versions will see update notification in the client's tray menu

### Auto-Update Feature

The client includes a built-in update checker:
- **Check for Updates**: Right-click tray icon → "Check for Updates..."
- **About Dialog**: Shows current version
- **Update Dialog**: Displays release notes and links to GitHub releases page
- **Manual Download**: Users click "View Release Page" to download new version from GitHub

The update checker:
- Queries GitHub Releases API for the latest version
- Compares with current version using semantic versioning
- Skips pre-releases automatically
- Links to GitHub release page for manual download
- No automatic downloads or installations (user maintains control)

## Configuration Files

### settings.py Key Sections
- `DATABASES`: PostgreSQL with psycopg3 pooling
- `STORAGES`: File storage abstraction (local → S3 migration path)
- `CELERY_BROKER_URL`: Redis connection for task queue
- `CHANNEL_LAYERS`: Redis connection for WebSockets
- `INSTALLED_APPS`: daphne (first!), channels, celery, allauth, telemetry app

### asgi.py
- Configure ASGI application with Channels routing
- WebSocket URL patterns for telemetry streams

### celery.py
- Celery app initialization
- Task autodiscovery
- Worker configuration (prefetch, max tasks per child)

## Security Considerations

- **File Validation**: Verify IBT file format before processing
- **Size Limits**: Enforce max upload size (e.g., 500MB)
- **Team Privacy**: Enforce team-only access to telemetry data
- **Rate Limiting**: Prevent abuse of upload/processing endpoints
- **Signed URLs**: Use for private file downloads (S3 compatibility)

## Performance Optimizations

- **Connection Pooling**: psycopg3 pools 2-10 connections per worker
- **Celery Prefetch**: `worker_prefetch_multiplier = 1` to prevent connection hogging
- **Database Indexes**: On Session (driver, track, car), Lap (session, lap_time)
- **Chunked Uploads**: Handle large files without loading into memory
- **Data Compression**: Consider compressing telemetry JSON in database
- **CDN**: Serve static files (Bootstrap, Plotly, Leaflet) from CDN in production

## Future Enhancements

### Phase 2+ Features
- **Setup File Sharing**: Upload and share car setups within teams
- **Automated Analysis**: AI-powered suggestions for improvement areas
- **Track Limits**: Overlay track boundary violations
- **Consistency Analysis**: Lap time variance, sector consistency metrics
- **Coaching Tools**: Annotation and video sync
- **Mobile App**: Native iOS/Android for on-track analysis

### Scalability Path
- **Database**: Migrate from SQLite → PostgreSQL (done) → PostgreSQL cluster
- **Storage**: Local files → S3/CloudFront for global distribution
- **Caching**: Add Redis caching layer for frequently accessed data
- **CDN**: Serve static assets and track maps via CDN
- **Load Balancing**: Multiple Django/Daphne instances behind nginx
- **Celery Scaling**: Add more worker nodes for processing

## Deployment Considerations

### Docker Strategy (Future)
- Separate containers: Django/Daphne, Celery worker, PostgreSQL, Redis
- Docker Compose for local development
- Kubernetes for production scaling

### Environment Variables
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `SECRET_KEY`: Django secret key
- `DEBUG`: True/False for development/production
- `ALLOWED_HOSTS`: Comma-separated hostnames
- `USE_S3`: True to enable S3 storage backend

## Project Structure

```
ridgway_garage/
├── garage/                   # Django web application
│   ├── manage.py
│   ├── requirements.txt
│   ├── package.json          # Node.js dependencies for Tailwind
│   ├── tailwind.config.js    # Tailwind theme configuration
│   ├── .env                 # Environment variables (not in git)
│   ├── .env.example         # Template for .env
│   ├── garage/              # Django project settings
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── asgi.py          # ASGI config for Channels
│   │   ├── wsgi.py
│   │   └── celery.py        # Celery configuration
│   ├── new_templates/       # Cyberpunk UI templates (NEW)
│   │   ├── base.html        # Cyberpunk base template with Tailwind
│   │   ├── login.html       # Custom auth login page
│   │   ├── register.html    # Custom auth registration page
│   │   └── telemetry/
│   │       └── home.html    # Dashboard with stats and recent sessions
│   ├── telemetry/           # Main app
│   │   ├── models.py        # Driver, Team, Track, Car, Session, Lap, TelemetryData
│   │   ├── views.py         # Upload, dashboard, comparison views
│   │   ├── auth_views.py    # Custom authentication (login, register, logout)
│   │   ├── tasks.py         # Celery tasks (parse_ibt_file)
│   │   ├── consumers.py     # WebSocket consumers
│   │   ├── routing.py       # WebSocket URL routing
│   │   ├── services/
│   │   │   └── ibt_parser.py    # pyirsdk integration
│   │   ├── templatetags/
│   │   │   └── telemetry_filters.py  # Custom filters (format_laptime, etc.)
│   │   ├── templates/       # Old Bootstrap templates (deprecated)
│   │   │   └── telemetry/
│   │   │       ├── base.html    # Old Bootstrap base (not used)
│   │   │       ├── session_detail.html
│   │   │       ├── lap_detail.html
│   │   │       └── lap_compare.html
│   │   └── static/
│   │       └── telemetry/   # Old Bootstrap assets
│   │           ├── css/style.css  # Old custom CSS (deprecated)
│   │           ├── vendor/bootstrap/
│   │           └── img/logo.png
│   ├── static/              # New Tailwind CSS assets (NEW)
│   │   ├── src/
│   │   │   └── input.css    # Tailwind directives + custom components
│   │   └── dist/
│   │       └── output.css   # Compiled Tailwind CSS (~24KB)
│   ├── media/               # Uploaded IBT files
│   │   └── telemetry/
│   │       └── 2025/01/17/
│   ├── staticfiles/         # Collected static files (production)
│   └── node_modules/        # npm dependencies (not in git)
├── iRacingTelemetryClient/  # Windows client (.NET 8.0)
│   ├── Models/              # Data models
│   │   └── AppSettings.cs
│   ├── Services/            # Business logic services
│   │   ├── LoggingService.cs
│   │   ├── UploadTracker.cs
│   │   ├── SettingsService.cs
│   │   └── WindowsStartupService.cs
│   ├── UI/                  # User interface
│   │   └── Forms/
│   │       ├── LogForm.cs
│   │       ├── StatusForm.cs
│   │       ├── SettingsForm.cs
│   │       └── DownloadProgressForm.cs
│   ├── Program.cs           # Entry point and MainForm (920 lines)
│   ├── UpdateChecker.cs     # GitHub Releases integration
│   ├── iRacingTelemetryClient.csproj
│   ├── app.ico              # System tray icon
│   ├── appsettings.json     # User settings (copied to output)
│   └── bin/Release/net8.0-windows/win-x64/publish/
│       └── RidgwayGarageAgent.exe  # Compiled executable
├── nginx/                   # Nginx reverse proxy config
│   └── nginx.conf
├── docker-compose.yml       # Docker orchestration
└── claude.md                # This file (project documentation)
```

## Key Design Patterns

### Separation of Concerns
- **Models**: Data structure and business logic
- **Views**: HTTP request handling and template rendering
- **Tasks**: Long-running background operations
- **Consumers**: WebSocket connection handling
- **Services**: Reusable business logic (IBT parsing, analysis)

### Asynchronous Processing
- Celery tasks for CPU-intensive work (parsing large files)
- Django Channels for I/O-bound real-time communication
- Redis as shared state between web and worker processes

### Storage Abstraction
- Use Django storage API, not direct file I/O
- Easy migration from local → S3 by changing one setting
- Consistent file handling across development and production

### Windows Client Architecture (iRacingTelemetryClient)
- **Clean Separation**: Models, Services, UI layers clearly separated
- **No Monoliths**: Maximum 500-line file limit enforced
- **Static Services**: LoggingService, SettingsService, WindowsStartupService are static
- **Direct Instantiation**: No DI container - services created directly for simplicity
- **Single Responsibility**: Each class has one clear, focused purpose
- **Form Extraction**: All UI dialogs in separate files under UI/Forms/

## Testing Strategy

- **Unit Tests**: Models, forms, utility functions
- **Integration Tests**: Views, Celery tasks, WebSocket consumers
- **End-to-End Tests**: File upload → processing → visualization workflow
- **Performance Tests**: Large file uploads, concurrent parsing
- **Load Tests**: Multiple simultaneous users, WebSocket connections

## Monitoring & Observability

- **Celery Flower**: Task monitoring dashboard
- **Django Debug Toolbar**: Development SQL query analysis
- **Logging**: Structured logs for parsing errors, task failures
- **Metrics**: Track upload sizes, processing times, error rates
- **Alerts**: Notify on task failures, high error rates

## Resources & References

- **iRacing SDK**: https://github.com/kutu/pyirsdk
- **Garage61**: Inspiration for features and UX
- **Django Channels**: https://channels.readthedocs.io/
- **Celery**: https://docs.celeryproject.org/
- **Plotly**: https://plotly.com/python/
- **Leaflet**: https://leafletjs.com/
- **OpenStreetMap**: https://www.openstreetmap.org/

## Project Status

**Current Phase**: UI modernization complete, core features operational
**Current Version**: v0.2.x (UI redesign November 2024)
**Last Updated**: 2025-01-24

**Recently Completed:**
- **🎨 Cyberpunk UI Modernization (November 2024)** - Complete UI redesign
  - Migrated from Bootstrap 5 to Tailwind CSS 3.4.18
  - Custom cyberpunk/neon racing aesthetic with cyan/orange/yellow color palette
  - Glass-morphic cards, neon borders, corner brackets, animated effects
  - Custom authentication (removed django-allauth dependency)
  - New templates: login, register, dashboard (home)
  - ~24KB minified CSS bundle (vs. Bootstrap's ~200KB)
  - Mobile-first responsive design with 56px touch targets
  - Template filters for lap time formatting (mm:ss.SSS)

- **Windows client refactoring (2024)** - Eliminated 1,669-line monolithic Program.cs
  - Reduced to 920 lines (45% reduction)
  - Extracted 9 classes to Models/, Services/, and UI/Forms/ folders
  - Established code quality standards and architectural guidelines
  - Clean separation of concerns: Models, Services, UI

- **Gzip compression for file uploads (v0.1.9)** - 60-80% bandwidth savings, comprehensive test coverage
- **File upload retry mechanism fix (v0.1.8)** - Automatic retry for locked files, 4-minute timeout
- **Windows client auto-update checking (v0.1.6-0.1.7)** - Version checking, GitHub release integration
- **GitHub Actions CI/CD pipeline** - Automated builds and releases

**Active Features:**
- **🆕 Cyberpunk UI** - Custom Tailwind CSS theme with racing aesthetics, neon accents
- **🆕 Custom Authentication** - Simple username/email/password (no third-party deps)
- **🆕 Dashboard** - Stats cards, 5 recent sessions with type badges, formatted lap times
- **Automatic gzip compression** - Client compresses before upload, server auto-decompresses
- **Intelligent upload retry** - Handles file locking, automatic retry on file system changes
- **IBT file upload and processing** - Celery background tasks for async processing
- **Lap-by-lap analysis** - Interactive Plotly charts with telemetry visualization
- **Team-based privacy and leaderboards** - Track + Car combination rankings
- **Personal best tracking** - Optional Discord notifications for new PBs
- **Windows client** - Automatic file monitoring, upload, and update checking
- **Version checking** - In-client update notifications with GitHub release links

**Test Coverage:**
- Comprehensive Django tests for compression (compressed, uncompressed, corrupted files)
- API authentication tests
- All tests passing ✓

**Next Priorities:**
- **Settings page** - User preferences, API token management (cyberpunk UI)
- **Port remaining pages** - Session list, session detail, lap comparison, leaderboards to new UI
- **Upload page redesign** - Cyberpunk dropzone with neon effects
- Additional telemetry analysis features (sector comparisons, consistency metrics)
- Performance optimizations for large file processing

## Template Migration Guide

**Current State (January 2025):**
- ✅ **Completed**: `base.html`, `login.html`, `register.html`, `home.html` (dashboard)
- ⏳ **Remaining**: All other pages still using old Bootstrap templates

**Migration Strategy:**

1. **Template Priority**: Django checks `new_templates/` first, then `telemetry/templates/`
2. **Parallel Operation**: Old and new templates coexist during migration
3. **URL Names**: Use `'telemetry:home'` for dashboard (NOT `'telemetry:dashboard'`)
4. **Template Filters**: Load `{% load telemetry_filters %}` for `format_laptime` filter

**How to Port a New Page:**

1. Create template in `new_templates/telemetry/page_name.html`
2. Extend `{% extends "base.html" %}` (cyberpunk base)
3. Load filters: `{% load static %}` and `{% load telemetry_filters %}`
4. Use component classes: `.glass-card`, `.btn-neon`, `.input-neon`, `.corner-brackets`
5. Use session badges: `.session-badge-practice`, `.session-badge-race`, etc.
6. Format lap times: `{{ lap_time|format_laptime }}`
7. If using new custom classes, add to `tailwind.config.js` safelist
8. Run `npm run build` to compile Tailwind CSS
9. Test responsive design (mobile + desktop)

**Component Reference:**

- **Cards**: `glass-card p-6 corner-brackets hover:shadow-neon-cyan`
- **Buttons**: `btn-neon` (primary), `border-2 border-cyber-border hover:border-neon-cyan` (secondary)
- **Inputs**: `input-neon` (applied via form widgets in Python)
- **Stat Cards**: See `home.html` for pattern (icon + stat + label)
- **Session Cards**: See `home.html` for layout (badge + info + stats + button)

**GitHub Links:**
- Repo: `https://github.com/fullydoved/ridgway_garage`
- Releases: `https://github.com/fullydoved/ridgway_garage/releases/latest`

---

*This documentation is maintained for AI agents and developers to understand the project architecture and design decisions. Update when making significant architectural changes.*
