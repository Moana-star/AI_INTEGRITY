# Kisii University Examination Policy Mapping

**Target institution:** Kisii University  
**Status:** Development mapping only; not an approved University policy configuration  
**Prepared from public documents checked:** 12 November 2026

## Primary public sources

1. **Kisii University Student Handbook, 4th edition (2019)**, published by the Dean of Students' Office and hosted on the official university domain:  
   https://kisiiuniversity.ac.ke/storage/public/downloads/Kisii%20University%20Revised%20Handbook%202019.pdf
   - University Examination Regulations, handbook pages 42–47 (PDF lines 899–1047).
2. **The Kisii University Statutes, 2020, Legal Notice No. 153 of 2020**, published by Kenya Law:  
   https://new.kenyalaw.org/akn/ke/act/ln/2020/153/eng%402020-08-14/source.pdf
   - Examination Processing and General Requirements, statute section 5 (PDF lines 3933–3961).
   - Invigilation of Examinations, statute section 6 (PDF lines 3963–3992).
   - Assessment Criteria and Procedures, statute section 7 (PDF lines 3994 onward).

The Kenya Law page explicitly warns that the displayed 2020 Legal Notice version is not necessarily the latest available version. The Registrar (Academic Affairs) must confirm the currently operative statutes, examination policy, Senate circulars and school-specific rules before production activation.

## Rule-to-system mapping

| Publicly stated requirement | EIMS treatment | Evidence needed |
|---|---|---|
| Register for the scheduled course | Hard eligibility prerequisite | Student-unit enrolment record, academic year and semester |
| Pay prescribed examination fees / clear fees | Hard eligibility prerequisite when applicable | Finance-system clearance or approved finance evidence reference |
| At least 80% lecture attendance (2019 handbook) | Configurable policy threshold; current draft default 80% | Total and attended lecture sessions from approved attendance register |
| Sit required CATs; at least two CATs per course (2019 handbook) | Configurable CAT minimum; current draft default 2 | Course assessment plan and CAT attendance/participation record |
| Examination card and student ID presented at exam | Identity/check-in workflow, not a substitute for academic eligibility | Examination card issue/validation and manual student-ID check |
| Special examination requires prior written authorization | Separate special-exam authorization workflow required | Authorization from the office identified by the applicable policy |
| Supplementary eligibility: fail no more than 25% of annual courses and pay prescribed fee (2019 handbook) | Not automatically adjudicated yet; requires annual results and finance data | Senate-approved annual results, total courses, failed courses, fee evidence |
| At most 50% failures: repeat year; over 50%: discontinuation (2019 handbook) | Academic progression flag only after verified annual results and Senate decision | Approved results and formal progression decision |
| Student cannot proceed unless prior examination requirements are satisfied (2020 Statutes) | Progression hold/review flag; never automatic discontinuation | Approved academic record and authorized progression decision |
| At least two invigilators; course lecturer is Chief Invigilator (2019 handbook) | Session scheduling validation to enforce at least two active invigilator assignments before activation | Verified staff appointment/assignment and course lecturer mapping |
| Students assemble 30 minutes before start (2019 handbook); 2020 Statutes say 10 minutes | Display timing as policy-configurable; do not silently choose one | Registrar confirmation of current operational rule |
| No entry after 30 minutes from start (both sources) | Late-entry warning and controlled exception workflow; no automatic misconduct finding | Server timestamp and Chief Invigilator decision |
| Disability-related adjustments | Accommodation and accessible seating workflow | Approved accommodation instruction, minimal necessary data |
| Review of Senate disciplinary verdict within 21 days of communication | Separate Senate-verdict review workflow needed; do not conflate with incident appeal | Senate decision and date communicated to student |

## Conflicts and policy decisions requiring Registrar confirmation

- The 2019 handbook describes undergraduate CATs as normally 30% and postgraduate CATs as 40%, unless the syllabus says otherwise. The 2020 Statutes state ordinary examinations consist of 30% CAT and 70% final examination. Do not implement a grade calculation until the current approved policy and programme-specific exceptions are confirmed.
- The 2019 handbook asks candidates to report 30 minutes before the examination. The 2020 Statutes say 10 minutes before. The no-entry-after-30-minutes provision appears in both sources. Confirm the currently enforced arrival time.
- The 2019 handbook is an older public document and the Kenya Law page warns that its displayed Statutes version may not be the latest. Obtain current signed/approved copies, including Senate amendments and school-specific rules.
- Fee clearance is a sensitive administrative decision. EIMS must consume an authorized Finance/SIS result or an auditable confirmation; it must not infer clearance from a receipt image or student assertion.
- Lecture attendance and CAT evidence must come from authorized academic records. Missing, stale or contradictory evidence results in **pending/manual review**, never a positive clearance.

## Current implementation in this branch

- Versioned, independently approved policy drafts.
- Rule parameters for active academic status, registered unit, fee clearance, minimum attendance percentage and minimum CAT count.
- Registrar, administrator or examination-officer evidence entry for total/attended lectures, CATs required/sat and fee-clearance status, with a source reference and verifying staff account.
- Missing evidence remains pending. Explicit failed requirements return an explainable ineligible result.
- The engine applies a decision only to scheduled sessions; it does not rewrite completed examination records.
- Added an annual progression/supplementary review calculator and auditable register: up to 25% failed courses can be marked supplementary-eligible only when fee evidence is recorded; over 25% and up to 50% returns repeat-year review; above 50% returns a discontinuation-review-required flag. Failed supplementary courses return a repeat-failed-courses pathway.
- These pathway results are recommendations for Registrar/Senate review only. They never automatically change academic status or discontinue a student.
- Newly created policy drafts prefill 80% attendance and two CATs from the 2019 handbook, but the policy is not pre-approved. A second administrator must independently approve it before it can be used.
- Session activation now requires an active venue within capacity and at least two active invigilators.
- A separate Senate verdict register records the communication date and enables a student to submit a review request within 21 calendar days. This is distinct from an ordinary incident appeal.
- The rule defaults (80% attendance and two CATs) are prefilled from the 2019 handbook as a **draft starting point only**. No policy is pre-approved or activated by this document.

## Not yet implemented

- Finance/SIS integration and independently reconciled fee status.
- Authoritative lecture and CAT attendance feeds.
- Integration with authoritative annual course-result feeds; current pathway calculation uses source-referenced counts entered by authorized staff.
- Special-examination authorization and evidence workflow.
- Senate review workflow with a verified 21-day communicated-decision deadline.
- Programme-level CAT weighting and grading policy.
- Full accommodation and accessible seating workflow.
- Confirmation of current policy by Registrar, Senate and relevant University offices.

## Go-live rule

No rule in this mapping is to be treated as an official production decision until the Registrar (Academic Affairs) confirms the current controlling document, section, approval date, effective date, programme scope and authorized data source. Preserve the original source reference and approver in every policy version. Do not backdate or silently rewrite prior decisions.
