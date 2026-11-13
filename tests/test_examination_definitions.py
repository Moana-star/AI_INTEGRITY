import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import app as flask_app
from modules import examination_definitions, institutional_registry, integrity, operations


class ExaminationDefinitionManagementTests(unittest.TestCase):
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
            CREATE TABLE invigilators (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                employee_number TEXT,
                first_name TEXT,
                last_name TEXT,
                status TEXT DEFAULT 'active'
            );
            CREATE TABLE incidents (
                id INTEGER PRIMARY KEY,
                status TEXT,
                student_id INTEGER,
                examination_id INTEGER,
                incident_type TEXT,
                description TEXT,
                severity TEXT,
                reported_at TEXT
            );
            CREATE TABLE examinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_code TEXT NOT NULL,
                examination_name TEXT NOT NULL,
                invigilator_id INTEGER
            );
            INSERT INTO users(id) VALUES (1), (2);
        """)
        connection.commit()
        connection.close()

        self.registry_patch = patch.object(institutional_registry, "DATABASE", self.path)
        self.operations_patch = patch.object(operations, "DATABASE", self.path)
        self.integrity_patch = patch.object(integrity, "DATABASE", self.path)
        self.registry_patch.start()
        self.operations_patch.start()
        self.integrity_patch.start()
        operations.SCHEMA_READY = False
        integrity.SCHEMA_READY = False
        examination_definitions.SCHEMA_READY = False
        examination_definitions.ensure_schema()

        self.previous_testing = flask_app.config.get("TESTING")
        self.previous_csrf = flask_app.config.get("WTF_CSRF_ENABLED")
        flask_app.config.update(
            TESTING=True,
            SECRET_KEY="phase-two-test-secret",
            WTF_CSRF_ENABLED=False,
        )
        self.client = flask_app.test_client()

    def tearDown(self):
        flask_app.config["TESTING"] = self.previous_testing
        flask_app.config["WTF_CSRF_ENABLED"] = self.previous_csrf
        self.registry_patch.stop()
        self.operations_patch.stop()
        self.integrity_patch.stop()
        operations.SCHEMA_READY = False
        integrity.SCHEMA_READY = False
        examination_definitions.SCHEMA_READY = False
        os.unlink(self.path)

    def sign_in(self, role="examination_officer", user_id=1):
        with self.client.session_transaction() as browser_session:
            browser_session["user_id"] = user_id
            browser_session["role"] = role

    def add_exam(self, code="CSC201", name="Data Structures"):
        connection = sqlite3.connect(self.path)
        cursor = connection.execute(
            "INSERT INTO examinations(course_code, examination_name) VALUES (?, ?)",
            (code, name),
        )
        exam_id = cursor.lastrowid
        connection.commit()
        connection.close()
        return exam_id

    def test_examination_officer_can_create_definition_and_audit_it(self):
        self.sign_in()
        response = self.client.post(
            "/admin/examinations/add",
            data={"course_code": "csc201", "examination_name": "Data Structures"},
        )
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        record = connection.execute(
            "SELECT course_code, examination_name, definition_status, definition_created_by "
            "FROM examinations"
        ).fetchone()
        audit = connection.execute(
            "SELECT action, entity_type, entity_id FROM audit_events"
        ).fetchone()
        connection.close()
        self.assertEqual(record, ("CSC201", "Data Structures", "active", 1))
        self.assertEqual(audit, ("create", "examination_definition", "1"))

    def test_invalid_definition_is_rejected_without_writing(self):
        self.sign_in()
        response = self.client.post(
            "/admin/examinations/add",
            data={"course_code": "?", "examination_name": "X"},
        )
        self.assertEqual(response.status_code, 400)
        connection = sqlite3.connect(self.path)
        count = connection.execute("SELECT COUNT(*) FROM examinations").fetchone()[0]
        connection.close()
        self.assertEqual(count, 0)

    def test_duplicate_code_and_name_is_rejected(self):
        self.add_exam()
        self.sign_in()
        response = self.client.post(
            "/admin/examinations/add",
            data={"course_code": "CSC201", "examination_name": "Data Structures"},
        )
        self.assertEqual(response.status_code, 409)
        connection = sqlite3.connect(self.path)
        count = connection.execute("SELECT COUNT(*) FROM examinations").fetchone()[0]
        connection.close()
        self.assertEqual(count, 1)

    def test_examination_officer_can_edit_definition_and_audit_it(self):
        exam_id = self.add_exam()
        self.sign_in()
        response = self.client.post(
            f"/admin/examinations/edit/{exam_id}",
            data={"course_code": "CSC202", "examination_name": "Advanced Data Structures"},
        )
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        record = connection.execute(
            "SELECT course_code, examination_name FROM examinations WHERE id=?",
            (exam_id,),
        ).fetchone()
        audit = connection.execute(
            "SELECT action, entity_type, entity_id FROM audit_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        connection.close()
        self.assertEqual(record, ("CSC202", "Advanced Data Structures"))
        self.assertEqual(audit, ("update", "examination_definition", str(exam_id)))

    def test_registrar_cannot_manage_examination_definitions(self):
        self.sign_in(role="registrar")
        response = self.client.get("/admin/examinations")
        self.assertEqual(response.status_code, 403)

    def test_archive_is_blocked_while_session_is_scheduled_or_active(self):
        exam_id = self.add_exam()
        connection = sqlite3.connect(self.path)
        connection.execute("""
            INSERT INTO examination_sessions
            (session_code, examination_id, academic_year, semester,
             session_date, start_time, end_time, status)
            VALUES ('CSC201-S1', ?, '2026/2027', 'Semester 1',
                    '2026-12-01', '09:00', '11:00', 'scheduled')
        """, (exam_id,))
        connection.commit()
        connection.close()
        self.sign_in()
        response = self.client.post(
            f"/admin/examinations/archive/{exam_id}",
            data={"reason": "Retiring this definition after timetable review."},
        )
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        status = connection.execute(
            "SELECT definition_status FROM examinations WHERE id=?", (exam_id,)
        ).fetchone()[0]
        connection.close()
        self.assertEqual(status, "active")

    def test_archive_and_restore_are_audited_and_preserve_identity(self):
        exam_id = self.add_exam()
        self.sign_in()
        archived = self.client.post(
            f"/admin/examinations/archive/{exam_id}",
            data={"reason": "This paper is no longer offered by the department."},
        )
        self.assertEqual(archived.status_code, 302)
        connection = sqlite3.connect(self.path)
        state = connection.execute(
            "SELECT definition_status, definition_archive_reason FROM examinations WHERE id=?",
            (exam_id,),
        ).fetchone()
        connection.close()
        self.assertEqual(state, ("archived", "This paper is no longer offered by the department."))

        restored = self.client.post(
            f"/admin/examinations/restore/{exam_id}",
            data={"reason": "The department has approved this paper for future use."},
        )
        self.assertEqual(restored.status_code, 302)
        connection = sqlite3.connect(self.path)
        state = connection.execute(
            "SELECT definition_status, definition_archive_reason FROM examinations WHERE id=?",
            (exam_id,),
        ).fetchone()
        events = connection.execute(
            "SELECT action FROM audit_events WHERE entity_type='examination_definition' "
            "AND entity_id=? ORDER BY id",
            (str(exam_id),),
        ).fetchall()
        connection.close()
        self.assertEqual(state, ("active", None))
        self.assertEqual([row[0] for row in events], ["archive", "restore"])

    def test_archived_definition_is_not_available_for_new_session(self):
        exam_id = self.add_exam()
        connection = sqlite3.connect(self.path)
        connection.execute(
            "UPDATE examinations SET definition_status='archived' WHERE id=?",
            (exam_id,),
        )
        connection.execute(
            "INSERT INTO academic_units(unit_code, unit_name) VALUES ('CSC201', 'Data Structures')"
        )
        connection.commit()
        connection.close()
        self.sign_in()
        response = self.client.post(
            "/operations/sessions",
            data={
                "session_code": "CSC201-2026-S1",
                "examination_id": str(exam_id),
                "unit_id": "1",
                "academic_year": "2026/2027",
                "semester": "Semester 1",
                "session_date": "2026-12-01",
                "start_time": "09:00",
                "end_time": "11:00",
            },
        )
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        count = connection.execute(
            "SELECT COUNT(*) FROM examination_sessions WHERE examination_id=?",
            (exam_id,),
        ).fetchone()[0]
        connection.close()
        self.assertEqual(count, 0)

    def test_legacy_delete_endpoint_never_deletes_definition(self):
        exam_id = self.add_exam()
        self.sign_in(role="admin")
        response = self.client.post(f"/admin/examinations/delete/{exam_id}")
        self.assertEqual(response.status_code, 303)
        connection = sqlite3.connect(self.path)
        count = connection.execute(
            "SELECT COUNT(*) FROM examinations WHERE id=?", (exam_id,)
        ).fetchone()[0]
        connection.close()
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
