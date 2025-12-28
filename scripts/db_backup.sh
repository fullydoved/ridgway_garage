#!/bin/bash
# Database backup script for Ridgway Garage
# Creates a gzipped PostgreSQL dump from the Docker container

set -e

# Configuration
CONTAINER_NAME="ridgway_garage_db"
DB_NAME="ridgway_garage"
DB_USER="postgres"
BACKUP_DIR="${BACKUP_DIR:-$(pwd)}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="ridgway_backup_${TIMESTAMP}.sql.gz"

echo "=== Ridgway Garage Database Backup ==="
echo "Container: $CONTAINER_NAME"
echo "Database: $DB_NAME"
echo "Output: $BACKUP_DIR/$BACKUP_FILE"
echo ""

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Error: Container '$CONTAINER_NAME' is not running"
    echo "Start it with: docker compose up -d db"
    exit 1
fi

# Create backup
echo "Creating backup..."
docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/$BACKUP_FILE"

# Show result
FILESIZE=$(ls -lh "$BACKUP_DIR/$BACKUP_FILE" | awk '{print $5}')
echo ""
echo "Backup complete: $BACKUP_FILE ($FILESIZE)"
echo ""
echo "To restore on another machine:"
echo "  ./scripts/db_restore.sh $BACKUP_FILE"
