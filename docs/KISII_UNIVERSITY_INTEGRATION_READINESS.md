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

No biometric provider has been selected. Camera preview is not facial recognition. Live capture, template creation, face matching and liveness checks remain disabled. A future integration requires provider due diligence, a DPIA, lawful-basis determination, data-processing agreement, retention/deletion controls, security testing and an equally usable manual alternative.

## University sign-off

Before any production integration, obtain written approval from the relevant ICT system owners, Registrar (Academic Affairs), Finance, the Data Protection Officer and the authorized institutional governance body.
