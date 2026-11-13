# Legacy attendance table retirement procedure

**Status:** Legacy table creation is disabled for new installations. Existing tables are preserved in place. Destructive retirement is deliberately gated on a database-specific archival rehearsal.

## Canonical attendance model

- `session_attendance` is the authoritative current-state projection keyed by `(session_id, student_id)`.
- `attendance_events` is the append-only event ledger for check-in/check-out and exception actions.
- `biometric_verification_events` records provider verification attempts, not attendance itself.

Current examination operations and biometric attendance routes write to the session-linked model. The old `examination_attendance` table has no active write path in these workflows.

## Change made in Phase 0

The registry bootstrap no longer creates `examination_attendance` on a new database. The schema bootstrap does not drop, truncate, rename or update a pre-existing table. This prevents fresh databases from acquiring a second, examination-level attendance store while preserving any historical records already present.

Tests cover both outcomes:
- A clean registry bootstrap does not create the deprecated table.
- A pre-existing legacy table and its sample record survive a subsequent registry bootstrap unchanged.

## Required process before physical removal from an existing institutional database

Do not run destructive SQL until the institution's database owner has approved the archive and retention plan.

1. Put the affected database into a maintenance/read-only window and take a verified backup.
2. Inspect whether `examination_attendance` exists; record its row count, schema, constraints, indexes, and date range.
3. Export every row, including primary keys and nullable metadata, to an institution-controlled restricted archive.
4. Map each legacy `examination_id` to the correct `examination_sessions` row. A single examination may have multiple sessions, so do not guess the mapping.
5. Where the mapping is unambiguous, compare candidate identity and attendance status/timestamps against `session_attendance` and `attendance_events`. Report conflicts; never silently overwrite the canonical ledger.
6. Obtain Registrar and ICT/data-owner approval for the archive, retention period, access permissions, and reconciliation report.
7. Test restore of the archive and verify row counts and checksums in an isolated database.
8. Only after sign-off, run a separately reviewed migration that removes the original table. Retain the approved archive and migration log.
9. Run the full application suite against SQLite and PostgreSQL and verify no application SQL references the retired table.

## Why the old table is not dropped automatically

A legacy row has `examination_id`, not `session_id`. Mapping it to a session can be ambiguous. Automatic copying or deletion could assign attendance to the wrong sitting or destroy evidence. Until the institution supplies the actual database and approves the mapping, preserving the table unchanged is the safe retirement state.

## Acceptance

- [x] New schema bootstrap no longer creates the legacy table.
- [x] Existing legacy rows survive bootstrap unchanged.
- [ ] Existing institutional databases inventoried and reconciled.
- [ ] Archive restored and verified by row count/checksum.
- [ ] Registrar/data owner approves archive and retention.
- [ ] Physical table removal approved and performed through a separately reviewed migration.
