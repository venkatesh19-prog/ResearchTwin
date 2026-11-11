"""unique open collaborations and pending collaboration requests

Revision ID: 0010_repair_batch_2
Revises: 0009_research_labs
Create Date: 2026-11-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_repair_batch_2"
down_revision: Union[str, None] = "0009_research_labs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _canonicalize_pair_keys() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                "UPDATE interuniversity_collaborations "
                "SET pair_key = LEAST(requester_lab_id, partner_lab_id)::text "
                "|| ':' || GREATEST(requester_lab_id, partner_lab_id)::text"
            )
        )
    else:
        bind.execute(
            sa.text(
                "UPDATE interuniversity_collaborations "
                "SET pair_key = CAST(MIN(requester_lab_id, partner_lab_id) AS TEXT) "
                "|| ':' || CAST(MAX(requester_lab_id, partner_lab_id) AS TEXT)"
            )
        )

    # Historical rows may already contain open duplicates. Keep the oldest
    # open row addressable by the unique index and clear the key on the rest;
    # the rows themselves are preserved for manual review.
    bind.execute(
        sa.text(
            "UPDATE interuniversity_collaborations "
            "SET pair_key = NULL "
            "WHERE status IN ('proposed', 'active') "
            "AND id NOT IN ("
            "    SELECT MIN(id) FROM interuniversity_collaborations "
            "    WHERE status IN ('proposed', 'active') GROUP BY pair_key"
            ")"
        )
    )


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return index_name in {
        index["name"] for index in inspector.get_indexes(table_name)
    }


def _require_unique_pending_requests() -> None:
    duplicates = op.get_bind().execute(
        sa.text(
            "SELECT student_user_id, researcher_id, COUNT(*) AS pending_count "
            "FROM collaboration_requests "
            "WHERE status = 'pending' "
            "GROUP BY student_user_id, researcher_id "
            "HAVING COUNT(*) > 1 "
            "ORDER BY student_user_id, researcher_id"
        )
    ).fetchall()
    if not duplicates:
        return

    pairs = "; ".join(
        f"student {row.student_user_id} / researcher {row.researcher_id} "
        f"has {row.pending_count} pending requests"
        for row in duplicates[:20]
    )
    if len(duplicates) > 20:
        pairs += f"; and {len(duplicates) - 20} more pair(s)"
    raise RuntimeError(
        "Cannot add uq_collaboration_requests_pending: "
        f"{len(duplicates)} student/researcher pair(s) already hold more "
        f"than one pending collaboration request ({pairs}). The product "
        "records only 'accepted' and 'rejected' as decisions, so keep "
        "exactly one request pending per pair and decide the others, then "
        "run 'alembic upgrade head' again. Nothing was changed: the upgrade "
        "transaction rolls back."
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"]
        for column in inspector.get_columns("interuniversity_collaborations")
    }
    if "pair_key" not in columns:
        op.add_column(
            "interuniversity_collaborations",
            sa.Column("pair_key", sa.String(length=32), nullable=True),
        )
    _canonicalize_pair_keys()
    if not _index_exists(
        "interuniversity_collaborations",
        "uq_interuniversity_collaborations_open_pair",
    ):
        op.create_index(
            "uq_interuniversity_collaborations_open_pair",
            "interuniversity_collaborations",
            ["pair_key"],
            unique=True,
            sqlite_where=sa.text(
                "pair_key IS NOT NULL AND status IN ('proposed', 'active')"
            ),
            postgresql_where=sa.text(
                "pair_key IS NOT NULL AND status IN ('proposed', 'active')"
            ),
        )
    if not _index_exists(
        "collaboration_requests", "uq_collaboration_requests_pending"
    ):
        _require_unique_pending_requests()
        op.create_index(
            "uq_collaboration_requests_pending",
            "collaboration_requests",
            ["student_user_id", "researcher_id"],
            unique=True,
            sqlite_where=sa.text("status = 'pending'"),
            postgresql_where=sa.text("status = 'pending'"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _index_exists(
        "collaboration_requests", "uq_collaboration_requests_pending"
    ):
        op.drop_index(
            "uq_collaboration_requests_pending",
            table_name="collaboration_requests",
        )
    if _index_exists(
        "interuniversity_collaborations",
        "uq_interuniversity_collaborations_open_pair",
    ):
        op.drop_index(
            "uq_interuniversity_collaborations_open_pair",
            table_name="interuniversity_collaborations",
        )
    columns = {
        column["name"]
        for column in inspector.get_columns("interuniversity_collaborations")
    }
    if "pair_key" in columns:
        op.drop_column("interuniversity_collaborations", "pair_key")
