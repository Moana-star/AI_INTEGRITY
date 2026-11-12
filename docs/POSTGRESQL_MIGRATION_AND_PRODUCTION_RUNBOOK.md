# PostgreSQL Migration and Production Readiness Runbook

**Current state: NOT production deployable.** The application still uses SQLite directly in the Flask entry point and multiple modules. This runbook is a controlled migration plan, not a claim that PostgreSQL or production backups are already implemented.

## Why the current app is blocked from production

- app.py and modules open the SQLite file directly.
- SQL uses SQLite-specific ? placeholders, PRAGMA, INSERT OR IGNORE, ON CONFLICT, lastrowid, SQLite trigger syntax and executescript.
- Schema creation is performed by runtime ensure_schema() functions instead of a complete versioned migration chain.
- Existing tests are SQLite-only.
- No PostgreSQL service, institutional data owner, backup KMS/key custody, or deployment environment was supplied.

The app now deliberately refuses FLASK_ENV=production startup until a PostgreSQL adapter and migration have been implemented and verified. Do not remove that guard to force a deployment.

## Required engineering sequence

### 1. Database abstraction
- Introduce SQLAlchemy 2.x Core/ORM and a single connection/session factory.
- Move every module from direct sqlite3.connect to the shared factory.
- Replace SQLite-only SQL with portable SQLAlchemy statements.
- Keep backend selection explicit; do not silently fall back to SQLite in production.
- Add connection pooling, transaction boundaries, health/readiness checks and query timeouts.

### 2. Versioned schema migrations
- Introduce Alembic and create a baseline migration representing the current schema.
- Add explicit migrations for role policy, academic registry, exam sessions, eligibility evidence, appeals, audit and evidence metadata.
- Preserve existing primary keys, unique constraints, foreign keys, check constraints and append-only protections.
- Review trigger semantics separately for PostgreSQL; do not assume SQLite triggers are portable.

### 3. Rehearsed data migration
- Freeze writes and take a verified SQLite snapshot.
- Export each table in dependency order, preserving IDs and timestamps.
- Load into an isolated PostgreSQL staging database.
- Reconcile row counts, null counts, primary/foreign-key orphans, unique keys and selected SHA-256 checksums.
- Compare representative student, enrolment, session, attendance, incident, evidence and audit histories.
- Run the complete test suite against PostgreSQL.
- Obtain Registrar and data-owner sign-off before cutover.
- Retain a tested rollback snapshot and documented read-only period.

### 4. Production secrets and network
- Use managed PostgreSQL with TLS and least-privilege application credentials.
- Store secrets in a managed secret store; never commit .env, passwords, database URLs or private keys.
- Use HTTPS, secure cookies, shared Redis-compatible rate-limit/session storage, restricted admin access and network allowlists.
- Separate production, staging and test data. Never copy live student data into developer laptops or public test environments.

### 5. Encrypted backup and recovery
- Use managed PostgreSQL encrypted snapshots plus point-in-time recovery/WAL retention.
- Encrypt exported backup artifacts with institution-controlled KMS keys.
- Define RPO/RTO with the University; do not invent these service levels.
- Restrict backup restore permissions and log every restore.
- Perform scheduled restore drills into an isolated environment and reconcile restored data.
- Define retention, legal hold, deletion and key-rotation policies with the University's data protection and ICT offices.

### 6. Deployment and operations
- Deploy through a reviewed CI/CD pipeline with pinned dependencies, migration gates and rollback strategy.
- Use a production WSGI server and managed process/container runtime.
- Add structured logs with sensitive-field redaction, metrics, error monitoring and actionable alerts.
- Add readiness/liveness probes, uptime monitoring, capacity tests, security scanning and incident response runbooks.
- Require penetration testing, accessibility review, backup restore proof and institutional UAT before go-live.

## Release gate checklist

- [ ] SQLAlchemy adapter used by every route/module; no direct SQLite production connections.
- [ ] Alembic migration chain reproducible from an empty PostgreSQL database.
- [ ] SQLite-to-PostgreSQL rehearsal passes reconciliation.
- [ ] PostgreSQL integration tests pass.
- [ ] TLS and secret-manager configuration reviewed.
- [ ] Backup encryption, key custody and restore drill verified.
- [ ] RPO/RTO approved by University ICT.
- [ ] Security, privacy, accessibility and load tests passed.
- [ ] Registrar, ICT, data protection officer and system owner approve go-live.
