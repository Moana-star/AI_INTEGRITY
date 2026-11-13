import unittest
from app import app


class SecurityHeaderTests(unittest.TestCase):
    def test_application_sets_browser_security_headers(self):
        app.config.update(TESTING=True, SECRET_KEY="security-header-test")
        response = app.test_client().get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("camera=(self)", response.headers.get("Permissions-Policy", ""))


if __name__ == "__main__":
    unittest.main()
