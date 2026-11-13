# Phase 0 — Closure Register

**Repository:** `Moana-star/AI_INTEGRITY`  
**Working branch:** `feature/eims-institutional-completion`  
**Latest reviewed change:** `5ed5e1b` (local acceptance evidence recorded after this commit)  
**Review date:** 13 November 2026  
**Disposition:** **Phase 0 repository engineering baseline closed; local full suite and four GitHub CI jobs passed. Not production-approved.**

This register is the concise status authority for Phase 0. It distinguishes repository work that can be verified by code and tests from institutional and operational acceptance that requires the university, its data owners, infrastructure operators or an independent assessor.

## 1. Verified repository capabilities

| Area | Evidence / status |
|---|---|
| Student registry | Student records, profiles, CSV intake, academic status/history and audit events are implemented. No authoritative SIS connection is present. |
| Academic operations | Academic-unit and enrolment workflows, venues/seats, examination sessions, candidates, invigilator assignments and scheduling checks are implemented. |
| Attendance | Session-linked current state in `session_attendance`, append-only `attendance_events`, manual/student-card fallback and reconciliation are implemented. |
| Eligibility | Policy/evidence workflow exists and fails closed to pending where required evidence or an approved policy is missing. University policy ownership and authoritative integrations remain external. |
| Integrity cases | Incident, evidence, student response, review and appeal workflows exist, including selected conflict-of-interest and ownership controls. |
| Staff access | Five institutional role labels/permissions, restricted staff provisioning, CSRF and targeted role/route/assignment denial tests exist. Full endpoint and record-scope authorization is not certified exhaustive. |
| Database | SQLite and PostgreSQL DB-API connectivity, PostgreSQL bootstrap/runtime CI and guarded SQLite snapshot migration utility exist. A complete versioned Alembic migration chain is not present. |
| Import safety | Institution operations CSV importer supports dry-run by default, validation, role restrictions, audit events and transactional apply. It imports units, venues and enrolments for existing registry students; it does not invent or create source student records. |
| Legacy attendance | New database bootstrap no longer creates the deprecated `examination_attendance` table. Existing tables/rows are preserved. Physical retirement requires reviewed mapping, backup/archive, reconciliation and Registrar/data-owner approval. |
| Deployment foundation | Dockerfile, PostgreSQL/Redis Compose starter, production configuration guards and CI container build exist. These are deployment foundations, not production certification. |

## 2. Workstation acceptance evidence

The user completed a separate clean Windows clone and setup in the directory `AI_INTEGRITY-phase0-clean`:

- Python 3.14 virtual environment created and dependencies installed.
- Application modules, scripts and tests compiled without reported errors.
- Flask application started and administrator sign-in succeeded.
- Institutional Registry and Academic Operations pages opened successfully.
- Existing local SQLite data was copied into the clean clone using SQLite backup, with integrity reported as `ok`; the source database was left untouched and backups retained.
- Read-only inspection reported zero academic units, zero student-unit enrolments, zero venues, zero examination sessions, zero session candidates and zero session-invigilator assignments. Five examination master records and two invigilator records were present.
- The provenance of the existing student/examination/incident records has not been independently established. One examination code is explicitly `DEMO`; do not treat the database as an authoritative university dataset without confirmation from the data owner.

### Local test result before the final test correction

On 13 November 2026 the user's full local suite ran 117 tests: 114 passed, one failed and two PostgreSQL-related tests were skipped because the local PostgreSQL service/environment was not configured.

The sole failure was a defective assertion in `test_existing_admin_account_is_listed_as_administrator_not_internal_slug`. The administrator account legitimately has both name and username `admin`; the old assertion rejected any table cell containing that text and therefore also rejected the Name and Username columns, despite the Role cell correctly displaying `Administrator`.

The assertion was corrected to inspect the complete table row and verify its third cell is `Administrator`. The correction is committed at `da92c76a04c5076e19406c45a5e08998834e80ff`. The user reran the complete suite after pulling commit `5ed5e1b`: `Ran 117 tests in 15.630s`, `OK (skipped=2)`. The corrected administrator-role test passed. The two skips are the local PostgreSQL integration/runtime tests, which require a local PostgreSQL service and `DATABASE_URL`; dedicated PostgreSQL CI coverage is recorded below.

## 3. Automated verification

The repository CI workflow runs four jobs:

