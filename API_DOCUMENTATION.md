# ResearchTwin API Reference

Generated from the FastAPI application in `backend/app` (the same code that serves `https://researchtwin-api.onrender.com`). It lists **152 operations on 110 paths**. The **Access** column is read from each route's dependencies, so it reflects what the server enforces.

Interactive schemas: `GET /openapi.json` and `/docs` on any running backend.

## Conventions

- **Base URL:** `https://researchtwin-api.onrender.com` in production, `http://127.0.0.1:8000` locally.
- **Authentication:** `POST /auth/login` returns `access_token`. Send it as `Authorization: Bearer <token>`. `POST /auth/logout` revokes it on the server.
- **Access values:** `public` needs no token; `public; more with sign-in` returns extra data for signed-in users; `signed in` accepts any active account; role names (`student`, `faculty`, `admin`) mean only those roles. Wrong role → `403`, no or invalid token → `401`.
- **Errors:** JSON `{"detail": ...}`. Validation errors → `422`. Conflicts (duplicates, illegal status changes) → `409`. Rate limits → `429` with `Retry-After`. Database outages → `503`.
- **Bodies:** JSON. Most request schemas set `extra="forbid"`, so unknown fields return `422`. Bodies over `MAX_REQUEST_BODY_BYTES` (64 KiB by default) return `413`.

## Endpoints by area

### Administration

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/admin/audit-events` | admin | List audit events |
| `GET` | `/admin/groups` | admin | List groups |
| `GET` | `/admin/groups/{group_id}/members` | admin | List group members |
| `POST` | `/admin/groups/{group_id}/members` | admin | Add group member |
| `DELETE` | `/admin/groups/{group_id}/members/{user_id}` | admin | Remove group member |
| `GET` | `/admin/users` | admin | List accounts |
| `PUT` | `/admin/users/{user_id}/active` | admin | Set account active |
| `GET` | `/admin/users/{user_id}/data-export` | admin | Export account data |
| `POST` | `/admin/users/{user_id}/password-reset` | admin | Reset account password |
| `PUT` | `/admin/users/{user_id}/role` | admin | Set account role |
| `POST` | `/admin/users/{user_id}/sessions/revoke` | admin | Revoke account sessions |

### Analytics

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/analytics/departments` | signed in | Get department analytics |
| `GET` | `/analytics/university` | signed in | Get university analytics |

### Authentication

| Method | Path | Access | Purpose |
|---|---|---|---|
| `POST` | `/auth/login` | public | Login |
| `POST` | `/auth/logout` | signed in | Logout |
| `GET` | `/auth/me` | signed in | Me |
| `POST` | `/auth/register` | public | Register |

### Collaboration

| Method | Path | Access | Purpose |
|---|---|---|---|
| `DELETE` | `/admin/faculty/{faculty_user_id}/researcher-link` | admin | Remove faculty researcher link |
| `PUT` | `/admin/faculty/{faculty_user_id}/researcher-link` | admin | Assign faculty researcher link |
| `GET` | `/faculty/me/collaboration-requests` | faculty | List faculty collaboration requests |
| `PUT` | `/faculty/me/collaboration-requests/{request_id}/decision` | faculty | Decide collaboration request |
| `GET` | `/faculty/me/researcher-link` | faculty | Get my researcher link |
| `PUT` | `/faculty/me/researcher-link` | faculty | Set my researcher link |
| `GET` | `/students/me/collaboration-requests` | student | List my collaboration requests |
| `POST` | `/students/me/collaboration-requests` | student | Create my collaboration request |

### General

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/` | public | Root |
| `GET` | `/health` | public | Health check |
| `GET` | `/readiness` | public | Readiness check |
| `GET` | `/ready` | public | Readiness check |

### Institutions

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/admin/institutions` | admin | Admin list institutions |
| `POST` | `/admin/institutions` | admin | Create institution |
| `PUT` | `/admin/institutions/{institution_id}` | admin | Rename institution |
| `GET` | `/admin/institutions/{institution_id}/members` | admin | Admin list members |
| `DELETE` | `/admin/institutions/{institution_id}/members/{user_id}` | admin | Remove member |
| `PUT` | `/admin/institutions/{institution_id}/members/{user_id}` | admin | Assign member |
| `GET` | `/institutions` | public | List institutions |
| `GET` | `/institutions/me` | signed in | My institution |

