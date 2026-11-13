# Kisii University Integration Readiness

## Current position

No SIS, finance, institutional identity/SSO, staff directory or official email API specification or test credentials have been supplied. No connection to university production systems is configured. The EIMS must not scrape portals, reuse personal credentials, or assume undocumented endpoints.

## Integration contracts required from Kisii University ICT

For each system, obtain:
- System owner and technical contact.
- Approved API specification and version.
- Institution-owned sandbox/test tenant and synthetic test records.
- Authentication method, service-account owner, scopes and rotation process.
- Data dictionary, authoritative identifiers and field-level source of truth.
- Rate limits, pagination, retry and idempotency requirements.
- Webhook signing and replay-protection specification, if applicable.
- Network allowlists, TLS requirements, data residency and logging expectations.
- Data-sharing agreement, retention schedule and incident escalation contacts.

## Required source systems

| Integration | Minimum read-only contract | EIMS use |
|---|---|---|
| Student Information System | Student ID, admission number, programme, campus, status, cohort | Student registry and academic history |
| Course registration | Unit registration, semester, academic year, add/drop status | Candidate list and registration prerequisite |
| Finance | Authoritative fee-clearance status and effective timestamp | Eligibility evidence; never infer from uploaded receipts |
| LMS/attendance/CAT records | Course attendance totals and CAT participation/assessment record | Attendance and CAT eligibility evidence |
| Institutional identity | OIDC/SAML metadata, issuer, client registration, claims and logout/revocation | Staff/student SSO |
| Staff directory/HR | Employee ID, role, department, active status, lecturer assignment | Invigilator and role provisioning |
| University email/SMS | Approved notification API, sender identity, delivery status | Notices and audit of delivery |

## Security requirements

- Prefer read-only, least-privilege service accounts.
- Use stable university identifiers, idempotent upserts and reconciliation reports.
- Encrypt transport and secrets; redact personal data from logs.
- Store source-system ID, sync time, record version and import batch ID.
- Detect stale/conflicting records and route them to manual review.
- Support disconnect/credential revocation without deleting local audit history.
- Test cross-account and cross-role isolation with synthetic users.

## SSO readiness

The current application uses local staff/student login. It does not yet support Kisii University SSO. Do not label the login as university-authenticated until ICT has supplied and approved the identity provider configuration and end-to-end login/logout tests have passed.

## Biometric status

A provider-backed biometric enrolment and attendance workflow is now implemented on the development branch: student enrolment submits a transient capture to an injected provider adapter; invigilator check-in captures a live browser frame, validates the selected session candidate and eligibility, and records attendance only when the provider confirms both a one-to-one match and liveness. EIMS stores opaque provider references and append-only verification metadata, not face images or templates. The workflow has no mock provider and returns unavailable until an institution-approved provider is configured and both deployment approval gates are enabled. No provider has been selected, no credentials supplied and no live biometric verification is active. Activation requires provider due diligence, a DPIA, lawful-basis determination, data-processing agreement, retention/deletion controls, security testing, accuracy/liveness validation and an equally usable manual alternative.

## University sign-off

Before any production integration, obtain written approval from the relevant ICT system owners, Registrar (Academic Affairs), Finance, the Data Protection Officer and the authorized institutional governance body.


## Completion intake pack

See [Institutional Integration and Production Acceptance](INSTITUTIONAL_INTEGRATION_AND_PRODUCTION_ACCEPTANCE.md) for the exact technical, legal, provider, infrastructure and institutional evidence required to close the remaining work. No production credentials or biometric secrets should be sent through chat or committed to the repository.
