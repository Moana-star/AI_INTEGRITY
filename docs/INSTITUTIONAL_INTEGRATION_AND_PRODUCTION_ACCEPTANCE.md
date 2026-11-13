# Institutional Integration and Production Acceptance Pack

**Status: blocked pending institutional owners, approved vendor contracts and controlled infrastructure.**

This is the intake checklist for completing the remaining EIMS work. It does not invent university APIs, provider credentials, legal approvals or production infrastructure.

## 1. PostgreSQL runtime conversion

The SQLite-to-PostgreSQL utility has been tested against PostgreSQL 16. That verifies data copying only. The Flask runtime still contains SQLite-specific connections, schema initialization, triggers and SQL. Do not set a PostgreSQL URL in production or remove the SQLite production guard until all of the following pass.

- [ ] One shared connection/transaction layer is used by app.py and every module.
- [ ] All runtime DDL is moved from request-time SQLite executescript calls into versioned, reviewed PostgreSQL migrations.
- [ ] SQLite-only PRAGMA, sqlite_master, last_insert_rowid, lastrowid, INSERT OR IGNORE, trigger syntax and table-upgrade logic are removed or replaced with explicit PostgreSQL equivalents.
- [ ] All application tests run against a disposable PostgreSQL database, not just SQLite.
- [ ] Tests cover transactions, rollback, concurrent attendance check-in, seat allocation races, uniqueness and isolation.
- [ ] Migration rehearsal includes a consistent source snapshot, row-count and key reconciliation, sequence validation, backup, rollback and restore.
- [ ] Cutover is rehearsed on a sanitized copy of the institution-authorized dataset.

## 2. Route and record-level authorization

- [ ] Run the route matrix for anonymous users and every role against every registered route and HTTP method.
- [ ] Test object-level ownership: student A cannot read or change student B's profile, attendance, response, appeal or review request.
- [ ] Test invigilator assignment boundaries across sessions, candidates, incident records, evidence, attendance and exports.
- [ ] Test registrar, examination officer, administrator and reviewer separation of duties.
- [ ] Test mass assignment, IDOR, CSRF, session fixation, stale/revoked sessions, brute-force controls and upload/download authorization.
- [ ] Obtain independent penetration test and remediate all critical/high findings.

The route matrix tests are regression controls, not a penetration test or proof of complete authorization.

## 3. Face verification — external approval gate

No face matching may be enabled until the university has selected and approved a provider. Required inputs from Kisii University:

- Provider legal name, product/service and technical documentation.
- Approved deployment architecture and supported SDK/API version.
- Institutional procurement approval and signed processor/data-processing agreement.
- Documented controller/processor roles, lawful basis, necessity/proportionality decision and DPIA approval by the university DPO/legal office.
- Approved privacy notice, student rights process, retention/deletion policy, breach process and meaningful non-biometric alternative.
- Provider sandbox tenant and test credentials supplied through an institution-approved secret manager. Never commit credentials or paste secrets into chat.
- One-to-one verification and liveness API contracts, error taxonomy, data residency, subprocessors, encryption and deletion guarantees.
- Independent performance evidence and supervised testing for false matches, false non-matches, demographic differences, spoof/presentation attacks and low-connectivity conditions.
- Signed operational approval for a limited pilot, named accountable owner and incident escalation process.

The EIMS adapter boundary must remain disabled until every required gate is approved. A biometric result is an identity signal only; it must not decide eligibility or misconduct. Manual/student-card verification must remain available without penalty.

## 4. Authoritative academic and finance integrations

The institution must provide, for each source system:

| Source | Required owner-approved interface | Required data |
|---|---|---|
| Student Information System | Versioned API/schema and read-only sandbox | Stable student ID, admission number, programme, campus, cohort, status |
| Course registration | API or controlled export contract | Unit registration, add/drop status, academic year, semester |
| Finance | Read-only fee-clearance endpoint | Clearance state, effective timestamp, source record/version |
| LMS / attendance / CAT | API or signed data-export contract | Attendance totals, CAT required/sat status, assessment identifiers |
| Staff directory / HR | Read-only API or signed export | Employee ID, active status, department, approved role |
| Institutional identity / SSO | OIDC or SAML metadata and test tenant | Issuer, client registration, scopes, claims, logout and revocation |
| University notifications | Approved email/SMS provider contract | Sender identity, delivery status and retry rules |

For each source the institution must also supply a data dictionary, stable identifiers, sandbox records, authentication method, scopes, pagination, rate limits, retry/idempotency rules, webhook signing specification if used, network restrictions, service-account lifecycle, data-sharing approval and named technical owner.

No scraping of university portals and no use of personal staff credentials. Until interfaces are approved, manual evidence entry with source references remains the controlled fallback; it is not an authoritative live integration.

## 5. Browser, accessibility and operational testing

- [ ] Chromium desktop and mobile browser smoke tests pass in CI.
- [ ] Complete role-specific end-to-end journeys using synthetic accounts.
- [ ] Test current supported browsers, low bandwidth, interrupted requests and duplicate submissions.
- [ ] Accessibility review: keyboard navigation, labels, focus order, contrast, screen-reader semantics and zoom.
- [ ] Load/concurrency test at institution-approved peak candidate and invigilator volumes.
- [ ] Security headers, TLS, secret rotation, centralized logs, alerting and incident response are verified in the target environment.

The Chromium smoke job covers public landing, staff sign-in, student sign-in and a mobile viewport only. It is not complete workflow, accessibility, load or cross-browser acceptance.

## 6. Backup, recovery and deployment

Required infrastructure and operations owner inputs:

- [ ] Institution-approved PostgreSQL host/service, version, network route and connection policy.
- [ ] Secret manager and rotation owner; do not place database credentials in repository files or CI logs.
- [ ] Encrypted backup destination, retention period, encryption-key custody and off-site/region policy.
- [ ] Agreed recovery point objective (RPO) and recovery time objective (RTO).
- [ ] Automated backup verification and scheduled restore drills into an isolated environment.
- [ ] Evidence-file backup and database/evidence consistency procedure.
- [ ] Production WSGI/container configuration, TLS termination, domain, monitoring and on-call owner.
- [ ] Rollback/cutover plan and a signed go/no-go decision.

## 7. Formal institutional acceptance

Required approvals before live student data or examinations:

- Registrar (Academic Affairs): current examination policy, eligibility and progression rules.
- ICT: architecture, APIs, identity, infrastructure and security operations.
- Finance: fee-clearance source and semantics.
- Data Protection Officer and legal office: DPIA, lawful basis, privacy notices and vendor processing.
- Procurement/vendor owner: provider contracts and support commitments.
- Examination office and invigilator representatives: operational workflow and exception handling.
- Accessibility/student support representatives: accessible process and non-biometric alternative.
- Authorized university governance body: pilot and production go-live approval.

## 8. Evidence required to close this pack

Each checklist item must be supported by a test report, signed approval, versioned API contract, deployment record or recovery drill record. A checked box without evidence is not accepted as completion.

**Current disposition:** development branch only; synthetic data only; production startup guard remains enabled; no biometric provider or institutional source-system connection is active; no production deployment or university acceptance is claimed.
