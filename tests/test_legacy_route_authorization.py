import unittest

from app import app as flask_app


class LegacyRouteAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.previous = {
            "TESTING": flask_app.config.get("TESTING"),
            "SECRET_KEY": flask_app.config.get("SECRET_KEY"),
            "WTF_CSRF_ENABLED": flask_app.config.get("WTF_CSRF_ENABLED"),
        }
        flask_app.config.update(
            TESTING=True,
            SECRET_KEY="legacy-route-auth-test",
            WTF_CSRF_ENABLED=False,
        )
        self.client = flask_app.test_client()
        with self.client.session_transaction() as state:
            state.clear()
            state["user_id"] = 42
            state["role"] = "invigilator"

    def tearDown(self):
        for key, value in self.previous.items():
            if value is None:
                flask_app.config.pop(key, None)
            else:
                flask_app.config[key] = value

    def test_invigilator_get_is_redirected_away_from_unscoped_legacy_student_picker(self):
        response = self.client.get("/admin/incidents/add")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/operations/", response.headers["Location"])

    def test_invigilator_post_cannot_submit_through_unscoped_legacy_incident_form(self):
        response = self.client.post("/admin/incidents/add", data={
            "student_id": "999",
            "examination_id": "999",
            "incident_type": "unauthorized legacy submission",
            "description": "Must not be accepted through the unscoped route.",
            "severity": "low",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/operations/", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
