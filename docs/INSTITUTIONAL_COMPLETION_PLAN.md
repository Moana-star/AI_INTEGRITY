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
- Complete calendar/list views, session lifecycle, bulk import, rescheduling and cancellation.
- Validate candidate, venue and invigilator clashes inside a transaction; handle concurrent booking attempts.
- Add room closure, seat blocks, approved accommodations, setup buffers and exam duration.
- Acceptance: conflicting reservations cannot be committed, and rescheduling/cancellation creates an attributable audit event.

### 3. Eligibility verification
- Added a versioned eligibility policy engine and officer workspace.
- Policy drafts require an official policy/source reference; approval is restricted to a different administrator from the creator.
- The current engine checks active academic status and registered unit enrolment. Without an effective approved policy, it records a pending decision rather than clearing or disqualifying the candidate.
- Remaining: add the full official Kisii University policy rule set, effective-date edge-case tests, decision review/override workflow and browser acceptance.
- Treat fee clearance or other sensitive administrative criteria only when the institution supplies and approves the policy/data source.
- Record rule version, evidence source, result and review reason.
- Acceptance: eligible, pending and ineligible states are explainable and reproducible; a rule change does not silently rewrite historical decisions.

### 4. Venue, seating and invigilator allocation
- Add venue layouts, seat maps, accessibility/accommodation blocks, staff ratios and assignment qualifications.
- Prevent double booking and preserve allocation history.
- Acceptance: allocation respects capacity and constraints; manual overrides require a reason and audit record.

### 5. Attendance interface
- Provide a responsive invigilator station with candidate search/scan, check-in, check-out, duplicate-event protection and offline-safe exception capture.
- Do not equate an ID or face match with eligibility.
- Acceptance: only assigned staff can record attendance for their session; duplicate and out-of-session events are rejected; reconciliation flags missing events for human review.

### 6. Student ID verification
- Verify an admission number or signed/QR student credential against the institution-authorized registry.
- Protect against replay where a signed, expiring token is used.
- Provide manual review and accessible fallback.
- Acceptance: unknown, inactive, expired and mismatched identities are distinguished and audited.

### 7. Biometric verification
- A provider-neutral boundary is introduced in `modules/biometric_verification.py`. It requires deployment enablement, institutional approval, a consent/alternative-process record and an explicitly supplied provider adapter.
- The boundary supports one-to-one verification only; it requires both match and liveness success and fails closed on provider errors or inconclusive responses.
- It does not store captures or create face templates. No provider is currently configured and no live camera route is enabled.
- Before a real integration: select a university-approved provider; obtain its API documentation, data residency/security details, DPA, liveness/matching semantics, retention policy and test credentials; complete DPIA and institutional approval.
- Acceptance: sandbox tests cover true/false/inconclusive outcomes, liveness failure, timeout, provider outage, consent withdrawal, manual fallback, data deletion and audit logging. No biometric result alone can deny exam access or determine misconduct.

### 8. Incident investigation and evidence
- Added a separate student appeal record and staff appeal queue.
- Student appeals are accepted only for a final recorded case outcome and only for the authenticated student's own incident.
- The original reporter and last recorded case reviewer are prevented from deciding the appeal.
- Appeal events are append-only; independent outcomes are stored separately and do not silently rewrite the original incident record.
- Remaining: formal appeal time limits and grounds from Kisii University policy, reviewer assignment workflow, appeal evidence submissions, acknowledgement/notifications, and full due-process browser tests.
- Evidence chain-of-custody hardening, malware scanning, private object storage and retention/legal hold remain outstanding.
- Acceptance: reporters cannot review their own cases; evidence access is authorized and audited; all status transitions have actor, timestamp and reason.

### 9. Portals and role separation
- Implement least-privilege administrator, registrar, examination officer, invigilator, reviewer and student permissions.
- Add MFA, verified institutional account recovery, session revocation and role-change audit.
- Acceptance: authorization tests cover every route and object ownership; a user cannot access another role's records by changing IDs or URLs.

### 10. Analytics, reporting and audit
- Build operational metrics for registration, eligibility, schedule coverage, attendance exceptions, case ageing and evidence status.
- Add institution-approved CSV/PDF exports with filters and access audit.
- Protect audit records against application-level alteration; define retention and privileged access review.
- Acceptance: dashboard counts reconcile to source records; exports are permission checked, no-store and audited.

### 11. PostgreSQL, security, backups and deployment
- Refactor SQLite-specific SQL behind a repository/database layer before introducing PostgreSQL.
- Add versioned migrations, transactional writes, connection pooling and a rehearsed SQLite-to-PostgreSQL migration with row-count and checksum reconciliation.
- Configure production WSGI hosting, TLS, secret manager, shared rate-limit storage, encrypted backups, point-in-time recovery, restore drills, monitoring and alerts.
- Acceptance: migration rehearsal and restore drill succeed; no SQLite-specific SQL remains in production paths; security and performance tests pass.

### 12. University data integration and approval
- Implement configurable adapters for SIS student/academic data, institutional SSO and email.
- Require documented API specifications, service accounts, scopes, rate limits, data mappings, data-sharing agreement and institution-owned test environment.
- Acceptance: integration is least privilege, idempotent, observable, reconciled and can be disabled without corrupting local records.

## Current external blockers

The following cannot be truthfully completed without institutional inputs:
- Named institution and approved academic/eligibility policies.
- SIS/SSO/email API specifications, test environment and service credentials.
- Approved biometric provider, provider API docs and sandbox credentials.
- Data Protection Impact Assessment, lawful-basis determination, data-sharing agreements and security approval.
- Production hosting account, PostgreSQL service, storage/KMS and backup ownership.

## Current verification boundary

The parent branch's 19 unit tests and CI success are inherited evidence only. This branch must run its own full test suite. A green unit-test workflow does not certify browser end-to-end behavior, security, accessibility, load, disaster recovery or institutional acceptance.


## Latest implementation increment

The institutional completion branch now includes:
- `modules/access_control.py` defines the staff-role policy and additive migration helpers.
- `modules/eligibility.py` with independently approved, versioned policy evaluation.
- `modules/appeals.py` with student-initiated appeals and independent review safeguards.
- Append-only academic history in the institutional registry.
- Administrator staff provisioning, updated staff login and role-specific navigation.
- New tests for role migration, eligibility decisions and append-only history.

These are development increments. They do not establish institutional policy approval, production authorization or full end-to-end readiness.
