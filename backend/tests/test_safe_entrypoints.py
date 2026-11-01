"""Regression coverage for safe root launch and out-of-band data tools."""

import importlib.util
import uuid
from pathlib import Path

import pytest

import provision_admin
import seed_researchers
from app.models import Researcher, User
from app.services.auth import hash_password, verify_password


def test_root_asgi_launcher_uses_canonical_authenticated_app(app_instance):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "researchtwin_root_launcher", root / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.app is app_instance
    paths = module.app.openapi()["paths"]
    assert "/api/student/profile/update" not in paths
    assert "/api/researcher/profile/update" not in paths


def test_seed_helper_only_inserts_into_empty_researcher_table(db, empty_db):
    count = seed_researchers.seed_researchers(
        db,
        [
            {
                "name": "Safe Local Seed",
                "department": "Computer Science",
                "designation": "Professor",
                "experience": 4,
                "research_areas": "AI",
                "expertise": "ML",
                "skills": "Python",
                "publications": "",
                "projects": "",
            }
        ],
    )
    assert count == 1
    assert db.query(Researcher).filter_by(name="Safe Local Seed").count() == 1


def test_seed_helper_refuses_and_preserves_existing_researcher_data(db, empty_db):
    marker = f"Preserve {uuid.uuid4().hex}"
    db.add(Researcher(name=marker))
    db.commit()

    with pytest.raises(seed_researchers.ExistingResearcherDataError):
        seed_researchers.seed_researchers(db)

    db.expire_all()
    assert db.query(Researcher).filter_by(name=marker).count() == 1
    assert db.query(Researcher).count() == 1


def test_admin_provisioning_requires_explicit_opt_in_and_database_url():
    with pytest.raises(ValueError, match="DATABASE_URL"):
        provision_admin.validate_provisioning_configuration("", "YES")
    with pytest.raises(ValueError, match="ENABLE_ADMIN_PROVISIONING"):
        provision_admin.validate_provisioning_configuration("sqlite:///local.db", "")


def test_admin_is_created_with_password_hash_and_existing_role_is_never_changed(db):
    email = f"new-admin-{uuid.uuid4().hex}@example.test"
    password = "Long Secure Operator Password 2026!"
    admin = provision_admin.provision_admin(
        db, email.upper(), "New Administrator", password
    )
    assert admin.role == "admin"
    assert admin.email == email
    assert admin.password_hash != password
    assert verify_password(password, admin.password_hash)

    existing = User(
        email=f"student-{uuid.uuid4().hex}@example.test",
        full_name="Existing Student",
        role="student",
        password_hash=hash_password("Existing Student Password 2026!"),
        is_active=True,
        created_at=1,
    )
    db.add(existing)
    db.commit()
    original_hash = existing.password_hash

    with pytest.raises(ValueError, match="role changes are refused"):
        provision_admin.provision_admin(
            db, existing.email.upper(), "Attempted Promotion", password
        )

    db.refresh(existing)
    assert existing.role == "student"
    assert existing.password_hash == original_hash
