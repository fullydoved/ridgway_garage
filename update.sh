#!/bin/bash
# Ridgway Garage Auto-Update Script
# This script handles the complete update process with backup and rollback capability

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="/home/mike/Code/ridgway_garage"
BACKUP_DIR="$PROJECT_DIR/backups"
LOG_FILE="$PROJECT_DIR/update.log"
STATUS_FILE="$PROJECT_DIR/update_status.json"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✓${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ✗${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠${NC} $1" | tee -a "$LOG_FILE"
}

# Update status in JSON file for WebSocket consumption
update_status() {
    local status=$1
    local message=$2
    local progress=$3
    cat > "$STATUS_FILE" <<EOF
{
  "status": "$status",
  "message": "$message",
  "progress": $progress,
  "timestamp": "$(date -Iseconds)"
}
EOF
}

# Cleanup function
cleanup() {
    if [ $? -ne 0 ]; then
        log_error "Update failed! Check $LOG_FILE for details"
        update_status "error" "Update failed" 0
    fi
}

trap cleanup EXIT

# Main update process
main() {
    log "=========================================="
    log "Starting Ridgway Garage Update Process"
    log "=========================================="

    update_status "running" "Initializing update process" 5

    cd "$PROJECT_DIR" || exit 1

    # Create backup directory if it doesn't exist
    mkdir -p "$BACKUP_DIR"

    # Step 1: Get current git commit for rollback
    log "Step 1: Recording current state..."
    CURRENT_COMMIT=$(git rev-parse HEAD)
    CURRENT_VERSION=$(cat VERSION 2>/dev/null || echo "unknown")
    log "Current commit: $CURRENT_COMMIT"
    log "Current version: $CURRENT_VERSION"
    update_status "running" "Recording current state" 10

    # Step 2: Backup database
    log "Step 2: Backing up database..."
    BACKUP_FILE="$BACKUP_DIR/db_backup_$TIMESTAMP.sql"

    if docker compose exec -T db pg_dump -U postgres ridgway_garage > "$BACKUP_FILE" 2>&1; then
        log_success "Database backed up to $BACKUP_FILE"
        # Compress backup
        gzip "$BACKUP_FILE"
        log_success "Backup compressed: ${BACKUP_FILE}.gz"
    else
        log_error "Database backup failed"
        exit 1
    fi
    update_status "running" "Database backed up successfully" 25

    # Step 3: Pull latest code
    log "Step 3: Pulling latest code from repository..."
    if git pull origin main; then
        NEW_COMMIT=$(git rev-parse HEAD)
        NEW_VERSION=$(cat VERSION 2>/dev/null || echo "unknown")
        log_success "Code updated successfully"
        log "New commit: $NEW_COMMIT"
        log "New version: $NEW_VERSION"

        if [ "$CURRENT_COMMIT" = "$NEW_COMMIT" ]; then
            log_warning "No new changes found. Already up to date!"
            update_status "success" "Already up to date" 100
            exit 0
        fi
    else
        log_error "Git pull failed"
        exit 1
    fi
    update_status "running" "Code updated from repository" 40

    # Step 4: Build new images
    log "Step 4: Building new Docker images..."
    if docker compose build --no-cache; then
        log_success "Docker images built successfully"
    else
        log_error "Docker build failed, rolling back..."
        git reset --hard "$CURRENT_COMMIT"
        echo "$CURRENT_VERSION" > VERSION
        exit 1
    fi
    update_status "running" "Docker images built" 60

    # Step 5: Stop containers gracefully
    log "Step 5: Stopping containers..."
    docker compose down
    log_success "Containers stopped"
    update_status "running" "Containers stopped" 70

    # Step 6: Start containers
    log "Step 6: Starting updated containers..."
    if docker compose up -d; then
        log_success "Containers started"
    else
        log_error "Failed to start containers, attempting rollback..."
        git reset --hard "$CURRENT_COMMIT"
        echo "$CURRENT_VERSION" > VERSION
        docker compose build
        docker compose up -d
        exit 1
    fi
    update_status "running" "Containers started" 80

    # Step 7: Wait for services to be healthy
    log "Step 7: Waiting for services to be healthy..."
    sleep 10

    # Check if web service is responding
    MAX_RETRIES=30
    RETRY_COUNT=0
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if docker compose exec -T web python manage.py check --deploy 2>&1 | grep -q "System check identified no issues"; then
            log_success "Application health check passed"
            break
        fi
        RETRY_COUNT=$((RETRY_COUNT + 1))
        log "Waiting for application to be ready... ($RETRY_COUNT/$MAX_RETRIES)"
        sleep 2
    done

    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        log_error "Application failed to start properly, rolling back..."
        docker compose down
        git reset --hard "$CURRENT_COMMIT"
        echo "$CURRENT_VERSION" > VERSION
        docker compose build
        docker compose up -d
        exit 1
    fi
    update_status "running" "Health check passed" 90

    # Step 8: Cleanup old backups (keep last 10)
    log "Step 8: Cleaning up old backups..."
    cd "$BACKUP_DIR"
    ls -t db_backup_*.sql.gz 2>/dev/null | tail -n +11 | xargs -r rm
    log_success "Old backups cleaned up (kept last 10)"
    update_status "running" "Cleanup completed" 95

    # Success!
    log_success "=========================================="
    log_success "Update completed successfully!"
    log_success "Old version: $CURRENT_VERSION"
    log_success "New version: $NEW_VERSION"
    log_success "=========================================="
    update_status "success" "Update completed successfully" 100
}

# Run main function
main "$@"
