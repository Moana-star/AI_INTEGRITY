# Phase 2 — Examination Management Audit

**Working branch:** `feature/eims-phase-2-examination-management`  
**Starting commit:** `893ee844b142786e50baa2c1d5d16d6907c21902`  
**Parent branch:** `feature/eims-institutional-completion`  
**Status:** Audit completed; implementation and acceptance work in progress.  
**Release boundary:** `main` is unchanged. This document is not a production-readiness declaration.

## 1. Objective

Deliver one coherent, auditable examination-management workflow:

1. An authorized examination officer creates and maintains an examination definition.
2. The officer creates one or more dated examination sessions for the correct academic unit, year and semester.
3. The candidate list is derived from current student-unit enrolments and remains pending until a current approved eligibility decision is applied.
4. The session is allocated to an active venue with sufficient capacity and a configured seating layout.
5. Active invigilators are assigned without timetable conflicts.
6. The session cannot be activated until its required operational controls pass.
7. Rescheduling, cancellation, allocation changes and exports are attributable and auditable.

Examination definition, examination session, eligibility, identity verification and attendance remain distinct records and decisions.

## 2. Existing functionality verified in the repository

The starting branch already contains substantial examination operations:

- An `examinations` master table and legacy administrator CRUD pages.
- `examination_sessions` with session code, examination, unit, academic year, semester, venue, date, start/end time and lifecycle status.
- Session candidate records with a uniqueness constraint on (session, student).
- Candidate-list creation from registered student-unit enrolments for the session's academic period.
- Candidate, venue and invigilator overlap checks in the existing scheduling/assignment paths.
- Venue capacity validation and active-venue checks.
- Venue seat layouts, accessible seat labels and approved accommodation-aware allocation.
- Invigilator assignments with a unique session/invigilator constraint.
- A minimum of two active invigilators and an active in-capacity venue before session activation.
- Role-scoped operations workspace and invigilator access limited to assigned sessions.
- Audit events for many create, assignment, status, allocation and export actions.
- Attendance register and CSV export, which are downstream of examination-session setup.

Existing tests cover venue layout validation, activation blockers, attendance export, role restrictions, candidate uniqueness and selected operational behavior. The local baseline supplied by the user is 127 passing tests with two PostgreSQL-dependent skips.

## 3. Important gaps and risks to resolve

### 3.1 Two overlapping examination-management surfaces

The legacy `/admin/examinations` pages create, edit and delete rows in `examinations`. The newer `/operations` workspace creates and manages `examination_sessions` that reference those rows.

The legacy form also stores date, time, venue and a single invigilator on the examination master record, while the session stores its own date, time, venue and many-to-many invigilator assignments. This creates two places where schedule-like information can disagree.

**Required:** define the master examination as the paper/assessment definition and the session as the actual scheduled sitting. Retire or safely redirect legacy schedule CRUD after an audited replacement for examination-definition management is in place. Do not silently delete or rewrite existing examination records.

### 3.2 Examination-definition lifecycle

The newer operations workspace can select an existing examination but does not provide a complete, role-appropriate examination-definition workflow there. The legacy CRUD is administrator-only and its edits are not consistently represented in the central audit history.

**Required:** examination officers need validated create/read/update operations for examination definitions, with authorization, audit events, safe status transitions and referential-integrity protection. Destructive deletion must be replaced with a controlled archive/retire approach when sessions or incidents reference the examination.

### 3.3 Scheduling lifecycle

Existing creation checks are useful but need stronger, explicitly tested lifecycle behavior.

**Required:** server-side date/time validation; conflict checks for candidates, venues and invigilators; safe rescheduling; cancellation reason and history; completed-session immutability; and clear rules for what can change after candidates, seats or attendance exist.

### 3.4 Venue and capacity management

Venue creation, active status, capacity and basic seat layouts exist. A configured layout cannot currently be replaced once used, but there is no complete room-closure, capacity-change, layout-version or audited seat-swap/override workflow.

**Required:** controlled venue maintenance, room closure, layout versioning and reasoned/audited overrides. Never reduce capacity below existing reservations without a safe resolution workflow.

### 3.5 Concurrency and database integrity

Several checks are performed as query-then-write operations. Unique constraints protect duplicate candidates and duplicate seat assignments, but do not alone prevent two concurrent requests from reserving the same venue or invigilator for overlapping sessions.

**Required:** transaction-safe reservation logic and tests that exercise competing writes. Do not claim concurrency safety until it is demonstrated on the supported database engines.

### 3.6 Bulk scheduling and operational usability

Bulk import, calendar/list filters, rescheduling workflow and browser-level acceptance are incomplete. Staff qualification/ratio rules and chief-invigilator assignment need institution-approved requirements before enforcement.

**Required:** add only after the core single-session workflow and data contracts are stable. Do not invent staff ratios or qualifications.

## 4. Delivery sequence

