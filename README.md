# Ridgway Garage - iRacing Telemetry Analysis Platform

A comprehensive web application for analyzing iRacing telemetry data, comparing laps, and improving your racing performance.

## Features

- 📊 **Telemetry Visualization** - Interactive charts showing speed, throttle, brake, steering, RPM, and tire temperatures
- 🗺️ **GPS Track Maps** - Visual representation of your racing line with speed overlays
- 🔄 **Lap Comparison** - Compare multiple laps side-by-side with overlay charts and track maps
- 📈 **Analysis System** - Create named analyses (like Garage 61) to save and revisit lap comparisons
- 🏆 **Personal Best Tracking** - Automatically identify and highlight your best laps
- 👥 **Team Collaboration** - Share analyses with team members
- 🔐 **Authentication** - Secure login with Discord OAuth integration
- 📦 **Large File Support** - Upload IBT files up to 2GB (handles Nurburgring endurance sessions)
- 🔄 **Auto-Update System** - One-click system updates with automatic backup and rollback (admin only)

## Tech Stack

- **Backend**: Django 5.2.8, Python 3.12
- **Database**: PostgreSQL 16 with connection pooling
- **Cache/Queue**: Redis 7
- **Task Queue**: Celery for background processing
- **WebSockets**: Django Channels for real-time updates
- **Web Server**: Nginx (Alpine) for static files and reverse proxy
- **Visualization**: Plotly.js, Leaflet.js (all bundled locally)
- **Deployment**: Docker & Docker Compose
- **Running on**: Port 42069 🚀

---

## Quick Start with Docker (Recommended)

This is the easiest way to get Ridgway Garage running on your machine.

### Prerequisites

1. **Docker Desktop** for Windows 11
   - Download from: https://www.docker.com/products/docker-desktop
   - Install and restart your computer
   - **IMPORTANT**: Docker Desktop requires WSL 2 (Windows Subsystem for Linux 2)
     - During installation, Docker Desktop will guide you through enabling WSL 2
     - If prompted, download and install the WSL 2 Linux kernel update
     - After installation, Docker Desktop should show "Engine running" in the system tray

2. **Git** for Windows
   - Download from: https://git-scm.com/download/win
   - Install with default settings (Git Bash will be included)

> **Note for Windows users**: This repository includes a `.gitattributes` file that ensures shell scripts use Unix line endings (LF) even on Windows. This prevents common "bad interpreter" errors when running Docker containers.

### Installation Steps

1. **Clone the repository**

   Open **Git Bash** (recommended) or **PowerShell** and run:
   ```bash
   git clone https://github.com/yourusername/ridgway_garage.git
   cd ridgway_garage
   ```

2. **Create environment file**

   **In Git Bash:**
   ```bash
   cp .env.example .env
   ```

   **In PowerShell or CMD:**
   ```powershell
   copy .env.example .env
   ```