1. `test`: dependency install, compilation and full unittest suite with a PostgreSQL service available for migration tests.
2. `browser-smoke`: isolated synthetic database, Flask readiness and Chromium browser smoke tests.
3. `postgres-runtime`: empty-first PostgreSQL bootstrap, repeat-bootstrap non-destructiveness and Flask/module runtime tests.
4. `container-build`: non-root Docker build and Docker Compose configuration validation.

GitHub Actions push run [43409416494](https://github.com/Moana-star/AI_INTEGRITY/actions/runs/43409416494) for commit `da92c76a04c5076e19406c45a5e08998834e80ff` completed with all four jobs successful: `test`, `browser-smoke`, `postgres-runtime` and `container-build`. The separate pull-request-triggered run was also initiated. Local skips do not replace the dedicated PostgreSQL CI jobs. The user subsequently pulled commit `5ed5e1b` (which includes the assertion correction and this closure register) and confirmed the full local suite: 117 tests, 0 failures, 2 expected PostgreSQL-related skips. Local compilation also completed without errors.

## 4. Explicit non-completions and release gates

These items are not represented as completed merely because code scaffolding or tests exist.

| Gate | Current status | Required evidence before live institutional use |
|---|---|---|
| Authoritative student data | Not connected | Authorized Registrar/SIS export or approved SIS integration, source-owner sign-off, data reconciliation and privacy controls. |
| Real operational dataset | Not established | Confirm the provenance and correctness of existing records; load real units, venues, enrolments, examinations, candidates and assignments only from authorized institutional sources. |
| Biometric verification | Disabled / provider-gated | Approved provider and contract, real adapter/credentials, liveness/match validation, DPIA/lawful basis, informed notices/consent where applicable, university approval and provider end-to-end acceptance. Camera capture alone is not face recognition. |
| Complete authorization assurance | Partial | Independent route × role × method × object/ownership assessment, including positive and negative cases. Existing tests provide meaningful but not exhaustive coverage. |
| Versioned schema migrations | Not complete | Reviewed, repeatable schema migration framework and upgrade/rollback tests across supported database versions. |
| Security assessment | Not complete | Independent penetration test on an authorized synthetic-data deployment, remediation and retest. |
| Privacy/data governance | Not complete | Institutional data-controller determination, DPIA where required, retention/deletion schedule, notices, processor agreements and access governance. |
| Operational security | Not complete | MFA, account/session lifecycle controls, secrets/key management, encrypted backups/evidence, malware scanning, monitoring, alerting and incident response. |
| Resilience/performance | Not complete | Successful backup restore and disaster-recovery drills, load/concurrency testing, accessibility and low-bandwidth acceptance. |
| PostgreSQL local workstation verification | Not performed locally | Run the documented PostgreSQL setup or rely on successful dedicated CI plus later institution-hosted acceptance; record the environment and evidence. |
| Legacy attendance retirement | Deferred safely | Inventory, backup/archive, examination-to-session mapping, row-count/checksum reconciliation, restore verification and data-owner approval. Never infer session mapping or delete rows automatically. |

## 5. Safety and scope decisions

- Keep all work on `feature/eims-institutional-completion` until the owner explicitly authorizes a merge.
- PR #2 remains separate from `main`; this register does not authorize merging it.
- Do not add synthetic or fabricated academic units, venues, students, enrolments or attendance to the user's operational database.
- Use isolated synthetic records only for automated tests.
- Do not enable biometric processing or enter live biometric/student data before institutional authorization and privacy/security acceptance.
- Do not delete the legacy attendance table or its rows as part of routine schema bootstrap.
- Do not describe EIMS as production-certified, SIS-integrated or actively performing face recognition.

## 6. Closure decision

**Repository engineering baseline:** substantially implemented and documented.  
**Final test closure:** local full suite passed (117 tests, 0 failures, 2 PostgreSQL-related skips) and all four GitHub CI jobs passed for the corrected code commit.  
**Institutional pilot readiness:** not yet established; authoritative data, policy-owner approval, full authorization assessment and operational acceptance remain necessary.  
**Production release:** not approved.

Phase 0 is **closed as an engineering foundation/audit phase with explicit external release gates**. This closure is limited to repository engineering and the recorded test/CI evidence. It is not approval to process live student records, activate biometric checks or deploy the system for official examinations.
