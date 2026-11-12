# Infrastructure, Data Migration and Institutional Integration Plan

**Current state:** This repository is still a SQLite-backed development application. This document is an implementation and approval plan, not evidence that production infrastructure or external university integrations have been provisioned.

## 1. PostgreSQL migration — required architecture

The application currently opens SQLite connections directly in `app.py`, `modules/institutional_registry.py`, `modules/operations.py`, `modules/integrity.py` and `modules/student_portal.py`. These modules use SQLite-specific SQL (including `?` parameters, `lastrowid`, `INSERT OR IGNORE`, `ON CONFLICT`, `PRAGMA` and `executescript`). Merely adding a PostgreSQL URL or driver would not migrate the application.

The migration must therefore be performed as a controlled refactor:

1. Introduce one application-owned database/repository layer and remove direct `sqlite3.connect` calls from request handlers.
2. Define versioned migrations for every existing table, foreign key, unique constraint, check constraint and index.
3. Translate SQLite-specific SQL to portable SQL or explicit PostgreSQL statements; use parameterized queries throughout.
4. Use PostgreSQL transactions and database-generated identifiers consistently.
5. Create a repeatable SQLite-to-PostgreSQL migration command with row counts, primary-key preservation, foreign-key validation, duplicate checks and checksums for critical records.
6. Run the migration against a copy of the database, compare every table, test rollback and rehearse cutover before production.
7. Keep the original SQLite database immutable as a rollback source until the institution signs off on reconciliation.

**Do not set `DATABASE_URL` to PostgreSQL in the current application.** The request handlers are not yet PostgreSQL-compatible.

## 2. Production hosting and configuration

Production deployment requires a managed application runtime and managed PostgreSQL service in an institution-approved region. Use a WSGI server such as Gunicorn behind HTTPS termination and a managed reverse proxy/load balancer. Do not use Flask's development server for production.

Required secret/configuration controls:

- A high-entropy `FLASK_SECRET_KEY` held in a secret manager.
- TLS-only access; secure, HTTP-only, SameSite cookies.
- A shared Redis-compatible `RATELIMIT_STORAGE_URI` for multi-worker rate limiting.
- Separate least-privilege database credentials for migrations and application runtime.
- Environment-specific configuration; no production secrets in source control, logs, images or test fixtures.
- Restricted outbound network access and explicit trusted-proxy configuration.
- Documented deployment, rollback, incident response and access revocation procedures.

## 3. Backups and recovery

After PostgreSQL migration:

- Enable managed point-in-time recovery and scheduled encrypted backups.
- Maintain a separate protected backup copy in an approved account/region.
- Define RPO and RTO with the institution; do not invent service guarantees.
- Alert on backup failures, age, size anomalies and storage exhaustion.
- Perform scheduled restore drills into an isolated environment.
- Verify restored row counts, constraints, application login, examination records, evidence references and file checksums.
- Record restore evidence and obtain operational sign-off.

Database backups alone are insufficient: private evidence objects and their metadata must be backed up consistently.

## 4. Monitoring, logging and alerts

Implement structured application logs with request/correlation IDs. Exclude passwords, session cookies, access tokens, student response text, evidence contents and unnecessary student identifiers.

Monitor at minimum:

- Application availability and database connectivity.
- HTTP 5xx rates and latency.
- Login failures, rate-limit events and privileged actions.
- Failed imports, failed scheduled jobs and integration errors.
- Evidence upload/scan/download failures.
- Backup age, restore verification and disk/object-storage capacity.

Send actionable alerts to an institution-owned on-call destination. Define retention and access controls for operational logs.

The current `/healthz` endpoint is a minimal database readiness probe only; it is not a monitoring or alerting system.

## 5. Evidence storage and key management

Before live evidence is accepted:

- Move evidence from local disk to private object storage with public access disabled.
- Encrypt in transit and at rest; use institution-controlled KMS-managed keys and rotation.
- Store object identifiers and cryptographic checksums in the database, not public URLs.
- Scan uploads with an institution-managed malware-scanning service before making them available for review.
- Quarantine files that fail scanning or cannot be scanned; fail closed in production.
- Preserve immutable access events and chain-of-custody metadata.
- Restrict downloads by case assignment and least privilege; require a reason for exceptional access.
- Test key rotation, revocation, backup and recovery.
- Apply approved retention, legal hold and secure deletion rules to both objects and backups.