### Literature

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/literature` | signed in | List literature |
| `POST` | `/literature` | signed in | Create literature entry |
| `DELETE` | `/literature/{entry_id}` | signed in | Delete literature entry |
| `GET` | `/literature/{entry_id}` | signed in | Get literature entry |
| `PUT` | `/literature/{entry_id}` | signed in | Update literature entry |

### Opportunities

| Method | Path | Access | Purpose |
|---|---|---|---|
| `POST` | `/admin/opportunities/import` | admin | Import funding opportunities |
| `GET` | `/admin/opportunities/sources` | admin | List funding sources |
| `GET` | `/opportunities` | public; more with sign-in | Search opportunities |
| `POST` | `/opportunities` | faculty or admin | Create opportunity |
| `GET` | `/opportunities/mine` | faculty or admin | List my opportunities |
| `DELETE` | `/opportunities/{opportunity_id}` | faculty or admin | Delete opportunity |
| `GET` | `/opportunities/{opportunity_id}` | public; more with sign-in | Get opportunity |
| `PUT` | `/opportunities/{opportunity_id}` | faculty or admin | Update opportunity |
| `GET` | `/opportunities/{opportunity_id}/applications` | faculty or admin | List opportunity applications |
| `POST` | `/opportunities/{opportunity_id}/applications` | student | Apply to opportunity |
| `DELETE` | `/opportunities/{opportunity_id}/applications/me` | student | Withdraw application |
| `PUT` | `/opportunities/{opportunity_id}/applications/{application_id}` | faculty or admin | Decide application |
| `GET` | `/opportunities/{opportunity_id}/eligibility` | student | Opportunity eligibility |
| `GET` | `/students/me/opportunity-applications` | student | List my applications |
| `POST` | `/students/me/opportunity-matches` | student | Match opportunities |

### Profiles

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/faculty/me/profile` | faculty | Get my faculty profile |
| `PUT` | `/faculty/me/profile` | faculty | Update my faculty profile |
| `GET` | `/students/me/profile` | student | Get my student profile |
| `PUT` | `/students/me/profile` | student | Update my student profile |
| `POST` | `/students/me/recommendations` | student | Recommendations for my profile |

### Proposals

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/proposals` | signed in | List proposals |
| `POST` | `/proposals` | signed in | Create proposal |
| `DELETE` | `/proposals/{proposal_id}` | signed in | Delete proposal |
| `GET` | `/proposals/{proposal_id}` | signed in | Get proposal |
| `PUT` | `/proposals/{proposal_id}` | signed in | Update proposal |
| `POST` | `/proposals/{proposal_id}/citations` | signed in | Add proposal citation |
| `DELETE` | `/proposals/{proposal_id}/citations/{citation_id}` | signed in | Delete proposal citation |
| `POST` | `/proposals/{proposal_id}/collaborators` | signed in | Add proposal collaborator |
| `DELETE` | `/proposals/{proposal_id}/collaborators/{user_id}` | signed in | Remove proposal collaborator |
| `POST` | `/proposals/{proposal_id}/sections` | signed in | Add proposal section |
| `DELETE` | `/proposals/{proposal_id}/sections/{section_id}` | signed in | Delete proposal section |
| `PUT` | `/proposals/{proposal_id}/sections/{section_id}` | signed in | Update proposal section |
| `GET` | `/proposals/{proposal_id}/versions` | signed in | List proposal versions |
| `GET` | `/proposals/{proposal_id}/versions/{version}` | signed in | Get proposal version |

### Publication Submissions

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/publication-submissions` | signed in | List publication submissions |
| `POST` | `/publication-submissions` | signed in | Create publication submission |
| `DELETE` | `/publication-submissions/{submission_id}` | signed in | Delete publication submission |
| `GET` | `/publication-submissions/{submission_id}` | signed in | Get publication submission |
| `PUT` | `/publication-submissions/{submission_id}` | signed in | Update publication submission |
| `POST` | `/publication-submissions/{submission_id}/revisions` | signed in | Add publication revision |
| `POST` | `/publication-submissions/{submission_id}/status` | signed in | Update publication status |

### Recommendations

| Method | Path | Access | Purpose |
|---|---|---|---|
| `POST` | `/recommendations/researchers` | student | Recommend researchers |
| `POST` | `/recommendations/roadmap/researcher` | student | Create researcher roadmap |

### Research Intelligence

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/research-intelligence/clusters` | signed in | Get research clusters |
| `POST` | `/research-intelligence/clusters/rebuild` | admin | Rebuild research clusters |
| `GET` | `/research-intelligence/knowledge-graph` | signed in | Get research knowledge graph |
| `GET` | `/research-intelligence/network` | signed in | Get research network |
| `POST` | `/research-intelligence/topics/predict` | signed in | Predict research topics |
| `GET` | `/research-intelligence/trends` | signed in | Get research trends |

### Research Labs

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/interuniversity-collaborations` | signed in | List collaborations |
| `POST` | `/interuniversity-collaborations` | faculty | Propose collaboration |
| `GET` | `/interuniversity-collaborations/{collaboration_id}` | signed in | Get collaboration |
| `POST` | `/interuniversity-collaborations/{collaboration_id}/status` | faculty | Update collaboration status |
| `GET` | `/labs` | public; more with sign-in | List labs |
| `POST` | `/labs` | faculty | Create lab |
| `DELETE` | `/labs/{lab_id}` | faculty | Delete lab |
| `GET` | `/labs/{lab_id}` | public; more with sign-in | Get lab |
| `PUT` | `/labs/{lab_id}` | faculty | Update lab |
| `GET` | `/labs/{lab_id}/members` | public; more with sign-in | List lab members |
| `POST` | `/labs/{lab_id}/members` | faculty | Add lab member |
| `DELETE` | `/labs/{lab_id}/members/{user_id}` | signed in | Remove lab member |

