import unittest

from modules.access_control import ROLES, has_permission, normalize_role, permissions_for


class AccessControlTests(unittest.TestCase):
    def test_exactly_five_institutional_roles_are_defined(self):
        self.assertEqual(ROLES, {
            "admin", "registrar", "examination_officer", "invigilator", "student"
        })

    def test_admin_has_wildcard_permission(self):
        self.assertTrue(has_permission("admin", "any.future.permission"))

    def test_registrar_can_manage_registry_but_not_exams_or_incidents(self):
        self.assertTrue(has_permission("registrar", "registry.write"))
        self.assertTrue(has_permission("registrar", "academic_history.write"))
        self.assertFalse(has_permission("registrar", "exams.write"))
        self.assertFalse(has_permission("registrar", "incidents.review"))

    def test_examination_officer_can_schedule_and_review_but_not_edit_registry(self):
        self.assertTrue(has_permission("examination_officer", "sessions.write"))
        self.assertTrue(has_permission("examination_officer", "eligibility.evaluate"))
        self.assertTrue(has_permission("examination_officer", "appeals.review"))
        self.assertFalse(has_permission("examination_officer", "registry.write"))

    def test_invigilator_is_limited_to_assigned_exam_operations(self):
        self.assertTrue(has_permission("invigilator", "attendance.record"))
        self.assertTrue(has_permission("invigilator", "incidents.report_assigned"))
        self.assertFalse(has_permission("invigilator", "sessions.write"))
        self.assertFalse(has_permission("invigilator", "incidents.review"))

    def test_student_permissions_are_own_record_scoped(self):
        self.assertTrue(has_permission("student", "own_schedule.read"))
        self.assertTrue(has_permission("student", "own_incidents.appeal"))
        self.assertFalse(has_permission("student", "registry.read"))
        self.assertFalse(has_permission("student", "attendance.record"))

    def test_unknown_or_malformed_roles_fail_closed(self):
        for role in ("superuser", "", None, 7):
            self.assertIsNone(normalize_role(role))
            self.assertFalse(has_permission(role, "registry.read"))
            self.assertEqual(permissions_for(role), frozenset())

    def test_permission_checks_are_case_normalized_for_roles(self):
        self.assertTrue(has_permission(" Registrar ", "registry.read"))

    def test_complete_critical_permission_matrix_fails_closed(self):
        matrix = {
            "admin": (
                ("registry.write", "sessions.write", "attendance.record",
                 "incidents.review", "appeals.review", "own_profile.read"),
                (),
            ),
            "registrar": (
                ("registry.read", "registry.write", "academic_history.write",
                 "unit_enrolment.write", "student_status.write"),
                ("sessions.write", "attendance.record", "incidents.review",
                 "appeals.review", "reports.read"),
            ),
            "examination_officer": (
                ("exams.write", "sessions.write", "eligibility.evaluate",
                 "attendance.reconcile", "incidents.review", "appeals.review"),
                ("registry.write", "academic_history.write",
                 "attendance.record", "own_profile.read"),
            ),
            "invigilator": (
                ("assigned_sessions.read", "assigned_candidates.read",
                 "attendance.read_assigned", "attendance.record",
                 "incidents.report_assigned"),
                ("registry.read", "sessions.write", "attendance.reconcile",
                 "reports.read", "incidents.review", "appeals.review"),
            ),
            "student": (
                ("own_profile.read", "own_schedule.read", "own_attendance.read",
                 "own_incidents.respond", "own_incidents.appeal"),
                ("registry.read", "sessions.read", "attendance.record",
                 "incidents.review", "appeals.review"),
            ),
        }
        for role, (allowed, denied) in matrix.items():
            for permission in allowed:
                with self.subTest(role=role, permission=permission, expected=True):
                    self.assertTrue(has_permission(role, permission))
            for permission in denied:
                with self.subTest(role=role, permission=permission, expected=False):
                    self.assertFalse(has_permission(role, permission))
        self.assertFalse(has_permission("admin", ""))
        self.assertFalse(has_permission("student", "unlisted.future.permission"))


if __name__ == "__main__":
    unittest.main()
