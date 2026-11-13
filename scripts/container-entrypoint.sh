#!/bin/sh
set -eu
python scripts/bootstrap_postgres.py
unset EIMS_BOOTSTRAP_ADMIN_USERNAME EIMS_BOOTSTRAP_ADMIN_PASSWORD
exec gunicorn --bind 0.0.0.0:8000 --workers "\${GUNICORN_WORKERS:-2}" --timeout "\${GUNICORN_TIMEOUT:-60}" --access-logfile - --error-logfile - app:app
