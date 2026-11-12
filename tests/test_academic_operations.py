import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from modules import institutional_registry, operations, integrity
from app import app as flask_app


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
            CREATE TABLE incidents (id INTEGER PRIMARY KEY, status TEXT, student_id INTEGER, examination_id INTEGER, incident_type TEXT, description TEXT, severity TEXT, reported_at TEXT);
            CREATE TABLE examinations (id INTEGER PRIMARY KEY, course_code TEXT, examination_name TEXT, invigilator_id INTEGER);
        """)
        connection.close()
        self.registry_patch = patch.object(institutional_registry, "DATABASE", self.path)
        self.operations_patch = patch.object(operations, "DATABASE", self.path)
        self.integrity_patch = patch.object(integrity, "DATABASE", self.path)
        self.registry_patch.start()
        self.operations_patch.start()
        self.integrity_patch.start()
        institutional_registry.ensure_schema()
        operations.ensure_schema()

    def tearDown(self):
        self.registry_patch.stop()
        self.operations_patch.stop()
        self.integrity_patch.stop()
        operations.SCHEMA_READY = False
        integrity.SCHEMA_READY = False
        os.unlink(self.path)

    def test_admin_can_export_session_attendance_csv(self):
        connection = sqlite3.connect(self.path)
        connection.execute("INSERT INTO users(id) VALUES(1)")
        connection.execute("INSERT INTO students(student_number,first_name,last_name) VALUES('REG/001','Amina','Otieno')")
        connection.execute("INSERT INTO examinations(id,course_code,examination_name) VALUES(1,'CSC201','Data Structures')")
        connection.execute("""
            INSERT INTO examination_sessions
            (id,session_code,examination_id,academic_year,semester,session_date,start_time,end_time)
            VALUES(1,'CSC201-S1-A',1,'2026/2027','Semester 1','2026-11-20','09:00','11:00')
        """)
        connection.execute("INSERT INTO session_candidates(session_id,student_id,seat_label) VALUES(1,1,'SEAT-001')")
        connection.commit()
        connection.close()
        flask_app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        client = flask_app.test_client()
        with client.session_transaction() as browser_session:
            browser_session["user_id"] = 1
            browser_session["role"] = "admin"
        response = client.get("/operations/sessions/1/attendance.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers.get("Content-Type", ""))
        self.assertIn(b"REG/001", response.data)
        self.assertIn(b"not_recorded", response.data)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store, private")

    def test_invigilator_cannot_export_attendance_csv(self):
        flask_app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        client = flask_app.test_client()
        with client.session_transaction() as browser_session:
            browser_session["user_id"] = 1
            browser_session["role"] = "invigilator"
        response = client.get("/operations/sessions/1/attendance.csv")
        self.assertEqual(response.status_code, 403)

    def test_reconciliation_flags_missing_checkin_for_review_not_absence(self):
        connection = sqlite3.connect(self.path)
        connection.execute("INSERT INTO users(id) VALUES(1)")
        connection.execute("INSERT INTO students(student_number,first_name,last_name) VALUES('REG/002','Brian','Kiptoo')")
        connection.execute("INSERT INTO examinations(id,course_code,examination_name) VALUES(1,'MAT101','Calculus')")
        connection.execute("""
            INSERT INTO examination_sessions
            (id,session_code,examination_id,academic_year,semester,session_date,start_time,end_time,status)
            VALUES(1,'MAT101-S1-A',1,'2026/2027','Semester 1','2020-01-01','09:00','11:00','completed')
        """)
        connection.execute("INSERT INTO session_candidates(session_id,student_id,seat_label) VALUES(1,1,'SEAT-001')")
        connection.commit()
        connection.close()
        flask_app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        client = flask_app.test_client()
        with client.session_transaction() as browser_session:
            browser_session["user_id"] = 1
            browser_session["role"] = "admin"
        page = client.get("/operations/sessions/1/attendance")
        import re
        token = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
        response = client.post("/operations/sessions/1/reconcile-attendance", data={"csrf_token": token})
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        result = connection.execute("SELECT status, verification_status FROM session_attendance WHERE session_id=1 AND student_id=1").fetchone()
        connection.close()
        self.assertEqual(result, ("disputed", "manual_review"))

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
