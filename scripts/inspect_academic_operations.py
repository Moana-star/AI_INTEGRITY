#!/usr/bin/env python3
"""Read-only inspection of EIMS academic-operations SQLite records.

This script never creates, updates, or deletes database records. It prints
integrity status, table counts, and column names only; it does not print
student names, admission numbers, passwords, or other record contents.

Run from the repository root:
    python scripts/inspect_academic_operations.py

Use another SQLite file:
    python scripts/inspect_academic_operations.py --database path/to/file.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

TABLES = (
    "academic_units",
    "student_unit_enrolments",
    "venues",
    "examinations",
    "examination_sessions",
    "session_candidates",
    "session_invigilators",
    "invigilators",
)

def quote_identifier(identifier: str) -> str:
    """Quote a SQLite identifier selected from the fixed allowlist."""
    return '"' + identifier.replace('"', '""') + '"'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("database/exam_integrity.db"),
        help="SQLite database path (default: database/exam_integrity.db)",
    )
    args = parser.parse_args()
    database = args.database.expanduser().resolve()

    if not database.is_file():
        print(f"ERROR: Database file not found: {database}", file=sys.stderr)
        return 2

    # SQLite URI mode=ro guarantees that this inspection cannot write to the DB.
    connection_uri = database.as_uri() + "?mode=ro"

    try:
        with sqlite3.connect(connection_uri, uri=True) as connection:
            connection.execute("PRAGMA query_only = ON")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            print(f"Database: {database}")
            print(f"Integrity: {integrity}")

            existing_tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

            print("\nACADEMIC OPERATIONS RECORD COUNTS")
            for table in TABLES:
                if table not in existing_tables:
                    print(f"{table}: TABLE NOT PRESENT")
                    continue

                count = connection.execute(
                    f"SELECT COUNT(*) FROM {quote_identifier(table)}"
                ).fetchone()[0]
                print(f"{table}: {count}")

            print("\nTABLE SCHEMA (COLUMN NAMES ONLY)")
            for table in TABLES:
                if table not in existing_tables:
                    continue
                columns = connection.execute(
                    f"PRAGMA table_info({quote_identifier(table)})"
                ).fetchall()
                names = ", ".join(column[1] for column in columns)
                print(f"{table}: {names}")

            foreign_key_issues = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            print(f"\nForeign-key violations: {len(foreign_key_issues)}")
            if foreign_key_issues:
                print("WARNING: Review database foreign-key consistency.")
            if integrity != "ok":
                print("WARNING: Database integrity check did not return 'ok'.")

            return 0 if integrity == "ok" and not foreign_key_issues else 1

    except sqlite3.Error as error:
        print(f"ERROR: SQLite inspection failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
