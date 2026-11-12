# ResearchTwin Database

PostgreSQL (Neon) in production; SQLite for local development and the test suite. The schema is owned by SQLAlchemy models in `backend/app/models.py` and changed only through Alembic migrations in `backend/migrations/`.

## Production

| Item | Value |
|---|---|
| Provider | Neon PostgreSQL 18, project `super-hill-93410289`, region aws-us-east-2 |
| Branch / endpoint | `production` (`br-little-waterfall-bdtwjbbf`) / `ep-floral-thunder-bddca63h` (direct connection) |
| Database | `neondb` |
| Schema revision | `0012_search_history` (Alembic head) |
| Tables | 44 (43 application tables + `alembic_version`) |

Connection strings are secrets. They live only in the Render dashboard (`DATABASE_URL`) and in operator-held files outside the repository; they are never committed.

## Migrations

A linear chain with a single head. Run from `backend/` only after confirming the target (see `DEPLOYMENT.md`).

| Revision | Purpose |
|---|---|
| `0001_baseline_schema` | Baseline schema |
| `0002_audit_events` | Audit events |
| `0003_groups` | Groups and group memberships |
| `0004_verified_profiles` | Verified researcher profile requests |
| `0005_workspaces_and_teams` | Collaboration workspaces and research teams |
| `0006_opportunities` | Research opportunities, funding calls and applications |
| `0007_research_intelligence` | Persisted research clustering results |
| `0008_research_outputs` | Literature, proposals, theses and publication submissions |
| `0009_research_labs` | Research labs and inter-university collaboration |
| `0010_repair_batch_2` | Unique open collaborations and pending collaboration requests |
| `0011_drop_redundant_indexes` | Drop redundant primary-key and unique-prefix indexes |
| `0012_search_history` | Add per-user search history |

```powershell
alembic current
alembic upgrade head
alembic check   # models and migration head agree
```

On PostgreSQL, `/ready` returns 503 unless `alembic_version` equals the code's head, so a backend never serves traffic against an unmigrated schema.

## Integrity rules worth knowing

- One pending collaboration request per (student, researcher) and one open inter-university collaboration per lab pair are enforced by partial unique indexes (`uq_collaboration_requests_pending`, `uq_interuniversity_collaborations_open_pair`).
- A workspace exists only for an accepted collaboration request (`collaboration_workspaces.collaboration_request_id` is unique).
- Each faculty account links to at most one researcher record, and each record to at most one faculty account.
- Each account belongs to at most one institution (unique index). A lab belongs to one institution; the API only lets members of that institution create labs there.
- Groups are role cohorts: `students` and `faculty`. Registration adds new accounts automatically; administrators are never placed in a group.
- At most one pending verification per researcher; verified records can expire.
- Status values follow server-side transition tables (theses, publications, inter-university collaborations); an illegal change returns `409`.

## Tables

Notation: `!` = NOT NULL, `->table.col` = foreign key, `UQ(...)` / `UIDX(...)` = unique constraint / unique index (with its `WHERE` condition when partial).

### Identity and access

**`users`** — `id:integer`, `email:varchar!`, `full_name:varchar!`, `role:varchar!`, `password_hash:varchar!`, `is_active:boolean!=True`, `created_at:integer!`
  - Constraints: `UIDX(email)`

**`auth_sessions`** — `id:integer`, `user_id:integer!->users.id`, `token_hash:varchar!`, `created_at:integer!`, `expires_at:integer!`, `revoked_at:integer`
  - Constraints: `UIDX(token_hash)`

**`audit_events`** — `id:integer`, `actor_user_id:integer->users.id`, `action:varchar!`, `target_type:varchar!`, `target_id:integer`, `detail:text!=''`, `created_at:integer!`

**`rate_limit_counters`** — `bucket_hash:varchar`, `window_start:integer!`, `count:integer!`, `updated_at:integer!`

**`groups`** — `id:integer`, `name:varchar!`, `created_at:integer!`
  - Constraints: `UIDX(name)`

