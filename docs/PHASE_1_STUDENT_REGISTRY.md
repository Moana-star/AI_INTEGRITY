# Phase 1 — Student Information Management

**Status: Implementation complete; operational acceptance pending.** The application code and automated checks cover the Phase 1 registry foundation. The phase must not be closed until the local demonstration-record cleanup, manual workflow checks, and current CI run are verified against the intended database.

## Source-of-truth model

- `students` remains the canonical student identity table.
- `student_profiles` stores additive academic placement and contact fields.
- `academic_units` stores unit catalogue records.
- `student_unit_enrolments` links students to units for a specific academic year and semester. Its uniqueness constraint prevents duplicate enrolment for the same student, unit, year and semester.
- `academic_history_events` records attributable, append-only academic events.
- `audit_events` records staff actions affecting registry records.

Admission number is the unique student identifier. EIMS does not infer an institutional identity from a name, email address or biometric result.

## Existing capabilities confirmed by repository inspection

- Registrar/admin-managed student creation and updates.
- Admission number uniqueness enforced by the database.
- Programme, year of study, faculty, department, institutional email, phone, academic year, semester and academic status fields.
- Registry search by admission number, names, programme and department.
- Append-only academic history, including status-change events.
- Unit catalogue and student-to-unit enrolment workflow in Academic Operations.
- Eligibility evaluation consumes the registry status and semester-specific unit-enrolment records; an approved institutional policy and source-referenced evidence are required before a final decision.

## Phase 1 changes

- Student CSV imports now validate the complete file before writing.
- Duplicate admission numbers and institutional emails within the file are reported.
- Existing admission numbers and institutional emails are reported as row-level errors.
- A file containing any invalid row is rejected as a whole; no partial student import is committed.
- Each imported student and the import operation receive audit events.
- The import page displays a row-by-row validation report.
- A consolidated read-only student record view displays profile information and unit-enrolment history.

## Explicit limitations and release gates

- The student import interface currently accepts UTF-8 CSV only; native XLS/XLSX import is not implemented.
- Profile photograph upload/storage is not implemented in the registry. Do not store student photos in the public repository or local web directory. This requires approved private object storage, access controls, retention/deletion rules and institutional authorization.
- There is no live SIS integration. Institutional records must be supplied through an authorized export or approved integration.
- Existing local records must not be presumed authentic solely because they are present in the database. Their source and authority must be confirmed by the Registrar/data owner.
- Current academic eligibility is only as authoritative as the approved policy and source-referenced evidence supplied by the institution.
- The CSV endpoint has a 2 MB upload limit. Large institutional imports require a separately designed background/batch workflow with resumability and reconciliation.

## Demonstration-record cleanup (local SQLite only)

Run from the repository root after pulling the development branch. First inspect the proposed changes; the default command is read-only:

```powershell
python scripts/remove_demo_students.py
```

If the report shows only the three expected demonstration records and no blocking references, obtain the administrator's numeric user ID from the authorized local staff account and apply the cleanup:

```powershell
python scripts/remove_demo_students.py --apply --actor-user-id <ADMIN_USER_ID>
```

The script creates a timestamped backup before writing. It refuses the entire operation if any demonstration student is referenced by operational or academic-history tables outside the narrowly allowed profile and unit-enrolment tables. In that case, do not force deletion: review the reported dependency and preserve institutional evidence. The script does not run against PostgreSQL; PostgreSQL requires a separately reviewed migration/maintenance procedure.

## Acceptance tests required

1. Create and update a student without changing the student's internal database identity.
2. Reject missing mandatory identity fields and invalid academic status/year values.
3. Enforce unique admission numbers and unique institutional email addresses.
4. Search by admission number, name, programme and department.
5. Display the consolidated student record and all semester-specific unit enrolments.
6. Prevent duplicate student/unit/year/semester enrolment.
7. Preserve academic history as append-only and attribute every change to an authenticated staff member.
8. Validate CSV headers, encoding, malformed rows, duplicate rows and conflicts with existing records.
9. Prove that an invalid CSV causes zero student writes and zero misleading success audit entries.
10. Verify the import and registry workflows on both SQLite and PostgreSQL.
11. Confirm authorization and CSRF protection for all registry mutations.
12. Complete institutional data-owner review before loading real student records.
13. Run the demonstration cleanup in dry-run mode, review all dependencies, apply it against the intended local database, and verify only the three named records were removed.
14. Verify student create/edit/search/import workflows manually in the running application and confirm current CI is green.

## Operational safety

Use synthetic data in automated tests only. Do not commit real student records, identity documents, photographs, credentials or database backups to GitHub. The cleanup utility creates a separate pre-cleanup backup; retain it under the institution's approved backup policy. Do not overwrite or delete the original database or existing backups.
