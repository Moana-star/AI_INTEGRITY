"""Safely initialize an empty PostgreSQL deployment from the empty-first EIMS schema."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from database import database as local_schema
from scripts.migrate_sqlite_to_postgres import migrate


def main():
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        raise SystemExit("DATABASE_URL must point to PostgreSQL.")
    username = (os.environ.get("EIMS_BOOTSTRAP_ADMIN_USERNAME") or "").strip()
    password = os.environ.get("EIMS_BOOTSTRAP_ADMIN_PASSWORD") or ""
    if not username or len(password) < 16:
        raise SystemExit("Set EIMS_BOOTSTRAP_ADMIN_USERNAME and a unique EIMS_BOOTSTRAP_ADMIN_PASSWORD of at least 16 characters.")

    with psycopg.connect(database_url.replace("postgresql+psycopg://", "postgresql://", 1)) as connection:
        tables = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema=current_schema() AND table_type='BASE TABLE'"
        ).fetchall()
        existing = {row[0] for row in tables}

    if existing:
        if not {"users", "students", "examinations"}.issubset(existing):
            raise SystemExit("PostgreSQL schema is partially initialized. Refusing to modify it.")
        print("Existing EIMS PostgreSQL schema detected; no bootstrap changes were made.")
        return

    source = Path(tempfile.gettempdir()) / "eims-empty-first-bootstrap.sqlite3"
    source.unlink(missing_ok=True)
    local_schema.DB_PATH = str(source)
    try:
        local_schema.build_database(include_demo_data=False)
        migrate(source, database_url, apply=True, confirm_empty=True)
    finally:
        source.unlink(missing_ok=True)
    print("Empty-first EIMS PostgreSQL schema initialized with only the provisioned administrator.")


if __name__ == "__main__":
    main()