The current local evidence directory and SHA-256 checks are development controls, not encrypted object storage or malware scanning.

## 6. Examination scheduling and attendance

Current development workflows include session creation, venue-overlap and candidate-overlap checks, candidate lists, seat labels, invigilator overlap checks, check-in/out and administrator review.

Added in this increment:
- Session attendance CSV export restricted to administrators and recorded in the audit log.
- Post-session reconciliation that flags missing check-ins as disputed for human review. It does not automatically conclude that a student was absent.

Still required:
- A calendar/timetable interface, bulk scheduling and rescheduling.
- Configurable exam duration, buffers, accessibility/accommodation seating and venue layouts.
- Capacity checks that include approved seat blocks, invigilator ratios and room closures.
- Concurrency-safe booking to prevent two simultaneous requests reserving the same venue or staff member.
- Approved late-arrival, check-out and exception policies.
- Human-reviewed attendance corrections with reason, evidence and independent approval.
- PDF exports and institution-approved report formats.
- Browser end-to-end tests for a complete examination day.

## 7. Integrity case review and appeals

Incident records are allegations requiring impartial review; risk indicators must never be treated as proof or automated disciplinary decisions.

Before institutional use, implement:
- Separate reporter, investigator, decision-maker and appeal reviewer permissions.
- Conflict-of-interest checks so a reporter cannot decide their own case.
- Reviewer assignment and reassignment history.
- Witness statements and evidence provenance.
- Immutable review events and externally protected audit export.
- Student notice, response deadline, extension request and accessible response channel.
- A formal appeal submission, independent appeal decision and reasoned outcome.
- Evidence access logs, legal holds and institution-approved retention/deletion jobs.
- Malware scanning and encryption before evidence access.

The current case workflow and response capture are an initial foundation. They are not a complete disciplinary or appeals process.

## 8. Biometric verification and non-biometric alternative

No face image, face embedding, biometric template, liveness result or biometric match is currently captured or processed by this application.

A manual/student-card check is available as the current alternative. Before any biometric pilot, the institution must approve the purpose, necessity, lawful basis, DPIA, vendor, hosting region, accuracy/bias evaluation, security architecture, retention schedule, access controls, incident response and independent audit. Provide a meaningful non-biometric route without academic penalty. A failed match must trigger human review, not an automatic misconduct finding or denial of examination access.

Do not enable a biometric provider or collect face data based only on a developer configuration change.

## 9. Institutional SIS and identity integration

The integration must be based on an institution-supplied, authorized API specification or approved secure file exchange. No university API endpoint, token, field mapping or email provider is assumed.

Required integration contract:

- Read-only SIS access initially, with a service account limited to approved student and academic fields.
- Explicit field mapping for student identifier, name, programme, faculty, department, enrolment, academic year, semester and status.
- Pagination, rate limits, timeouts, retries with backoff and idempotency.
- Dry-run preview, row-level validation, conflict report and authorized approval before applying updates.
- Never overwrite locally reviewed corrections silently.
- Record source system, sync timestamp, batch ID, source record ID and audit outcome.
- Reconcile deactivations, programme changes and withdrawn/deferred status safely.
- Protect API credentials in a secret manager and rotate them.
- Use institutional SSO/OIDC/SAML for staff identity when the institution provides a supported IdP; email alone is not authentication.
- Use approved institutional email/SMS services for notifications with delivery logs and opt-out/retention rules where applicable.

A generic adapter can be implemented after the institution provides the actual API contract and test environment.

## 10. Acceptance gates

No production go-live until all of the following have evidence:

1. PostgreSQL migration rehearsed and reconciled.
2. Production hosting, secrets, HTTPS, RBAC, MFA and session controls reviewed.
3. Encrypted database and evidence backups restored successfully.
4. Malware scanning, retention and legal-hold controls tested.
5. Full browser workflows and role-isolation tests pass.
6. Performance, accessibility and independent security testing pass.
7. SIS/identity integration tested with institution-authorized non-production records.
8. Biometric processing remains disabled unless separately approved.
9. Registrar, examination office, data protection officer, security team and institutional sponsor sign off.
