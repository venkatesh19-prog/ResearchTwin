import importlib
import pkgutil

import app as app_package


EXPECTED_ENDPOINTS = {
    ("/", "GET"),
    ("/health", "GET"),
    ("/ready", "GET"),
    ("/readiness", "GET"),
    ("/researchers/", "GET"),
    ("/researchers/", "POST"),
    ("/researchers/intelligence", "GET"),
    ("/researchers/verification-summary", "GET"),
    ("/researchers/{researcher_id}", "GET"),
    ("/researchers/{researcher_id}", "PUT"),
    ("/researchers/{researcher_id}", "DELETE"),
    ("/researchers/{researcher_id}/verification", "GET"),
    ("/researchers/import", "POST"),
    ("/search-history", "GET"),
    ("/search-history", "POST"),
    ("/recommendations/researchers", "POST"),
    ("/recommendations/roadmap/researcher", "POST"),
    ("/auth/register", "POST"),
    ("/auth/login", "POST"),
    ("/auth/logout", "POST"),
    ("/auth/me", "GET"),
    ("/students/me/profile", "GET"),
    ("/students/me/profile", "PUT"),
    ("/students/me/recommendations", "POST"),
    ("/students/me/expertise-gaps", "GET"),
    ("/students/me/researchers/{researcher_id}/roadmap", "GET"),
    ("/students/me/researchers/{researcher_id}/roadmap/progress", "PUT"),
    ("/students/me/collaboration-requests", "GET"),
    ("/students/me/collaboration-requests", "POST"),
    ("/faculty/me/researcher-link", "GET"),
    ("/faculty/me/researcher-link", "PUT"),
    ("/faculty/me/researcher-link/verification", "GET"),
    ("/faculty/me/researcher-link/verification", "POST"),
    ("/admin/faculty/{faculty_user_id}/researcher-link", "PUT"),
    ("/admin/faculty/{faculty_user_id}/researcher-link", "DELETE"),
    ("/admin/users", "GET"),
    ("/admin/users/{user_id}/active", "PUT"),
    ("/admin/users/{user_id}/role", "PUT"),
    ("/admin/users/{user_id}/sessions/revoke", "POST"),
    ("/admin/users/{user_id}/password-reset", "POST"),
    ("/admin/users/{user_id}/data-export", "GET"),
    ("/admin/audit-events", "GET"),
    ("/admin/verifications", "GET"),
    ("/admin/verifications/{verification_id}", "PUT"),
    ("/admin/researchers/{researcher_id}/verifications", "GET"),
    ("/admin/groups", "GET"),
    ("/admin/groups/{group_id}/members", "GET"),
    ("/admin/groups/{group_id}/members", "POST"),
    ("/admin/groups/{group_id}/members/{user_id}", "DELETE"),
    ("/faculty/me/collaboration-requests", "GET"),
    ("/faculty/me/collaboration-requests/{request_id}/decision", "PUT"),
    ("/faculty/me/profile", "GET"),
    ("/faculty/me/profile", "PUT"),
    ("/analytics/university", "GET"),
    ("/analytics/departments", "GET"),
    ("/research-intelligence/network", "GET"),
    ("/research-intelligence/clusters", "GET"),
    ("/research-intelligence/clusters/rebuild", "POST"),
    ("/research-intelligence/topics/predict", "POST"),
    ("/research-intelligence/trends", "GET"),
    ("/research-intelligence/knowledge-graph", "GET"),
    ("/workspaces/me", "GET"),
    ("/workspaces/{workspace_id}", "GET"),
    ("/workspaces/{workspace_id}/tasks", "GET"),
    ("/workspaces/{workspace_id}/tasks", "POST"),
    ("/workspaces/{workspace_id}/tasks/{task_id}", "PUT"),
    ("/workspaces/{workspace_id}/tasks/{task_id}", "DELETE"),
    ("/workspaces/{workspace_id}/comments", "GET"),
    ("/workspaces/{workspace_id}/comments", "POST"),
    ("/workspaces/{workspace_id}/comments/{comment_id}", "DELETE"),
    ("/workspaces/{workspace_id}/milestones", "GET"),
    ("/workspaces/{workspace_id}/milestones", "POST"),
    ("/workspaces/{workspace_id}/milestones/{milestone_id}", "PUT"),
    ("/workspaces/{workspace_id}/milestones/{milestone_id}", "DELETE"),
    ("/teams", "POST"),
    ("/teams/me", "GET"),
    ("/teams/{team_id}", "GET"),
    ("/teams/{team_id}", "DELETE"),
    ("/teams/{team_id}/invitations", "POST"),
    ("/teams/{team_id}/invitations/{invitation_id}", "PUT"),
    ("/teams/{team_id}/members/{user_id}", "DELETE"),
    ("/teams/{team_id}/recommendations", "POST"),
    ("/opportunities", "GET"),
    ("/opportunities", "POST"),
    ("/opportunities/mine", "GET"),
    ("/opportunities/{opportunity_id}", "GET"),
    ("/opportunities/{opportunity_id}", "PUT"),
    ("/opportunities/{opportunity_id}", "DELETE"),
    ("/opportunities/{opportunity_id}/eligibility", "GET"),
    ("/opportunities/{opportunity_id}/applications", "GET"),
    ("/opportunities/{opportunity_id}/applications", "POST"),
    ("/opportunities/{opportunity_id}/applications/{application_id}", "PUT"),
    ("/opportunities/{opportunity_id}/applications/me", "DELETE"),
    ("/students/me/opportunity-applications", "GET"),
    ("/students/me/opportunity-matches", "POST"),
    ("/admin/opportunities/sources", "GET"),
    ("/admin/opportunities/import", "POST"),
    ("/literature", "GET"),
    ("/literature", "POST"),
    ("/literature/{entry_id}", "GET"),
    ("/literature/{entry_id}", "PUT"),
    ("/literature/{entry_id}", "DELETE"),
    ("/proposals", "GET"),
    ("/proposals", "POST"),
    ("/proposals/{proposal_id}", "GET"),
    ("/proposals/{proposal_id}", "PUT"),
    ("/proposals/{proposal_id}", "DELETE"),
    ("/proposals/{proposal_id}/collaborators", "POST"),
    ("/proposals/{proposal_id}/collaborators/{user_id}", "DELETE"),
    ("/proposals/{proposal_id}/sections", "POST"),
    ("/proposals/{proposal_id}/sections/{section_id}", "PUT"),
    ("/proposals/{proposal_id}/sections/{section_id}", "DELETE"),
    ("/proposals/{proposal_id}/citations", "POST"),
    ("/proposals/{proposal_id}/citations/{citation_id}", "DELETE"),
    ("/proposals/{proposal_id}/versions", "GET"),
    ("/proposals/{proposal_id}/versions/{version}", "GET"),
    ("/theses", "GET"),
    ("/theses", "POST"),
    ("/theses/{thesis_id}", "GET"),
    ("/theses/{thesis_id}", "PUT"),
    ("/theses/{thesis_id}", "DELETE"),
    ("/theses/{thesis_id}/milestones", "POST"),
    ("/theses/{thesis_id}/milestones/{milestone_id}", "PUT"),
    ("/theses/{thesis_id}/milestones/{milestone_id}", "DELETE"),
    ("/theses/{thesis_id}/history", "GET"),
    ("/publication-submissions", "GET"),
    ("/publication-submissions", "POST"),
    ("/publication-submissions/{submission_id}", "GET"),
    ("/publication-submissions/{submission_id}", "PUT"),
    ("/publication-submissions/{submission_id}", "DELETE"),
    ("/publication-submissions/{submission_id}/status", "POST"),
    ("/publication-submissions/{submission_id}/revisions", "POST"),
    ("/institutions", "GET"),
    ("/institutions/me", "GET"),
    ("/admin/institutions", "GET"),
    ("/admin/institutions", "POST"),
    ("/admin/institutions/{institution_id}", "PUT"),
    ("/admin/institutions/{institution_id}/members", "GET"),
    ("/admin/institutions/{institution_id}/members/{user_id}", "PUT"),
    ("/admin/institutions/{institution_id}/members/{user_id}", "DELETE"),
    ("/labs", "GET"),
    ("/labs", "POST"),
    ("/labs/{lab_id}", "GET"),
    ("/labs/{lab_id}", "PUT"),
    ("/labs/{lab_id}", "DELETE"),
    ("/labs/{lab_id}/members", "GET"),
    ("/labs/{lab_id}/members", "POST"),
    ("/labs/{lab_id}/members/{user_id}", "DELETE"),
    ("/interuniversity-collaborations", "GET"),
    ("/interuniversity-collaborations", "POST"),
    ("/interuniversity-collaborations/{collaboration_id}", "GET"),
    ("/interuniversity-collaborations/{collaboration_id}/status", "POST"),
}


def _walk_module_names():
    yield app_package.__name__
    for module in pkgutil.walk_packages(app_package.__path__, prefix="app."):
        yield module.name


def test_every_app_module_imports_without_error():
    failures = []
    for name in _walk_module_names():
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - collect all import errors
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert failures == []


def test_router_endpoints_are_registered(app_instance):
    schema = app_instance.openapi()
    registered = {
        (path, method.upper())
        for path, operations in schema["paths"].items()
        for method in operations
        if method.lower() in {"get", "post", "put", "delete", "patch"}
    }

    assert registered == EXPECTED_ENDPOINTS


def test_openapi_schema_builds(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert set(schema["paths"]) >= {
        "/researchers/",
        "/recommendations/researchers",
        "/recommendations/roadmap/researcher",
        "/health",
    }


def test_unknown_route_returns_404(client):
    assert client.get("/does-not-exist").status_code == 404


def test_wrong_method_returns_405(client):
    assert client.get("/recommendations/researchers").status_code == 405
