#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting WorkXplorer Backend (Development)...${NC}"

# Wait for database
wait_for_db() {
    echo -e "${YELLOW}⏳ Waiting for PostgreSQL at $DB_HOST:$DB_PORT...${NC}"
    while ! nc -z $DB_HOST $DB_PORT 2>/dev/null; do
        echo -e "${BLUE}   Still waiting for PostgreSQL...${NC}"
        sleep 2
    done
    echo -e "${GREEN}✅ PostgreSQL is ready!${NC}"
}

# Only wait for DB if we're not in RQ worker/scheduler mode
if [[ "$@" != *"rqworker"* ]] && [[ "$@" != *"rqscheduler"* ]]; then
    wait_for_db
fi

# Create logs directory
echo -e "${YELLOW}📁 Setting up logs directory...${NC}"
mkdir -p /app/logs

# Setup scheduled tasks (only for rq-scheduler)
if [[ "$@" == *"rqscheduler"* ]]; then
    echo -e "${YELLOW}⏰ Setting up scheduled tasks...${NC}"
    
    # Wait a bit for Redis to be fully ready
    sleep 2
    
    # Setup vacancy expiration scheduler
    python manage.py setup_vacancy_scheduler
    
    echo -e "${GREEN}✅ Scheduled tasks configured!${NC}"
fi

echo -e "${GREEN}🎉 Ready to start!${NC}"

# Execute the main command
exec "$@"