"""Role cohort groups: each student/faculty account belongs to one group.

Administrator accounts are never automatically added to a group.
"""

import time

from sqlalchemy.orm import Session

from ..models import Group, GroupMembership, User

ROLE_GROUP_NAMES = {"student": "students", "faculty": "faculty"}


def group_name_for_role(role: str) -> str | None:
    return ROLE_GROUP_NAMES.get(role)


def ensure_role_group(db: Session, role: str) -> Group | None:
    """Return the role's group, creating it if the seed is missing."""
    name = group_name_for_role(role)
    if name is None:
        return None
    group = db.query(Group).filter(Group.name == name).first()
    if group is None:
        group = Group(name=name, created_at=int(time.time()))
        db.add(group)
        db.flush()
    return group


def assign_role_group(db: Session, user: User) -> GroupMembership | None:
    """Attach a new account to its role group in the caller's transaction."""
    group = ensure_role_group(db, user.role)
    if group is None:
        return None
    membership = GroupMembership(
        group_id=group.id,
        user_id=user.id,
        created_at=int(time.time()),
    )
    db.add(membership)
    return membership
