import os
import unittest
from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("EIMS_BROWSER_BASE_URL", "http://127.0.0.1:5000")


class BrowserSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1365, "height": 900})
        self.page = self.context.new_page()

    def tearDown(self):
        self.context.close()

    def test_public_home_and_staff_login_render(self):
        response = self.page.goto(BASE_URL + "/", wait_until="networkidle")
        self.assertEqual(response.status, 200)
        self.assertIn("Examination Integrity Management System", self.page.title())
        self.page.get_by_role("link", name="Staff sign in").click()
        self.page.wait_for_url("**/login")
        self.assertEqual(self.page.locator('meta[name="csrf-token"]').count(), 1)
        self.assertTrue(self.page.get_by_label("Username").is_visible())
        self.assertTrue(self.page.get_by_label("Password").is_visible())
        self.assertTrue(self.page.get_by_label("Role").is_visible())

    def test_invalid_staff_login_shows_generic_error_without_authentication(self):
        self.page.goto(BASE_URL + "/login", wait_until="networkidle")
        self.page.get_by_label("Username").fill("not-a-real-account")
        self.page.get_by_label("Password").fill("not-a-real-password")
        self.page.get_by_label("Role").select_option("admin")
        self.page.get_by_role("button", name="Sign in").click()
        self.page.get_by_role("alert").wait_for()
        self.assertIn("Invalid username or password", self.page.get_by_role("alert").inner_text())
        self.assertTrue(self.page.url.endswith("/login"))

    def test_student_login_page_is_reachable(self):
        self.page.goto(BASE_URL + "/login", wait_until="networkidle")
        self.page.get_by_role("link", name="Student portal sign in").click()
        self.page.wait_for_url("**/student/login")
        self.assertTrue(self.page.get_by_label("Admission number").is_visible())
        self.assertTrue(self.page.get_by_label("Password").is_visible())

    def test_login_page_fits_mobile_viewport_without_horizontal_overflow(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.goto(BASE_URL + "/login", wait_until="networkidle")
        dimensions = self.page.evaluate(
            "() => ({body: document.body.scrollWidth, viewport: document.documentElement.clientWidth})"
        )
        self.assertLessEqual(dimensions["body"], dimensions["viewport"])


if __name__ == "__main__":
    unittest.main()
