import re
import unittest

from app import app as flask_app


class BlueprintAuthorizationMatrixTests(unittest.TestCase):
    DENIED_ROLE_BY_BLUEPRINT = {
        "registry": "examination_officer",
        "operations": "student",
        "eligibility": "invigilator",
        "integrity": "registrar",
        "appeals": "invigilator",
        "identity": "registrar",
        "biometric_attendance": "student",
    }

    def setUp(self):
        self.previous = {
            "TESTING": flask_app.config.get("TESTING"),
            "SECRET_KEY": flask_app.config.get("SECRET_KEY"),
            "WTF_CSRF_ENABLED": flask_app.config.get("WTF_CSRF_ENABLED"),
        }
        flask_app.config.update(
            TESTING=True,
            SECRET_KEY="blueprint-auth-matrix-test",
            WTF_CSRF_ENABLED=False,
        )
        self.client = flask_app.test_client()

    def tearDown(self):
        for key, value in self.previous.items():
            if value is None:
                flask_app.config.pop(key, None)
            else:
                flask_app.config[key] = value

    def test_every_protected_blueprint_route_rejects_a_role_outside_its_boundary(self):
        failures = []
        checked = 0
        for rule in flask_app.url_map.iter_rules():
            blueprint = rule.endpoint.split(".", 1)[0] if "." in rule.endpoint else None
            role = self.DENIED_ROLE_BY_BLUEPRINT.get(blueprint)
            if role is None:
                continue
            path = re.sub(r"<(?:[^:>]+:)?[^>]+>", "1", rule.rule)
            methods = set(rule.methods or ()) & {"GET", "POST", "PUT", "PATCH", "DELETE"}
            for method in sorted(methods):
                with self.client.session_transaction() as state:
                    state.clear()
                    state["user_id"] = 991
                    state["student_id"] = 991 if role == "student" else None
                    state["role"] = role
                response = self.client.open(path, method=method, data={})
                checked += 1
                if response.status_code not in {302, 403}:
                    failures.append((blueprint, role, method, path, response.status_code))
        self.assertGreaterEqual(checked, 30, "Authorization matrix should cover all registered protected routes.")
        self.assertEqual(failures, [])

    def test_all_protected_blueprints_reject_anonymous_requests(self):
        failures = []
        checked = 0
        for rule in flask_app.url_map.iter_rules():
            blueprint = rule.endpoint.split(".", 1)[0] if "." in rule.endpoint else None
            if blueprint not in self.DENIED_ROLE_BY_BLUEPRINT:
                continue
            path = re.sub(r"<(?:[^:>]+:)?[^>]+>", "1", rule.rule)
            methods = set(rule.methods or ()) & {"GET", "POST", "PUT", "PATCH", "DELETE"}
            for method in sorted(methods):
                with self.client.session_transaction() as state:
                    state.clear()
                response = self.client.open(path, method=method, data={})
                checked += 1
                if response.status_code not in {302, 403}:
                    failures.append((blueprint, method, path, response.status_code))
        self.assertGreaterEqual(checked, 30)
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
