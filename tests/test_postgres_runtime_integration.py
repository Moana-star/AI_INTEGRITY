import os
import unittest

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
        finally:
            connection.close()

    def test_biometric_routes_fail_closed_without_provider(self):
        self._as_role("admin")
        response = self.client.post("/biometric/students/1/enrol")
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
