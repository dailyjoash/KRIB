#!/bin/sh
set -e

python manage.py migrate --noinput

if [ "${DJANGO_COLLECTSTATIC:-1}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

if [ "${KRIB_LOAD_DEMO_DATA:-0}" = "1" ] && [ "${DJANGO_DEBUG:-0}" = "1" ]; then
  python manage.py seed_krib
elif [ "${KRIB_LOAD_DEMO_DATA:-0}" = "1" ]; then
  echo "Refusing to seed demo data because DJANGO_DEBUG=0. Set DJANGO_DEBUG=1 explicitly if this is a staging restore." >&2
fi

exec gunicorn krib_backend.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers "${DJANGO_GUNICORN_WORKERS:-3}" \
  --timeout "${DJANGO_GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile -
