#!/bin/sh
set -e

infer_role() {
  app_name="${DOKKU_APP_NAME:-${APP_NAME:-}}"

  case "$app_name" in
    *-worker) printf '%s\n' "worker"; return ;;
    *-beat) printf '%s\n' "beat"; return ;;
    *-api) printf '%s\n' "api"; return ;;
  esac

  if env | grep -Eq '^[A-Z0-9_]+_API_URL=' \
    && env | grep -Eq '^[A-Z0-9_]+_FRONTEND_URL=' \
    && env | grep -Eq '^[A-Z0-9_]+_BEAT_URL=' \
    && ! env | grep -Eq '^[A-Z0-9_]+_WORKER_URL='; then
    printf '%s\n' "worker"
    return
  fi

  if env | grep -Eq '^[A-Z0-9_]+_API_URL=' \
    && env | grep -Eq '^[A-Z0-9_]+_FRONTEND_URL=' \
    && env | grep -Eq '^[A-Z0-9_]+_WORKER_URL=' \
    && ! env | grep -Eq '^[A-Z0-9_]+_BEAT_URL='; then
    printf '%s\n' "beat"
    return
  fi

  printf '%s\n' "api"
}

ROLE="${SERVICE_ROLE:-$(infer_role)}"
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
    export DATABASE_NULL_POOL="${DATABASE_NULL_POOL:-true}"
    start_health_server
    exec celery -A app.tasks.celery_app.celery_app worker --loglevel=INFO
    ;;
  beat)
    export DATABASE_NULL_POOL="${DATABASE_NULL_POOL:-true}"
    start_health_server
    exec celery -A app.tasks.celery_app.celery_app beat --loglevel=INFO
    ;;
  *)
    exec "$@"
    ;;
esac
