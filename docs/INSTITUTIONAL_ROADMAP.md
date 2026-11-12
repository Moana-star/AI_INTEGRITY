# EIMS Institutional Development Roadmap

## Product direction

EIMS is being developed as a configurable university examination operations platform. The current feature branch adds connected student, academic, examination, attendance, student self-service, and incident-review workflows. It is still a development build and must not be used with real student data until the readiness gates in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) are completed.

## Product principles

1. Admission number is the unique institutional student identifier.
2. Authoritative academic records must come from the institution or an approved import.
3. Eligibility must be based on explicit, reviewable enrolment rules.
4. Attendance and identity verification are distinct, auditable records.
5. Incident reports document observations; they do not establish guilt.
6. Students can respond to incidents when a response is requested.
7. Review indicators never make disciplinary decisions.
8. Sensitive data is collected only for a defined institutional purpose.
9. Biometric processing remains disabled until institution approval and privacy governance are complete.

## Current implementation status

### Phase 1 — Student registry

**Implemented on the feature branch; needs full local and security verification.**

- Admission-number-based student registry and profiles.
- Academic placement and status fields.
- Institutional contact fields.
- UTF-8 CSV import with validation and row-level savepoints.
- Student profile audit events.

Remaining: import preview/reconciliation, data mapping, migration/rollback plan, broader authorization tests.

### Phase 2 — Academic and examination operations

**Core workflows implemented on the feature branch; further capabilities remain.**

- Academic unit catalogue creation.
- Student unit enrolment by academic year and semester.
- Examination session creation linked to an existing examination.
- Candidate lists derived from registered active enrolments.
- Venue registration and candidate-capacity validation.
- Invigilator assignment.
- Sequential seat labels.
- Session status lifecycle.

Remaining: programme/course catalogue normalization, timetable conflict detection, venue scheduling conflict detection, room layout and seat-map configuration, eligibility exceptions, invigilator workload rules, and session completion sign-off.

### Phase 3 — Attendance and identity assurance

**Manual/student-card attendance workflow implemented; biometric verification is not implemented.**

- Session-specific candidate attendance register.
- Check-in and check-out timestamps.
- Manual and student-card verification method recording.
- Duplicate check-in/check-out prevention.
- Invigilator attribution and audit events.
- Student view of examination schedule, seat and attendance.

Remaining: absent/disputed attendance resolution, attendance export and reconciliation, card barcode/QR validation, device registration, offline operation design, exception handling and end-to-end testing.

Biometric identity verification requires an approved provider, institutional authorization, DPIA, lawful-basis review, meaningful alternative, demographic accuracy evaluation, security assessment and retention controls. No face data is captured or matched by this code.

### Phase 4 — Integrity case management

**Initial review and evidence workflows implemented; full case management remains.**

- Case workflow statuses: reported, under review, student response requested, reviewed, resolved, dismissed and referred.
- Reviewer notes and status history.
- Student portal response submission when requested.
- Restricted PDF/PNG/JPEG evidence upload.
- Private evidence storage outside the public static directory.
- SHA-256 evidence checksum.
- Administrator-only evidence download with access audit event.

Remaining: formal chain-of-custody procedures, evidence retention/deletion tooling, reviewer assignment, witness statements, appeal workflow, student notifications, response deadlines, legal hold and tamper-evident external audit storage.

### Phase 5 — Reporting and decision support

**Partially inherited from the original application; institutional reporting remains incomplete.**

- Existing incident summaries and transparent rule-based review indicators remain.
- Existing dashboard and report views remain available.

Remaining: session attendance rates, absent/late/disputed breakdowns, eligibility and enrolment reconciliation, venue utilization, invigilator workload, case outcomes, semester comparisons, CSV/PDF exports and validated data-quality reporting.

No automated model should infer guilt or make a disciplinary decision.

### Phase 6 — Institutional readiness and deployment

**Not complete.**

- PostgreSQL migration and managed database operations.
- University SIS integration and reconciliation.
- Institutional identity provider, MFA and least-privilege roles.
- CSRF protection, rate limiting, secure session policy and security testing.
- Evidence encryption, backups, restore drills, monitoring and incident response.
- DPIA, legal review, retention schedule and institutional sign-off.
- Accessibility and user-acceptance testing.
- Controlled pilot, training and support.

## Configurability

The current code does not hard-code Kisii University admission formats or institutional SIS endpoints. Institution-specific admission rules, academic calendars, course structures, identity providers and integration contracts must be configured from authorized institutional specifications.

## Non-negotiable safety boundary

A face match, risk category, attendance anomaly or incident report must never independently establish misconduct, determine guilt, or trigger a disciplinary sanction.
