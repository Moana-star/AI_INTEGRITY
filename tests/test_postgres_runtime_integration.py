import os
import unittest
import threading

if not os.environ.get("DATABASE_URL", "").startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
    raise unittest.SkipTest("PostgreSQL runtime integration requires DATABASE_URL.")

from app import app


class PostgreSQLRuntimeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SECRET_KEY="postgres-runtime-integration-test")

    def setUp(self):
        self.client = app.test_client()

    def _as_role(self, role):
        with self.client.session_transaction() as state:
            state.clear()
            state["user_id"] = 1
            state["role"] = role

    def test_empty_first_bootstrap_creates_no_fictional_records(self):
        from modules.database import get_connection
        connection = get_connection("database/exam_integrity.db")
        try:
            for table in ("students", "examinations", "incidents", "invigilators"):
                count = connection.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()["total"]
                self.assertEqual(count, 0, f"{table} must not be populated with demo records.")
            admin = connection.execute(
                "SELECT username, role FROM users"
            ).fetchall()
            self.assertEqual(len(admin), 1)
            self.assertEqual(admin[0]["role"], "admin")
        finally:
            connection.close()

    def test_health_check_uses_postgresql_connection(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_all_module_schemas_initialize_on_postgresql(self):
        cases = [
            ("examination_officer", "/operations/"),
            ("examination_officer", "/eligibility/"),
            ("examination_officer", "/integrity/incidents"),
            ("examination_officer", "/appeals/"),
            ("registrar", "/admin/registry/students"),
            ("examination_officer", "/identity/sessions/1"),
        ]
        for role, path in cases:
            with self.subTest(path=path):
                self._as_role(role)
                response = self.client.get(path)
                self.assertNotEqual(
                    response.status_code, 500,
                    f"{path} failed during PostgreSQL schema initialization: {response.get_data(as_text=True)[:1000]}",
                )

    def test_registry_can_create_and_read_a_real_student_record(self):
        self._as_role("registrar")
        response = self.client.post(
            "/admin/registry/students/new",
            data={
                "admission_number": "PG-RUNTIME-001",
                "first_name": "Runtime",
                "last_name": "Candidate",
                "course": "Computer Science",
                "year_of_study": "1",
                "faculty": "Computing",
                "department": "Computer Science",
                "institutional_email": "pg-runtime-001@example.invalid",
                "phone": "",
                "academic_status": "active",
                "academic_year": "2026/2027",
                "semester": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        from modules.database import get_connection
        connection = get_connection("database/exam_integrity.db")
        try:
            record = connection.execute(
                "SELECT student_number, first_name, last_name FROM students WHERE student_number=?",
                ("PG-RUNTIME-001",),
            ).fetchone()
            self.assertIsNotNone(record)
            self.assertEqual(record["first_name"], "Runtime")
            student = connection.execute(
                "SELECT id FROM students WHERE student_number=?",
                ("PG-RUNTIME-001",),
            ).fetchone()
            connection.execute("""
                INSERT INTO academic_history_events
                    (student_id,event_type,effective_date,reason,recorded_by)
                VALUES (?,'progression','2026-11-13','PostgreSQL append-only trigger integration test',1)
            """, (student["id"],))
            connection.commit()
            import psycopg
            with self.assertRaises(psycopg.Error):
                connection.execute(
                    "UPDATE academic_history_events SET reason='tampered' WHERE student_id=?",
                    (student["id"],),
                )
            connection.rollback()
        finally:
            connection.close()

    def test_registrar_can_create_an_academic_unit(self):
        self._as_role("registrar")
        response = self.client.post(
            "/operations/units",
            data={
                "unit_code": "PG101",
                "unit_name": "PostgreSQL Runtime Integration",
                "department": "Computer Science",
                "faculty": "Computing",
            },
        )
        self.assertEqual(response.status_code, 302)
        from modules.database import get_connection
        connection = get_connection("database/exam_integrity.db")
        try:
            unit = connection.execute(
                "SELECT unit_code, unit_name FROM academic_units WHERE unit_code=?",
                ("PG101",),
            ).fetchone()
            self.assertIsNotNone(unit)
            self.assertEqual(unit["unit_name"], "PostgreSQL Runtime Integration")
        finally:
            connection.close()

    def test_biometric_routes_fail_closed_without_provider(self):
        self._as_role("admin")
        response = self.client.post("/biometric/students/1/enrol")
        self.assertEqual(response.status_code, 503)


    def test_postgresql_scheduling_lock_serializes_competing_writers(self):
        from modules import operations
        from modules.database import get_connection
        operations.ensure_schema()
        first = get_connection("database/exam_integrity.db")
        operations._begin_scheduling_write(first)
        attempted = threading.Event()
        acquired = threading.Event()
        errors = []

        def competing_writer():
            second = get_connection("database/exam_integrity.db")
            try:
                attempted.set()
                operations._begin_scheduling_write(second)
                acquired.set()
                second.rollback()
            except Exception as error:
                errors.append(error)
            finally:
                second.close()

        worker = threading.Thread(target=competing_writer)
        worker.start()
        self.assertTrue(attempted.wait(2))
        self.assertFalse(acquired.wait(0.2), "PostgreSQL row lock must block the competing scheduler")
        first.commit()
        self.assertTrue(acquired.wait(5), "competing scheduler should proceed after the first commit")
        worker.join(5)
        first.close()
        self.assertFalse(errors)


if __name__ == "__main__":
    unittest.main()
