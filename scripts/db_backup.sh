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

# Default values
DAYS=""
SESSION_ID=""
OUTPUT_FILE=""

usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Create a backup of the Ridgway Garage database.

OPTIONS:
    -d, --days N        Only backup data from the last N days
    -s, --session ID    Only backup a specific session (and its laps/telemetry)
    -o, --output FILE   Custom output filename (default: ridgway_backup_TIMESTAMP.sql.gz)
    -h, --help          Show this help message

EXAMPLES:
    $(basename "$0")                    # Full database backup
    $(basename "$0") --days 30          # Last 30 days only
    $(basename "$0") --session 1209     # Specific session only
    $(basename "$0") -d 7 -o weekly.sql.gz

ENVIRONMENT:
    BACKUP_DIR          Directory for backup files (default: current directory)

EOF
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--days)
            DAYS="$2"
            shift 2
            ;;
        -s|--session)
            SESSION_ID="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Set output filename
if [ -z "$OUTPUT_FILE" ]; then
    if [ -n "$DAYS" ]; then
        OUTPUT_FILE="ridgway_backup_${DAYS}days_${TIMESTAMP}.sql.gz"
    elif [ -n "$SESSION_ID" ]; then
        OUTPUT_FILE="ridgway_backup_session${SESSION_ID}_${TIMESTAMP}.sql.gz"
    else
        OUTPUT_FILE="ridgway_backup_${TIMESTAMP}.sql.gz"
    fi
fi

echo "=== Ridgway Garage Database Backup ==="
echo "Container: $CONTAINER_NAME"
echo "Database: $DB_NAME"
echo "Output: $BACKUP_DIR/$OUTPUT_FILE"

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Error: Container '$CONTAINER_NAME' is not running"
    echo "Start it with: docker compose up -d db"
    exit 1
fi

# Build the backup command based on options
if [ -n "$DAYS" ] || [ -n "$SESSION_ID" ]; then
    echo ""
    echo "Creating filtered backup using Django..."

    # Use Django's dumpdata for filtered exports
    FILTER_ARGS=""
    if [ -n "$DAYS" ]; then
        echo "Filter: Last $DAYS days"
        FILTER_ARGS="--days $DAYS"
    elif [ -n "$SESSION_ID" ]; then
        echo "Filter: Session ID $SESSION_ID"
        FILTER_ARGS="--session $SESSION_ID"
    fi

    # Run Django management command for filtered export
    docker compose exec -T web python manage.py export_data $FILTER_ARGS | gzip > "$BACKUP_DIR/$OUTPUT_FILE"
else
    echo ""
    echo "Creating full database backup..."
    docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/$OUTPUT_FILE"
fi

# Show result
if [ -f "$BACKUP_DIR/$OUTPUT_FILE" ]; then
    FILESIZE=$(ls -lh "$BACKUP_DIR/$OUTPUT_FILE" | awk '{print $5}')
    echo ""
    echo "Backup complete: $OUTPUT_FILE ($FILESIZE)"
    echo ""
    echo "To restore on another machine:"
    echo "  ./scripts/db_restore.sh $OUTPUT_FILE"
else
    echo "Error: Backup file was not created"
    exit 1
fi
