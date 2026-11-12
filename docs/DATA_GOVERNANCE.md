# EIMS Data Governance and Biometric Safeguards

## Scope

This document defines minimum design safeguards for the institutional direction of EIMS. It is not legal advice, a completed Data Protection Impact Assessment (DPIA), or evidence of institutional approval.

## Student information

The registry should use the admission number as its unique student identifier. Names, programme, faculty, department, year, academic year, semester, and academic status should be maintained only where they serve a defined academic or examination purpose.

Institutional email and telephone number are optional fields and should only be populated when approved for the intended workflow. Do not collect national identity numbers, dates of birth, home addresses, family details, medical histories, or other sensitive information by default.

## Access and accountability

- Restrict student registry access to authorized roles.
- Apply least-privilege permissions to student, attendance, incident, and evidence records.
- Record who creates or changes important institutional records.
- Do not expose student information in public URLs, logs, or error messages.
- Define retention and secure deletion schedules with the institution.
- Provide a correction and dispute process for inaccurate records.
- Protect exports and imported files; delete temporary copies when no longer required.

## Attendance and identity verification

Attendance is an examination-session record, not a disciplinary conclusion. Store the session, student, attendance state, timestamps, verification method, responsible invigilator, device reference where appropriate, and the reason for any manual override.

Manual verification and institution-approved student-card workflows must remain available. A failed automated identity check must lead to a review process, not automatic exclusion from an examination.

## Biometric processing boundary

The current EIMS registry does not capture, compare, or store face images, face embeddings, biometric templates, or liveness recordings. The attendance schema includes a future verification-method value for provider integration, but that value does not mean a biometric service exists or is enabled.

Before any biometric pilot:
1. Obtain documented institutional authorization and identify the controller/processor responsibilities.
2. Establish and document the lawful basis and necessity of the proposed processing.
3. Complete a DPIA and consult the institution's data protection officer and legal advisers.
4. Provide clear privacy notices and a meaningful non-biometric alternative.
5. Define purpose limitation, retention, deletion, access, and breach-response procedures.
6. Select and independently evaluate the biometric provider and its security controls.
7. Test false-match and false-non-match performance across relevant demographic groups and capture conditions.
8. Assess presentation-attack/liveness controls without treating them as infallible.
9. Provide human review, correction, and appeal routes.
10. Conduct a limited, supervised pilot and suspend processing if unacceptable error or harm is observed.

No face match, confidence score, or attendance anomaly may independently establish misconduct, determine guilt, or trigger a disciplinary sanction.

## Data classification

| Data class | Examples | Baseline handling |
|---|---|---|
| Academic record | Admission number, programme, year, unit enrolment | Restricted institutional access |
| Contact detail | Institutional email, phone | Optional and purpose-limited |
| Attendance record | Session, timestamps, status, verifier | Restricted, auditable access |
| Incident record | Observation, response, review outcome | Strictly restricted; fair process |
| Evidence | Files, references, checksums, access events | Private storage and chain-of-custody controls |
| Biometric data | Face image, template, embedding, liveness data | Not collected by current implementation; separate approval and safeguards required |

## Operational warning

The repository currently uses a local SQLite database and demonstration-oriented authentication. The safeguards described here are design requirements, not a statement that the current application is ready to process real university records.
