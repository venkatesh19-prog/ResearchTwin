# ResearchTwin 2.0 Features

Each area lists what it does, who can use it, and where it lives. The **Status** column records what was verified on 2026-11-12; `TESTING.md` explains how.

| # | Area | Who | Frontend view | Status |
|---|---|---|---|---|
| 1 | Admin groups and role management | Admin | Admin console → Account Management, Groups | PASS |
| 2 | User and researcher verification | Faculty submits, admin decides | Researcher Verification | PASS |
| 3 | Workspaces | Student and faculty members | Workspaces | PASS |
| 4 | Teams and collaboration recommendations | Students and faculty | Research Teams | PASS |
| 5 | Research opportunities and eligibility | Everyone reads; faculty publish research, admins publish funding | Opportunities | PASS |
| 6 | Applications | Students apply; the opportunity owner decides | My Applications, Opportunities | PASS |
| 7 | Research intelligence | Signed-in users; rebuild is admin-only | Research Intelligence | PASS |
| 8 | Analytics | Signed-in users | Analytics | PASS |
| 9 | Literature library | Every account, private to its owner | Literature Library | PASS |
| 10 | Research proposals | Owner plus invited editors and viewers | Research Proposals | PASS |
| 11 | Thesis management | Student owner and faculty supervisor | Thesis Tracking | PASS |
| 12 | Publications | Owner | Publications | PASS |
| 13 | Research labs | Faculty create and manage; visibility rules apply | Research Labs | PASS |
| 14 | Institutions | Admins manage; members see their own | Institutions | PASS |
| 15 | Inter-university collaborations | Lab owners at different institutions | Inter-university Collaborations | PASS |
| 16 | Search history | Each account, private | Search History | PASS |

Production sign-in with real accounts is the one acceptance step left to the project owner (see `TESTING.md`).

## Details

### 1. Admin groups and role management
- **Groups are role cohorts.** Registration places every student in `students` and every faculty member in `faculty`; administrators are never placed in a group.
- **Group membership:** admins can remove a member and add them back, but only to the group matching their role. Anything else returns `400`, for example "Student accounts can only join the students group".
- **Account management:** list users, change role, activate or deactivate, revoke sessions, reset a password, export an account's data.
- **Audit:** every change is written to `audit_events`, which admins can browse.
- **API:** `/admin/users*`, `/admin/groups*`, `/admin/audit-events`.

### 2. Verification
- **Submitting:** a faculty member whose account is linked to a researcher record submits a verification request with an evidence reference. There is at most one pending request per researcher.
- **Deciding:** admins verify or reject. A verification can carry an expiry, and public directory views show the status.
- **API:** `/faculty/me/researcher-link/verification`, `/admin/verifications*`, `/researchers/{id}/verification`, `/researchers/verification-summary`.

### 3. Workspaces
- **Creation:** accepting a student's collaboration request creates a workspace. The student is its owner and the faculty member a member.
- **Contents:** tasks (`todo` / `in_progress` / `done`, with assignee and due date), milestones and comments.
- **Access:** non-members get `403` or `404`.
- **API:** `/workspaces/*`, plus `/students/me/collaboration-requests` and `/faculty/me/collaboration-requests/{id}/decision`.

### 4. Teams and collaboration recommendations
- **Teams:** students and faculty create teams, invite members, and accept or decline invitations. Only owners manage membership.
- **Recommendations:** `POST /teams/{id}/recommendations` suggests researchers from the team's combined profile.
- **API:** `/teams*`.

### 5. Research opportunities and eligibility
- **Publishing:** faculty publish *research* opportunities tied to their own linked researcher record. Only admins publish *funding* opportunities, which never reference a researcher.
- **Lifecycle:** `draft` / `open` / `closed`, with search and filtering.
- **Matching:** `GET /opportunities/{id}/eligibility` explains whether a student qualifies, and `POST /students/me/opportunity-matches` ranks open opportunities for the student.
- **Optional import:** a grants.gov import, admin-triggered and off unless `FUNDING_GRANTS_GOV_ENABLED` is set.

### 6. Applications
- **Applying:** students apply with a message, with at most one pending application per opportunity.
- **Deciding:** the opportunity owner sees applicants and accepts or rejects. A student can withdraw a pending application.
- **API:** `/opportunities/{id}/applications*`, `/students/me/opportunity-applications`.

### 7. Research intelligence
- **Analyses:** clusters, a similarity network, trends, topic prediction from free text, and a knowledge graph, all computed from researcher records.
- **Rebuilds:** only admins can rebuild clusters; reads serve the latest run.
- **API:** `/research-intelligence/*`, `/researchers/intelligence`.

### 8. Analytics
- **University view** (`/analytics/university`) and **department view** (`/analytics/departments`).
- **Contents:** researcher counts, verification state, collaboration totals and acceptance rate, research-area distribution, user counts.
- **Source:** computed from live records, with nothing hard-coded.

### 9. Literature library
- **Entries:** each user keeps private entries with title, authors, venue, year, DOI, URL, abstract, notes, tags, review status (`to_read`, `reading`, `reviewed`, `archived`) and a citation key unique per owner.
- **Citations:** proposals cite entries from the owner's library.
- **API:** `/literature*`.

### 10. Research proposals
- **Structure:** proposals have ordered sections, collaborators (`editor` or `viewer`), citations and immutable versions. Status is `draft`, `submitted` or `archived`.
- **Permissions:** viewers can read but not edit.
- **API:** `/proposals*`.

### 11. Thesis management
- **Ownership:** a student records a thesis with a faculty supervisor.
- **Status:** status changes follow a transition table, `proposed → in_progress → submitted → defended → completed`, plus allowed reversals and withdrawal.
- **History:** milestones and a full progress history are kept.
- **API:** `/theses*`.

### 12. Publications
- **Tracking:** publication submissions move through `draft → submitted → under_review → revision_requested / accepted / rejected → published`, or `withdrawn`.
- **History:** a status event is recorded for every change, and numbered revisions are kept.
- **API:** `/publication-submissions*`.

### 13. Research labs
- **Creation:** faculty create labs within their own institution, as `public` or `institution`-only, and manage members.
- **Visibility:** the lab list shows public labs, the caller's institution's labs and the caller's own labs.
- **API:** `/labs*`.

### 14. Institutions
- **Management:** admins create and rename institutions and assign members.
- **Rules:** each account belongs to at most one institution. Members see their institution with member and lab counts.
- **API:** `/institutions*`, `/admin/institutions*`.

### 15. Inter-university collaborations
- **Proposing:** a lab owner proposes a collaboration with a visible lab at another institution.
- **Responding:** the partner lab's owner accepts (`active`) or declines. Statuses follow a transition table: `proposed → active / declined / withdrawn`, then `active → completed / withdrawn`.
- **Duplicates:** only one open collaboration per lab pair (`409` otherwise).
- **API:** `/interuniversity-collaborations*`.

### 16. Search history
- **Behaviour:** queries are recorded per user and listed newest first. Each user sees only their own.
- **API:** `/search-history`.

## Core 1.x features (still present)

- **Profiles:** student and faculty profiles.
- **Directory:** a researcher directory with admin create, edit, delete and CSV import.
- **Recommendations:** ML researcher recommendations with explanations.
- **Development planning:** skill-gap roadmaps with saved milestone progress, and expertise-gap analysis.
- **Collaboration requests:** students request to work with researchers.
