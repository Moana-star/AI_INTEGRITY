# Biometric Identity and Examination Attendance Integration

## Implemented application workflow

This increment adds an institution-gated, provider-backed workflow on
`feature/eims-institutional-completion`:

- Student Registry has a provider-backed enrolment submission endpoint.
- The approved provider receives the transient capture and returns an opaque
  enrolment reference. EIMS stores the reference, consent/alternative-process
  record ID, approval reference and staff audit metadata only.
- The invigilator identity station captures a live frame from the browser camera.
- The claimed student is looked up in the selected examination candidate list.
- The system checks session status, candidate eligibility, active enrolment and
  invigilator assignment before calling the provider.
- Only a provider response with both `matched=true` and
  `liveness_passed=true` can create biometric check-in attendance.
- Failed or inconclusive results are recorded as verification events and do
  not create attendance.
- Duplicate check-ins are rejected.
- Biometric verification events are append-only. Revocation is audited.
- EIMS does not store the captured image or face template.

## Explicit non-demo safety behaviour

There is no built-in/mock provider and no fallback that fabricates a match.
Until the deployment injects a real, approved provider and both institutional
gates are explicitly enabled, biometric endpoints return HTTP 503. The manual
identity route remains available.

## Provider adapter contract

The deployment must configure `app.config["BIOMETRIC_PROVIDER"]` with an
institution-approved adapter implementing:

```python
def enrol_one_to_one(*, capture: bytes, student_reference: str,
                     purpose: str, consent_record_id: str) -> dict:
    # Return {"reference_id": "...", "provider": "..."}
    ...

def verify_one_to_one(*, capture: bytes, reference_id: str,
                      purpose: str) -> dict:
    # Return {"matched": bool, "liveness_passed": bool,
    #         "provider": "...", "verification_reference": "..."}
    ...
```

The provider must perform secure template creation, presentation-attack
detection/liveness, one-to-one matching, secure deletion, and provider-side
retention controls. Do not return face images, embeddings or templates to EIMS.
Provider timeouts, errors, malformed responses and inconclusive results must
never result in attendance.

The deployment must explicitly set both:
- `BIOMETRIC_ENABLED = True`
- `BIOMETRIC_INSTITUTIONAL_APPROVAL = True`

These are deployment-controlled gates, not values to enable in a developer
environment. No provider is currently selected or configured in this project.

## Database and attendance behaviour

The operations schema now permits `biometric` as an attendance verification
method. Existing SQLite `attendance_events` tables are upgraded in place by
copying all prior event rows into the expanded constraint table before dropping
the legacy table. Existing attendance history is preserved.

The `biometric_enrolments` table stores opaque provider references only.
`biometric_verification_events` stores outcome, provider metadata, reason,
session/student identifiers, actor and timestamp. It is append-only.

## Required before any real student enrolment

1. Kisii University written authorization and approved DPIA/privacy review.
2. Confirmed lawful basis, student notice, consent/alternative-process design,
   retention and deletion schedule, data residency and breach response.
3. Signed provider data-processing agreement and security review.
4. Provider test tenant, credentials, API documentation and an implemented
   adapter with timeout/retry and idempotency behaviour.
5. Browser, device, lighting, demographic performance, liveness, spoof,
   accessibility and manual fallback testing.
6. End-to-end tests with institution-approved synthetic identities.
7. Registrar, ICT and Data Protection Officer acceptance before production.

## Important limitations

The application routes and browser capture are implemented, but real biometric
matching is not active because no approved provider, provider credentials or
institutional authorization have been supplied. This is intentionally not
described as a finished live biometric deployment.
