#!/bin/sh
set -eu
python scripts/bootstrap_postgres.py
exec gunicorn --bind 0.0.0.0:8000 --workers "\${GUNICORN_WORKERS:-2}" --timeout "\${GUNICORN_TIMEOUT:-60}" --access-logfile - --error-logfile - app:app
