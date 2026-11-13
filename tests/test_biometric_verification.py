import unittest

from modules.biometric_verification import (
    BiometricProviderUnavailable,
    BiometricVerificationDisabled,
    verify_one_to_one,
)


class FakeApprovedProvider:
    def __init__(self, result=None, error=None):
        self.result = result or {
            "matched": True,
            "liveness_passed": True,
            "provider": "test-provider",
            "verification_reference": "test-ref-001",
        }
        self.error = error
        self.calls = []

    def verify_one_to_one(self, *, capture, reference_id, purpose):
        self.calls.append((capture, reference_id, purpose))
        if self.error:
            raise self.error
        return self.result


class BiometricVerificationTests(unittest.TestCase):
    def setUp(self):
        self.args = {
            "capture": b"transient-test-capture",
            "reference_id": "institution-reference-123",
            "purpose": "exam-entry-identity-check",
            "consent_record_id": "consent-record-001",
            "deployment_enabled": True,
            "institutional_approval": True,
        }

    def test_disabled_without_both_approval_gates(self):
        with self.assertRaises(BiometricVerificationDisabled):
            verify_one_to_one(
                provider=FakeApprovedProvider(),
                **{**self.args, "institutional_approval": False},
            )

    def test_requires_consent_record(self):
        with self.assertRaises(BiometricVerificationDisabled):
            verify_one_to_one(
                provider=FakeApprovedProvider(),
                **{**self.args, "consent_record_id": None},
            )

    def test_requires_real_provider_adapter(self):
        with self.assertRaises(BiometricProviderUnavailable):
            verify_one_to_one(provider=None, **self.args)

    def test_positive_match_requires_liveness(self):
        provider = FakeApprovedProvider()
        result = verify_one_to_one(provider=provider, **self.args)
        self.assertEqual(result.status, "verified")
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(provider.calls[0][0], b"transient-test-capture")

    def test_failed_liveness_is_not_verified(self):
        provider = FakeApprovedProvider({
            "matched": True, "liveness_passed": False, "provider": "test-provider"
        })
        result = verify_one_to_one(provider=provider, **self.args)
        self.assertEqual(result.status, "failed")

    def test_inconclusive_provider_result_requires_manual_review(self):
        provider = FakeApprovedProvider({"matched": None, "liveness_passed": None})
        result = verify_one_to_one(provider=provider, **self.args)
        self.assertEqual(result.status, "manual_review")

    def test_provider_error_fails_closed(self):
        provider = FakeApprovedProvider(error=TimeoutError("provider timeout"))
        with self.assertRaises(BiometricProviderUnavailable):
            verify_one_to_one(provider=provider, **self.args)

    def test_empty_capture_is_rejected(self):
        with self.assertRaises(ValueError):
            verify_one_to_one(
                provider=FakeApprovedProvider(),
                **{**self.args, "capture": b""},
            )


if __name__ == "__main__":
    unittest.main()
