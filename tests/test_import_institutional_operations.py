from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from scripts import import_institutional_operations as importer


class InstitutionalOperationsImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "eims-test.db"
        self._create_database()
        self.units = self._csv(
            "units.csv",
            ["unit_code", "unit_name", "department", "faculty"],
            [["CSC201", "Data Structures", "Computing", "Science"]],
        )
        self.venues = self._csv(
            "venues.csv",
            ["venue_code", "building", "room_name", "capacity"],
            [["LAB-A", "Main Block", "Laboratory A", "60"]],
        )
        self.enrolments = self._csv(
            "enrolments.csv",
            ["admission_number", "unit_code", "academic_year", "semester"],
            [["TEST/001", "CSC201", "2026/2027", "Semester 1"]],
        )

    def tearDown(self):
        self.temp.cleanup()

    def _connect(self):
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _create_database(self):
        connection = self._connect()
        connection.executescript("""
            CREATE TABLE users(id INTEGER PRIMARY KEY, role TEXT NOT NULL);
            CREATE TABLE students(id INTEGER PRIMARY KEY, student_number TEXT NOT NULL UNIQUE);
            CREATE TABLE student_profiles(
                student_id INTEGER PRIMARY KEY,
                academic_status TEXT NOT NULL DEFAULT 'active'
            );
            CREATE TABLE academic_units(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_code TEXT NOT NULL UNIQUE,
                unit_name TEXT NOT NULL,
                department TEXT,
                faculty TEXT,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE venues(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_code TEXT NOT NULL UNIQUE,
                building TEXT,
                room_name TEXT NOT NULL,
                capacity INTEGER NOT NULL
            );
            CREATE TABLE student_unit_enrolments(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                unit_id INTEGER NOT NULL,
                academic_year TEXT NOT NULL,
                semester TEXT NOT NULL,
                UNIQUE(student_id,unit_id,academic_year,semester),
                FOREIGN KEY(student_id) REFERENCES students(id),
                FOREIGN KEY(unit_id) REFERENCES academic_units(id)
            );
            CREATE TABLE audit_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id INTEGER,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                summary TEXT NOT NULL
            );
            INSERT INTO users(id,role) VALUES(1,'admin'),(2,'registrar');
            INSERT INTO students(id,student_number) VALUES(1,'TEST/001');
            INSERT INTO student_profiles(student_id,academic_status) VALUES(1,'active');
        """)
        connection.commit()
        connection.close()

    def _csv(self, name, headers, rows):
        path = self.root / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)
        return str(path)

    def _args(self, apply=False, actor=1, **overrides):
        values = {
            "database": str(self.database),
            "units_csv": self.units,
            "venues_csv": self.venues,
            "enrolments_csv": self.enrolments,
            "apply": apply,
            "actor_user_id": actor if apply else None,
        }
        values.update(overrides)
        return Namespace(**values)

    def _run(self, args):
        with patch.object(importer, "get_connection", side_effect=lambda _path: self._connect()), \
             patch.object(importer, "is_postgres", return_value=False):
            return importer.run(args)

    def _counts(self):
        connection = self._connect()
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("academic_units", "venues", "student_unit_enrolments", "audit_events")
        }
        connection.close()
        return counts

    def test_default_dry_run_writes_nothing(self):
        result = self._run(self._args())
        self.assertEqual(result, 0)
        self.assertEqual(self._counts(), {
            "academic_units": 0,
            "venues": 0,
            "student_unit_enrolments": 0,
            "audit_events": 0,
        })

    def test_apply_commits_records_and_audit_events(self):
        result = self._run(self._args(apply=True))
        self.assertEqual(result, 0)
        self.assertEqual(self._counts(), {
            "academic_units": 1,
            "venues": 1,
            "student_unit_enrolments": 1,
            "audit_events": 3,
        })

    def test_unknown_student_aborts_entire_import(self):
        self.enrolments = self._csv(
            "bad-enrolments.csv",
            ["admission_number", "unit_code", "academic_year", "semester"],
            [["NOT/IN/REGISTRY", "CSC201", "2026/2027", "Semester 1"]],
        )
        result = self._run(self._args(apply=True))
        self.assertEqual(result, 1)
        self.assertEqual(self._counts(), {
            "academic_units": 0,
            "venues": 0,
            "student_unit_enrolments": 0,
            "audit_events": 0,
        })

    def test_role_cannot_import_venues(self):
        result = self._run(self._args(apply=True, actor=2))
        self.assertEqual(result, 1)
        self.assertEqual(self._counts(), {
            "academic_units": 0,
            "venues": 0,
            "student_unit_enrolments": 0,
            "audit_events": 0,
        })

    def test_duplicate_unit_code_in_file_is_rejected(self):
        self.units = self._csv(
            "duplicate-units.csv",
            ["unit_code", "unit_name", "department", "faculty"],
            [
                ["CSC201", "Data Structures", "Computing", "Science"],
                ["CSC201", "Different title", "Computing", "Science"],
            ],
        )
        result = self._run(self._args())
        self.assertEqual(result, 1)
        self.assertEqual(self._counts()["academic_units"], 0)


if __name__ == "__main__":
    unittest.main()
