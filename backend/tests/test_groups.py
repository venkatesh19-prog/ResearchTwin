"""Role group membership: registration assignment, admin management, backfill."""

import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import SessionLocal
from app.models import Group, GroupMembership, User
from app.services.groups import assign_role_group
from conftest import register_test_account

GROUPS = "/admin/groups"
PASSWORD = "TestPassword123!"


def _membership_rows(db):
    return (
        db.query(GroupMembership, Group)
        .join(Group, Group.id == GroupMembership.group_id)
        .all()
    )


def test_registration_assigns_student_to_students_group(client, db):
    _, user = register_test_account(client, role="student")

    rows = [
        (membership, group)
        for membership, group in _membership_rows(db)
        if membership.user_id == user["id"]
    ]
    assert len(rows) == 1
    membership, group = rows[0]
    assert group.name == "students"


def test_registration_assigns_faculty_to_faculty_group(client, db):
    _, user = register_test_account(client, role="faculty")

    rows = [
        (membership, group)
        for membership, group in _membership_rows(db)
        if membership.user_id == user["id"]
    ]
    assert len(rows) == 1
    membership, group = rows[0]
    assert group.name == "faculty"


def test_assign_role_group_never_adds_administrators(db):
    admin = User(
        email=f"admin-{uuid.uuid4().hex}@example.test",
        full_name="Test Operator",
        role="admin",
        password_hash="provisioned-out-of-band-for-test-only",
        is_active=True,
        created_at=int(time.time()),
    )
    db.add(admin)
    db.commit()

    assert assign_role_group(db, admin) is None
    db.commit()
    assert db.query(GroupMembership).filter_by(user_id=admin.id).count() == 0


def test_failed_membership_rolls_back_the_new_account(raw_client, db, monkeypatch):
    def fail(_db, _user):
        raise SQLAlchemyError("membership insert failed")

    monkeypatch.setattr("app.api.auth.assign_role_group", fail)

    memberships_before = db.query(GroupMembership).count()
    email = f"rollback-{uuid.uuid4().hex}@example.test"
    response = raw_client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "full_name": "Rollback Test",
            "role": "student",
        },
    )

    assert response.status_code == 500
    assert db.query(User).filter_by(email=email).first() is None
    assert db.query(GroupMembership).count() == memberships_before


