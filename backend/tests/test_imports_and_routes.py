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
    ("/researchers/{researcher_id}", "GET"),
    ("/researchers/{researcher_id}", "PUT"),
    ("/researchers/{researcher_id}", "DELETE"),
    ("/researchers/import", "POST"),
    ("/recommendations/researchers", "POST"),
    ("/recommendations/roadmap/researcher", "POST"),
    ("/auth/register", "POST"),
    ("/auth/login", "POST"),
    ("/auth/logout", "POST"),
    ("/auth/me", "GET"),
    ("/students/me/profile", "GET"),
    ("/students/me/profile", "PUT"),
    ("/students/me/recommendations", "POST"),
    ("/students/me/researchers/{researcher_id}/roadmap", "GET"),
    ("/students/me/researchers/{researcher_id}/roadmap/progress", "PUT"),
    ("/students/me/collaboration-requests", "GET"),
    ("/students/me/collaboration-requests", "POST"),
    ("/faculty/me/researcher-link", "GET"),
    ("/faculty/me/researcher-link", "PUT"),
    ("/admin/faculty/{faculty_user_id}/researcher-link", "PUT"),
    ("/admin/faculty/{faculty_user_id}/researcher-link", "DELETE"),
    ("/admin/users", "GET"),
    ("/admin/users/{user_id}/active", "PUT"),
    ("/admin/users/{user_id}/role", "PUT"),
    ("/admin/users/{user_id}/sessions/revoke", "POST"),
    ("/admin/users/{user_id}/password-reset", "POST"),
    ("/admin/users/{user_id}/data-export", "GET"),
    ("/admin/audit-events", "GET"),
    ("/faculty/me/collaboration-requests", "GET"),
    ("/faculty/me/collaboration-requests/{request_id}/decision", "PUT"),
    ("/faculty/me/profile", "GET"),
    ("/faculty/me/profile", "PUT"),
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
