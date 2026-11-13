# Institutional EIMS Completion Plan

**Branch:** `feature/eims-institutional-completion`  
**Base:** `feature/institutional-eims-foundation`  
**Status:** Active development plan. This document is not a declaration of production readiness.

## Delivery rules

1. Keep all work on this feature branch until code, tests, browser acceptance and owner review are complete.
2. Never use real student records in development or automated tests.
3. A feature is complete only when its workflow, authorization, failure paths, audit events and automated/browser tests pass.
4. Keep academic eligibility, identity verification and attendance as separate decisions.
5. External integrations require institution-owned credentials, technical specifications, an approved data-sharing basis and a named institutional owner.
6. Do not enable biometric processing in production without institutional approval, a completed DPIA, documented lawful basis and notice/consent process as advised by the institution, a non-biometric alternative, provider security review and retention/deletion controls.

## Workstreams and acceptance gates

### 1. Student information and academic history
- Student profile and registry fields are available in the existing institutional registry increment.
- Added append-only academic-history events for programme changes, deferments, suspensions, progression, status changes and graduation, with effective dates, reasons and recording user.
- SQLite triggers reject updates and deletes to recorded history; corrections must be recorded as a new event.
- Remaining: history workflow browser tests, richer programme/cohort structure, and policy-approved validation of each event type.
- Add controlled unit registration, add/drop windows, prerequisite checks, duplicate prevention and completion history.
- Restrict updates by role and retain before/after audit metadata without copying sensitive values into logs.
- Acceptance: a registrar can create and amend a synthetic student record; academic history is chronological; duplicate unit registration and invalid status transitions are rejected; a student can see only their own permitted record.

### 2. Timetable and examination sessions
- Added generated venue row/seat layouts with explicit accessible-seat labels.
- Added Registrar/Admin accommodation records containing only approved accessible-seat and extra-time flags plus a source reference; no diagnosis is collected.
- Accommodation changes are retained in append-only history. Session seat allocation reserves accessible seats for approved accommodations and carries approved extra time into the invigilator station.
- Session activation now requires an active venue within capacity and at least two active invigilators, based on the published handbook.
- Existing scheduling checks detect candidate, venue and invigilator overlaps.
- Remaining: calendar/list views, bulk import, rescheduling, cancellation history, concurrency-safe reservations, room closure, setup buffers, lecturer-as-chief-invigilator mapping and browser acceptance.
- Acceptance: conflicting reservations cannot be committed, and rescheduling/cancellation creates an attributable audit event.

### 3. Eligibility verification
- Added a versioned eligibility policy engine and officer workspace.
- Policy drafts require an official policy/source reference; approval is restricted to a different administrator from the creator.
- Public source mapping is documented in docs/KISII_UNIVERSITY_POLICY_MAPPING.md using the Kisii University Student Handbook (2019) and Kisii University Statutes, 2020.
- Policy drafts now support active academic status, registered unit, fee clearance, minimum attendance percentage (draft default 80%) and minimum CAT count (draft default 2).
- Authorized staff can record source-referenced lecture attendance, CAT and fee-clearance evidence. Missing evidence remains pending; unmet approved criteria produce explainable ineligible results.
- Evidence versions and eligibility decisions are append-only. Legacy policy JSON that lacks the current rule set fails closed to pending.
- The 80% and two-CAT defaults are drawn from the 2019 handbook and are not automatically approved. A second administrator must approve a policy draft; the Registrar must confirm that the 2019 handbook remains current.
- Record rule version, evidence source, result and review reason.
- New session candidates now begin as pending. Attendance is blocked until an effective approved policy has been evaluated and the decision has been applied to that scheduled session.
- Candidate-list refresh resets scheduled candidates to pending so stale eligibility is not silently reused.
- Acceptance: eligible, pending and ineligible states are explainable and reproducible; a rule change does not silently rewrite historical decisions.

### 4. Venue, seating and invigilator allocation
- Added configurable venue row/seat layouts, accessible seat flags and accommodation-aware allocation.
- Approved accommodations are stored as minimal flags and an official reference; the history of changes is retained.
- Added a two-active-invigilator minimum before a session can be activated.
- Remaining: staff ratios/qualifications, layout version history, seat swap/override workflow, concurrency-safe booking and complete browser acceptance.
- Acceptance: allocation respects capacity and approved accommodations; manual overrides require a reason and audit record.

### 5. Attendance interface
- Provide a responsive invigilator station with candidate search/scan, check-in, check-out, duplicate-event protection and offline-safe exception capture.
- Do not equate an ID or face match with eligibility.
- Attendance recording now requires an explicit eligible candidate status; pending or ineligible candidates cannot be checked in.
- Acceptance: only assigned staff can record attendance for their session; duplicate and out-of-session events are rejected; reconciliation flags missing events for human review.

### 6. Student ID verification
- Added a session-scoped candidate identity review page. It shows only candidates attached to the selected examination session.
- Invigilators can open the page only for sessions assigned to their account; admin and examination officers have authorized staff access.
- Added an optional browser camera preview that requests permission only after a user click. It does not capture, upload, compare, template or store face images.
- The page explicitly distinguishes visual preview from identity proof, eligibility and attendance. Manual identity procedures remain the only active verification route.
- Remaining: institution-approved student-card/QR credential validation, signed-token anti-replay, and audited verification outcomes after university policy and credential specifications are supplied.

