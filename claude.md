# Claude Development Notes

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

## Development Modes

### Option 1: Full Docker (Production-like)
All services run in Docker. Access via http://172.28.208.237:42069

### Option 2: Hybrid Mode (Current Dev Setup)
- Docker: PostgreSQL, Redis, Celery workers, nginx
- Local: Django development server on http://172.28.208.237:42069 OR via Docker nginx

**Note**: You can run Django locally for faster development/debugging while still using Dockerized services.

## Essential Docker Commands

### Check Container Status
```bash
docker ps -a
# Shows all containers (running and stopped)
```

### View Logs
```bash
# Last 20 lines from a specific container
docker logs ridgway_garage_nginx --tail 20
docker logs ridgway_garage_web --tail 20
docker logs ridgway_garage_celery --tail 20

# Follow logs in real-time
docker logs -f ridgway_garage_celery
```

### Container Management
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

### Inspect Container Details
```bash
# Check which network a container is on
docker inspect ridgway_garage_web -f '{{range $key, $value := .NetworkSettings.Networks}}{{$key}} {{end}}'

# Get container IP address
docker inspect ridgway_garage_web -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```

### Execute Commands in Containers
```bash
# Access PostgreSQL
docker compose exec db psql -U postgres ridgway_garage

# Access Redis CLI
docker compose exec redis redis-cli

# Django management commands via web container
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

## Troubleshooting

### Upload Files Hang / Don't Process

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

### Nginx Can't Connect to Web Container

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

### Database Connection Errors

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

## File Upload Processing Flow

1. User uploads IBT file via Django web interface
2. File is saved to `media/telemetry/` directory
3. Django creates a TelemetrySession record
4. Django queues a Celery task: `process_ibt_file.delay(session_id)`
5. **Celery worker** (running in Docker) picks up the task
6. Celery worker parses IBT file and extracts telemetry data
7. WebSocket sends real-time updates to browser
8. Processing completes, user is redirected

**If uploads hang**: The Celery worker container is likely not running or has crashed.

## Local Development Server

When running Django locally (not in Docker):
```bash
cd /home/mike/Code/ridgway_garage && source venv/bin/activate && cd garage
python manage.py runserver 172.28.208.237:42069
```

The local Django server can still connect to Dockerized PostgreSQL and Redis because the WSL IP (172.28.208.237) is accessible from both the host and Docker containers.

## Network Architecture

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

## Common Mistakes to Avoid

1. **Don't assume Django is running locally** - Check `docker ps` first to see if web container is running
2. **Don't assume Celery is running locally** - It's ALWAYS in Docker (`ridgway_garage_celery`)
3. **Remember to check container logs** - Use `docker logs` instead of looking for local log files
4. **Network names matter** - All containers must be on `ridgway_garage_ridgway_network` to communicate

## Quick Reference Card

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