### Research Teams

| Method | Path | Access | Purpose |
|---|---|---|---|
| `POST` | `/teams` | student or faculty | Create team |
| `GET` | `/teams/me` | signed in | List my teams |
| `DELETE` | `/teams/{team_id}` | signed in | Delete team |
| `GET` | `/teams/{team_id}` | signed in | Get team |
| `POST` | `/teams/{team_id}/invitations` | signed in | Invite member |
| `PUT` | `/teams/{team_id}/invitations/{invitation_id}` | signed in | Decide invitation |
| `DELETE` | `/teams/{team_id}/members/{user_id}` | signed in | Remove member |
| `POST` | `/teams/{team_id}/recommendations` | signed in | Recommend for team |

### Researcher Verification

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/admin/researchers/{researcher_id}/verifications` | admin | Researcher verification history |
| `GET` | `/admin/verifications` | admin | List verification requests |
| `PUT` | `/admin/verifications/{verification_id}` | admin | Decide verification request |
| `GET` | `/faculty/me/researcher-link/verification` | faculty | My researcher verification |
| `POST` | `/faculty/me/researcher-link/verification` | faculty | Submit researcher verification |
| `GET` | `/researchers/verification-summary` | public | Verification summary |
| `GET` | `/researchers/{researcher_id}/verification` | public | Researcher verification status |

### Researchers

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/researchers/` | public | Get researchers |
| `POST` | `/researchers/` | admin | Create researcher |
| `POST` | `/researchers/import` | admin | Import researcher data |
| `GET` | `/researchers/intelligence` | public | Researcher intelligence |
| `DELETE` | `/researchers/{researcher_id}` | admin | Delete researcher |
| `GET` | `/researchers/{researcher_id}` | public | Get researcher |
| `PUT` | `/researchers/{researcher_id}` | admin | Update researcher |

### Roadmap

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/students/me/expertise-gaps` | student | Get my expertise gaps |
| `GET` | `/students/me/researchers/{researcher_id}/roadmap` | student | Get my researcher roadmap |
| `PUT` | `/students/me/researchers/{researcher_id}/roadmap/progress` | student | Update my roadmap progress |

### Search History

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/search-history` | signed in | List search history |
| `POST` | `/search-history` | signed in | Record search |

### Theses

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/theses` | signed in | List theses |
| `POST` | `/theses` | student | Create thesis |
| `DELETE` | `/theses/{thesis_id}` | signed in | Delete thesis |
| `GET` | `/theses/{thesis_id}` | signed in | Get thesis |
| `PUT` | `/theses/{thesis_id}` | signed in | Update thesis |
| `GET` | `/theses/{thesis_id}/history` | signed in | Thesis history |
| `POST` | `/theses/{thesis_id}/milestones` | signed in | Add thesis milestone |
| `DELETE` | `/theses/{thesis_id}/milestones/{milestone_id}` | signed in | Delete thesis milestone |
| `PUT` | `/theses/{thesis_id}/milestones/{milestone_id}` | signed in | Update thesis milestone |

### Workspaces

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/workspaces/me` | signed in | List my workspaces |
| `GET` | `/workspaces/{workspace_id}` | signed in | Get workspace |
| `GET` | `/workspaces/{workspace_id}/comments` | signed in | List comments |
| `POST` | `/workspaces/{workspace_id}/comments` | signed in | Create comment |
| `DELETE` | `/workspaces/{workspace_id}/comments/{comment_id}` | signed in | Delete comment |
| `GET` | `/workspaces/{workspace_id}/milestones` | signed in | List milestones |
| `POST` | `/workspaces/{workspace_id}/milestones` | signed in | Create milestone |
| `DELETE` | `/workspaces/{workspace_id}/milestones/{milestone_id}` | signed in | Delete milestone |
| `PUT` | `/workspaces/{workspace_id}/milestones/{milestone_id}` | signed in | Update milestone |
| `GET` | `/workspaces/{workspace_id}/tasks` | signed in | List tasks |
| `POST` | `/workspaces/{workspace_id}/tasks` | signed in | Create task |
| `DELETE` | `/workspaces/{workspace_id}/tasks/{task_id}` | signed in | Delete task |
| `PUT` | `/workspaces/{workspace_id}/tasks/{task_id}` | signed in | Update task |
