#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."
while ! pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER; do
  sleep 1
done
echo "PostgreSQL is ready!"

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "Creating superuser if needed..."
python manage.py shell << END
from django.contrib.auth import get_user_model
import os
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    admin_password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', None)
    if admin_password:
        User.objects.create_superuser('admin', 'admin@example.com', admin_password)
        print('Superuser created: username=admin')
    else:
        print('WARNING: DJANGO_SUPERUSER_PASSWORD not set - skipping superuser creation')
else:
    print('Superuser already exists')
END

echo "Starting server..."
exec "$@"
