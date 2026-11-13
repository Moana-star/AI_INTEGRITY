import re
import unittest

from app import app as flask_app


class LegacyAdminNamespaceAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.previous = {
            "TESTING": flask_app.config.get("TESTING"),
            "SECRET_KEY": flask_app.config.get("SECRET_KEY"),
            "WTF_CSRF_ENABLED": flask_app.config.get("WTF_CSRF_ENABLED"),
        }
        flask_app.config.update(
            TESTING=True,
            SECRET_KEY="legacy-admin-matrix-test",
            WTF_CSRF_ENABLED=False,
        )
        self.client = flask_app.test_client()

    def tearDown(self):
        for key, value in self.previous.items():
            if value is None:
                flask_app.config.pop(key, None)
            else:
                flask_app.config[key] = value

    @staticmethod
    def legacy_admin_rules():
        for rule in flask_app.url_map.iter_rules():
            if not rule.rule.startswith("/admin"):
                continue
            if rule.rule.startswith("/admin/registry"):
                continue
            if rule.endpoint == "static":
                continue
            yield rule

    def test_every_legacy_admin_route_denies_non_admin_roles(self):
        rules = list(self.legacy_admin_rules())
        self.assertGreaterEqual(len(rules), 20)
        roles = ("registrar", "examination_officer", "invigilator", "student")
        failures = []
        for role in roles:
            for rule in rules:
                path = re.sub(r"<[^>]+>", "1", rule.rule)
                methods = set(rule.methods or ())
                methods.discard("HEAD")
                methods.discard("OPTIONS")
                with self.client.session_transaction() as state:
                    state.clear()
                    state["user_id"] = 77
                    state["student_id"] = 77 if role == "student" else None
                    state["role"] = role
                for method in sorted(methods & {"GET", "POST"}):
                    response = self.client.open(path, method=method, data={})
                    allowed_redirect = (
                        role == "invigilator"
                        and path == "/admin/incidents/add"
                        and response.status_code == 302
                        and "/operations/" in response.headers.get("Location", "")
                    )
                    if response.status_code not in {302, 403} and not allowed_redirect:
                        failures.append((role, method, path, response.status_code))
        self.assertEqual(failures, [])

if __name__ == "__main__":
    unittest.main()
