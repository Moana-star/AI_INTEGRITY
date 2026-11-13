import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import app as flask_app
from modules import biometric_attendance, institutional_registry, operations


class ApprovedTestProvider:
    def __init__(self, matched=True, live=True):
        self.matched = matched
        self.live = live
        self.calls = []

    def verify_one_to_one(self, *, capture, reference_id, purpose):
        self.calls.append((capture, reference_id, purpose))
        return {
            "matched": self.matched,
            "liveness_passed": self.live,
            "provider": "approved-test-adapter",
            "verification_reference": "provider-event-001",
        }


class BiometricAttendanceRouteTests(unittest.TestCase):
    def setUp(self):
        self.original_config = {key: flask_app.config.get(key) for key in (
            "TESTING", "SECRET_KEY", "WTF_CSRF_ENABLED", "BIOMETRIC_ENABLED",
            "BIOMETRIC_INSTITUTIONAL_APPROVAL", "BIOMETRIC_PROVIDER"
        )}
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        connection = sqlite3.connect(self.path)
        connection.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT);
            CREATE TABLE students(
                id INTEGER PRIMARY KEY, student_number TEXT UNIQUE NOT NULL,
                first_name TEXT NOT NULL, last_name TEXT NOT NULL, course TEXT,
                year_of_study INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE invigilators(
                id INTEGER PRIMARY KEY, user_id INTEGER, employee_number TEXT,
                first_name TEXT, last_name TEXT, phone TEXT, status TEXT DEFAULT 'active'
            );
            CREATE TABLE examinations(
                id INTEGER PRIMARY KEY, course_code TEXT, examination_name TEXT,
                invigilator_id INTEGER
            );
            CREATE TABLE academic_units(
                id INTEGER PRIMARY KEY, unit_code TEXT, unit_name TEXT, active INTEGER DEFAULT 1
            );
            CREATE TABLE audit_events(
                id INTEGER PRIMARY KEY, actor_user_id INTEGER, action TEXT,
                entity_type TEXT, entity_id TEXT, summary TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO users(id,username) VALUES(1,'invigilator');
            INSERT INTO students(id,student_number,first_name,last_name)
                VALUES(1,'KSU/TEST/001','Test','Student');
            INSERT INTO invigilators(id,user_id,employee_number,first_name,last_name)
                VALUES(1,1,'EMP-TEST','Test','Invigilator');
            INSERT INTO examinations(id,course_code,examination_name)
                VALUES(1,'CSC101','Test Examination');
        """)
        connection.commit()
        connection.close()
        self.patches = [
            patch.object(biometric_attendance, "DATABASE", self.path),
            patch.object(operations, "DATABASE", self.path),
            patch.object(institutional_registry, "DATABASE", self.path),
        ]
        for item in self.patches:
            item.start()
        institutional_registry.ensure_schema()
        operations.ensure_schema()
        connection = sqlite3.connect(self.path)
        connection.execute("""
            INSERT INTO examination_sessions
            (id,session_code,examination_id,academic_year,semester,venue_id,
             session_date,start_time,end_time,status)
            VALUES(1,'CSC101-TEST',1,'2026/2027','Semester 1',NULL,
                   '2099-11-20','09:00','11:00','active')
        """)
        connection.execute("""
            INSERT INTO session_invigilators(session_id,invigilator_id) VALUES(1,1)
        """)
        connection.execute("""
            INSERT INTO session_candidates(session_id,student_id,eligibility_status)
            VALUES(1,1,'eligible')
        """)
        connection.commit()
        connection.close()
        biometric_attendance.ensure_schema()
        flask_app.config.update(
            TESTING=True, SECRET_KEY="biometric-test-secret", WTF_CSRF_ENABLED=False,
            BIOMETRIC_ENABLED=True, BIOMETRIC_INSTITUTIONAL_APPROVAL=True,
            BIOMETRIC_PROVIDER=ApprovedTestProvider(),
        )
        self.client = flask_app.test_client()
        with self.client.session_transaction() as state:
            state.clear()
            state["role"] = "invigilator"
            state["user_id"] = 1

    def tearDown(self):
        for item in self.patches:
            item.stop()
        operations.SCHEMA_READY = False
        institutional_registry._schema_ready = False
        for key, value in self.original_config.items():
            if value is None:
                flask_app.config.pop(key, None)
            else:
                flask_app.config[key] = value
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass

    def enrol_test_reference(self):
        connection = sqlite3.connect(self.path)
        connection.execute("""
            INSERT INTO biometric_enrolments
            (student_id,provider_name,provider_reference,consent_record_id,
             approval_reference,enrolled_by)
            VALUES(1,'approved-test-adapter','test-reference-001',
                   'test-consent-record','KSU-APPROVAL-TEST-001',1)
        """)
        connection.commit()
        connection.close()

    def test_successful_match_and_liveness_record_biometric_attendance(self):
        self.enrol_test_reference()
        response = self.client.post(
            "/biometric/sessions/1/students/1/verify",
            data={"capture": ( __import__("io").BytesIO(b"jpeg-test-bytes"), "capture.jpg", "image/jpeg")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        attendance = connection.execute("""
            SELECT status,verification_method,verification_status
            FROM session_attendance WHERE session_id=1 AND student_id=1
        """).fetchone()
        event = connection.execute("""
            SELECT event_type,verification_method FROM attendance_events
            WHERE session_id=1 AND student_id=1
        """).fetchone()
        connection.close()
        self.assertEqual(attendance, ("present","biometric","verified"))
        self.assertEqual(event, ("check_in","biometric"))

    def test_failed_liveness_never_records_attendance(self):
        self.enrol_test_reference()
        flask_app.config["BIOMETRIC_PROVIDER"] = ApprovedTestProvider(matched=True, live=False)
        response = self.client.post(
            "/biometric/sessions/1/students/1/verify",
            data={"capture": (__import__("io").BytesIO(b"jpeg-test-bytes"), "capture.jpg", "image/jpeg")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        attendance_count = connection.execute("SELECT COUNT(*) FROM session_attendance").fetchone()[0]
        outcomes = connection.execute("SELECT outcome FROM biometric_verification_events").fetchall()
        connection.close()
        self.assertEqual(attendance_count, 0)
        self.assertEqual(outcomes, [("failed",)])

    def test_duplicate_check_in_is_rejected(self):
        self.enrol_test_reference()
        connection = sqlite3.connect(self.path)
        connection.execute("""
            INSERT INTO session_attendance
            (session_id,student_id,status,check_in_at,verification_method,
             verification_status,verified_by)
            VALUES(1,1,'present','2026-11-20T08:00:00','manual','verified',1)
        """)
        connection.commit()
        connection.close()
        response = self.client.post(
            "/biometric/sessions/1/students/1/verify",
            data={"capture": (__import__("io").BytesIO(b"jpeg-test-bytes"), "capture.jpg", "image/jpeg")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
