#!/usr/bin/env python3
"""Validate and import institution-supplied academic operations CSV files.

Dry-run is the default. No records are written unless --apply is supplied.
The script never creates sample/demo records and never updates or deletes rows.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from modules.database import get_connection, is_postgres

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "database" / "exam_integrity.db"

SPECS = {
    "units": {
        "headers": {"unit_code", "unit_name", "department", "faculty"},
        "path_arg": "units_csv",
    },
    "venues": {
        "headers": {"venue_code", "building", "room_name", "capacity"},
        "path_arg": "venues_csv",
    },
    "enrolments": {
        "headers": {"admission_number", "unit_code", "academic_year", "semester"},
        "path_arg": "enrolments_csv",
    },
}


def read_csv(path: str | None, required: set[str], label: str) -> list[dict[str, str]]:
    if not path:
        return []
    source = Path(path).expanduser()
    if not source.is_file():
        raise ValueError(f"{label}: file not found: {source}")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        raw_headers = reader.fieldnames or []
        headers = [h.strip() if h else h for h in raw_headers]
        if len(headers) != len(set(headers)):
            raise ValueError(f"{label}: duplicate column names are not allowed.")
        missing = required - {h for h in headers if h}
        if missing:
            raise ValueError(f"{label}: missing columns: {', '.join(sorted(missing))}")
        reader.fieldnames = headers
        rows = []
        for line, row in enumerate(reader, start=2):
            cleaned = {str(k).strip(): (v or "").strip() for k, v in row.items() if k}
            if not any(cleaned.values()):
                continue
            cleaned["_line"] = str(line)
            rows.append(cleaned)
    return rows


def normalize_inputs(args):
    units = read_csv(args.units_csv, SPECS["units"]["headers"], "Units")
    venues = read_csv(args.venues_csv, SPECS["venues"]["headers"], "Venues")
    enrolments = read_csv(args.enrolments_csv, SPECS["enrolments"]["headers"], "Enrolments")

    seen_units = set()
    for row in units:
        code = row["unit_code"].upper()
        name = row["unit_name"]
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9./_-]{1,24}", code):
            raise ValueError(f"Units row {row['_line']}: invalid unit_code '{code}'.")
        if not name or len(name) > 160:
            raise ValueError(f"Units row {row['_line']}: unit_name is required (max 160 characters).")
        if code in seen_units:
            raise ValueError(f"Units row {row['_line']}: duplicate unit_code '{code}' in the file.")
        seen_units.add(code)
        row["unit_code"] = code
        row["department"] = row["department"][:160] or None
        row["faculty"] = row["faculty"][:160] or None

    seen_venues = set()
    for row in venues:
        code = row["venue_code"].upper()
        room = row["room_name"]
        try:
            capacity = int(row["capacity"])
        except ValueError:
            capacity = 0
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9./_-]{0,29}", code):
            raise ValueError(f"Venues row {row['_line']}: invalid venue_code '{code}'.")
        if not room or len(room) > 100 or len(row["building"]) > 100:
            raise ValueError(f"Venues row {row['_line']}: room_name is required; building/room max 100 characters.")
        if not 1 <= capacity <= 10000:
            raise ValueError(f"Venues row {row['_line']}: capacity must be between 1 and 10,000.")
        if code in seen_venues:
            raise ValueError(f"Venues row {row['_line']}: duplicate venue_code '{code}' in the file.")
        seen_venues.add(code)
        row["venue_code"] = code
        row["capacity"] = capacity
        row["building"] = row["building"][:100] or None

    seen_enrolments = set()
    for row in enrolments:
        admission = row["admission_number"]
        unit_code = row["unit_code"].upper()
        year = row["academic_year"]
        semester = row["semester"]
        if not admission or len(admission) > 60:
            raise ValueError(f"Enrolments row {row['_line']}: admission_number is required (max 60 characters).")
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9./_-]{1,24}", unit_code):
            raise ValueError(f"Enrolments row {row['_line']}: invalid unit_code '{unit_code}'.")
        if not year or len(year) > 20 or not semester or len(semester) > 40:
            raise ValueError(f"Enrolments row {row['_line']}: academic_year and semester are required.")
        key = (admission, unit_code, year, semester)
        if key in seen_enrolments:
            raise ValueError(f"Enrolments row {row['_line']}: duplicate enrolment in the file.")
        seen_enrolments.add(key)
        row["unit_code"] = unit_code
    if not (units or venues or enrolments):
        raise ValueError("Supply at least one CSV file.")
    return units, venues, enrolments


def available_tables(connection) -> set[str]:
    if is_postgres():
        rows = connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema()"
        ).fetchall()
        return {row["table_name"] for row in rows}
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {row["name"] for row in rows}


def run(args) -> int:
    units, venues, enrolments = normalize_inputs(args)
    connection = get_connection(args.database)
    try:
        tables = available_tables(connection)
        required_tables = ("academic_units", "venues", "student_unit_enrolments", "students", "student_profiles")
        missing_tables = [table for table in required_tables if table not in tables]
        if missing_tables:
            raise ValueError(
                "Database schema is not initialized. Start the application and open the Institutional Registry "
                "and Academic Operations pages once, then rerun. Missing: " + ", ".join(missing_tables)
            )

        existing_unit_codes = {
            row["unit_code"] for row in connection.execute("SELECT unit_code FROM academic_units").fetchall()
        }
        existing_venue_codes = {
            row["venue_code"] for row in connection.execute("SELECT venue_code FROM venues").fetchall()
        }
        duplicate_units = sorted(existing_unit_codes.intersection(r["unit_code"] for r in units))
        duplicate_venues = sorted(existing_venue_codes.intersection(r["venue_code"] for r in venues))
        if duplicate_units:
            raise ValueError("Unit codes already exist; no updates are performed: " + ", ".join(duplicate_units))
        if duplicate_venues:
            raise ValueError("Venue codes already exist; no updates are performed: " + ", ".join(duplicate_venues))

        unit_ids = {row["unit_code"]: row["id"] for row in connection.execute(
            "SELECT id, unit_code FROM academic_units WHERE active=1"
        ).fetchall()}
        unit_ids.update({row["unit_code"]: None for row in units})

        resolved_enrolments = []
        for row in enrolments:
            student = connection.execute("""
                SELECT s.id, COALESCE(p.academic_status, 'active') AS academic_status
                FROM students s LEFT JOIN student_profiles p ON p.student_id=s.id
                WHERE s.student_number=?
            """, (row["admission_number"],)).fetchone()
            if not student:
                raise ValueError(
                    f"Enrolments row {row['_line']}: admission number '{row['admission_number']}' "
                    "does not match an existing student record."
                )
            if student["academic_status"] != "active":
                raise ValueError(
                    f"Enrolments row {row['_line']}: student record is not active; no enrolment created."
                )
            if row["unit_code"] not in unit_ids:
                raise ValueError(
                    f"Enrolments row {row['_line']}: unit '{row['unit_code']}' is neither active in the database "
                    "nor included in the supplied units CSV."
                )
            resolved_enrolments.append((student["id"], row))

        for student_id, row in resolved_enrolments:
            existing = connection.execute("""
                SELECT 1 FROM student_unit_enrolments e
                JOIN academic_units u ON u.id=e.unit_id
                WHERE e.student_id=? AND u.unit_code=? AND e.academic_year=? AND e.semester=?
            """, (student_id, row["unit_code"], row["academic_year"], row["semester"])).fetchone()
            if existing:
                raise ValueError(
                    f"Enrolments row {row['_line']}: this student is already enrolled in "
                    f"{row['unit_code']} for {row['academic_year']} {row['semester']}."
                )

        if args.apply:
            if not args.actor_user_id:
                raise ValueError("--actor-user-id is required with --apply.")
            actor = connection.execute(
                "SELECT id, role FROM users WHERE id=?", (args.actor_user_id,)
            ).fetchone()
            if not actor:
                raise ValueError("The supplied actor user ID does not exist.")
            role = actor["role"]
            if units or enrolments:
                if role not in {"admin", "registrar"}:
                    raise ValueError("Only an administrator or registrar may import units/enrolments.")
            if venues and role not in {"admin", "examination_officer"}:
                raise ValueError("Only an administrator or examination officer may import venues.")
            if "audit_events" not in tables:
                raise ValueError("audit_events table is missing; initialize the application schema first.")

        print("VALIDATION PASSED")
        print(f"Academic units to add: {len(units)}")
        print(f"Venues to add: {len(venues)}")
        print(f"Student-unit enrolments to add: {len(enrolments)}")
        print("Existing records will not be updated or deleted.")
        if not args.apply:
            connection.rollback()
            print("DRY RUN ONLY — database changes rolled back. Re-run with --apply and an authorized actor ID to write.")
            return 0

        for row in units:
            cursor = connection.execute("""
                INSERT INTO academic_units(unit_code, unit_name, department, faculty)
                VALUES (?, ?, ?, ?)
            """, (row["unit_code"], row["unit_name"], row["department"], row["faculty"]))
            connection.execute("""
                INSERT INTO audit_events(actor_user_id, action, entity_type, entity_id, summary)
                VALUES (?, 'import', 'academic_unit', ?, ?)
            """, (args.actor_user_id, str(cursor.lastrowid), f"Imported institution-supplied unit {row['unit_code']}."))
            unit_ids[row["unit_code"]] = cursor.lastrowid

        for row in venues:
            cursor = connection.execute("""
                INSERT INTO venues(venue_code, building, room_name, capacity)
                VALUES (?, ?, ?, ?)
            """, (row["venue_code"], row["building"], row["room_name"], row["capacity"]))
            connection.execute("""
                INSERT INTO audit_events(actor_user_id, action, entity_type, entity_id, summary)
                VALUES (?, 'import', 'venue', ?, ?)
            """, (args.actor_user_id, str(cursor.lastrowid), f"Imported institution-supplied venue {row['venue_code']}."))
        for student_id, row in resolved_enrolments:
            cursor = connection.execute("""
                INSERT INTO student_unit_enrolments(student_id, unit_id, academic_year, semester)
                VALUES (?, ?, ?, ?)
            """, (student_id, unit_ids[row["unit_code"]], row["academic_year"], row["semester"]))
            connection.execute("""
                INSERT INTO audit_events(actor_user_id, action, entity_type, entity_id, summary)
                VALUES (?, 'import', 'student_unit_enrolment', ?, ?)
            """, (args.actor_user_id, str(cursor.lastrowid), "Imported institution-supplied student-unit enrolment."))
        connection.commit()
        print("IMPORT COMMITTED — review the registry and operations workspace before creating sessions.")
        return 0
    except Exception as error:
        connection.rollback()
        print(f"IMPORT ABORTED: {error}", file=sys.stderr)
        return 1
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(DEFAULT_DATABASE),
                        help="SQLite database path; ignored when DATABASE_URL selects PostgreSQL.")
    parser.add_argument("--units-csv", help="CSV with unit_code,unit_name,department,faculty.")
    parser.add_argument("--venues-csv", help="CSV with venue_code,building,room_name,capacity.")
    parser.add_argument("--enrolments-csv", help="CSV with admission_number,unit_code,academic_year,semester.")
    parser.add_argument("--apply", action="store_true", help="Commit validated rows. Default behavior is dry-run.")
    parser.add_argument("--actor-user-id", type=int, help="Existing authorized staff user ID for audit attribution.")
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as error:
        print(f"IMPORT ABORTED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
