# Kisii University staff authentication and role migration

## What this increment implements

- Adds an additive SQLite migration for `users.institutional_role`; the existing
  constrained `users.role` column remains intact for compatibility.
- Backfills existing administrator and invigilator accounts without deleting or
  rebuilding user records.
- Adds staff profile and role-change audit tables.
- Uses the institutional role column at staff login and supports administrator,
  registrar, examination officer and invigilator roles. Student authentication
  remains in the separate student portal.
- Disables public staff self-registration. New staff accounts are provisioned
  through an administrator-only page and require a role, a 12-character
  password, an authorization reason and an employee number for invigilators.
- Routes registrar sign-in to the registry, examination-officer sign-in to
  examination operations, and invigilator sign-in to the assigned-staff area.
- Grants registrar access to registry workflows; examination officers can use
  examination operations and incident review; invigilators remain restricted to
  assigned operations and incidents.

## Important boundaries still outstanding

- This is not yet full route-by-route/object-level authorization coverage.
  Existing legacy administrator routes remain administrator-only.
- Role provisioning currently relies on an administrator's assertion; it does
  not verify staff identity against Kisii University HR/SSO.
- MFA, institutional SSO, secure invitation delivery, account lockout policy,
  recovery workflow and role revocation UI are not implemented.
- Student remains authenticated through a separate student portal account
  table. Student account lifecycle and institutional identity integration need
  further work.
- The legacy `users.role` column is retained intentionally. PostgreSQL
  migration must introduce a versioned schema and a verified data migration;
  this SQLite additive migration is not a PostgreSQL migration.

## Local verification

After pulling the feature branch, run:

```powershell
python -m unittest discover -v
```

Use only synthetic records. Do not provision real Kisii University staff or
student accounts until institutional authorization and security review are in
place.