**`group_memberships`** — `id:integer`, `group_id:integer!->groups.id`, `user_id:integer!->users.id`, `created_at:integer!`
  - Constraints: `UQ(group_id,user_id)`

**`search_history`** — `id:integer`, `user_id:integer!->users.id`, `query:varchar!`, `created_at:integer!`

### Directory, profiles and verification

**`researchers`** — `id:integer`, `name:varchar!`, `department:varchar`, `designation:varchar`, `experience:integer`, `research_areas:text`, `expertise:text`, `skills:text`, `publications:text`, `projects:text`, `profile_url:varchar`

**`researcher_verifications`** — `id:integer`, `researcher_id:integer!->researchers.id`, `status:varchar!='pending'`, `evidence_reference:text!=''`, `note:text!=''`, `review_note:text!=''`, `submitted_by_user_id:integer->users.id`, `reviewed_by_user_id:integer->users.id`, `submitted_at:integer!`, `reviewed_at:integer`, `expires_at:integer`, `created_at:integer!`
  - Constraints: `UIDX(researcher_id` `WHERE` `status` `=` `'pending')`

**`faculty_researcher_links`** — `id:integer`, `faculty_user_id:integer!->users.id`, `researcher_id:integer!->researchers.id`, `created_at:integer!`
  - Constraints: `UIDX(researcher_id)` `UIDX(faculty_user_id)`

**`student_profiles`** — `id:integer`, `user_id:integer!->users.id`, `research_areas:text!=''`, `expertise:text!=''`, `skills:text!=''`, `projects:text!=''`, `publications:text!=''`, `courses:text!=''`, `academic_details:text!=''`, `updated_at:integer!`
  - Constraints: `UIDX(user_id)`

**`faculty_profiles`** — `id:integer`, `user_id:integer!->users.id`, `department:varchar!=''`, `designation:varchar!=''`, `research_areas:text!=''`, `expertise:text!=''`, `skills:text!=''`, `publications:text!=''`, `projects:text!=''`, `profile_url:varchar!=''`, `updated_at:integer!`
  - Constraints: `UIDX(user_id)`

**`roadmap_progress`** — `id:integer`, `user_id:integer!->users.id`, `researcher_id:integer!->researchers.id`, `skill:varchar!`, `milestone_index:integer!`, `is_completed:boolean!=False`, `updated_at:integer!`
  - Constraints: `UQ(user_id,researcher_id,skill,milestone_index)`

### Collaboration and teams

**`collaboration_requests`** — `id:integer`, `student_user_id:integer!->users.id`, `researcher_id:integer!->researchers.id`, `message:text!=''`, `status:varchar!='pending'`, `faculty_response:text!=''`, `reviewed_at:integer`, `created_at:integer!`, `updated_at:integer!`
  - Constraints: `UIDX(student_user_id,researcher_id` `WHERE` `status` `=` `'pending')`

**`collaboration_workspaces`** — `id:integer`, `collaboration_request_id:integer!->collaboration_requests.id`, `researcher_id:integer!->researchers.id`, `student_user_id:integer!->users.id`, `faculty_user_id:integer!->users.id`, `title:varchar!`, `status:varchar!='active'`, `created_at:integer!`, `updated_at:integer!`
  - Constraints: `UIDX(collaboration_request_id)`

**`workspace_members`** — `id:integer`, `workspace_id:integer!->collaboration_workspaces.id`, `user_id:integer!->users.id`, `role:varchar!='member'`, `created_at:integer!`
  - Constraints: `UQ(workspace_id,user_id)`

**`workspace_tasks`** — `id:integer`, `workspace_id:integer!->collaboration_workspaces.id`, `title:varchar!`, `description:text!=''`, `status:varchar!='todo'`, `assignee_user_id:integer->users.id`, `created_by_user_id:integer->users.id`, `due_at:integer`, `created_at:integer!`, `updated_at:integer!`

**`workspace_milestones`** — `id:integer`, `workspace_id:integer!->collaboration_workspaces.id`, `title:varchar!`, `status:varchar!='pending'`, `due_at:integer`, `completed_at:integer`, `created_by_user_id:integer->users.id`, `created_at:integer!`, `updated_at:integer!`

