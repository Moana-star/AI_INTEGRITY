import unittest
from modules.eligibility import evaluate_annual_progression


class AnnualProgressionPolicyTests(unittest.TestCase):
    def test_all_courses_passed(self):
        result=evaluate_annual_progression(8,0,False)
        self.assertEqual(result["pathway"],"all_courses_passed")
        self.assertTrue(result["requires_institutional_approval"])

    def test_exactly_25_percent_failed_with_fee_is_supplementary_eligible(self):
        result=evaluate_annual_progression(8,2,True)
        self.assertEqual(result["pathway"],"supplementary_eligible")

    def test_exactly_25_percent_failed_without_fee_remains_pending(self):
        result=evaluate_annual_progression(8,2,False)
        self.assertEqual(result["pathway"],"pending_supplementary_fee")

    def test_more_than_25_percent_and_up_to_50_percent_repeats_year(self):
        self.assertEqual(evaluate_annual_progression(8,3,True)["pathway"],"repeat_academic_year")
        self.assertEqual(evaluate_annual_progression(8,4,True)["pathway"],"repeat_academic_year")

    def test_more_than_50_percent_requires_formal_review(self):
        result=evaluate_annual_progression(8,5,True)
        self.assertEqual(result["pathway"],"discontinuation_review_required")
        self.assertTrue(result["requires_institutional_approval"])

    def test_failed_supplementary_course_requires_repeat(self):
        self.assertEqual(evaluate_annual_progression(8,2,True,1)["pathway"],"repeat_failed_courses")

    def test_invalid_course_counts_are_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_annual_progression(0,0,False)
        with self.assertRaises(ValueError):
            evaluate_annual_progression(8,9,False)


if __name__ == "__main__":
    unittest.main()
