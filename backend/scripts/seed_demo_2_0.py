"""Idempotent ResearchTwin 2.0 demo seed for the existing demo accounts (users 1-6).

Every inserted row is looked up by a natural key first, so a rerun inserts
nothing. All human-readable content is fictional and marked [DEMO]. The script
never touches users, credentials, roles, sessions, audit events or user 7.

Run without --commit for a dry run: everything executes inside one transaction
that is rolled back at the end.

    cd backend
    python scripts/seed_demo_2_0.py            # dry run
    python scripts/seed_demo_2_0.py --commit   # apply
"""

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

# A dotenv file holding only DATABASE_URL for the approved target, kept outside
# the repository. The resolved URL must still match the reviewed fingerprint and
# the server must report the reviewed Neon endpoint.
ENV_FILE = os.environ.get(
    "RESEARCHTWIN_SEED_ENV_FILE",
    os.path.join(os.path.expanduser("~"), ".researchtwin-neon-prod.env"),
)
EXPECTED_FINGERPRINT = "75d4fe804228"
EXPECTED_ENDPOINT = "ep-floral-thunder-bddca63h"

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
from app.models import (  # noqa: E402
    CollaborationRequest, CollaborationWorkspace, FacultyResearcherLink,
    Institution, InstitutionMembership, InterUniversityCollaboration,
    LiteratureEntry, Opportunity, OpportunityApplication, ProposalCitation,
    ProposalCollaborator, ProposalSection, PublicationRevision, PublicationStatusEvent,
    PublicationSubmission, ResearchClusterRun, ResearchLab, ResearchLabMember,
    ResearchProposal, ResearchTeam, ResearchTeamInvitation, ResearchTeamMember,
    Researcher, ResearcherVerification, RoadmapProgress, SearchHistory, StudentProfile,
    ThesisMilestone, ThesisProgressEvent, ThesisRecord, User, WorkspaceComment,
    WorkspaceMember, WorkspaceMilestone, WorkspaceTask,
)
from app.services import research_outputs, workspaces as workspace_service  # noqa: E402
from app.services.readiness_roadmap import build_student_roadmap  # noqa: E402
from app.services.skill_gap import calculate_skill_gap  # noqa: E402

NOW = int(time.time())
DAY = 86400
inserted = Counter()   # (feature, owner) -> count
updated = Counter()


def ago(days, hours=0):
    return NOW - int(days * DAY) - int(hours * 3600)


def get_or_create(db, model, feature, owner, lookup, **values):
    row = db.query(model).filter_by(**lookup).first()
    if row is not None:
        return row, False
    row = model(**lookup, **values)
    db.add(row)
    db.flush()
    inserted[(feature, owner)] += 1
    return row, True


