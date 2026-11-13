# PostgreSQL Migration: Technical Inventory and Execution Plan

## Current truth

The application is SQLite-backed. Production startup deliberately fails when FLASK_ENV=production is set. Setting DATABASE_URL alone will not make this application PostgreSQL-compatible. Do not deploy or enable production mode until all application modules, migrations, transaction semantics and tests use the PostgreSQL backend.

## Repository inventory

The following application files open SQLite connections directly and must be migrated together to avoid split-brain data:

- app.py
- modules/appeals.py
- modules/biometric_attendance.py
- modules/eligibility.py
- modules/identity_check.py
- modules/institutional_registry.py
- modules/integrity.py
- modules/operations.py
- modules/student_portal.py

SQLite-specific constructs found in the current source include:

- sqlite3.connect, sqlite3.Row, sqlite3.IntegrityError
- PRAGMA foreign_keys, PRAGMA table_info, sqlite_master
- executescript
- INTEGER PRIMARY KEY AUTOINCREMENT
- cursor.lastrowid and last_insert_rowid()
- INSERT OR IGNORE, ON CONFLICT upserts
- SQLite trigger syntax and dynamically applied ALTER TABLE migrations
- qmark (?) parameter placeholders

## Required target architecture

1. One database access package owns connections, transactions, row mapping, health checks, migrations and backend selection.
2. Application modules depend on that package, not sqlite3.connect.
3. PostgreSQL uses psycopg 3 with explicit connection pooling, parameterized SQL, transaction boundaries and server-side statement timeouts.
4. A versioned migration system is the only schema-change mechanism. Startup must not run ad-hoc CREATE TABLE/DDL in web requests.
5. PostgreSQL migrations create all legacy and institutional tables, indexes, unique constraints, check constraints, append-only audit triggers and foreign keys. Migrations must be reviewed and reversible where practical.
6. Production configuration requires PostgreSQL TLS, a least-privilege runtime role, a separate migration role, managed secrets and encrypted backups.
7. SQLite remains a local-development/test adapter only until the PostgreSQL migration is accepted; never write some modules to SQLite and others to PostgreSQL.

## Migration phases

### Phase A — schema freeze and data inventory
- Capture the current SQLite schema and row counts.
- Record foreign-key relationships, unique indexes, triggers and CHECK rules.
- Identify orphan records and duplicate keys before export.
- Create a tested migration manifest with source-to-target column mappings.
- Decide institutional IDs and preserve every existing primary key/reference.

### Phase B — connection and repository layer
- Introduce a single DB interface and PostgreSQL adapter.
- Convert all SQL placeholders and driver-specific row/error handling.
- Remove runtime schema creation from request handlers.
- Add transaction, rollback, concurrency and connection-pool tests.
- Keep SQLite tests passing until all modules are converted.

### Phase C — schema and data migration
- Create versioned PostgreSQL DDL and seed/reference data.
- Migrate records in dependency order with stable IDs.
- Verify row counts, checksums, foreign keys, unique constraints and audit history. Never migrate biometric image/template data because EIMS does not hold those artifacts.
- Test interrupted migration and safe rerun/reconciliation.

### Phase D — integration and cutover rehearsal
- Run the complete test suite against PostgreSQL, not only SQLite.
- Run browser end-to-end tests, role/tenant isolation tests and concurrent attendance check-in tests.
- Rehearse backup restore and rollback to the source database.
- Run a read-only comparison period and obtain Registrar/ICT acceptance.

### Phase E — production activation
- Provision managed PostgreSQL with TLS, backups, monitoring and least privilege.
- Set production secrets and migration version.
- Perform a controlled cutover with a verified backup and rollback window.
- Only then remove the production-startup guard.

## Acceptance gates

- No application module calls sqlite3.connect in PostgreSQL production mode.
- All migrations are versioned, repeatable where designed, and tested on a clean database and an upgrade copy of the real schema.
- All existing tests plus PostgreSQL integration tests pass.
- Attendance duplicate checks are concurrency-safe through database unique constraints and transaction handling.
- Restore drill and integrity verification succeed.
- Security review and institutional data-governance approvals are recorded.

## Current blockers

No PostgreSQL service, database credentials, institutional deployment environment or data export has been supplied in this task. Therefore no PostgreSQL server migration or cutover has been executed. The production guard must remain in place. The inventory above is based on the current source tree and is the required migration worklist, not a claim of PostgreSQL support.

## Migration utility added

- `scripts/migrate_sqlite_to_postgres.py` performs a fail-closed, one-way copy from a fully initialized SQLite source to an empty PostgreSQL public schema.
- It validates SQLite integrity and foreign keys, inventories every table and row count, refuses unknown SQLite triggers, recreates the known append-only history guards in PostgreSQL, copies records in dependency order, resets identity sequences, and verifies row counts.
- Default invocation is a dry run. Applying requires both `--apply` and `--confirm-empty-target`; the destination URL is read only from `EIMS_POSTGRES_URL` so credentials are not placed in command-line arguments.
- It intentionally does not activate PostgreSQL for Flask. The runtime modules still use SQLite directly, so production remains blocked.
- Preflight tests cover valid history triggers, unknown-trigger refusal, broken foreign-key refusal and table counting. These tests do not replace a real PostgreSQL migration rehearsal.