def test_duplicate_membership_is_prevented(client, admin_headers, db):
    _, student = register_test_account(client, role="student")
    group = db.query(Group).filter_by(name="students").one()

    db.add(
        GroupMembership(
            group_id=group.id, user_id=student["id"], created_at=int(time.time())
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    duplicate = client.post(
        f"{GROUPS}/{group.id}/members",
        json={"user_id": student["id"]},
        headers=admin_headers,
    )
    assert duplicate.status_code == 409


def test_group_endpoints_reject_anonymous_and_non_admin_callers(client):
    _, student = register_test_account(client, role="student")
    _, faculty = register_test_account(client, role="faculty")
    calls = [
        ("get", GROUPS, None),
        ("get", f"{GROUPS}/1/members", None),
        ("post", f"{GROUPS}/1/members", {"user_id": student["id"]}),
        ("delete", f"{GROUPS}/1/members/{student['id']}", None),
    ]

    for method, url, body in calls:
        anonymous = (
            getattr(client, method)(url, json=body)
            if body
            else getattr(client, method)(url)
        )
        assert anonymous.status_code == 401, (url, anonymous.text)

    student_headers, _ = register_test_account(client, role="student")
    faculty_headers, _ = register_test_account(client, role="faculty")
    for headers in (student_headers, faculty_headers):
        for method, url, body in calls:
            denied = (
                getattr(client, method)(url, json=body, headers=headers)
                if body
                else getattr(client, method)(url, headers=headers)
            )
            assert denied.status_code == 403, (url, denied.text)


def test_admin_can_list_groups_add_and_remove_members(client, admin_headers, db):
    _, student = register_test_account(client, role="student")
    _, faculty = register_test_account(client, role="faculty")
    students = db.query(Group).filter_by(name="students").one()
    faculty_group = db.query(Group).filter_by(name="faculty").one()

    listed = client.get(GROUPS, headers=admin_headers)
    assert listed.status_code == 200
    by_name = {row["name"]: row for row in listed.json()}
    assert set(by_name) == {"students", "faculty"}
    assert by_name["students"]["member_count"] == (
        db.query(GroupMembership).filter_by(group_id=students.id).count()
    )
    assert by_name["faculty"]["member_count"] == (
        db.query(GroupMembership).filter_by(group_id=faculty_group.id).count()
    )

    members = client.get(f"{GROUPS}/{students.id}/members", headers=admin_headers)
    assert members.status_code == 200
    student_rows = [row for row in members.json() if row["user_id"] == student["id"]]
    assert len(student_rows) == 1
    assert student_rows[0]["email"] == student["email"]

    added = client.post(
        f"{GROUPS}/{students.id}/members",
        json={"user_id": faculty["id"]},
        headers=admin_headers,
    )
    assert added.status_code == 400
    assert added.json()["detail"] == "Faculty accounts can only join the faculty group"

    removed = client.delete(
        f"{GROUPS}/{students.id}/members/{student['id']}",
        headers=admin_headers,
    )
    assert removed.status_code == 200
    db.expire_all()
    assert (
        db.query(GroupMembership)
        .filter_by(group_id=students.id, user_id=student["id"])
        .first()
        is None
    )

    reregistered = client.post(
        f"{GROUPS}/{students.id}/members",
        json={"user_id": student["id"]},
        headers=admin_headers,
    )
    assert reregistered.status_code == 201
    assert reregistered.json()["user_id"] == student["id"]

    missing_group = client.get(f"{GROUPS}/99999/members", headers=admin_headers)
    assert missing_group.status_code == 404
    missing_account = client.post(
        f"{GROUPS}/{faculty_group.id}/members",
        json={"user_id": 99999},
        headers=admin_headers,
    )
    assert missing_account.status_code == 404
    missing_membership = client.delete(
        f"{GROUPS}/{faculty_group.id}/members/{student['id']}",
        headers=admin_headers,
    )
    assert missing_membership.status_code == 404

    admin_account = (
        db.query(User).filter_by(role="admin").order_by(User.id.desc()).first()
    )
    admin_denied = client.post(
        f"{GROUPS}/{students.id}/members",
        json={"user_id": admin_account.id},
        headers=admin_headers,
    )
    assert admin_denied.status_code == 400
    assert admin_denied.json()["detail"] == (
        "Administrator accounts are not assigned to role groups"
    )


def test_membership_changes_are_audited(client, admin_headers, db):
    _, student = register_test_account(client, role="student")
    students = db.query(Group).filter_by(name="students").one()

    from app.models import AuditEvent

    prior_ids = {
        event_id
        for (event_id,) in db.query(AuditEvent.id).filter(
            AuditEvent.target_type == "group",
            AuditEvent.target_id == students.id,
        )
    }
    db.expire_all()

    client.delete(
        f"{GROUPS}/{students.id}/members/{student['id']}", headers=admin_headers
    )
    client.post(
        f"{GROUPS}/{students.id}/members",
        json={"user_id": student["id"]},
        headers=admin_headers,
    )

    actions = [
        event.action
        for event in db.query(AuditEvent)
        .filter(
            AuditEvent.target_type == "group",
            AuditEvent.target_id == students.id,
        )
        .order_by(AuditEvent.id)
        .all()
        if event.id not in prior_ids
    ]
    assert actions == ["group.member_removed", "group.member_added"]


def test_registration_membership_backfill_in_migration_is_idempotent(tmp_path):
    """The 0003 data migration seeds groups, backfills by role, skips admins,
    and can be re-executed without changing membership counts."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))

    url = "sqlite:///" + (tmp_path / "groups.db").as_posix()
    config.set_main_option("sqlalchemy.url", url)
    engine = create_engine(url)

    command.upgrade(config, "0002_audit_events")
    now = 1_760_000_000
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, email, full_name, role, password_hash, "
                "is_active, created_at) VALUES "
                "(1, 'legacy-student@example.edu', 'Legacy Student', 'student', "
                "'hash', 1, :now), "
                "(2, 'legacy-faculty@example.edu', 'Legacy Faculty', 'faculty', "
                "'hash', 1, :now), "
                "(3, 'legacy-admin@example.edu', 'Legacy Admin', 'admin', "
                "'hash', 1, :now)"
            ),
            {"now": now},
        )

    command.upgrade(config, "head")

    def membership_snapshot():
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT g.name, u.email FROM group_memberships m "
                    "JOIN groups g ON g.id = m.group_id "
                    "JOIN users u ON u.id = m.user_id ORDER BY u.id"
                )
            ).all()
            counts = connection.execute(
                text(
                    "SELECT g.name, COUNT(*) FROM group_memberships m "
                    "JOIN groups g ON g.id = m.group_id "
                    "GROUP BY g.name ORDER BY g.name"
                )
            ).all()
            return rows, counts

    rows, counts = membership_snapshot()
    assert rows == [("students", "legacy-student@example.edu"),
                    ("faculty", "legacy-faculty@example.edu")]
    assert dict(counts) == {"faculty": 1, "students": 1}

    backfill = text(
        "INSERT INTO group_memberships (group_id, user_id, created_at) "
        "SELECT g.id, u.id, :now FROM users u JOIN groups g "
        "ON g.name = CASE u.role WHEN 'student' THEN 'students' "
        "WHEN 'faculty' THEN 'faculty' END "
        "WHERE u.role IN ('student', 'faculty') "
        "ON CONFLICT (group_id, user_id) DO NOTHING"
    )
    with engine.begin() as connection:
        connection.execute(backfill, {"now": now})
        connection.execute(backfill, {"now": now})

    rows_again, counts_again = membership_snapshot()
    assert rows_again == rows
    assert counts_again == counts