1. **Unify examination definitions and sessions:** define the source of truth and remove conflicting legacy schedule-edit paths safely.
2. **Harden examination-definition CRUD:** validation, role authorization, audit, archive/retire behavior and foreign-key-safe handling.
3. **Harden session scheduling:** date/time validation, conflict detection and transaction-safe create/reschedule/cancel operations.
4. **Harden venue operations:** room closure, capacity safety, layout versioning and audited seat overrides.
5. **Harden invigilator allocation:** assignment overlap, active status, role mapping and auditable reassignment.
6. **Improve session administration:** filtering, calendar/list views and carefully validated bulk import.
7. **Automated and browser acceptance:** administrator and examination-officer workflows, invigilator visibility boundaries, failure paths, audit history and database consistency.

## 5. Phase 2 acceptance criteria

Phase 2 is not complete until all of the following are demonstrated:

- An examination officer can create and edit an examination definition without accessing student-registry administration.
- An examination definition can have multiple sessions without duplicating its identity.
- A session is linked to an existing examination, academic unit, academic year and semester.
- Candidates come only from current registered enrolments for that exact unit and period; candidate rows are unique.
- Eligibility remains pending until a current approved policy evaluation is applied.
- Invalid dates, invalid times, past-date policy violations and overlapping reservations are rejected server-side.
- A venue cannot be double-booked; its active capacity and configured seat inventory are respected.
- An invigilator cannot be double-booked and can see only sessions assigned to their staff identity.
- Activation is blocked until all required venue, capacity, candidate and invigilator controls pass.
- Rescheduling and cancellation require a reason, preserve history and write attributable audit events.
- Completed sessions cannot be silently altered; records with candidates, attendance or incidents cannot be destructively deleted.
- Tests cover permissions, invalid input, conflicts, rollback, duplicate requests, concurrent reservation behavior and browser workflows.
- Existing Phase 1 registry data and history remain unchanged by Phase 2 migrations and tests.

## 6. External decisions and boundaries

- The institution must confirm examination regulations, timetable rules, room setup buffers, staff qualifications/ratios and chief-invigilator requirements before those rules are enforced.
- No live institutional SIS or staff-directory integration is assumed. Controlled institutional imports remain the interim data path.
- Development and automated tests use synthetic data only. Never commit real student or staff records.
- Do not enable biometric processing as part of Phase 2. Identity/biometric verification is a separately gated workstream.
- Do not merge this branch into the parent branch or `main` until its review and acceptance gates pass.


## 7. Implemented examination-definition management increment

**Implementation status:** Completed on the Phase 2 branch.  
**Verified commit:** `9235d2296fe0ef188f9aeaac89bcd9410df85c5e`

Implemented:

- Dedicated examination-definition register and create/edit forms.
- Server-side validation for examination code and name, including duplicate detection.
- Administrator and examination-officer access through the existing `exams.write` permission; registrar, invigilator and student roles are denied.
- Additive lifecycle metadata on existing examination master records: active/archived status, creator, update time, archive actor/time and archive reason.
- Scheduled sitting details remain in `examination_sessions`; the definition form does not accept dates, times, venues, candidates or invigilator assignments.
- Archived definitions are excluded from new session selection and rejected by the session-creation endpoint.
- Archival requires a reason and is blocked while scheduled or active sessions still reference the definition.
- Restore requires a reason. Archive/restore preserve the original examination ID and all session, attendance and incident references.
- Physical deletion through the old URL is disabled.
- Create, edit, archive and restore actions write attributable `audit_events`.
- Administrator dashboard and examination summary reports now derive schedule/status information from actual examination sessions, not master definitions.
- The legacy invigilator dashboard redirects to the authoritative assigned-session workspace.
- Phase 2 branch was added to GitHub Actions push and pull-request triggers.

### Automated verification

At commit `9235d22`:

- Python unit suite: **136 tests passed, 0 failures, 0 errors; 1 environment-dependent skip**.
- Chromium browser smoke suite: passed.
- PostgreSQL runtime integration: passed.
- Non-root container build: passed.
- Docker Compose validation: passed.

Run: [GitHub Actions — Phase 2 verification](https://github.com/Moana-star/AI_INTEGRITY/actions/runs/43422511428).

### Compatibility note

The original `examinations` table has legacy NOT NULL schedule columns. To avoid a destructive rebuild while keeping existing foreign-key identities intact, newly created definition-only rows receive inert compatibility values in those legacy columns. They are not shown as actual sittings; all real dates, times, venues, candidates and assignments are managed through `examination_sessions`. A separately reviewed schema migration should remove those legacy requirements before production.

## 8. Remaining Phase 2 closure gates

The examination-definition increment above is implemented and CI-verified. The whole Phase 2 is **not yet production-accepted**. The remaining work from the audit is:

1. Transaction/concurrency-safe reservations for competing venue, candidate and invigilator allocations.
2. Audited rescheduling and cancellation reason/history workflows, including immutable completed-session handling.
3. Controlled venue closure, capacity changes, seat-layout versioning and reasoned seat overrides.
4. Institution-approved scheduling buffers, invigilator qualifications/ratios and chief-invigilator rules.
5. Browser-level acceptance of authenticated examination-officer workflows using institution-authorized data and manual review of the real local database.
6. A reviewed migration to retire the legacy schedule columns without losing existing examination, session or incident references.

No production deployment, institutional data import, merge to `main`, or biometric activation is authorized by this implementation.
