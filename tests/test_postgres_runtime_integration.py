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

    def test_biometric_routes_fail_closed_without_provider(self):
        self._as_role("admin")
        response = self.client.post("/biometric/students/1/enrol")
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