db = SessionLocal()
try:
    endpoint = db.execute(text("select current_setting('neon.endpoint_id', true)")).scalar()
    if endpoint != EXPECTED_ENDPOINT:
        raise SystemExit(f"Unexpected endpoint {endpoint!r} - refusing to run")
    if db.execute(text("select version_num from alembic_version")).scalar() != "0012_search_history":
        raise SystemExit("Schema is not at 0012_search_history - refusing to run")

    def user_fingerprint():
        rows = db.execute(text(
            "select id, email, full_name, role, password_hash, is_active, created_at "
            "from users order by id")).fetchall()
        return hashlib.sha256(repr(rows).encode()).hexdigest()

    users_before = user_fingerprint()
    users = {u.id: u for u in db.query(User).filter(User.id.in_([1, 2, 3, 4, 5, 6])).all()}
    expected_roles = {1: "student", 2: "student", 3: "faculty", 4: "faculty", 5: "faculty", 6: "admin"}
    for uid, role in expected_roles.items():
        if uid not in users or users[uid].role != role or not users[uid].is_active:
            raise SystemExit(f"Account {uid} is not the expected active {role} - refusing to run")

    RIYA, ADITYA, PRIYA, AISHA, ROHAN, ADMIN = 1, 2, 3, 4, 5, 6
    name = {uid: users[uid].full_name for uid in users}

    # Faculty accounts and their same-name directory records.
    faculty_researcher = {}
    for uid in (PRIYA, AISHA, ROHAN):
        r = db.query(Researcher).filter(Researcher.name == users[uid].full_name).one()
        faculty_researcher[uid] = r
    R_PRIYA, R_AISHA, R_ROHAN = (faculty_researcher[u] for u in (PRIYA, AISHA, ROHAN))

    # ------------------------------------------------------------------ profiles
    student_publications = {
        RIYA: "[DEMO] Code-mixed question answering with lightweight retrieval (student workshop poster, draft)",
        ADITYA: "[DEMO] Lesion boundary refinement with test-time augmentation (course project report)",
    }
    for uid, pubs in student_publications.items():
        profile = db.query(StudentProfile).filter_by(user_id=uid).one()
        if not profile.publications.strip():   # fill only empty fields; never overwrite
            profile.publications = pubs
            profile.updated_at = NOW
            updated[("student_profile.publications", name[uid])] += 1

    for uid, r in faculty_researcher.items():
        existing = db.query(FacultyResearcherLink).filter(
            (FacultyResearcherLink.faculty_user_id == uid) |
            (FacultyResearcherLink.researcher_id == r.id)).first()
        if existing is None:
            db.add(FacultyResearcherLink(faculty_user_id=uid, researcher_id=r.id, created_at=ago(9)))
            db.flush()
            inserted[("faculty_researcher_link", name[uid])] += 1
        elif not (existing.faculty_user_id == uid and existing.researcher_id == r.id):
            raise SystemExit(f"Conflicting researcher link for {name[uid]} - refusing to run")

    # Verification requests stay PENDING: nothing is approved on anyone's behalf.
    for uid, r, days in ((PRIYA, R_PRIYA, 6), (AISHA, R_AISHA, 4)):
        exists = db.query(ResearcherVerification).filter_by(researcher_id=r.id).first()
        if exists is None:
            db.add(ResearcherVerification(
                researcher_id=r.id, status="pending",
                evidence_reference="[DEMO] Placeholder evidence reference - not a real document",
                note="[DEMO DATA] Sample verification request awaiting administrator review.",
                review_note="", submitted_by_user_id=uid, reviewed_by_user_id=None,
                submitted_at=ago(days), reviewed_at=None, expires_at=None, created_at=ago(days)))
            db.flush()
            inserted[("verification_request(pending)", name[uid])] += 1

    # Groups are role cohorts ("students", "faculty") managed by registration and
    # the admin console; the demo accounts already belong to theirs, so no extra
    # groups are seeded.

    # ------------------------------------------------------------------ institutions and labs
    north, _ = get_or_create(db, Institution, "institution", name[ADMIN],
                             {"name": "[DEMO] Northbridge Institute of Technology"}, created_at=ago(12))
    west, _ = get_or_create(db, Institution, "institution", name[ADMIN],
                            {"name": "[DEMO] Westvale University"}, created_at=ago(12))
    for uid, inst in ((RIYA, north), (ADITYA, north), (PRIYA, north), (AISHA, north), (ROHAN, west)):
        m = db.query(InstitutionMembership).filter_by(user_id=uid).first()
        if m is None:
            db.add(InstitutionMembership(institution_id=inst.id, user_id=uid, created_at=ago(12)))
            db.flush()
            inserted[("institution_membership", name[uid])] += 1
        elif m.institution_id != inst.id:
            raise SystemExit(f"{name[uid]} already belongs to another institution - refusing to run")

    lab_specs = [
        (north, PRIYA, "[DEMO] Applied NLP Lab",
         "[DEMO DATA] Fictional lab studying multilingual and code-mixed language understanding.",
         "Natural Language Processing, Generative AI, Multilingual NLP", "public", (RIYA,)),
        (north, AISHA, "[DEMO] Vision and Imaging Lab",
         "[DEMO DATA] Fictional lab working on medical image segmentation and robust vision models.",
         "Computer Vision, Deep Learning, Medical Imaging", "public", (ADITYA,)),
        (west, ROHAN, "[DEMO] Recommender Systems Group",
         "[DEMO DATA] Fictional group on fair, explainable recommender systems.",
         "Recommender Systems, Machine Learning, Data Mining", "public", ()),
    ]
    labs = {}
    for inst, owner, lname, desc, areas, vis, members in lab_specs:
        lab, _ = get_or_create(db, ResearchLab, "research_lab", name[owner],
                               {"institution_id": inst.id, "name": lname},
                               owner_user_id=owner, description=desc, research_areas=areas,
                               visibility=vis, created_at=ago(11), updated_at=ago(11))
        labs[owner] = lab
        for uid in (owner,) + members:
            get_or_create(db, ResearchLabMember, "research_lab_member", name[owner],
                          {"lab_id": lab.id, "user_id": uid}, created_at=ago(11))

    def pair_key(a, b):
        return f"{min(a, b)}:{max(a, b)}"

    for req_owner, partner_owner, title, desc, status, decided in (
        (PRIYA, ROHAN, "[DEMO] Explainable recommendations for multilingual learners",
         "[DEMO DATA] Fictional joint project between two demo labs.", "active", ROHAN),
        (AISHA, ROHAN, "[DEMO] Recommending annotation tasks for imaging datasets",
         "[DEMO DATA] Fictional proposal awaiting the partner lab's response.", "proposed", None),
    ):
        a, b = labs[req_owner], labs[partner_owner]
        existing = db.query(InterUniversityCollaboration).filter_by(
            requester_lab_id=a.id, partner_lab_id=b.id, title=title).first()
        if existing is None:
            db.add(InterUniversityCollaboration(
                requester_lab_id=a.id, partner_lab_id=b.id, initiated_by_user_id=req_owner,
                decided_by_user_id=decided, title=title, description=desc, status=status,
                resolution_note="[DEMO] Accepted for the demonstration." if decided else "",
                responded_at=ago(7) if decided else None, created_at=ago(9), updated_at=ago(7 if decided else 9),
                pair_key=pair_key(a.id, b.id)))
            db.flush()
            inserted[("interuniversity_collaboration", name[req_owner])] += 1

    # ------------------------------------------------------------------ collaboration requests and workspaces
    collab_specs = [
        (RIYA, PRIYA, "accepted", 14, 12,
         "[DEMO] I would like to work on code-mixed question answering under your guidance.",
         "[DEMO] Happy to supervise - let's set up a workspace."),
        (ADITYA, AISHA, "accepted", 13, 11,
         "[DEMO] I am interested in your medical image segmentation work.",
         "[DEMO] Welcome aboard - start with the dataset audit task."),
        (ADITYA, PRIYA, "rejected", 10, 9,
         "[DEMO] Could I join your NLP projects this semester?",
         "[DEMO] My group is full this term; please apply next semester."),
        (RIYA, ROHAN, "pending", 3, None,
         "[DEMO] I'd like to explore fairness in recommender evaluation.", ""),
        (ADITYA, ROHAN, "pending", 2, None,
         "[DEMO] Interested in recommendation for annotation workflows.", ""),
    ]
    workspaces = {}
    for student, fac, status, created_days, reviewed_days, msg, response in collab_specs:
        r = faculty_researcher[fac]
        req, created = get_or_create(
            db, CollaborationRequest, "collaboration_request", name[student],
            {"student_user_id": student, "researcher_id": r.id, "message": msg},
            status=status, faculty_response=response,
            reviewed_at=ago(reviewed_days) if reviewed_days else None,
            created_at=ago(created_days), updated_at=ago(reviewed_days or created_days))
        if status == "accepted":
            ws = db.query(CollaborationWorkspace).filter_by(collaboration_request_id=req.id).first()
            if ws is None:
                ws = workspace_service.create_for_accepted_request(
                    db, request=req, researcher=r, faculty_user_id=fac)
                ws.created_at = ws.updated_at = ago(reviewed_days)
                for m in db.query(WorkspaceMember).filter_by(workspace_id=ws.id):
                    m.created_at = ago(reviewed_days)
                inserted[("workspace", name[student])] += 1
                inserted[("workspace_member", name[student])] += 2
            workspaces[student] = (ws, fac)

    ws_content = {
        RIYA: (
            [("[DEMO] Collect a code-mixed QA evaluation set", "done", RIYA, -4),
             ("[DEMO] Baseline: multilingual retriever + reader", "in_progress", RIYA, 6),
             ("[DEMO] Review error categories with supervisor", "todo", PRIYA, 12)],
            [("[DEMO] Literature review complete", "completed", -5),
             ("[DEMO] Baseline results", "pending", 10)],
            [(PRIYA, "[DEMO] Nice start on the dataset - please document the annotation guidelines."),
             (RIYA, "[DEMO] Guidelines added to the shared notes; baseline run is in progress.")]),
        ADITYA: (
            [("[DEMO] Audit the public imaging dataset licence and splits", "done", ADITYA, -3),
             ("[DEMO] Train U-Net baseline", "in_progress", ADITYA, 8),
             ("[DEMO] Prepare augmentation ablation plan", "todo", AISHA, 14)],
            [("[DEMO] Dataset audit", "completed", -3),
             ("[DEMO] Baseline Dice score report", "pending", 12)],
            [(AISHA, "[DEMO] Please track Dice and boundary F1 separately."),
             (ADITYA, "[DEMO] Will do - both metrics are now logged per epoch.")]),
    }
    for student, (ws, fac) in workspaces.items():
        tasks, milestones, comments = ws_content[student]
        first_task = None
        for title, status, assignee, due in tasks:
            t, _ = get_or_create(db, WorkspaceTask, "workspace_task", name[student],
                                 {"workspace_id": ws.id, "title": title},
                                 description="[DEMO DATA] Sample task.", status=status,
                                 assignee_user_id=assignee, created_by_user_id=fac,
                                 due_at=NOW + due * DAY, created_at=ago(10), updated_at=ago(2))
            first_task = first_task or t
        for title, status, due in milestones:
            get_or_create(db, WorkspaceMilestone, "workspace_milestone", name[student],
                          {"workspace_id": ws.id, "title": title}, status=status,
                          due_at=NOW + due * DAY, completed_at=(NOW + due * DAY) if status == "completed" else None,
                          created_by_user_id=fac, created_at=ago(10), updated_at=ago(2))
        for i, (author, body) in enumerate(comments):
            get_or_create(db, WorkspaceComment, "workspace_comment", name[student],
                          {"workspace_id": ws.id, "body": body}, task_id=first_task.id,
                          author_user_id=author, created_at=ago(4 - i))

    # ------------------------------------------------------------------ teams
    team_specs = [
        (PRIYA, "[DEMO] Multilingual QA Team",
         "[DEMO DATA] Fictional team building code-mixed QA resources.",
         "Natural Language Processing, Question Answering", "Transformers, Evaluation",
         "Python, PyTorch, Hugging Face", [RIYA], [(ADITYA, "pending")]),
        (AISHA, "[DEMO] Medical Imaging Reading Group",
         "[DEMO DATA] Fictional reading group on segmentation papers.",
         "Computer Vision, Medical Imaging", "Segmentation, Deep Learning",
         "Python, PyTorch, OpenCV", [ADITYA], [(ROHAN, "pending")]),
        (RIYA, "[DEMO] Student NLP Hack Team",
         "[DEMO DATA] Fictional student team for a weekend NLP hackathon.",
         "Natural Language Processing", "Prompting, Evaluation", "Python",
         [], [(ADITYA, "accepted")]),
    ]
    for owner, tname, desc, areas, expertise, skills, members, invites in team_specs:
        team, _ = get_or_create(db, ResearchTeam, "research_team", name[owner],
                                {"owner_user_id": owner, "name": tname},
                                description=desc, research_areas=areas, expertise=expertise,
                                skills=skills, projects="[DEMO] Sample project", publications="",
                                created_at=ago(9), updated_at=ago(3))
        get_or_create(db, ResearchTeamMember, "team_member", name[owner],
                      {"team_id": team.id, "user_id": owner}, role="owner", created_at=ago(9))
        for uid in members:
            get_or_create(db, ResearchTeamMember, "team_member", name[owner],
                          {"team_id": team.id, "user_id": uid}, role="member", created_at=ago(8))
        for uid, status in invites:
            get_or_create(db, ResearchTeamInvitation, "team_invitation", name[owner],
                          {"team_id": team.id, "invited_user_id": uid},
                          invited_by_user_id=owner, status=status, created_at=ago(5),
                          responded_at=ago(4) if status != "pending" else None)
            if status == "accepted":
                get_or_create(db, ResearchTeamMember, "team_member", name[owner],
                              {"team_id": team.id, "user_id": uid}, role="member", created_at=ago(4))

    # ------------------------------------------------------------------ opportunities and applications
    opp_specs = [
        (PRIYA, R_PRIYA.id, "research", "open", "[DEMO] Research Assistant - Low-resource NLP",
         "[DEMO DATA] Fictional RA position on multilingual QA datasets.", "[DEMO] Applied NLP Lab",
         "Python, PyTorch, NLP", "Natural Language Processing", "Transformers", "Undergraduate or postgraduate students", 30),
        (AISHA, R_AISHA.id, "research", "open", "[DEMO] Summer Internship - Medical Image Segmentation",
         "[DEMO DATA] Fictional internship on segmentation baselines.", "[DEMO] Vision and Imaging Lab",
         "Python, PyTorch, OpenCV", "Computer Vision, Medical Imaging", "Deep Learning", "Students with a deep learning course", 21),
        (ROHAN, R_ROHAN.id, "research", "open", "[DEMO] Graduate Project - Fair Recommender Evaluation",
         "[DEMO DATA] Fictional project on fairness metrics for recommenders.", "[DEMO] Recommender Systems Group",
         "Python, Pandas, Scikit-learn", "Recommender Systems", "Machine Learning", "Final-year students", 40),
        (PRIYA, R_PRIYA.id, "research", "closed", "[DEMO] Annotation Sprint - Code-mixed Corpus",
         "[DEMO DATA] Fictional, already-closed annotation call.", "[DEMO] Applied NLP Lab",
         "Annotation", "Natural Language Processing", "Linguistics", "All students", -5),
        (ADMIN, None, "funding", "open", "[DEMO] Seed Grant - Student-led AI for Social Good",
         "[DEMO DATA] Fictional institutional seed grant.", "[DEMO] Fictional Innovation Fund",
         "", "Artificial Intelligence", "", "Student teams with a faculty mentor", 45),
        (ADMIN, None, "funding", "closed", "[DEMO] Conference Travel Fellowship",
         "[DEMO DATA] Fictional, closed travel fellowship.", "[DEMO] Fictional Research Office",
         "", "", "", "Students presenting an accepted paper", -10),
    ]
    opps = {}
    for creator, rid, cat, status, title, desc, org, skills, areas, expertise, elig, deadline in opp_specs:
        o, _ = get_or_create(db, Opportunity, "opportunity", name[creator],
                             {"created_by_user_id": creator, "title": title},
                             category=cat, description=desc, organization=org, location="[DEMO] Hybrid",
                             url="", deadline_at=NOW + deadline * DAY, status=status, researcher_id=rid,
                             required_skills=skills, required_research_areas=areas,
                             required_expertise=expertise, eligibility=elig,
                             external_source=None, external_id=None,
                             created_at=ago(15), updated_at=ago(3))
        opps[title] = o
    app_specs = [
        (RIYA, "[DEMO] Research Assistant - Low-resource NLP", "accepted", PRIYA,
         "[DEMO] I have built a small code-mixed dataset and would love to contribute.", "[DEMO] Accepted - see the workspace."),
        (RIYA, "[DEMO] Seed Grant - Student-led AI for Social Good", "pending", None,
         "[DEMO] Our team proposes a multilingual helpline triage assistant.", ""),
        (ADITYA, "[DEMO] Summer Internship - Medical Image Segmentation", "pending", None,
         "[DEMO] I completed a U-Net course project and want to go further.", ""),
        (ADITYA, "[DEMO] Graduate Project - Fair Recommender Evaluation", "rejected", ROHAN,
         "[DEMO] Interested in fairness metrics.", "[DEMO] Please re-apply after the ML elective."),
    ]
    for student, otitle, status, reviewer, msg, note in app_specs:
        o = opps[otitle]
        get_or_create(db, OpportunityApplication, "opportunity_application", name[student],
                      {"opportunity_id": o.id, "student_user_id": student},
                      message=msg, status=status, decision_note=note, reviewed_by_user_id=reviewer,
                      created_at=ago(8), updated_at=ago(5 if reviewer else 8),
                      reviewed_at=ago(5) if reviewer else None)

    # ------------------------------------------------------------------ literature
    lit_specs = {
        RIYA: [("demo-cmqa-survey", "[DEMO] A Survey of Code-mixed Question Answering", "A. Fictional, B. Example", "DEMO Workshop on Multilingual NLP", 2025, "reviewed", "survey, code-mixing"),
               ("demo-retrieval-lowres", "[DEMO] Lightweight Retrieval for Low-resource Languages", "C. Sample", "DEMO Conference on Language Technology", 2024, "reading", "retrieval"),
               ("demo-eval-multiling", "[DEMO] Evaluating Multilingual Readers Beyond Accuracy", "D. Placeholder", "DEMO Journal of Applied NLP", 2025, "to_read", "evaluation"),
               ("demo-annot-guidelines", "[DEMO] Annotation Guidelines for Mixed-script Corpora", "E. Fictional", "DEMO Workshop on Resources", 2023, "reviewed", "annotation")],
        ADITYA: [("demo-unet-revisit", "[DEMO] Revisiting U-Net Baselines for Lesion Segmentation", "F. Example", "DEMO Medical Imaging Symposium", 2024, "reviewed", "segmentation"),
                 ("demo-tta-boundary", "[DEMO] Test-time Augmentation for Boundary Quality", "G. Sample", "DEMO Vision Workshop", 2025, "reading", "augmentation"),
                 ("demo-dataset-shift", "[DEMO] Dataset Shift in Clinical Imaging: A Primer", "H. Placeholder", "DEMO Journal of Imaging Notes", 2023, "to_read", "robustness")],
        PRIYA: [("demo-genai-tutoring", "[DEMO] Generative Tutors for Multilingual Classrooms", "I. Fictional", "DEMO Education & AI Forum", 2025, "reviewed", "generative-ai"),
                ("demo-prompt-robust", "[DEMO] Prompt Robustness Across Scripts", "J. Example", "DEMO NLP Letters", 2024, "reading", "prompting")],
        AISHA: [("demo-weak-labels", "[DEMO] Weak Labels for Medical Segmentation", "K. Sample", "DEMO Imaging Letters", 2024, "reviewed", "weak-supervision"),
                ("demo-calibration-seg", "[DEMO] Calibration of Segmentation Networks", "L. Placeholder", "DEMO Vision Review", 2025, "to_read", "calibration")],
        ROHAN: [("demo-fair-recsys", "[DEMO] Fairness Metrics for Top-k Recommendation", "M. Fictional", "DEMO RecSys Workshop", 2024, "reviewed", "fairness"),
                ("demo-explain-recs", "[DEMO] Explaining Recommendations to Learners", "N. Example", "DEMO Learning Analytics Notes", 2025, "reading", "explainability")],
    }
    literature = {}
    for owner, entries in lit_specs.items():
        for key, title, authors, venue, year, status, tags in entries:
            e, _ = get_or_create(db, LiteratureEntry, "literature_entry", name[owner],
                                 {"owner_user_id": owner, "citation_key": key},
                                 title=title, authors=authors, venue=venue, year=year, doi="", url="",
                                 abstract="[DEMO DATA] Fictional abstract for demonstration purposes.",
                                 notes="[DEMO] Sample reading notes.", tags=tags, review_status=status,
                                 created_at=ago(20), updated_at=ago(3))
            literature[key] = e

    # ------------------------------------------------------------------ proposals
    prop_specs = [
        (RIYA, "[DEMO] Proposal: Code-mixed Question Answering for Campus Help Desks", "draft",
         [("Background", "[DEMO] Students often ask questions mixing two languages."),
          ("Objectives", "[DEMO] Build and evaluate a lightweight code-mixed QA system."),
          ("Methodology", "[DEMO] Multilingual retriever, reader fine-tuning and error analysis."),
          ("Timeline", "[DEMO] Twelve weeks across three milestones.")],
         [(PRIYA, "editor")], ["demo-cmqa-survey", "demo-retrieval-lowres"]),
        (AISHA, "[DEMO] Proposal: Robust Lesion Segmentation under Dataset Shift", "submitted",
         [("Problem", "[DEMO] Segmentation quality drops across scanners."),
          ("Approach", "[DEMO] Test-time augmentation and calibration."),
          ("Evaluation", "[DEMO] Dice, boundary F1 and calibration error.")],
         [(ADITYA, "viewer")], ["demo-weak-labels", "demo-calibration-seg"]),
    ]
    for owner, title, status, sections, collaborators, cites in prop_specs:
        p, created = get_or_create(db, ResearchProposal, "proposal", name[owner],
                                   {"owner_user_id": owner, "title": title},
                                   status=status, created_at=ago(10), updated_at=ago(2))
        sec_rows = []
        for pos, (heading, body) in enumerate(sections):
            s, _ = get_or_create(db, ProposalSection, "proposal_section", name[owner],
                                 {"proposal_id": p.id, "heading": heading},
                                 body=body, position=pos, created_at=ago(10), updated_at=ago(2))
            sec_rows.append(s)
        for uid, role in collaborators:
            get_or_create(db, ProposalCollaborator, "proposal_collaborator", name[owner],
                          {"proposal_id": p.id, "user_id": uid}, role=role, created_at=ago(9))
        for key in cites:
            get_or_create(db, ProposalCitation, "proposal_citation", name[owner],
                          {"proposal_id": p.id, "literature_entry_id": literature[key].id},
                          section_id=sec_rows[0].id, created_by_user_id=owner, created_at=ago(8))
        if research_outputs.latest_proposal_version(db, p.id) == 0:
            research_outputs.record_proposal_version(db, p, owner)
            inserted[("proposal_version", name[owner])] += 1

    # ------------------------------------------------------------------ theses
    thesis_specs = [
        (RIYA, PRIYA, "[DEMO] Thesis: Code-mixed QA for Low-resource Settings", "in_progress",
         [("[DEMO] Literature review", "completed", -20), ("[DEMO] Dataset construction", "completed", -6),
          ("[DEMO] Baseline experiments", "pending", 14), ("[DEMO] Thesis draft", "pending", 60)]),
        (ADITYA, AISHA, "[DEMO] Thesis: Boundary-aware Lesion Segmentation", "proposed",
         [("[DEMO] Problem statement approval", "pending", 10), ("[DEMO] Baseline replication", "pending", 35)]),
    ]
    for owner, supervisor, title, status, milestones in thesis_specs:
        th, created = get_or_create(db, ThesisRecord, "thesis", name[owner],
                                    {"owner_user_id": owner, "title": title},
                                    supervisor_user_id=supervisor,
                                    abstract="[DEMO DATA] Fictional thesis abstract.",
                                    status=status, created_at=ago(30), updated_at=ago(2))
        if created:
            research_outputs.record_thesis_event(db, th, actor_user_id=owner, event_type="thesis_created",
                                                 note="[DEMO] Thesis record created.")
            research_outputs.record_thesis_event(db, th, actor_user_id=owner, event_type="supervisor_assigned",
                                                 note=f"[DEMO] Supervisor assigned: {name[supervisor]}.")
            if status != "proposed":
                research_outputs.record_thesis_event(db, th, actor_user_id=owner, event_type="status_changed",
                                                     note="[DEMO] Work started.", from_status="proposed", to_status=status)
            inserted[("thesis_event", name[owner])] += 2 + (status != "proposed")
        for pos, (mtitle, mstatus, due) in enumerate(milestones):
            m, mcreated = get_or_create(db, ThesisMilestone, "thesis_milestone", name[owner],
                                        {"thesis_id": th.id, "title": mtitle},
                                        due_at=NOW + due * DAY, status=mstatus, position=pos,
                                        completed_at=(NOW + due * DAY) if mstatus == "completed" else None,
                                        created_by_user_id=owner, created_at=ago(28), updated_at=ago(2))
            if mcreated:
                research_outputs.record_thesis_event(db, th, actor_user_id=owner, event_type="milestone_added",
                                                     note=f"Milestone '{mtitle}' added.", milestone_id=m.id)
                inserted[("thesis_event", name[owner])] += 1
                if mstatus == "completed":
                    research_outputs.record_thesis_event(db, th, actor_user_id=owner, event_type="milestone_completed",
                                                         note=f"Milestone '{mtitle}' completed.", milestone_id=m.id)
                    inserted[("thesis_event", name[owner])] += 1

    # ------------------------------------------------------------------ publications
    PATHS = {
        "published": ["submitted", "under_review", "accepted", "published"],
        "under_review": ["submitted", "under_review"],
        "revision_requested": ["submitted", "under_review", "revision_requested"],
        "draft": [],
    }
    pub_specs = [
        (PRIYA, "[DEMO] Code-mixed Reading Comprehension: A Benchmark", "[DEMO] Journal of Applied Language Technology", "journal", "published"),
        (AISHA, "[DEMO] Boundary-aware Losses for Lesion Segmentation", "[DEMO] Conference on Medical Vision", "conference", "under_review"),
        (ROHAN, "[DEMO] Auditing Fairness in Course Recommenders", "[DEMO] Workshop on Fair RecSys", "workshop", "revision_requested"),
        (RIYA, "[DEMO] Lightweight Retrieval for Code-mixed Queries", "[DEMO] Student Research Workshop", "workshop", "draft"),
    ]
    for owner, title, venue, vtype, final in pub_specs:
        path = PATHS[final]
        start = ago(40)
        steps = {s: start + (i + 1) * 7 * DAY for i, s in enumerate(path)}
        sub, created = get_or_create(db, PublicationSubmission, "publication", name[owner],
                                     {"owner_user_id": owner, "title": title},
                                     venue=venue, venue_type=vtype, status=final, doi="", url="",
                                     notes="[DEMO DATA] Fictional submission.",
                                     submitted_at=steps.get("submitted"),
                                     decision_at=steps.get("accepted"),
                                     published_at=steps.get("published"),
                                     created_at=start, updated_at=max(steps.values(), default=start))
        if created:
            prev = "draft"
            for s in path:
                db.add(PublicationStatusEvent(submission_id=sub.id, actor_user_id=owner, from_status=prev,
                                              to_status=s, note="[DEMO] Status update.", created_at=steps[s]))
                inserted[("publication_status_event", name[owner])] += 1
                prev = s
            if "submitted" in path:
                db.add(PublicationRevision(submission_id=sub.id, revision_number=1,
                                           notes="[DEMO] Initial submission.", submitted_at=steps["submitted"],
                                           created_by_user_id=owner, created_at=steps["submitted"]))
                inserted[("publication_revision", name[owner])] += 1
            db.flush()

    # ------------------------------------------------------------------ search history
    searches = {
        RIYA: ["code-mixed question answering", "multilingual retrieval", "natural language processing faculty"],
        ADITYA: ["medical image segmentation", "computer vision internship", "u-net"],
        PRIYA: ["generative ai education", "prompt robustness"],
        AISHA: ["weak supervision segmentation"],
        ROHAN: ["fair recommender evaluation", "explainable recommendations"],
    }
    for uid, queries in searches.items():
        for i, qtext in enumerate(queries):
            get_or_create(db, SearchHistory, "search_history", name[uid],
                          {"user_id": uid, "query": qtext}, created_at=ago(6 - i))

    # ------------------------------------------------------------------ roadmap progress (server-computed skills)
    for student, fac in ((RIYA, PRIYA), (ADITYA, AISHA)):
        profile = db.query(StudentProfile).filter_by(user_id=student).one()
        r = faculty_researcher[fac]
        roadmap = build_student_roadmap(
            researcher={"researcher_id": r.id, "name": r.name, "department": r.department},
            skill_data=calculate_skill_gap(profile.skills, r),
            completed_milestones=set())
        plans = [x for x in json.loads(json.dumps(roadmap, default=str)).get("roadmap", roadmap.get("skills", []))
                 if isinstance(x, dict) and "skill" in x and x.get("milestones")] \
            if isinstance(roadmap, dict) else []
        if not plans:
            for value in roadmap.values():
                if isinstance(value, list) and value and isinstance(value[0], dict) and "skill" in value[0] and "milestones" in value[0]:
                    plans = value
                    break
        for plan in plans[:2]:
            for idx in range(min(2, len(plan["milestones"]))):
                get_or_create(db, RoadmapProgress, "roadmap_progress", name[student],
                              {"user_id": student, "researcher_id": r.id, "skill": plan["skill"],
                               "milestone_index": idx},
                              is_completed=True, updated_at=ago(3 - idx))

    # ------------------------------------------------------------------ research intelligence clusters
    if db.query(ResearchClusterRun).count() == 0:
        from app.services.research_intelligence import rebuild_clusters
        # rebuild_clusters commits on its own; keep it inside this seed's single
        # transaction so a dry run (or a later failure) rolls it back too.
        # actor=None: the rebuild is a system action, so its audit event and run
        # must not be attributed to a person who did not perform it.
        real_commit = db.commit
        db.commit = db.flush
        try:
            result = rebuild_clusters(db, actor=None, use_semantic=False)
        finally:
            db.commit = real_commit
        inserted[("research_cluster_run", "system")] += 1
        inserted[("research_cluster_assignment", "system")] += sum(
            len(c.get("researchers", c.get("members", []))) for c in result.get("clusters", [])) or 0

    db.flush()
    if user_fingerprint() != users_before:
        raise SystemExit("User records changed during the seed - aborting")

    report = {
        "mode": "COMMIT" if args.commit else "DRY RUN (rolled back)",
        "inserted": {f"{k[0]} | {k[1]}": v for k, v in sorted(inserted.items())},
        "inserted_total": sum(inserted.values()),
        "filled_empty_fields": {f"{k[0]} | {k[1]}": v for k, v in sorted(updated.items())},
        "users_unchanged": True,
    }
    if args.commit:
        db.commit()
    else:
        db.rollback()
    print(json.dumps(report, indent=1))
finally:
    db.close()
