import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from modules import institutional_registry, operations, integrity, student_portal


class IntegrityAndStudentPortalSchemaTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        connection = sqlite3.connect(self.path)
        connection.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT);
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
            CREATE TABLE incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                examination_id INTEGER,
                incident_type TEXT NOT NULL,
                description TEXT,
                severity TEXT DEFAULT 'low',
                status TEXT DEFAULT 'open'
            );
        """)
        connection.close()
        self.patches = [
            patch.object(institutional_registry, "DATABASE", self.path),
            patch.object(operations, "DATABASE", self.path),
            patch.object(integrity, "DATABASE", self.path),
            patch.object(student_portal, "DATABASE", self.path),
        ]
        for item in self.patches:
            item.start()
        institutional_registry.ensure_schema()
        operations.ensure_schema()
        integrity.ensure_schema()
        student_portal.ensure_schema()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        os.unlink(self.path)

    def test_student_portal_and_case_response_tables_exist(self):
        connection = sqlite3.connect(self.path)
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        connection.close()
        self.assertIn("student_portal_accounts", tables)
        self.assertIn("incident_case_responses", tables)
        self.assertIn("incident_evidence", tables)
        self.assertIn("incident_review_events", tables)
        self.assertIn("evidence_access_events", tables)

    def test_one_response_per_incident_is_enforced(self):
        connection = sqlite3.connect(self.path)
        connection.execute("INSERT INTO students(student_number,first_name,last_name) VALUES('ST/1','A','Student')")
        connection.execute("INSERT INTO incidents(student_id,incident_type) VALUES(1,'Reported event')")
        connection.execute("INSERT INTO incident_case_responses(incident_id,student_id,response_text) VALUES(1,1,'The student response is sufficiently detailed for this test.')")
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO incident_case_responses(incident_id,student_id,response_text) VALUES(1,1,'A second response must not overwrite the first.')")
        connection.close()


if __name__ == "__main__":
    unittest.main()
