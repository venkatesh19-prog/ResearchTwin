"""Repair two states the first demo seed created that the app itself cannot.

1. Groups are role cohorts ("students", "faculty"); the admin API only lets an
   account join its own role's group, so the three extra [DEMO] groups were
   invalid. They and their memberships are removed.
2. Inter-university collaborations need the partner lab to be visible to the
   requester, but the seeded "[DEMO] Recommender Systems Group" was
   institution-only. It becomes public, matching the corrected seed.

Safeguards: the target must match the reviewed fingerprint and Neon endpoint;
each group's membership must equal what the seed created; no other table may
reference groups; only the named [DEMO] rows are touched.

Run from backend/ without --commit for a rolled-back dry run.
"""

import argparse
import hashlib
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

ENV_FILE = os.environ.get(
    "RESEARCHTWIN_SEED_ENV_FILE",
    os.path.join(os.path.expanduser("~"), ".researchtwin-neon-prod.env"),
)
EXPECTED_FINGERPRINT = "75d4fe804228"
EXPECTED_ENDPOINT = "ep-floral-thunder-bddca63h"
SEEDED = {
    "[DEMO] NLP Interest Group": {1, 3},
    "[DEMO] Medical Imaging Interest Group": {2, 4},
    "[DEMO] Research Mentors": {3, 4, 5},
}

parser = argparse.ArgumentParser()
parser.add_argument("--commit", action="store_true")
args = parser.parse_args()

url = next(
    line.split("=", 1)[1].strip()
    for line in open(ENV_FILE, encoding="utf-8")
    if line.startswith("DATABASE_URL=")
)
if hashlib.sha256(url.encode()).hexdigest()[:12] != EXPECTED_FINGERPRINT:
    raise SystemExit("Target fingerprint mismatch - refusing to run")
os.environ.pop("RESEARCHTWIN_ENV_FILE", None)
os.environ.pop("RENDER", None)
os.environ["DATABASE_URL"] = url

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Group, GroupMembership, ResearchLab  # noqa: E402

db = SessionLocal()
try:
    if db.execute(text("select current_setting('neon.endpoint_id', true)")).scalar() != EXPECTED_ENDPOINT:
        raise SystemExit("Unexpected endpoint - refusing to run")
    # Only group_memberships may reference groups; refuse if anything else does.
    refs = db.execute(text(
        "select conrelid::regclass::text from pg_constraint "
        "where contype='f' and confrelid='groups'::regclass")).scalars().all()
    if set(refs) - {"group_memberships"}:
        raise SystemExit(f"Unexpected tables reference groups: {refs} - refusing to run")

    removed_groups = removed_members = 0
    for name, expected_members in SEEDED.items():
        group = db.query(Group).filter(Group.name == name).first()
        if group is None:
            continue
        members = {m.user_id for m in db.query(GroupMembership).filter_by(group_id=group.id)}
        if members != expected_members:
            raise SystemExit(f"{name} membership changed since seeding ({sorted(members)}) - refusing to run")
        removed_members += db.query(GroupMembership).filter_by(group_id=group.id).delete()
        db.delete(group)
        removed_groups += 1
    labs_made_public = 0
    lab = db.query(ResearchLab).filter(ResearchLab.name == "[DEMO] Recommender Systems Group").first()
    if lab is not None and lab.visibility == "institution":
        lab.visibility = "public"
        labs_made_public = 1
    db.flush()
    remaining = sorted(g.name for g in db.query(Group))
    print(f"{'COMMIT' if args.commit else 'DRY RUN (rolled back)'}: removed {removed_groups} groups, "
          f"{removed_members} memberships, made {labs_made_public} lab public; groups now {remaining}")
    if args.commit:
        db.commit()
    else:
        db.rollback()
finally:
    db.close()
