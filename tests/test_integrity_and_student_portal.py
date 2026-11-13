import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import re

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
        operations.SCHEMA_READY = False
        integrity.SCHEMA_READY = False
        institutional_registry.ensure_schema()
        operations.ensure_schema()
        integrity.ensure_schema()
        student_portal.ensure_schema()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        operations.SCHEMA_READY = False
        integrity.SCHEMA_READY = False
        student_portal.SCHEMA_READY = False
        os.unlink(self.path)

    def _seed_two_student_portal_records(self):
        connection = sqlite3.connect(self.path)
        connection.executemany("""
            INSERT INTO students(id,student_number,first_name,last_name)
            VALUES(?,?,?,?)
        """, [
            (1, "KSU/OWN/001", "Amina", "OwnRecord"),
            (2, "KSU/OTHER/002", "Brian", "PrivateRecord"),
        ])
        connection.executemany("""
            INSERT INTO student_portal_accounts
                (student_id,password_hash,must_change_password,active)
            VALUES(?,?,0,1)
        """, [(1, "unused-test-hash-a"), (2, "unused-test-hash-b")])
        connection.executemany("""
            INSERT INTO incidents(id,student_id,incident_type,description,severity,status)
            VALUES(?,?,?,?,?,?)
        """, [
            (1, 1, "Own case", "OWN-CASE-DETAIL", "low", "open"),
            (2, 2, "Other case", "PRIVATE-CASE-DETAIL", "high", "open"),
        ])
        connection.executemany("""
            INSERT INTO incident_case_workflow(incident_id,case_status,reported_by)
            VALUES(?,?,?)
        """, [(1, "student_response_requested", 10),
              (2, "student_response_requested", 11)])
        connection.commit()
        connection.close()

    def test_student_portal_discloses_only_authenticated_students_records(self):
        from app import app as flask_app
        self._seed_two_student_portal_records()
        previous = {
            "TESTING": flask_app.config.get("TESTING"),
            "SECRET_KEY": flask_app.config.get("SECRET_KEY"),
            "WTF_CSRF_ENABLED": flask_app.config.get("WTF_CSRF_ENABLED"),
        }
        try:
            flask_app.config.update(
                TESTING=True, SECRET_KEY="student-ownership-test", WTF_CSRF_ENABLED=False
            )
            client = flask_app.test_client()
            with client.session_transaction() as state:
                state.clear()
                state["role"] = "student"
                state["student_id"] = 1
            response = client.get("/student/portal")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"KSU/OWN/001", response.data)
            self.assertIn(b"OWN-CASE-DETAIL", response.data)
            self.assertNotIn(b"KSU/OTHER/002", response.data)
            self.assertNotIn(b"PRIVATE-CASE-DETAIL", response.data)
        finally:
            for key, value in previous.items():
                if value is None:
                    flask_app.config.pop(key, None)
                else:
                    flask_app.config[key] = value

    def test_student_cannot_submit_response_to_another_students_incident(self):
        from app import app as flask_app
        self._seed_two_student_portal_records()
        previous = {
            "TESTING": flask_app.config.get("TESTING"),
            "SECRET_KEY": flask_app.config.get("SECRET_KEY"),
            "WTF_CSRF_ENABLED": flask_app.config.get("WTF_CSRF_ENABLED"),
        }
        try:
            flask_app.config.update(
                TESTING=True, SECRET_KEY="student-ownership-test", WTF_CSRF_ENABLED=False
            )
            client = flask_app.test_client()
            with client.session_transaction() as state:
                state.clear()
                state["role"] = "student"
                state["student_id"] = 1
            response = client.post(
                "/student/incidents/2/respond",
                data={"response_text": "This unauthorized response must not be accepted for another student's incident."},
            )
            self.assertEqual(response.status_code, 403)
            connection = sqlite3.connect(self.path)
            count = connection.execute(
                "SELECT COUNT(*) FROM incident_case_responses WHERE incident_id=2"
            ).fetchone()[0]
            connection.close()
            self.assertEqual(count, 0)
        finally:
            for key, value in previous.items():
                if value is None:
                    flask_app.config.pop(key, None)
                else:
                    flask_app.config[key] = value

    def test_incident_reporter_cannot_review_own_case(self):
        from app import app as flask_app
        connection = sqlite3.connect(self.path)
        connection.execute("INSERT INTO users(id,username) VALUES(1,'reporter')")
        connection.execute("INSERT INTO students(student_number,first_name,last_name) VALUES('ST/2','Test','Student')")
        connection.execute("INSERT INTO incidents(student_id,incident_type) VALUES(1,'Observed event')")
        connection.execute("INSERT INTO incident_case_workflow(incident_id,case_status,reported_by) VALUES(1,'reported',1)")
        connection.commit()
        connection.close()
        flask_app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        client = flask_app.test_client()
        with client.session_transaction() as browser_session:
            browser_session['user_id'] = 1
            browser_session['role'] = 'admin'
        page = client.get('/forgot-password')
        token = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
        response = client.post('/integrity/incidents/1/status', data={
            'case_status': 'under_review',
            'review_note': 'Review attempted by the original incident reporter.',
            'csrf_token': token,
        })
        self.assertEqual(response.status_code, 403)
        connection = sqlite3.connect(self.path)
        status = connection.execute("SELECT case_status FROM incident_case_workflow WHERE incident_id=1").fetchone()[0]
        connection.close()
        self.assertEqual(status, 'reported')

    def test_schema_records_incident_reporter_for_conflict_checks(self):
        connection = sqlite3.connect(self.path)
        columns = {row[1] for row in connection.execute('PRAGMA table_info(incident_case_workflow)')}
        connection.close()
        self.assertIn('reported_by', columns)

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
