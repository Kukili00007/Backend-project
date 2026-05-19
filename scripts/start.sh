#!/bin/sh
set -e

ROLE="${SERVICE_ROLE:-api}"
APP_PORT="${PORT:-8000}"

start_health_server() {
  python -m http.server "$APP_PORT" >/tmp/leanstock-health.log 2>&1 &
}

case "$ROLE" in
  api)
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port "$APP_PORT"
    ;;
  worker)
    start_health_server
    exec celery -A app.tasks.celery_app.celery_app worker --loglevel=INFO
    ;;
  beat)
    start_health_server
    exec celery -A app.tasks.celery_app.celery_app beat --loglevel=INFO
    ;;
  *)
    exec "$@"
    ;;
esac
