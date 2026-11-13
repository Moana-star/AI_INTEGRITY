# PostgreSQL Migration and Production Readiness Runbook

**Current state: PostgreSQL runtime adapter and targeted CI integration are present; production deployment is not yet approved.** This runbook distinguishes implemented runtime capability from the remaining migration, security, governance and operational release gates.

## Current verified architecture

- `modules/database.py` provides the shared DB-API connection adapter. SQLite is the local-development default; PostgreSQL is selected explicitly through `DATABASE_URL`.
- `requirements.txt` includes SQLAlchemy 2.x and psycopg 3.x.
- The Flask entry point refuses `FLASK_ENV=production` unless PostgreSQL, a sufficiently long `FLASK_SECRET_KEY`, and Redis-backed rate-limit storage are configured.
- GitHub Actions includes a PostgreSQL runtime job that bootstraps an empty database, checks non-destructive repeat bootstrap, exercises Flask/module schema creation and runs targeted runtime integration tests.
- Runtime module `ensure_schema()` functions still create/upgrade parts of the schema. A complete, reviewed Alembic/versioned migration chain has not been established.
- The SQLite-to-PostgreSQL script is a guarded snapshot migration/reconciliation utility; it is not an ongoing schema migration framework.

Do not describe this application as SQLite-only, and do not describe the PostgreSQL adapter or targeted PostgreSQL CI as proof of production readiness.

## Remaining production blockers

- Expand PostgreSQL coverage across every registry, examination, candidate, seat, attendance, incident, evidence and appeal write path.
- Introduce a versioned migration chain and test upgrades from every supported deployed schema version.
- Complete the role/record authorization matrix and independent security assessment.
- Obtain institution-owned PostgreSQL, Redis, secret-management and deployment configuration.
- Implement and test encrypted backups, restore drills, retention and disaster recovery.
- Complete privacy, accessibility, load, concurrency and institutional acceptance testing.
- Obtain Registrar, ICT, data protection officer and system-owner approval before any live student-data or biometric processing.

## Rehearsed data migration

1. Freeze writes and take a verified SQLite snapshot.
2. Run the migration preflight and review all warnings.
3. Export/import tables in dependency order, preserving IDs and timestamps.
4. Reconcile row counts, null counts, primary/foreign-key orphans, unique keys and selected SHA-256 checksums.
5. Compare representative student, enrolment, session, attendance, incident, evidence and audit histories.
6. Run the complete application test suite against the target PostgreSQL version.
7. Obtain Registrar and data-owner sign-off before cutover.
8. Retain a tested rollback snapshot and documented read-only period.

Never migrate live student data into developer laptops or public test environments.

## Production secrets and network

- Use managed PostgreSQL with TLS and least-privilege application credentials.
- Store secrets in a managed secret store; never commit `.env`, passwords, database URLs or private keys.
- Use HTTPS, secure cookies, shared Redis-compatible rate-limit storage, restricted administrator access and network allowlists.
- Separate production, staging and test data.
- Keep production configuration fail-closed; do not remove startup guards to force deployment.

## Encrypted backup and recovery

- Use managed PostgreSQL encrypted snapshots plus point-in-time recovery/WAL retention.
- Encrypt exported backup artifacts with institution-controlled KMS keys.
- Define RPO/RTO with the University; do not invent these service levels.
- Restrict backup restore permissions and log every restore.
- Perform scheduled restore drills into an isolated environment and reconcile restored data.
- Define retention, legal hold, deletion and key-rotation policies with the University's data protection and ICT offices.

## Deployment and operations

- Deploy through a reviewed CI/CD pipeline with dependency pinning, migration gates and rollback strategy.
- Use a production WSGI server and managed process/container runtime.
- Add structured logs with sensitive-field redaction, metrics, error monitoring and actionable alerts.
- Add readiness/liveness probes, uptime monitoring, capacity tests, security scanning and incident response runbooks.
- Require penetration testing, accessibility review, backup-restore proof and institutional UAT before go-live.

## Release gate checklist

- [x] Shared SQLite/PostgreSQL runtime adapter is present.
- [x] Production startup guard requires PostgreSQL, a strong secret and Redis-backed rate limiting.
- [x] Targeted PostgreSQL bootstrap/runtime CI job passes.
- [ ] Complete versioned schema migration chain is reproducible from an empty PostgreSQL database.
- [ ] All PostgreSQL business workflows and concurrency/rollback cases pass.
- [ ] SQLite-to-PostgreSQL rehearsal and data reconciliation pass.
- [ ] TLS, network and secret-manager configuration are reviewed.
- [ ] Backup encryption, key custody and restore drill are verified.
- [ ] RPO/RTO are approved by University ICT.
- [ ] Security, privacy, accessibility and load tests pass.
- [ ] Registrar, ICT, data protection officer and system owner approve go-live.
