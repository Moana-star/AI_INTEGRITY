"""Provider-neutral, fail-closed biometric verification boundary.

This module does not capture, persist, template, or compare faces itself. A
university-approved provider adapter must be supplied explicitly. Verification
is disabled unless the deployment enables it AND records institutional
approval. The caller must obtain and validate a consent/alternative-process
record before invoking this service.

A successful face match is only an identity signal. It never grants exam
eligibility or writes attendance; those remain separate application decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


MAX_CAPTURE_BYTES = 5 * 1024 * 1024


class BiometricVerificationError(RuntimeError):
    """Base error for a fail-closed biometric verification request."""


class BiometricVerificationDisabled(BiometricVerificationError):
    """Raised when institutional approval or deployment configuration is absent."""


class BiometricProviderUnavailable(BiometricVerificationError):
    """Raised when no approved provider adapter is configured."""


class BiometricProvider(Protocol):
    def verify_one_to_one(
        self, *, capture: bytes, reference_id: str, purpose: str
    ) -> dict[str, Any]:
        """Compare a transient live capture to one claimed identity reference."""


@dataclass(frozen=True)
class VerificationOutcome:
    status: str
    provider: str | None
    provider_reference: str | None
    reason: str


def verify_one_to_one(
    *,
    provider: BiometricProvider | None,
    capture: bytes,
    reference_id: str,
    purpose: str,
    consent_record_id: str | None,
    deployment_enabled: bool,
    institutional_approval: bool,
) -> VerificationOutcome:
    """Run one-to-one verification without retaining the submitted capture.

    The approved provider is responsible for liveness detection and match
    quality. Ambiguous or malformed provider responses fail to manual review;
    provider exceptions fail closed. The capture bytes are passed only to the
    provider call and are not written to disk or returned in the outcome.
    """
    if not deployment_enabled or not institutional_approval:
        raise BiometricVerificationDisabled(
            "Biometric verification is not enabled and institutionally approved."
        )
    if not consent_record_id:
        raise BiometricVerificationDisabled(
            "A valid consent and alternative-process record is required."
        )
    if provider is None:
        raise BiometricProviderUnavailable(
            "No institution-approved biometric provider adapter is configured."
        )
    if not isinstance(capture, bytes) or not capture or len(capture) > MAX_CAPTURE_BYTES:
        raise ValueError("Capture must be non-empty bytes no larger than 5 MiB.")
    if not reference_id or not purpose:
        raise ValueError("A claimed identity reference and declared purpose are required.")

    try:
        result = provider.verify_one_to_one(
            capture=capture, reference_id=reference_id, purpose=purpose
        )
    except Exception as exc:
        raise BiometricProviderUnavailable(
            "The biometric provider could not complete verification; use manual review."
        ) from exc

    if not isinstance(result, dict):
        return VerificationOutcome(
            "manual_review", None, None, "Provider returned an invalid response."
        )

    matched = result.get("matched")
    live = result.get("liveness_passed")
    provider_name = result.get("provider")
    provider_reference = result.get("verification_reference")

    if matched is True and live is True:
        return VerificationOutcome(
            "verified",
            str(provider_name) if provider_name else "approved-provider",
            str(provider_reference) if provider_reference else None,
            "Provider reported a live one-to-one identity match.",
        )
    if matched is False or live is False:
        return VerificationOutcome(
            "failed",
            str(provider_name) if provider_name else "approved-provider",
            str(provider_reference) if provider_reference else None,
            "Provider did not confirm both identity match and liveness; refer to manual review.",
        )
    return VerificationOutcome(
        "manual_review",
        str(provider_name) if provider_name else None,
        str(provider_reference) if provider_reference else None,
        "Provider result was inconclusive; manual identity review is required.",
    )
