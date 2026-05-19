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

INFERRED_ROLE="$(infer_role)"
if [ -n "${SERVICE_ROLE:-}" ] && [ "$SERVICE_ROLE" != "api" ]; then
  ROLE="$SERVICE_ROLE"
else
  ROLE="$INFERRED_ROLE"
fi
APP_PORT="${PORT:-8000}"

printf 'LeanStock start role: %s (SERVICE_ROLE=%s, inferred=%s)\n' "$ROLE" "${SERVICE_ROLE:-}" "$INFERRED_ROLE"

start_health_server() {
  python - <<'PY' >/tmp/leanstock-health.log 2>&1 &
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health"):
            self.send_response(404)
            self.end_headers()
            return
        payload = {
            "status": "ok",
            "role": os.environ.get("SERVICE_ROLE") or os.environ.get("ROLE") or "unknown",
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


HTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8000"))), HealthHandler).serve_forever()
PY
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
