#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Starting WorkXplorer Backend (Production)...${NC}"

# Load .env.production if it exists and variables aren't already set
if [ -f /app/.env.production ]; then
    echo -e "${YELLOW}📁 Loading environment from .env.production...${NC}"
    export $(grep -v '^#' /app/.env.production | xargs)
    echo -e "${GREEN}✅ Environment loaded${NC}"
fi

# Validate required environment variables
required_vars=(
    "SECRET_KEY"
    "JWT_SECRET_KEY"
    "DB_PASSWORD"
    "FIREBASE_PRIVATE_KEY"
    "DB_HOST"
    "DB_NAME"
    "DB_USER"
)

echo -e "${YELLOW}🔍 Checking required environment variables...${NC}"
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo -e "${RED}❌ Required environment variable $var is not set${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✅ All required environment variables are set${NC}"

# Function to wait for database
wait_for_db() {
    echo -e "${YELLOW}⏳ Waiting for PostgreSQL at $DB_HOST:$DB_PORT...${NC}"
    while ! nc -z $DB_HOST $DB_PORT; do
        echo -e "${BLUE}   Still waiting for PostgreSQL...${NC}"
        sleep 2
    done
    echo -e "${GREEN}✅ PostgreSQL is ready!${NC}"
}

# Only wait for DB if we're not in RQ worker/scheduler mode
if [[ "$@" != *"rqworker"* ]] && [[ "$@" != *"rqscheduler"* ]]; then
    # Wait for database
    wait_for_db

    # Test database connection with psycopg2
    echo -e "${YELLOW}🔌 Testing database connection...${NC}"
    python -c "
import psycopg2
import sys
import os

try:
    conn = psycopg2.connect(
        host=os.environ['DB_HOST'],
        port=os.environ['DB_PORT'],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )
    cursor = conn.cursor()
    cursor.execute('SELECT 1')
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    print('✅ Database connection successful')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    sys.exit(1)
"

    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Database connection test failed${NC}"
        exit 1
    fi

    echo -e "${YELLOW}🔄 Running database migrations...${NC}"
    python manage.py migrate --noinput

    echo -e "${YELLOW}📊 Collecting static files...${NC}"
    python manage.py collectstatic --noinput

    # Compile translation messages (ponytail: .mo files already built in Dockerfile, non-fatal)
    echo -e "${YELLOW}🌐 Compiling translation messages...${NC}"
    python manage.py compilemessages --ignore=venv 2>/dev/null || true

    # Create superuser if it doesn't exist
    echo -e "${YELLOW}👤 Creating superuser if needed...${NC}"
    python manage.py shell << PYEOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser(
        email='admin@workxplorer.backend',
        password='${ADMIN_PASSWORD:-admin123}'
    )
    print("✅ Superuser created: admin@workxplorer.backend")
else:
    print("ℹ️ Superuser already exists")
PYEOF
fi

# Create logs directory (without chmod)
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

echo -e "${GREEN}🎉 WorkXplorer Backend (Production) is ready!${NC}"
if [[ "$@" != *"rqworker"* ]] && [[ "$@" != *"rqscheduler"* ]]; then
    echo -e "${GREEN}🌐 Backend running on port 8001${NC}"
fi

# Execute the main command
exec "$@"