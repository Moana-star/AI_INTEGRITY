import re
import unittest
from unittest.mock import patch

import app as application


class PasswordRecoverySecurityTests(unittest.TestCase):
    def setUp(self):
        application.app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        self.client = application.app.test_client()

    def csrf_token(self):
        response = self.client.get("/forgot-password")
        match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', response.data)
        self.assertIsNotNone(match, "shared layout must render a CSRF token")
        return match.group(1).decode("utf-8")

    def test_state_changing_request_without_csrf_token_is_rejected(self):
        response = self.client.post("/forgot-password", data={"username": "admin"})
        self.assertEqual(response.status_code, 400)

    def test_forgot_password_does_not_create_username_authorized_reset(self):
        response = self.client.post(
            "/forgot-password",
            data={"username": "admin", "csrf_token": self.csrf_token()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"self-service password recovery is not available", response.data.lower())
        with self.client.session_transaction() as browser_session:
            self.assertNotIn("password_reset_user_id", browser_session)

    def test_legacy_reset_endpoint_never_changes_a_password(self):
        with self.client.session_transaction() as browser_session:
            browser_session["password_reset_user_id"] = 1
        with patch.object(application, "get_db_connection", side_effect=AssertionError("database must not be accessed")):
            response = self.client.post(
                "/reset-password",
                data={
                    "password": "AttackerControlledPassword123!",
                    "confirm_password": "AttackerControlledPassword123!",
                    "csrf_token": self.csrf_token(),
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No password has been changed", response.data)
        self.assertNotIn(b'name="password"', response.data)


if __name__ == "__main__":
    unittest.main()