### 7. Biometric verification
- A provider-neutral boundary is introduced in `modules/biometric_verification.py`. It requires deployment enablement, institutional approval, a consent/alternative-process record and an explicitly supplied provider adapter.
- A preview-only camera interface exists in `modules/identity_check.py` and `static/js/camera_preview.js`; it performs no biometric capture or matching.
- The boundary supports one-to-one verification only; it requires both match and liveness success and fails closed on provider errors or inconclusive responses.
- It does not store captures or create face templates. No provider is currently configured and no live camera route is enabled.
- Before a real integration: select a university-approved provider; obtain its API documentation, data residency/security details, DPA, liveness/matching semantics, retention policy and test credentials; complete DPIA and institutional approval.
- Acceptance: sandbox tests cover true/false/inconclusive outcomes, liveness failure, timeout, provider outage, consent withdrawal, manual fallback, data deletion and audit logging. No biometric result alone can deny exam access or determine misconduct.

### 8. Incident investigation and evidence
- Added a separate student appeal record and staff appeal queue.
- Student appeals are accepted only for a final recorded case outcome and only for the authenticated student's own incident.
- The original reporter and last recorded case reviewer are prevented from deciding the appeal.
- Appeal events are append-only; independent outcomes are stored separately and do not silently rewrite the original incident record.
- Added a separate Senate-verdict register and student review request route. The recorded communication date controls the 21-calendar-day submission window stated in the 2019 handbook; tests cover day 21 and day 22.
- The Senate review queue records requests but does not adjudicate them; only the Senate or its authorized committee can decide.
- Remaining: Senate committee membership/assignment, evidence uploads, acknowledgement/notifications, formal review outcome capture and full due-process browser tests.
- Evidence chain-of-custody hardening, malware scanning, private object storage and retention/legal hold remain outstanding.
- Acceptance: reporters cannot review their own cases; evidence access is authorized and audited; all status transitions have actor, timestamp and reason.

### 9. Portals and role separation
- Implemented the initial five-role foundation: administrator, registrar, examination officer, invigilator and student. Reviewer independence is enforced within case/appeal workflows, not yet a separately provisioned sixth role.
- Add MFA, verified institutional account recovery, session revocation and role-change audit.
- Acceptance: authorization tests cover every route and object ownership; a user cannot access another role's records by changing IDs or URLs.

### 10. Analytics, reporting and audit
- Build operational metrics for registration, eligibility, schedule coverage, attendance exceptions, case ageing and evidence status.
- Add institution-approved CSV/PDF exports with filters and access audit.
- Protect audit records against application-level alteration; define retention and privileged access review.
- Acceptance: dashboard counts reconcile to source records; exports are permission checked, no-store and audited.

### 11. PostgreSQL, security, backups and deployment
- Added browser security response headers and a production-startup guard that refuses to run while the app still uses SQLite directly.
- PostgreSQL remains outstanding: refactor SQLite-specific SQL behind a repository/database layer before introducing PostgreSQL.
- Add versioned migrations, transactional writes, connection pooling and a rehearsed SQLite-to-PostgreSQL migration with row-count and checksum reconciliation.
- Configure production WSGI hosting, TLS, secret manager, shared rate-limit storage, encrypted backups, point-in-time recovery, restore drills, monitoring and alerts.
- Acceptance: migration rehearsal and restore drill succeed; no SQLite-specific SQL remains in production paths; security and performance tests pass.

### 12. University data integration and approval
- Implement configurable adapters for SIS student/academic data, institutional SSO and email.
- Require documented API specifications, service accounts, scopes, rate limits, data mappings, data-sharing agreement and institution-owned test environment.
- Acceptance: integration is least privilege, idempotent, observable, reconciled and can be disabled without corrupting local records.

## Current external blockers

The following cannot be truthfully completed without institutional inputs:
- Registrar confirmation of current examination regulations and approval of the exact policy version/effective date.
- SIS/Finance/LMS/SSO/email API specifications, test environment and service credentials.
- Approved biometric provider, provider API docs and sandbox credentials.
- Data Protection Impact Assessment, lawful-basis determination, data-sharing agreements and security approval.
- Production hosting account, PostgreSQL service, storage/KMS and backup ownership.

## Current verification boundary

The parent branch's 19 unit tests and CI success are inherited evidence only. The current branch adds tests for policy evidence, append-only records, venue layouts, session activation and the 21-day Senate review period. The latest CI run must be checked before treating this increment as green. A green unit-test workflow does not certify browser end-to-end behavior, security, accessibility, load, disaster recovery or institutional acceptance.


## Latest implementation increment

The institutional completion branch now includes:
- `modules/access_control.py` defines the staff-role policy and additive migration helpers.
- `modules/eligibility.py` with independently approved, versioned policy evaluation.
- `modules/appeals.py` with student-initiated appeals and independent review safeguards.
- `modules/identity_check.py` with session-scoped candidate review and preview-only camera interface.
- `docs/KISII_UNIVERSITY_POLICY_MAPPING.md`, `docs/KISII_UNIVERSITY_INTEGRATION_READINESS.md` and `docs/POSTGRESQL_MIGRATION_AND_PRODUCTION_RUNBOOK.md` for institution-specific policy and release planning.
- Append-only academic history in the institutional registry.
- Administrator staff provisioning, updated staff login and role-specific navigation.
- New tests for role migration, staff authentication, eligibility decisions, appeals, identity scope and append-only history.

These are development increments. They do not establish institutional policy approval, production authorization or full end-to-end readiness. Live face matching remains disabled because Kisii University has not selected an approved provider.
