#!/bin/bash
# Database restore script for Ridgway Garage
# Restores a PostgreSQL dump to the Docker container

set -e

# Configuration
CONTAINER_NAME="ridgway_garage_db"
DB_NAME="ridgway_garage"
DB_USER="postgres"

# Default values
FORCE=false
MERGE=false

usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS] <backup_file>

Restore a Ridgway Garage database backup.

ARGUMENTS:
    backup_file         The backup file to restore (.sql or .sql.gz)

OPTIONS:
    -f, --force         Skip confirmation prompt
    -m, --merge         Merge data instead of replacing (for filtered backups)
    -h, --help          Show this help message

EXAMPLES:
    $(basename "$0") ridgway_backup_20250128_120000.sql.gz
    $(basename "$0") --force backup.sql.gz          # No confirmation
    $(basename "$0") --merge session_backup.sql.gz  # Merge filtered data

NOTES:
    - Without --merge, the database will be dropped and recreated
    - With --merge, data is imported into existing database (for filtered backups)
    - Web and Celery containers are stopped during restore

EOF
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--force)
            FORCE=true
            shift
            ;;
        -m|--merge)
            MERGE=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        -*)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
        *)
            BACKUP_FILE="$1"
            shift
            ;;
    esac
done

# Check arguments
if [ -z "$BACKUP_FILE" ]; then
    echo "Error: No backup file specified"
    echo ""
    usage
fi

# Check if file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file '$BACKUP_FILE' not found"
    exit 1
fi

echo "=== Ridgway Garage Database Restore ==="
echo "Container: $CONTAINER_NAME"
echo "Database: $DB_NAME"
echo "Backup: $BACKUP_FILE"
if [ "$MERGE" = true ]; then
    echo "Mode: MERGE (importing into existing database)"
else
    echo "Mode: REPLACE (drop and recreate database)"
fi
echo ""

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Error: Container '$CONTAINER_NAME' is not running"
    echo "Start it with: docker compose up -d db"
    exit 1
fi

# Confirm restore
if [ "$FORCE" = false ]; then
    if [ "$MERGE" = true ]; then
        read -p "This will MERGE data into the existing database. Continue? (y/N) " -n 1 -r
    else
        read -p "This will DROP and RECREATE the database. Continue? (y/N) " -n 1 -r
    fi
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# Stop web and celery to avoid connection issues
echo "Stopping web and celery containers..."
docker compose stop web celery_worker celery_beat 2>/dev/null || true

if [ "$MERGE" = false ]; then
    # Drop and recreate database
    echo "Dropping existing database..."
    docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "DROP DATABASE IF EXISTS $DB_NAME;"

    echo "Creating fresh database..."
    docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "CREATE DATABASE $DB_NAME;"
fi

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
