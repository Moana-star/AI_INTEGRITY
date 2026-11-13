# Phase 0 — Existing EIMS Application Audit

**Audit date:** 2026-11-13  
**Repository:** `Moana-star/AI_INTEGRITY`  
**Audited branch:** `feature/eims-institutional-completion`  
**Audited branch head:** `2a5b48babd9d4b8ab755201b278834f42e6cd38f`  
**Pull request:** [#2 — Begin institutional EIMS completion and biometric provider boundary](https://github.com/Moana-star/AI_INTEGRITY/pull/2)  
**Audit disposition:** Development branch with meaningful operational workflows; **not approved for production or live student data**.

This report records what was verified in repository source, documentation and the linked GitHub Actions run. It is not a claim that a local installation, university environment, or live biometric provider was tested.

## 1. Repository and change safety

- The repository exists and is accessible.
- The default branch is `main`.
- The audited work is on `feature/eims-institutional-completion`.
- PR #2 is open, draft, and targets `feature/institutional-eims-foundation`, not `main`.
- No repository files were changed on `main` during this audit.

## 2. Verified implemented foundations

| Area | Evidence found | Audit result |
|---|---|---|
| Student registry | `modules/institutional_registry.py` | Admission-number-based records, profiles, CSV import, academic status and audit events exist. |
| Academic units | `modules/institutional_registry.py`, `modules/operations.py` | Unit creation and student-unit enrolment exist. |
| Examination operations | `modules/operations.py` | Sessions, candidate lists, venues, seats, invigilator assignments and scheduling checks exist. |
| Attendance | `modules/operations.py` | Session-level manual/student-card check-in/out, attendance events and reconciliation exist. |
| Student portal | `modules/student_portal.py` | A student-facing self-service workflow exists. |
| Eligibility | `modules/eligibility.py` | Policy/evidence-based eligibility workflow exists; institutional policy ownership and authoritative integrations remain external dependencies. |
| Incident review | `modules/integrity.py`, `modules/appeals.py` | Incident workflow, evidence, student responses and appeal/review records exist. |
| Access control | `modules/access_control.py` and route checks | Five role names and a granular permission catalogue exist; complete route/object-level enforcement still needs systematic verification. |
| Database connectivity | `modules/database.py` | Shared SQLite/PostgreSQL connection adapter exists. SQLite is the local default; PostgreSQL is selected by `DATABASE_URL`. |
| Container/deployment starter | `Dockerfile`, `scripts/bootstrap_postgres.py`, deployment guide | Non-root container and PostgreSQL/Redis Compose deployment starter exist. This is not a production deployment. |

## 3. Facial verification and attendance — exact status

**Finding: the end-to-end biometric feature is scaffolded but not operational.**

What exists:
- `templates/identity_session.html` presents the candidate list for a specific examination session.
- `static/js/biometric_capture.js` requests browser camera access, captures a frame and posts it to the session/student verification endpoint.
- `modules/biometric_verification.py` defines a provider-neutral, fail-closed interface.
- `modules/biometric_attendance.py` defines provider enrolment, revocation and verification routes.
- The verification route checks session candidacy, eligibility, invigilator assignment and duplicate check-in; on a verified provider response it writes session attendance, an attendance event and an audit event in one transaction.
- The system is designed to store an opaque provider reference rather than retain face images/templates itself.

What is not present or not verified:
- No concrete approved biometric vendor adapter or live provider credentials were found.
- No deployment-level provider configuration or institutional enablement was verified.
- The verification endpoint deliberately returns HTTP 503 while biometric verification is disabled or unapproved.
- No real face comparison or liveness result has been demonstrated.
- The provider must supply and substantiate liveness and match-quality behavior; the interface alone does not provide it.
- A complete student biometric-enrolment user journey has not been verified.
- No biometric-specific end-to-end test with a real provider exists in the inspected test suite.
- The current camera workflow is therefore not a working face-recognition system yet.

**Conclusion:** Do not describe EIMS as having active face recognition. It has a camera capture path and provider integration boundary, deliberately disabled pending institutional approval and provider configuration. Manual/student-card attendance is the available fallback.

## 4. Student data — exact status

The registry schema includes:
- Unique admission/student number.
- First and last names.
- Course/programme and year of study.
- Faculty and department.
- Institutional email and phone.
- Academic status, academic year and semester.
- Unit enrolment and academic history.

CSV import is supported. No live university SIS/API connection or authoritative student dataset was supplied or verified. The inspected student profile schema does not establish an implemented official profile-photo repository or face-template store. The database is intended to initialize empty unless the explicit demo option is selected.

**Conclusion:** The system can hold administrator-entered or imported records. It is not yet connected to the university's authoritative student information system. Real student data must only be introduced after institutional authorization and privacy/security approval.

## 5. Database and architecture findings

- A shared DB-API adapter for SQLite and PostgreSQL is present.
- PostgreSQL CI exercises empty-first bootstrap, repeat bootstrap, module schema initialization, a student create/read path, academic-unit creation, append-only history enforcement and biometric fail-closed behavior.
- Module tables are still created using request-time `ensure_schema()` / DDL logic. A reviewed, versioned Alembic migration chain was not found.
- `scripts/migrate_sqlite_to_postgres.py` is a guarded SQLite snapshot migration utility; it is not a replacement for ongoing versioned schema migrations.
- The registry defines a legacy `examination_attendance` table, while the newer session workflow uses `session_attendance` and `attendance_events`. These overlapping attendance stores need an explicit source-of-truth decision and reconciliation/migration plan before further expansion.
- Business modules still use SQLite-compatible SQL through the adapter. The adapter's translation behavior needs broader PostgreSQL coverage before production use.

## 6. Security and governance findings

Controls found:
- Flask-WTF CSRF protection.
- IP-based login rate limiting, with Redis required for production.
- HTTP security headers and configurable secure session cookies.
- Password hashing and controlled staff-account provisioning.
- Private evidence storage and SHA-256 evidence checksums.
- Append-only protections on selected academic, appeal, biometric and audit histories.
- A fail-closed biometric approval boundary and non-biometric fallback.

Still outstanding:
- Complete role-by-route and record-ownership authorization matrix.
- MFA, account-level lockout/throttling, session expiry/revocation and institutional recovery workflow.
- Independent security/penetration testing.
- Encryption and key management for database backups and evidence storage.
- Malware scanning and retention/deletion automation for evidence.
- Monitoring, alerting and incident response procedures.
- DPIA, lawful-basis determination, notices, provider agreement and signed university authorization before biometric processing.
- Accessibility, load, low-bandwidth and concurrency testing.
- Tested backup restoration and disaster-recovery procedures.

## 7. CI evidence checked

GitHub Actions run [43389961871](https://github.com/Moana-star/AI_INTEGRITY/actions/runs/43389961871) for the audited head completed successfully. The four jobs reported success:
- `test`
- `browser-smoke`
- `postgres-runtime`
- `container-build`

This is positive automated evidence. The browser job is a smoke suite, not complete role-specific workflow acceptance. The PostgreSQL job is targeted runtime integration coverage, not full PostgreSQL coverage. CI success is not production certification.

## 8. Documentation inconsistencies to correct

The repository contains conflicting status descriptions:
- `docs/POSTGRESQL_MIGRATION_AND_PRODUCTION_RUNBOOK.md` still says the app uses SQLite directly and that no PostgreSQL runtime adapter exists.
- The current source and `docs/INSTITUTIONAL_INTEGRATION_AND_PRODUCTION_ACCEPTANCE.md` describe the shared PostgreSQL adapter and PostgreSQL CI job.
- README and deployment documents should use one consistent description of the current PostgreSQL runtime capability and the remaining migration/production gates.

These documents should be reconciled after confirming the current implementation and test coverage, rather than treating older statements as current facts.

## 9. Required closure work before Phase 1

1. Run the application locally from a clean checkout using the documented empty-first setup; record actual startup and login results.
2. Run the full local test suite and retain the output; independently inspect the CI test job if test counts are to be quoted.
3. Build a route/role/HTTP-method authorization matrix for anonymous, administrator, registrar, examination officer, invigilator and student users.
4. Trace the student create/import/edit/read journey and the examination → candidate → attendance journey against database writes.
5. Resolve the duplicate attendance data model and identify the canonical session-linked attendance records.
6. Trace biometric enrolment and verification from UI through provider adapter to attendance persistence; add provider-contract tests using a deliberately fake test provider only in isolated tests, never as a production match.
7. Reconcile outdated PostgreSQL and production-readiness documentation.
8. Record every finding as a defect, accepted limitation, external institutional dependency or verified feature.

## 10. Explicit release decision

**Phase 0 source/CI inspection: substantially completed.**  
**Phase 0 local runtime and full role/security verification: pending.**  
**Production readiness: not achieved.**  
**Biometric verification: disabled; no live provider connected.**  
**Live university student-data integration: not connected.**

Do not merge PR #2 into `main`, enable biometric processing, or use live student data on the strength of this audit alone. Proceed to Phase 1 only after the outstanding Phase 0 verification and data-model decisions are recorded.
