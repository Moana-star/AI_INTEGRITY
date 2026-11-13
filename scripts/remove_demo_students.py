#!/usr/bin/env python3
"""Safely remove the three known demonstration students from a local SQLite DB.

Dry-run is the default. --apply requires an existing administrator user ID.
A timestamped SQLite backup is created before any write. Only the exact
admission numbers below are targeted. Profile and unit-enrolment rows may be
removed with their demo student; any other FK dependency blocks the entire
cleanup for manual review. Existing audit history is retained.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "database" / "exam_integrity.db"
TARGETS = ("DEMO-CRITICAL", "DEMO-HIGH", "DEMO-WATCH")
SAFE_CHILD_TABLES = {"student_profiles", "student_unit_enrolments"}


def quote_identifier(value: str) -> str:
    if not value.replace("_", "").isalnum():
        raise ValueError(f"Unsafe SQL identifier discovered in schema: {value!r}")
    return '"' + value.replace('"', '""') + '"'


def open_readonly(database: Path):
    uri = database.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def find_targets(connection):
    return connection.execute(
        "SELECT id, student_number FROM students WHERE student_number IN (?, ?, ?) ORDER BY student_number",
        TARGETS,
    ).fetchall()


def find_references(connection, student_ids):
    tables = {
        row["name"] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    references = []
    for table in sorted(tables - {"students"}):
        for fk in connection.execute(f"PRAGMA foreign_key_list({quote_identifier(table)})"):
            if fk["table"] != "students":
                continue
            source_column = fk["from"]
            target_column = fk["to"] or "id"
            for student_id in student_ids:
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {quote_identifier(table)} "
                    f"WHERE {quote_identifier(source_column)}=?",
                    (student_id,),
                ).fetchone()[0]
                if count:
                    references.append({
                        "table": table,
                        "column": source_column,
                        "student_id": student_id,
                        "count": count,
                        "safe": table in SAFE_CHILD_TABLES and target_column == "id",
                    })
    return references


def validate_actor(connection, actor_user_id):
    if not actor_user_id:
        raise ValueError("--actor-user-id is required with --apply.")
    actor = connection.execute(
        "SELECT id, role FROM users WHERE id=?", (actor_user_id,)
    ).fetchone()
    if not actor or actor["role"] != "admin":
        raise ValueError("The supplied actor must be an existing administrator account.")


def backup_database(database: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = database.with_name(f"{database.stem}.pre_demo_cleanup_{stamp}{database.suffix}.bak")
    source = sqlite3.connect(str(database))
    destination = sqlite3.connect(str(backup))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return backup


def inspect(connection):
    tables = {
        row["name"] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "students" not in tables:
        raise ValueError("The selected database does not contain a students table.")
    targets = find_targets(connection)
    references = find_references(connection, [row["id"] for row in targets])
    blockers = [ref for ref in references if not ref["safe"]]
    return targets, references, blockers


def run(args) -> int:
    database = Path(args.database).expanduser().resolve()
    if not database.is_file():
        print(f"ERROR: SQLite database not found: {database}", file=sys.stderr)
        return 2

    try:
        with open_readonly(database) as connection:
            targets, references, blockers = inspect(connection)
            if args.apply:
                validate_actor(connection, args.actor_user_id)

        print(f"Database: {database}")
        print("Target admission numbers: " + ", ".join(TARGETS))
        print(f"Matching student records: {len(targets)}")
        for row in targets:
            print(f"  FOUND {row['student_number']} (internal ID {row['id']})")
        for ref in references:
            label = "SAFE RELATED ROW" if ref["safe"] else "BLOCKING REFERENCE"
            print(f"  {label}: {ref['table']}.{ref['column']} -> student ID "
                  f"{ref['student_id']}: {ref['count']} row(s)")

        if blockers:
            print("CLEANUP BLOCKED: linked operational/history records require manual review.")
            print("No records were changed.")
            return 1
        if not targets:
            print("No matching demonstration student records exist. Nothing to do.")
            return 0
        if not args.apply:
            print("DRY RUN ONLY: no database changes were made.")
            print("Review the references above. To apply, provide --apply --actor-user-id <admin-id>.")
            return 0

        backup = backup_database(database)
        print(f"Backup created: {backup}")
        connection = sqlite3.connect(str(database))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            connection.execute("BEGIN IMMEDIATE")
            targets, references, blockers = inspect(connection)
            if blockers:
                raise ValueError("Database references changed after preflight; cleanup stopped.")
            for row in targets:
                student_id = row["id"]
                for table in sorted(SAFE_CHILD_TABLES):
                    if table in {
                        item["name"] for item in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )
                    }:
                        fk_rows = [
                            fk for fk in connection.execute(
                                f"PRAGMA foreign_key_list({quote_identifier(table)})"
                            ) if fk["table"] == "students" and (fk["to"] or "id") == "id"
                        ]
                        for fk in fk_rows:
                            connection.execute(
                                f"DELETE FROM {quote_identifier(table)} "
                                f"WHERE {quote_identifier(fk['from'])}=?",
                                (student_id,),
                            )
                connection.execute("DELETE FROM students WHERE id=?", (student_id,))
                connection.execute("""
                    INSERT INTO audit_events
                        (actor_user_id, action, entity_type, entity_id, summary)
                    VALUES (?, 'delete', 'student', ?, ?)
                """, (
                    args.actor_user_id,
                    row["student_number"],
                    "Removed an explicitly identified demonstration student after dependency review.",
                ))
            remaining = find_targets(connection)
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if remaining or violations:
                raise ValueError("Post-cleanup verification failed; transaction rolled back.")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        print(f"CLEANUP COMPLETE: removed {len(targets)} demonstration student record(s).")
        print("Existing non-demo students and existing audit history were preserved.")
        return 0
    except (sqlite3.Error, ValueError) as error:
        print(f"CLEANUP ABORTED: {error}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(DEFAULT_DATABASE),
                        help="SQLite database path (default: database/exam_integrity.db)")
    parser.add_argument("--apply", action="store_true",
                        help="Commit cleanup after backup and dependency checks; default is dry-run.")
    parser.add_argument("--actor-user-id", type=int,
                        help="Existing administrator user ID required with --apply.")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