3. **Generate a secret key**

   Open `.env` in a text editor (Notepad, VS Code, etc.) and replace the `SECRET_KEY` value.

   **In Git Bash or PowerShell:**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(50))"
   ```

   Copy the output and paste it as your `SECRET_KEY` in `.env`:
   ```
   SECRET_KEY=your-generated-key-here
   ```

4. **Start the application**
   ```bash
   docker compose up -d
   ```

   **Note**: If you see "command not found", try `docker-compose up -d` (with hyphen) instead.

   This will:
   - Download and build all required containers
   - Set up PostgreSQL database
   - Set up Redis for caching and background tasks
   - Run database migrations
   - Create a default admin user
   - Start the Django web server
   - Start Celery workers for background processing

   **First-time setup takes 2-5 minutes.** You'll see lots of output as containers download and build.

5. **Access the application**
   - Open your browser and go to: http://localhost:42069
   - Login with default credentials:
     - **Username**: `admin`
     - **Password**: `admin`
   - **IMPORTANT**: Change the admin password after first login!

6. **Stop the application**
   ```bash
   docker compose down
   ```

7. **View logs** (useful for troubleshooting)
   ```bash
   docker compose logs -f web
   docker compose logs -f celery_worker
   ```

---

## Manual Installation (Advanced)

If you prefer not to use Docker, you can install manually.

### Prerequisites

- Python 3.12+
- PostgreSQL 16+
- Redis 7+
- Git

### Windows 11 Manual Installation

**Note**: Manual installation is significantly more complex than Docker. Only choose this if you have specific requirements.

1. **Install Python 3.12**
   - Download from: https://www.python.org/downloads/
   - **IMPORTANT**: During installation, check "Add Python to PATH"
   - Verify installation: Open PowerShell and run `python --version`

2. **Install PostgreSQL**
   - Download from: https://www.postgresql.org/download/windows/
   - During installation:
     - Remember the password you set for the `postgres` user
     - Keep the default port (5432)
     - Install pgAdmin 4 (optional, but helpful for database management)

3. **Install Redis**
   - Download from: https://github.com/tporadowski/redis/releases
   - Download `Redis-x64-x.x.xxx.zip`
   - Extract to a permanent location (e.g., `C:\Redis`)
   - You'll need to run `redis-server.exe` manually each time (see step 12)

4. **Clone the repository**

   Open **PowerShell** or **Git Bash**:
   ```bash
   git clone https://github.com/yourusername/ridgway_garage.git
   cd ridgway_garage
   ```

5. **Create virtual environment**

   **In PowerShell:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

   If you get an execution policy error, run:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```

   **In Git Bash or CMD:**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

6. **Install dependencies**
   ```bash
   cd garage
   pip install -r requirements.txt
   ```

7. **Configure environment**

   **In PowerShell or CMD:**
   ```powershell
   copy .env.example .env
   ```

   **In Git Bash:**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` in a text editor and update:
   ```
   SECRET_KEY=your-generated-secret-key
   DB_NAME=ridgway_garage
   DB_USER=postgres
   DB_PASSWORD=your_postgres_password
   DB_HOST=localhost
   DB_PORT=5432
   REDIS_URL=redis://localhost:6379/0
   ```

   Generate a secret key:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(50))"
   ```

8. **Create database**
   Open pgAdmin or psql and create the database:
   ```sql
   CREATE DATABASE ridgway_garage;
   ```

9. **Run migrations**
   ```bash
   python manage.py migrate
   ```

10. **Create superuser**
    ```bash
    python manage.py createsuperuser
    ```

11. **Collect static files**
    ```bash
    python manage.py collectstatic
    ```

12. **Start the development server** (in separate terminals)

    Terminal 1 - Django:
    ```bash
    python manage.py runserver
    ```

    Terminal 2 - Celery Worker:
    ```bash
    celery -A garage worker -l info
    ```

    Terminal 3 - Daphne (for WebSockets, optional):
    ```bash
    daphne -p 8001 garage.asgi:application
    ```

---

## Usage Guide

### Uploading Telemetry

1. Go to **Upload** in the navigation menu
2. Select your `.ibt` file from iRacing
3. The system will automatically:
   - Parse the telemetry data
   - Identify the track and car
   - Segment laps
   - Calculate lap times
   - Mark personal bests

### Viewing Sessions

1. Go to **My Sessions**
2. Click on any session to see all laps
3. Click **View** on any lap to see detailed telemetry charts and GPS track map

### Creating Analyses (Lap Comparisons)

1. Go to **Analyses** → **Create New Analysis**
2. Give it a descriptive name (e.g., "Baseline vs New Setup")
3. Navigate to any lap in **My Sessions**
4. Click **Add to Analysis** dropdown
5. Select the analysis you created
6. Repeat for additional laps you want to compare
7. Go to **Analyses** → Click on your analysis
8. View the overlay charts and track map showing all laps

### Features in Analysis View

- **Track Overlay Map**: Shows all laps color-coded on the same track
  - Toggle "Show Map Background" to show/hide OpenStreetMap tiles
  - Click any racing line to see lap details
- **Comparison Charts**: Speed, throttle/brake, steering, RPM, and tire temperatures
  - All charts are synchronized - hover to see values across all laps
  - Each lap has a unique color for easy identification
- **Lap List**: Shows all laps in the analysis with lap times and session info

---

## Project Structure

