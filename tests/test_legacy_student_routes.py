import unittest

from app import app


class LegacyStudentRouteTests(unittest.TestCase):
    def setUp(self):
        self.previous_testing = app.config.get("TESTING")
        self.previous_csrf = app.config.get("WTF_CSRF_ENABLED")
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = app.test_client()

    def tearDown(self):
        app.config.update(
            TESTING=self.previous_testing,
            WTF_CSRF_ENABLED=self.previous_csrf,
        )

    def test_legacy_student_list_redirects_to_authoritative_registry(self):
        response = self.client.get("/admin/students")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/admin/registry/students"))

    def test_legacy_create_and_edit_urls_redirect_to_registry_forms(self):
        create = self.client.get("/admin/students/add")
        edit = self.client.get("/admin/students/edit/12")
        self.assertEqual(create.status_code, 302)
        self.assertTrue(create.headers["Location"].endswith("/admin/registry/students/new"))
        self.assertEqual(edit.status_code, 302)
        self.assertTrue(edit.headers["Location"].endswith("/admin/registry/students/12/edit"))

    def test_legacy_delete_is_disabled_and_redirects_to_registry(self):
        response = self.client.post("/admin/students/delete/12")
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/admin/registry/students"))


if __name__ == "__main__":
    unittest.main()
