#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON_BIN="$ROOT_DIR/.venv/Scripts/python.exe"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Python virtualenv not found under $ROOT_DIR/.venv" >&2
  exit 1
fi

echo "==> Backend tests"
cd "$ROOT_DIR/backend"
"$PYTHON_BIN" manage.py test

echo "==> Django deploy checks"
DJANGO_DEBUG=0 \
DJANGO_SECRET_KEY=12345678901234567890123456789012345678901234567890 \
DJANGO_ALLOWED_HOSTS=example.com \
DJANGO_CORS_ALLOWED_ORIGINS=https://app.example.com \
DJANGO_CSRF_TRUSTED_ORIGINS=https://app.example.com \
DJANGO_SECURE_SSL_REDIRECT=1 \
"$PYTHON_BIN" manage.py check --deploy

echo "==> Static asset collection"
DJANGO_DEBUG=0 \
DJANGO_SECRET_KEY=12345678901234567890123456789012345678901234567890 \
DJANGO_ALLOWED_HOSTS=example.com \
DJANGO_CORS_ALLOWED_ORIGINS=https://app.example.com \
DJANGO_CSRF_TRUSTED_ORIGINS=https://app.example.com \
DJANGO_SECURE_SSL_REDIRECT=1 \
"$PYTHON_BIN" manage.py collectstatic --noinput

echo "==> Frontend build"
cd "$ROOT_DIR/frontend"
npm run build

if command -v docker >/dev/null 2>&1; then
  echo "==> Docker Compose prod config"
  cd "$ROOT_DIR"
  docker compose -f docker-compose.prod.yml config >/dev/null
else
  echo "Skipping Docker validation because docker is not installed in this environment."
fi

echo "Release check passed."