```
ridgway_garage/
├── garage/                    # Django project root
│   ├── garage/               # Django settings and config
│   │   ├── settings.py       # Main settings
│   │   ├── urls.py           # URL routing
│   │   ├── asgi.py           # ASGI config (WebSockets)
│   │   └── celery.py         # Celery configuration
│   ├── telemetry/            # Main Django app
│   │   ├── models.py         # Database models
│   │   ├── views.py          # View logic
│   │   ├── forms.py          # Django forms
│   │   ├── tasks.py          # Celery background tasks
│   │   ├── consumers.py      # WebSocket consumers
│   │   ├── routing.py        # WebSocket routing
│   │   ├── utils/            # Utility modules
│   │   │   ├── ibt_parser.py # IBT file parsing
│   │   │   └── charts.py     # Plotly chart generation
│   │   ├── templates/        # HTML templates
│   │   └── static/           # CSS, JS, images, vendor libs
│   │       └── telemetry/
│   │           ├── css/      # Custom stylesheets
│   │           ├── img/      # Images and favicon
│   │           ├── js/       # Custom JavaScript
│   │           └── vendor/   # Third-party libraries (local)
│   │               ├── bootstrap/
│   │               ├── bootstrap-icons/
│   │               ├── leaflet/
│   │               └── plotly/
│   ├── media/                # User uploads (IBT files)
│   ├── staticfiles/          # Collected static files
│   ├── manage.py             # Django management script
│   └── requirements.txt      # Python dependencies
├── nginx/                    # Nginx web server config
│   ├── nginx.conf            # Nginx configuration
│   └── README.md             # Nginx documentation
├── docker-compose.yml        # Docker services configuration
├── Dockerfile                # Docker image build instructions
├── docker-entrypoint.sh      # Container startup script
├── .env.example              # Example environment variables
└── README.md                 # This file
```

---

## Docker Services

The `docker-compose.yml` defines the following services:

- **db** - PostgreSQL 16 database
- **redis** - Redis 7 for caching and message broker
- **web** - Django application (Daphne ASGI server)
- **nginx** - Nginx web server for static files and reverse proxy
- **celery_worker** - Background task processor
- **celery_beat** - Scheduled task scheduler

### Network Isolation & Architecture

All services are connected via a **private Docker network** (`ridgway_network`) with the following benefits:

✅ **No Port Conflicts** - PostgreSQL and Redis do NOT expose ports to your host machine, so they won't conflict with system installations
✅ **Isolated Environment** - Services communicate internally using container names (e.g., `db:5432`, `redis:6379`)
✅ **Secure by Default** - Database and Redis are only accessible from within the Docker network
✅ **Production-Ready Web Server** - Nginx serves static files efficiently and proxies Django/WebSocket requests
✅ **Only Port 42069 Exposed** - The web application is accessible at `http://localhost:42069`
✅ **Self-Contained** - All CSS, JS, fonts, and icons are bundled locally (no CDN dependencies - works offline!)

This means you can run Ridgway Garage alongside your system PostgreSQL/Redis without any conflicts!

---

## Configuration

### Environment Variables

Key environment variables in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key (required) | - |
| `DEBUG` | Debug mode (True/False) | `True` |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts | `localhost,127.0.0.1` |
| `DB_NAME` | PostgreSQL database name | `ridgway_garage` |
| `DB_USER` | PostgreSQL username | `postgres` |
| `DB_PASSWORD` | PostgreSQL password | `postgres` |
| `DB_HOST` | PostgreSQL host | `db` (Docker) / `localhost` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `DISCORD_CLIENT_ID` | Discord OAuth client ID (optional) | - |
| `DISCORD_CLIENT_SECRET` | Discord OAuth secret (optional) | - |

---

## Troubleshooting

### Windows-Specific Docker Issues

**Docker Desktop not starting / "Docker Engine stopped"**

1. Ensure WSL 2 is installed and set as default:
   ```powershell
   wsl --set-default-version 2
   wsl --update
   ```

2. Restart Docker Desktop from the system tray icon

3. If still not working, restart your computer

**"docker compose" command not found**

- Try using `docker-compose` (with hyphen) instead: `docker-compose up -d`
- Or update Docker Desktop to the latest version (includes Compose V2)

**Line ending errors (LF vs CRLF)**

If you see errors like `^M: bad interpreter` or `\r: command not found`:

1. Git is converting line endings to Windows format (CRLF)
2. Configure Git to keep Unix line endings for shell scripts:
   ```bash
   git config --global core.autocrlf input
   ```

3. Re-clone the repository or reset files:
   ```bash
   git rm -rf --cached .
   git reset --hard
   ```

**Port 42069 already in use on Windows**

Check what's using the port:
```powershell
netstat -ano | findstr :42069
```

Kill the process (replace PID with the actual process ID):
```powershell
taskkill /PID <PID> /F
```

Or change the port in `docker-compose.yml` as described below.

### General Docker Issues

**Docker permission denied (Linux/WSL)**

If you see "permission denied" when running Docker commands:
```bash
sudo usermod -aG docker $USER
newgrp docker
```

Then log out and log back in, or restart your computer.

**Container won't start**
```bash
docker compose down -v
docker compose up -d --build
```

**Database connection errors**
```bash
docker compose logs db
```

**View all logs**
```bash
docker compose logs -f
```

### Port Already in Use

If port 42069 is already in use, edit `docker-compose.yml`:
```yaml
nginx:
  ports:
    - "8080:80"  # Change host port to 8080 (or any available port)
```

Then access the app at http://localhost:8080 (or whatever port you chose)

### Celery Tasks Not Running

Check Celery worker logs:
```bash
docker compose logs -f celery_worker
```

Restart Celery worker:
```bash
docker compose restart celery_worker
```

### Large File Upload Issues

If you're having trouble uploading very large IBT files (>1GB):

1. **Check nginx logs**:
   ```bash
   docker compose logs -f nginx
   ```

2. **Verify settings**:
   - Nginx: `client_max_body_size 2G` in `nginx/nginx.conf`
   - Django: `DATA_UPLOAD_MAX_MEMORY_SIZE = 2147483648` in `settings.py`

3. **Increase limits if needed** (for files >2GB):
   - Update `nginx/nginx.conf`: change `client_max_body_size` value
   - Update `garage/garage/settings.py`: change `DATA_UPLOAD_MAX_MEMORY_SIZE`
   - Rebuild: `docker compose down && docker compose build && docker compose up -d`

---

## Development

### Running Tests

```bash
docker compose exec web python manage.py test
```

Or with pytest:
```bash
docker compose exec web pytest
```

### Creating Migrations

```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

### Accessing Django Shell

```bash
docker compose exec web python manage.py shell
```

### Accessing Database

The PostgreSQL and Redis ports are NOT exposed to the host machine to prevent conflicts with system installations. To access them:

**PostgreSQL**:
```bash
# Access PostgreSQL shell
docker compose exec db psql -U postgres ridgway_garage

# Run SQL commands
docker compose exec db psql -U postgres -d ridgway_garage -c "SELECT COUNT(*) FROM telemetry_session;"
```

**Redis**:
```bash
# Access Redis CLI
docker compose exec redis redis-cli

# Check keys
docker compose exec redis redis-cli KEYS '*'
```

**If you need external access** (for tools like pgAdmin or Redis Desktop Manager), temporarily add port mappings to docker-compose.yml:
```yaml
db:
  ports:
    - "5433:5432"  # Use different host port to avoid conflicts

redis:
  ports:
    - "6380:6379"  # Use different host port to avoid conflicts
```

---

## Production Deployment

For production deployment, you should:

1. Set `DEBUG=False` in `.env`
2. Generate a strong `SECRET_KEY`
3. Update `ALLOWED_HOSTS` with your domain
4. Use a production-grade database (managed PostgreSQL)
5. Configure email settings for user notifications
6. Set up SSL/TLS with a reverse proxy (nginx)
7. Configure S3 for media file storage
8. Set up monitoring and logging
9. Use environment-specific `.env` files
10. Enable database backups

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## License

This project is licensed under the MIT License.

---

## Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Contact the development team

---

## Acknowledgments

- Built with Django, Celery, and Channels
- Uses pyirsdk for iRacing telemetry parsing
- Visualization powered by Plotly.js and Leaflet.js
- Inspired by Garage 61 and other telemetry analysis platforms
