#!/usr/bin/env python3
"""One-way, fail-closed SQLite to PostgreSQL migration utility.

This copies a fully initialized EIMS SQLite database into an EMPTY PostgreSQL
database. It does not switch the Flask application to PostgreSQL. Production
startup must remain blocked until the runtime DB adapter and integration tests
are migrated separately.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine


IMMUTABLE_HISTORY_TABLES = {
    "student_exam_accommodation_history",
    "annual_progression_reviews",
    "eligibility_evidence_history",
    "eligibility_decisions",
    "incident_appeal_events",
    "senate_review_events",
    "biometric_verification_events",
    "academic_history_events",
}
EXPECTED_TRIGGER_TABLES = IMMUTABLE_HISTORY_TABLES


def validate_source(source_path: Path):
    if not source_path.is_file():
        raise RuntimeError(f"SQLite source database does not exist: {source_path}")
    connection = sqlite3.connect(f"file:{source_path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {integrity}")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                f"SQLite foreign_key_check found {len(violations)} violation(s); repair before migration."
            )
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        required = {"users", "students", "examinations"}
        missing = required - tables
        if missing:
            raise RuntimeError(f"Source database is missing required tables: {sorted(missing)}")
        triggers = connection.execute(
            "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger' ORDER BY name"
        ).fetchall()
        unknown = [
            (name, table) for name, table, sql in triggers
            if table not in EXPECTED_TRIGGER_TABLES
            or not sql
            or "BEFORE UPDATE" not in sql.upper()
            and "BEFORE DELETE" not in sql.upper()
            or "RAISE(ABORT" not in sql.upper()
        ]
        if unknown:
            raise RuntimeError(
                "Unrecognized SQLite triggers need an explicit PostgreSQL equivalent before migration: "
                + repr(unknown)
            )
        return sorted(tables), triggers
    finally:
        connection.close()


def table_counts(engine: Engine, table_names: list[str]) -> dict[str, int]:
    metadata = MetaData()
    metadata.reflect(bind=engine, only=table_names)
    counts = {}
    with engine.connect() as connection:
        for table in metadata.sorted_tables:
            counts[table.name] = connection.execute(
                select(func.count()).select_from(table)
            ).scalar_one()
    return counts


def assert_empty_postgres(engine: Engine):
    inspector = inspect(engine)
    existing = set(inspector.get_table_names(schema="public"))
    if existing:
        raise RuntimeError(
            "Target PostgreSQL public schema is not empty. Refusing to merge or overwrite data. "
            f"Existing tables: {sorted(existing)}"
        )


def install_immutable_history_guards(connection, table_names: set[str]):
    present = sorted(IMMUTABLE_HISTORY_TABLES & table_names)
    if not present:
        return
    connection.execute(text("""
        CREATE OR REPLACE FUNCTION eims_reject_immutable_history_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $eims$
        BEGIN
            RAISE EXCEPTION '% is append-only; UPDATE and DELETE are prohibited',
                TG_TABLE_NAME USING ERRCODE = '55000';
        END;
        $eims$
    """))
    preparer = connection.dialect.identifier_preparer
    for table_name in present:
        quoted = preparer.quote(table_name)
        trigger_name = preparer.quote(f"eims_{table_name[:32]}_immutable")
        connection.execute(text(
            f"CREATE TRIGGER {trigger_name} BEFORE UPDATE OR DELETE ON public.{quoted} "
            "FOR EACH ROW EXECUTE FUNCTION eims_reject_immutable_history_mutation()"
        ))


def reset_identity_sequences(connection, metadata: MetaData):
    preparer = connection.dialect.identifier_preparer
    for table in metadata.sorted_tables:
        identity_column = getattr(table, "autoincrement_column", None)
        if identity_column is None:
            continue
        table_name = preparer.quote(table.name)
        column_name = preparer.quote(identity_column.name)
        qualified_name = f"public.{table_name}"
        sequence = connection.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": qualified_name, "column_name": identity_column.name},
        ).scalar_one_or_none()
        if not sequence:
            continue
        maximum = connection.execute(
            text(f"SELECT MAX({column_name}) FROM public.{table_name}")
        ).scalar_one_or_none()
        if maximum is not None:
            connection.execute(
                text("SELECT setval(CAST(:sequence AS regclass), :value, true)"),
                {"sequence": sequence, "value": maximum},
            )


def migrate(source_path: Path, database_url: str, apply: bool, confirm_empty: bool):
    source_tables, source_triggers = validate_source(source_path)
    source_engine = create_engine(f"sqlite:///{source_path.resolve().as_posix()}")
    target_engine = create_engine(database_url, pool_pre_ping=True)

    try:
        source_metadata = MetaData()
        source_metadata.reflect(bind=source_engine, only=source_tables)
        counts = table_counts(source_engine, source_tables)
        print(f"Source tables: {len(source_tables)}")
        print(f"Source rows: {sum(counts.values())}")
        for name, count in counts.items():
            print(f"  {name}: {count}")
        print(f"Append-only SQLite triggers to recreate: {len(source_triggers)}")

        if target_engine.dialect.name != "postgresql":
            raise RuntimeError("Destination must be PostgreSQL; no other target dialect is accepted.")
        assert_empty_postgres(target_engine)

        if not apply:
            print("DRY RUN ONLY. No PostgreSQL tables or records were changed.")
            print("Review this inventory, then rerun with --apply --confirm-empty-target.")
            return
        if not confirm_empty:
            raise RuntimeError("--apply also requires --confirm-empty-target as an explicit safety gate.")

        with target_engine.begin() as target:
            source_metadata.create_all(target, checkfirst=False)
            with source_engine.connect() as source:
                for table in source_metadata.sorted_tables:
                    result = source.execute(select(table))
                    while True:
                        batch = result.fetchmany(500)
                        if not batch:
                            break
                        target.execute(table.insert(), [dict(row._mapping) for row in batch])
            install_immutable_history_guards(target, set(source_tables))
            reset_identity_sequences(target, source_metadata)

        target_counts = table_counts(target_engine, source_tables)
        mismatches = {
            name: (counts[name], target_counts.get(name))
            for name in counts
            if counts[name] != target_counts.get(name)
        }
        if mismatches:
            raise RuntimeError(f"Post-migration row-count verification failed: {mismatches}")
        print("Migration copy completed and row counts match.")
        print("Run application-level PostgreSQL integration tests before any cutover.")
    finally:
        source_engine.dispose()
        target_engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=os.environ.get(
        "EIMS_SQLITE_SOURCE", "database/exam_integrity.db"
    ))
    parser.add_argument("--apply", action="store_true", help="perform the copy; default is dry-run")
    parser.add_argument(
        "--confirm-empty-target", action="store_true",
        help="confirm the PostgreSQL public schema is intentionally empty",
    )
    args = parser.parse_args()
    database_url = os.environ.get("EIMS_POSTGRES_URL")
    if not database_url:
        parser.error("Set EIMS_POSTGRES_URL in the environment; credentials are never accepted as CLI arguments.")
    try:
        migrate(Path(args.source), database_url, args.apply, args.confirm_empty_target)
    except Exception as exc:
        print(f"MIGRATION STOPPED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
