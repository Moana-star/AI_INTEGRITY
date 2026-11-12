import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from modules import institutional_registry, operations


class AcademicOperationsSchemaTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        connection = sqlite3.connect(self.path)
        connection.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY);
            CREATE TABLE students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_number TEXT UNIQUE NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                course TEXT,
                year_of_study INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE invigilators (id INTEGER PRIMARY KEY, user_id INTEGER);
            CREATE TABLE examinations (id INTEGER PRIMARY KEY);
        """)
        connection.close()
        self.registry_patch = patch.object(institutional_registry, "DATABASE", self.path)
        self.operations_patch = patch.object(operations, "DATABASE", self.path)
        self.registry_patch.start()
        self.operations_patch.start()
        institutional_registry.ensure_schema()
        operations.ensure_schema()

    def tearDown(self):
        self.registry_patch.stop()
        self.operations_patch.stop()
        os.unlink(self.path)

    def test_operational_tables_are_created(self):
        connection = sqlite3.connect(self.path)
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        connection.close()
        self.assertTrue({
            "venues", "examination_sessions", "session_invigilators",
            "session_candidates", "attendance_events", "session_attendance",
            "academic_units", "student_unit_enrolments", "audit_events"
        }.issubset(tables))

    def test_duplicate_candidate_is_rejected(self):
        connection = sqlite3.connect(self.path)
        connection.execute("INSERT INTO students(student_number,first_name,last_name) VALUES('A/1','A','One')")
        connection.execute("INSERT INTO examinations DEFAULT VALUES")
        connection.execute("INSERT INTO examination_sessions(session_code,examination_id,academic_year,semester,session_date,start_time,end_time) VALUES('S-1',1,'2026/27','S1','2026-11-20','09:00','11:00')")
        connection.execute("INSERT INTO session_candidates(session_id,student_id) VALUES(1,1)")
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO session_candidates(session_id,student_id) VALUES(1,1)")
        connection.close()

    def test_duplicate_attendance_per_session_student_is_rejected(self):
        connection = sqlite3.connect(self.path)
        connection.execute("INSERT INTO students(student_number,first_name,last_name) VALUES('A/1','A','One')")
        connection.execute("INSERT INTO examinations DEFAULT VALUES")
        connection.execute("INSERT INTO examination_sessions(session_code,examination_id,academic_year,semester,session_date,start_time,end_time) VALUES('S-1',1,'2026/27','S1','2026-11-20','09:00','11:00')")
        connection.execute("INSERT INTO session_attendance(session_id,student_id) VALUES(1,1)")
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO session_attendance(session_id,student_id) VALUES(1,1)")
        connection.close()


if __name__ == "__main__":
    unittest.main()