**`workspace_comments`** — `id:integer`, `workspace_id:integer!->collaboration_workspaces.id`, `task_id:integer->workspace_tasks.id`, `author_user_id:integer->users.id`, `body:text!`, `created_at:integer!`

**`research_teams`** — `id:integer`, `owner_user_id:integer!->users.id`, `name:varchar!`, `description:text!=''`, `research_areas:text!=''`, `expertise:text!=''`, `skills:text!=''`, `projects:text!=''`, `publications:text!=''`, `created_at:integer!`, `updated_at:integer!`

**`research_team_members`** — `id:integer`, `team_id:integer!->research_teams.id`, `user_id:integer!->users.id`, `role:varchar!='member'`, `created_at:integer!`
  - Constraints: `UQ(team_id,user_id)`

**`research_team_invitations`** — `id:integer`, `team_id:integer!->research_teams.id`, `invited_user_id:integer!->users.id`, `invited_by_user_id:integer->users.id`, `status:varchar!='pending'`, `created_at:integer!`, `responded_at:integer`
  - Constraints: `UIDX(team_id,invited_user_id` `WHERE` `status` `=` `'pending')`

### Opportunities

**`opportunities`** — `id:integer`, `category:varchar!`, `title:varchar!`, `description:text!=''`, `organization:varchar!=''`, `location:varchar!=''`, `url:varchar!=''`, `deadline_at:integer`, `status:varchar!='open'`, `researcher_id:integer->researchers.id`, `created_by_user_id:integer->users.id`, `required_skills:text!=''`, `required_research_areas:text!=''`, `required_expertise:text!=''`, `eligibility:text!=''`, `external_source:varchar`, `external_id:varchar`, `created_at:integer!`, `updated_at:integer!`
  - Constraints: `UQ(external_source,external_id)`

**`opportunity_applications`** — `id:integer`, `opportunity_id:integer!->opportunities.id`, `student_user_id:integer!->users.id`, `message:text!=''`, `status:varchar!='pending'`, `decision_note:text!=''`, `reviewed_by_user_id:integer->users.id`, `created_at:integer!`, `updated_at:integer!`, `reviewed_at:integer`
  - Constraints: `UIDX(opportunity_id,student_user_id` `WHERE` `status` `=` `'pending')`

### Research outputs

**`literature_entries`** — `id:integer`, `owner_user_id:integer!->users.id`, `title:varchar!`, `authors:text!=''`, `venue:varchar!=''`, `year:integer`, `doi:varchar!=''`, `url:varchar!=''`, `abstract:text!=''`, `notes:text!=''`, `tags:text!=''`, `review_status:varchar!='to_read'`, `citation_key:varchar`, `created_at:integer!`, `updated_at:integer!`
  - Constraints: `UQ(owner_user_id,citation_key)`

**`research_proposals`** — `id:integer`, `owner_user_id:integer!->users.id`, `title:varchar!`, `status:varchar!='draft'`, `created_at:integer!`, `updated_at:integer!`

**`proposal_sections`** — `id:integer`, `proposal_id:integer!->research_proposals.id`, `heading:varchar!`, `body:text!=''`, `position:integer!`, `created_at:integer!`, `updated_at:integer!`

**`proposal_collaborators`** — `id:integer`, `proposal_id:integer!->research_proposals.id`, `user_id:integer!->users.id`, `role:varchar!='viewer'`, `created_at:integer!`
  - Constraints: `UQ(proposal_id,user_id)`

**`proposal_versions`** — `id:integer`, `proposal_id:integer!->research_proposals.id`, `version_number:integer!`, `snapshot:text!`, `created_by_user_id:integer->users.id`, `created_at:integer!`
  - Constraints: `UQ(proposal_id,version_number)`

**`proposal_citations`** — `id:integer`, `proposal_id:integer!->research_proposals.id`, `literature_entry_id:integer!->literature_entries.id`, `section_id:integer->proposal_sections.id`, `created_by_user_id:integer->users.id`, `created_at:integer!`
  - Constraints: `UQ(proposal_id,literature_entry_id)`

