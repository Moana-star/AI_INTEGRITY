import unittest
from modules.appeals import within_senate_review_period


class SenateReviewDeadlineTests(unittest.TestCase):
    def test_request_on_communication_date_is_within_period(self):
        self.assertTrue(within_senate_review_period("2026-11-01","2026-11-01"))

    def test_request_on_day_21_is_within_period(self):
        self.assertTrue(within_senate_review_period("2026-11-01","2026-11-22"))

    def test_request_on_day_22_is_outside_period(self):
        self.assertFalse(within_senate_review_period("2026-11-01","2026-11-23"))

    def test_request_before_communication_date_is_invalid(self):
        self.assertFalse(within_senate_review_period("2026-11-01","2026-10-31"))

    def test_invalid_dates_are_rejected(self):
        self.assertFalse(within_senate_review_period("not-a-date","2026-11-01"))


if __name__ == "__main__":
    unittest.main()
