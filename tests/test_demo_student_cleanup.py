import contextlib
import io
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts import remove_demo_students as cleanup


class DemoStudentCleanupTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.database = Path(self.path)
        connection = sqlite3.connect(self.path)
        connection.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE users (id INTEGER PRIMARY KEY, role TEXT NOT NULL);
            INSERT INTO users(id, role) VALUES (1, 'admin');
            CREATE TABLE students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_number TEXT UNIQUE NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                course TEXT
            );
            INSERT INTO students(student_number,first_name,last_name,course)
                VALUES ('DEMO-CRITICAL','Demo','Critical','DEMO'),
                       ('DEMO-HIGH','Demo','High','DEMO'),
                       ('DEMO-WATCH','Demo','Watch','DEMO'),
                       ('REG/001','Real','Student','Computing');
            CREATE TABLE student_profiles (
                student_id INTEGER PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
                academic_status TEXT
            );
            CREATE TABLE academic_units (id INTEGER PRIMARY KEY, unit_code TEXT);
            CREATE TABLE student_unit_enrolments (
                id INTEGER PRIMARY KEY,
                student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
                unit_id INTEGER REFERENCES academic_units(id)
            );
            CREATE TABLE audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id INTEGER,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                summary TEXT NOT NULL
            );
            INSERT INTO student_profiles(student_id, academic_status)
                SELECT id, 'active' FROM students WHERE student_number LIKE 'DEMO-%';
            INSERT INTO academic_units(id, unit_code) VALUES (1, 'TEST101');
            INSERT INTO student_unit_enrolments(id, student_id, unit_id)
                SELECT id, id, 1 FROM students WHERE student_number LIKE 'DEMO-%';
        """)
        connection.commit()
        connection.close()

    def tearDown(self):
        for candidate in self.database.parent.glob(self.database.stem + ".pre_demo_cleanup_*"):
            candidate.unlink(missing_ok=True)
        self.database.unlink(missing_ok=True)

    def args(self, apply=False, actor=1):
        return SimpleNamespace(database=str(self.database), apply=apply, actor_user_id=actor)

    def counts(self):
        with contextlib.closing(sqlite3.connect(self.path)) as connection:
            return (
                connection.execute("SELECT COUNT(*) FROM students").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM student_profiles").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM student_unit_enrolments").fetchone()[0],
            )

    def test_dry_run_does_not_change_database(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = cleanup.run(self.args())
        self.assertEqual(result, 0)
        self.assertEqual(self.counts(), (4, 3, 3))

    def test_apply_removes_only_exact_demo_students_and_safe_children(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = cleanup.run(self.args(apply=True))
        self.assertEqual(result, 0)
        self.assertEqual(self.counts(), (1, 0, 0))
        with contextlib.closing(sqlite3.connect(self.path)) as connection:
            remaining = connection.execute(
                "SELECT student_number FROM students"
            ).fetchall()
            audit_count = connection.execute(
                "SELECT COUNT(*) FROM audit_events WHERE action='delete' AND entity_type='student'"
            ).fetchone()[0]
        self.assertEqual(remaining, [("REG/001",)])
        self.assertEqual(audit_count, 3)
        backups = list(self.database.parent.glob(self.database.stem + ".pre_demo_cleanup_*"))
        self.assertEqual(len(backups), 1)

    def test_operational_reference_blocks_entire_cleanup(self):
        with contextlib.closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript("""
                CREATE TABLE incidents (
                    id INTEGER PRIMARY KEY,
                    student_id INTEGER REFERENCES students(id)
                );
                INSERT INTO incidents(student_id)
                    SELECT id FROM students WHERE student_number='DEMO-HIGH';
            """)
            connection.commit()
        with contextlib.redirect_stdout(io.StringIO()):
            result = cleanup.run(self.args(apply=True))
        self.assertEqual(result, 1)
        self.assertEqual(self.counts(), (4, 3, 3))
        self.assertFalse(list(self.database.parent.glob(self.database.stem + ".pre_demo_cleanup_*")))

    def test_apply_requires_existing_administrator(self):
        with contextlib.redirect_stderr(io.StringIO()):
            result = cleanup.run(self.args(apply=True, actor=999))
        self.assertEqual(result, 1)
        self.assertEqual(self.counts(), (4, 3, 3))


if __name__ == "__main__":
    unittest.main()