**`thesis_records`** — `id:integer`, `owner_user_id:integer!->users.id`, `supervisor_user_id:integer->users.id`, `title:varchar!`, `abstract:text!=''`, `status:varchar!='proposed'`, `created_at:integer!`, `updated_at:integer!`

**`thesis_milestones`** — `id:integer`, `thesis_id:integer!->thesis_records.id`, `title:varchar!`, `due_at:integer`, `status:varchar!='pending'`, `position:integer!`, `completed_at:integer`, `created_by_user_id:integer->users.id`, `created_at:integer!`, `updated_at:integer!`

**`thesis_progress_events`** — `id:integer`, `thesis_id:integer!->thesis_records.id`, `actor_user_id:integer->users.id`, `event_type:varchar!`, `note:text!=''`, `from_status:varchar`, `to_status:varchar`, `milestone_id:integer`, `created_at:integer!`

**`publication_submissions`** — `id:integer`, `owner_user_id:integer!->users.id`, `title:varchar!`, `venue:varchar!=''`, `venue_type:varchar!='journal'`, `status:varchar!='draft'`, `doi:varchar!=''`, `url:varchar!=''`, `notes:text!=''`, `submitted_at:integer`, `decision_at:integer`, `published_at:integer`, `created_at:integer!`, `updated_at:integer!`

**`publication_revisions`** — `id:integer`, `submission_id:integer!->publication_submissions.id`, `revision_number:integer!`, `notes:text!`, `submitted_at:integer!`, `created_by_user_id:integer->users.id`, `created_at:integer!`
  - Constraints: `UQ(submission_id,revision_number)`

**`publication_status_events`** — `id:integer`, `submission_id:integer!->publication_submissions.id`, `actor_user_id:integer->users.id`, `from_status:varchar!`, `to_status:varchar!`, `note:text!=''`, `created_at:integer!`

### Research intelligence

**`research_cluster_runs`** — `id:integer`, `method:varchar!`, `semantic_used:boolean!=False`, `min_similarity:float!`, `researcher_count:integer!`, `cluster_count:integer!`, `created_by_user_id:integer->users.id`, `created_at:integer!`

**`research_cluster_assignments`** — `id:integer`, `run_id:integer!->research_cluster_runs.id`, `researcher_id:integer!->researchers.id`, `cluster_index:integer!`, `cluster_label:varchar!=''`
  - Constraints: `UQ(run_id,researcher_id)`

### Institutions and labs

**`institutions`** — `id:integer`, `name:varchar!`, `created_at:integer!`
  - Constraints: `UIDX(name)`

**`institution_memberships`** — `id:integer`, `institution_id:integer!->institutions.id`, `user_id:integer!->users.id`, `created_at:integer!`
  - Constraints: `UIDX(user_id)`

**`research_labs`** — `id:integer`, `institution_id:integer!->institutions.id`, `owner_user_id:integer!->users.id`, `name:varchar!`, `description:text!=''`, `research_areas:text!=''`, `visibility:varchar!='institution'`, `created_at:integer!`, `updated_at:integer!`
  - Constraints: `UQ(institution_id,name)`

**`research_lab_members`** — `id:integer`, `lab_id:integer!->research_labs.id`, `user_id:integer!->users.id`, `created_at:integer!`
  - Constraints: `UQ(lab_id,user_id)`

**`interuniversity_collaborations`** — `id:integer`, `requester_lab_id:integer!->research_labs.id`, `partner_lab_id:integer!->research_labs.id`, `initiated_by_user_id:integer->users.id`, `decided_by_user_id:integer->users.id`, `title:varchar!`, `description:text!=''`, `status:varchar!='proposed'`, `resolution_note:text!=''`, `responded_at:integer`, `created_at:integer!`, `updated_at:integer!`, `pair_key:varchar`
  - Constraints: `UIDX(pair_key` `WHERE` `pair_key` `IS` `NOT` `NULL` `AND` `status` `IN` `('proposed',` `'active'))`
