# EIMS Production Readiness Gate

**Status: Not production-ready. Do not process real student data or deploy for a live examination.**

This checklist distinguishes implemented development workflows from the work required before a university can responsibly operate the system.

## Implemented on the current feature branch

- Admission-number-based student registry and CSV import.
- Academic unit creation and student enrolment.
- Examination sessions and candidate lists derived from enrolments.
- Venue registration, capacity checks and invigilator assignment.
- Seat labels and manual/student-card attendance check-in/check-out.
- Session-scoped attendance CSV export restricted to administrators, with an audit event and no-store response headers.
- Post-session reconciliation that flags missing check-ins as disputed for human review; it does not automatically declare students absent.
- Minimal `/healthz` database readiness endpoint that returns no connection details.
- Student portal accounts provisioned by an administrator, with forced first-login password change.
- Student access to their own profile, enrolments, sessions, attendance and incident notices.
- Student response submission when an authorized reviewer requests a response.
- Incident workflow statuses and review notes.
- Records the staff reporter and prevents that same account from changing the case review status (initial conflict-of-interest safeguard).
- Private evidence file storage, file-size/type checks, SHA-256 checksums and administrator-only download audit.
- Automated Python compilation and unit-test workflow.

## Security hardening already applied on this branch

- The legacy username-only password-recovery flow has been disabled. Knowing or guessing a username must never authorize a password change.
- The password-reset page no longer accepts a new password until a verified institutional recovery channel is integrated.
- Flask-WTF CSRF validation is enabled for unsafe HTTP requests. The shared layout exposes a session-bound token, and the form helper attaches it to standard and dynamically submitted forms.
- Staff and student login endpoints are limited to five attempts per minute per source IP. Production startup requires a shared Redis-compatible `RATELIMIT_STORAGE_URI`; the in-memory fallback is for local development only.
- Regression tests cover missing CSRF tokens and attempts to use the former reset flow, including a forged legacy reset-session value.

These are targeted security improvements, not a substitute for the remaining controls below. MFA, complete RBAC, secure session lifecycle, account-level throttling/lockout policy, and comprehensive authorization testing remain required.

## Required before any real student data

### Institutional and legal approval

- [ ] Identify the data controller and processor roles and sign appropriate agreements.
- [ ] Obtain written institutional authorization and data-owner approval.
- [ ] Complete a DPIA and legal/privacy review.
- [ ] Approve a data inventory, purpose, lawful basis, retention and deletion schedule.
- [ ] Approve student notices, access/correction requests and complaint procedures.
- [ ] Confirm institutional security and procurement requirements.

### Security engineering

- [ ] Replace SQLite with a supported PostgreSQL deployment and test migrations.
- [x] Implement CSRF protection for state-changing requests; verify every page and non-form client integration during end-to-end testing.
- [x] Add IP-based login rate limits for staff and student sign-in; configure shared Redis-compatible storage before production.
- [ ] Add account-level throttling/lockout policy and MFA for privileged roles.
- [ ] Replace broad administrator/invigilator roles with least-privilege registrar, examination officer, invigilator, reviewer and system-administrator permissions.
- [ ] Enforce password reset, recovery, session expiration and session revocation policies.
- [ ] Configure persistent high-entropy secrets and HTTPS-only secure cookies.
- [ ] Encrypt database backups and evidence storage at rest; manage keys separately.
- [ ] Add malware scanning and content-disarm review for uploaded evidence.
- [ ] Add retention enforcement, secure deletion, legal holds and evidence access reviews.
- [ ] Perform dependency, SAST, DAST, penetration and authorization testing.
- [ ] Add structured security logging, monitoring, alerting and incident response.

### Data and integration

- [ ] Obtain an approved student-information-system data dictionary and integration contract.
- [ ] Validate import files against authoritative records and reconcile rejected rows.
- [ ] Implement timetable and venue conflict detection.
- [ ] Validate examination eligibility with the registrar's approved rules.
- [ ] Implement attendance exception resolution, absent/disputed statuses and signed session close-out.
- [ ] Add institution-approved staff and student identity lifecycle management.
- [ ] Test concurrent use with realistic examination sizes and unreliable network conditions.

### Biometric identity verification — separately gated

- [ ] Written institutional approval and completed DPIA.
- [ ] Approved provider, processor agreement and data-location/security assessment.
- [ ] Documented lawful basis, necessity and proportionality.
- [ ] Meaningful non-biometric alternative that does not disadvantage students.
- [ ] Independent false-match/false-non-match and demographic performance testing.
- [ ] Liveness/presentation-attack assessment and human exception review.
- [ ] Defined template retention, revocation and deletion controls.
- [ ] Security test and supervised pilot approval.

**The current application does not perform face detection, face matching or liveness detection.** No biometric verification outcome should be inferred from the attendance method fields.

### Operational assurance

- [ ] Complete end-to-end tests for each role and workflow.
- [ ] Complete accessibility and usability testing with representative users.
- [ ] Configure production WSGI hosting, TLS, monitoring and managed secrets.
- [ ] Perform backup restoration and disaster-recovery drills.
- [ ] Train administrators, registrars, invigilators and reviewers.
- [ ] Run a limited pilot with synthetic or explicitly authorized data.
- [ ] Obtain formal go-live approval from the institution.

## Current technical limitations

- The application still uses SQLite and raw SQLite access throughout the legacy application.
- The student/staff role model is not yet a complete institutional RBAC model.
- CSRF validation and IP-based login rate limiting are enabled. Production must configure shared Redis-compatible rate-limit storage; account-level lockout and MFA remain outstanding.
- Evidence files are private by path and access control, but encrypted storage, malware scanning and retention automation are not yet implemented.
- The current test suite is a small automated foundation, not comprehensive coverage.
- The biometric provider is not connected.
- No university SIS integration or institutional deployment is configured.

A successful unit-test workflow does not certify production security, legal compliance, or operational readiness.
