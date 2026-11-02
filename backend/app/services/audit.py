"""Small append-only audit trail for administrative and collaboration actions."""

import json
import time

from sqlalchemy.orm import Session

from ..models import AuditEvent, User


def record_event(
    db: Session,
    *,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    detail: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor.id if actor is not None else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=json.dumps(detail or {}, sort_keys=True, separators=(",", ":")),
        created_at=int(time.time()),
    )
    db.add(event)
    return event
