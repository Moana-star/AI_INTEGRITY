# EIMS Institutional Development Roadmap

## Product direction

EIMS is being evolved from a local academic application into an institutional examination operations platform. The target is a system that a university can evaluate and pilot after governance, security, integration, and operational requirements have been satisfied.

**This roadmap is not a claim that the application is already approved or production-ready.** The current repository remains an implementation in progress. Use synthetic data during development and testing.

## Product principles

1. The admission number is the unique institutional student identifier.
2. Authoritative academic records should come from the university registry or an approved export.
3. Examination eligibility must be based on explicit, reviewable registration rules.
4. Attendance and identity verification are separate records with clear provenance.
5. Incident reports document observations and evidence; they do not establish guilt.
6. Risk indicators support authorized human review and never make disciplinary decisions.
7. Every sensitive administrative change should be attributable and auditable.
8. Collect only information needed for a defined institutional purpose.
9. Students must have a process to challenge inaccurate identity, attendance, or incident records.
10. Biometric processing remains disabled until institutional authorization and privacy governance are complete.

## Delivery phases

### Phase 1 — Student registry foundation

**Status: Initial implementation added on the feature branch.**

- Extended student profile records linked to the existing student table.
- Admission-number-based student register.
- Academic placement and status fields.
- Institutional contact fields.
- CSV onboarding for authorized student records.
- Academic unit and enrolment schema foundation.
- Audit-event and examination-attendance schema foundation.

Remaining phase-one work:
- Automated route and authorization tests.
- Unit catalogue and student enrolment screens.
- CSV export, import preview, and reconciliation report.
- Field-level validation and institutional data mapping.
- Formal data migration and rollback procedure.

### Phase 2 — Examination operations

- Academic years, semesters, programmes, departments, and units.
- Examination sessions with dates, times, venue, capacity, and status.
- Candidate eligibility and session registration.
- Seat allocation and invigilator assignments.
- Session-level operational controls.

### Phase 3 — Attendance and identity assurance

- Session attendance register with present, absent, late, and disputed states.
- Check-in and check-out timestamps.
- Manual and student-card verification.
- Exception queue for identity mismatches.
- Device and invigilator attribution.
- Optional biometric provider integration only after formal approval, DPIA, lawful-basis review, accuracy testing, alternatives, retention controls, and security review.

### Phase 4 — Integrity case management

- Structured incident reports and evidence references.
- Chain-of-custody events and evidence access history.
- Student response and correction workflow.
- Reviewer assignment, decisions, appeals, and referrals.
- Immutable or tamper-evident audit design.

### Phase 5 — Reporting and decision support

- Attendance and examination operations reports.
- Incident volumes and outcomes.
- Transparent, configurable review indicators.
- Bias, accuracy, and impact evaluation for any statistical models.
- No automated finding of misconduct or disciplinary action.

### Phase 6 — Institutional readiness and deployment

- PostgreSQL migration and managed database operations.
- Authentication integration, MFA, and least-privilege authorization.
- CSRF protection, secure session policy, rate limiting, and security testing.
- Encryption, backup/restore, monitoring, incident response, and disaster recovery.
- Data protection impact assessment and institutional sign-off.
- Accessibility and usability testing.
- Controlled pilot, training, support, and documented operating procedures.

## Current implementation boundaries

The first registry increment does not provide:
- A live connection to any university student information system.
- Verified official student data.
- Examination eligibility decisions.
- A complete unit registration workflow.
- An operational attendance interface.
- Face detection, face matching, liveness detection, or biometric template storage.
- Production-grade authentication, hosting, or institutional security certification.

Do not represent these capabilities as implemented until their code, tests, integrations, and operational controls have been completed and verified.
