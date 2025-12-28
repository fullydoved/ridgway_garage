#!/bin/bash
# Database restore script for Ridgway Garage
# Restores a PostgreSQL dump to the Docker container

set -e

# Configuration
CONTAINER_NAME="ridgway_garage_db"
DB_NAME="ridgway_garage"
DB_USER="postgres"

# Check arguments
if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file.sql.gz>"
    echo ""
    echo "Example: $0 ridgway_backup_20250128_120000.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"

# Check if file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file '$BACKUP_FILE' not found"
    exit 1
fi

echo "=== Ridgway Garage Database Restore ==="
echo "Container: $CONTAINER_NAME"
echo "Database: $DB_NAME"
echo "Backup: $BACKUP_FILE"
echo ""

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Error: Container '$CONTAINER_NAME' is not running"
    echo "Start it with: docker compose up -d db"
    exit 1
fi

# Confirm restore
read -p "This will DROP and recreate the database. Continue? (y/N) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Stop web and celery to avoid connection issues
echo "Stopping web and celery containers..."
docker compose stop web celery_worker celery_beat 2>/dev/null || true

# Drop and recreate database
echo "Dropping existing database..."
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "DROP DATABASE IF EXISTS $DB_NAME;"

echo "Creating fresh database..."
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "CREATE DATABASE $DB_NAME;"

# Restore backup
echo "Restoring backup (this may take a while)..."
if [[ "$BACKUP_FILE" == *.gz ]]; then
    gunzip -c "$BACKUP_FILE" | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME"
else
    docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" < "$BACKUP_FILE"
fi

# Restart services
echo "Restarting services..."
docker compose start web celery_worker celery_beat 2>/dev/null || true

echo ""
echo "Restore complete!"
echo ""
echo "You may need to run migrations if the backup is from a different version:"
echo "  docker compose exec web python manage.py migrate"
