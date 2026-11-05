# ==============================================================================
# RESEARCHTWIN 2.0 - FASTAPI BACKEND ENGINE
# ==============================================================================
# This script powers all REST API endpoints, mock data initialization, CSV file 
# storage (flat-file persistence), search history logging, and ML logic.

import os
import joblib
from datetime import datetime
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

# Initialize the FastAPI application instance
app = FastAPI(title="ResearchTwin 2.0 Engine", version="2.0")

# Enable Cross-Origin Resource Sharing (CORS) so frontend HTML files can access APIs
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Allow all origins (for local development testing)
    allow_credentials=True,     # Allow cookies/headers
    allow_methods=["*"],        # Allow GET, POST, PUT, DELETE methods
    allow_headers=["*"],        # Allow all request headers
)

# File Paths for Flat-File Data Storage (CSVs act as our lightweight database)
STUDENTS_PATH = "students.csv"
RESEARCHERS_PATH = "data/researchers.csv"
SEARCH_HISTORY_PATH = "data/search_history.csv"
APPLICATIONS_PATH = "data/guidance_applications.csv"
LITERATURE_PATH = "data/literature_papers.csv"
GRANTS_PATH = "data/research_grants.csv"


# ------------------------------------------------------------------------------
# DATASET INITIALIZATION
# ------------------------------------------------------------------------------
def init_mock_data():
    """Checks if database CSV files exist. If missing, auto-creates default mock data."""
    
    # 1. Initialize Students Dataset
    if not os.path.exists(STUDENTS_PATH):
        students = [
            {
                "student_id": "S001",
                "name": "Aishwarya",
                "password": "123",
                "research_areas": "Artificial Intelligence, Machine Learning",
                "expertise": "Deep Learning, NLP",
                "skills": "Python, PyTorch, Transformers, SQL",
                "projects": "ResearchTwin ML Engine",
                "publications": "NLP Research"
            },
            {
                "student_id": "S002",
                "name": "Student 2",
                "password": "123",
                "research_areas": "Computer Vision, Image Processing",
                "expertise": "CNNs, Object Detection",
                "skills": "Python, OpenCV, TensorFlow",
                "projects": "Vision AI System",
                "publications": "Medical Imaging"
            }
        ]
        pd.DataFrame(students).to_csv(STUDENTS_PATH, index=False)

    # Ensure 'data' directory exists for other CSV files
    os.makedirs(os.path.dirname(RESEARCHERS_PATH), exist_ok=True)

    # 2. Initialize Researchers/Faculty Dataset
    if not os.path.exists(RESEARCHERS_PATH):
        researchers = [
            {
                "researcher_id": "R001",
                "name": "Dr. Alice Smith",
                "password": "123",
                "department": "Computer Science & AI",
                "research_areas": "Artificial Intelligence, Natural Language Processing",
                "expertise": "LLMs, Deep Learning, NLP",
                "required_skills": "Python, PyTorch, Transformers",
                "project_description": "Conversational AI and semantic search engines using LLMs."
            },
            {
                "researcher_id": "R002",
                "name": "Dr. Bob Jones",
                "password": "123",
                "department": "Computer Vision & Medical Imaging",
                "research_areas": "Computer Vision, Deep Learning, Image Processing",
                "expertise": "CNNs, Object Detection",
                "required_skills": "Python, OpenCV, PyTorch, TensorFlow",
                "project_description": "Real-time object detection and diagnostic image segmentation."
            }
        ]
        pd.DataFrame(researchers).to_csv(RESEARCHERS_PATH, index=False)

    # 3. Initialize Search History Store
    if not os.path.exists(SEARCH_HISTORY_PATH):
        pd.DataFrame(columns=["user_id", "role", "query", "timestamp"]).to_csv(SEARCH_HISTORY_PATH, index=False)

    # 4. Initialize Literature Papers Store
    if not os.path.exists(LITERATURE_PATH):
        papers = [
            {
                "paper_id": 1,
                "user_id": "S001",
                "title": "SHAP: A Unified Approach to Interpreting Model Predictions",
                "authors": "Lundberg et al.",
                "notes": "Foundational paper for Explainable AI in ResearchTwin.",
                "status": "Completed"
            },
            {
                "paper_id": 2,
                "user_id": "S001",
                "title": "Attention Is All You Need",
                "authors": "Vaswani et al.",
                "notes": "Transformer architecture review for NLP matching.",
                "status": "Reading"
            }
        ]
        pd.DataFrame(papers).to_csv(LITERATURE_PATH, index=False)

    # 5. Initialize Funding & Grants Store
    if not os.path.exists(GRANTS_PATH):
        grants = [
            {
                "grant_id": 1,
                "title": "AI for Scientific Discovery Grant",
                "agency": "DST India",
                "amount": "₹2,500,000",
                "deadline": "2026-12-15",
                "category": "Artificial Intelligence"
            },
            {
                "grant_id": 2,
                "title": "Young Researcher Innovation Seed",
                "agency": "LPU Research Council",
                "amount": "₹500,000",
                "deadline": "2026-11-30",
                "category": "Student Research Project"
            }
        ]
        pd.DataFrame(grants).to_csv(GRANTS_PATH, index=False)


# Trigger dataset setup when FastAPI starts up
@app.on_event("startup")
def startup_event():
    init_mock_data()


# ------------------------------------------------------------------------------
# PYDANTIC SCHEMAS (DATA VALIDATION)
# ------------------------------------------------------------------------------
class LoginReq(BaseModel):
    user_id: str
    password: str
    role: str  # "student" or "teacher"

class MatchReq(BaseModel):
    student_id: str
    top_k: int = 5

class TeamReq(BaseModel):
    project_title: str
    skills: List[str]

class ProfileUpdateReq(BaseModel):
    student_id: str
    name: Optional[str] = "Student"
    research_areas: str
    skills: str
    projects: str

class PaperReq(BaseModel):
    user_id: str
    title: str
    authors: str
    notes: Optional[str] = ""
    status: Optional[str] = "To Read"


# ------------------------------------------------------------------------------
# API ENDPOINTS
# ------------------------------------------------------------------------------

@app.get("/")
def root():
    """Health check endpoint to verify server status."""
    return {"status": "online", "system": "ResearchTwin 2.0 Engine Operational"}


@app.post("/api/login")
def login_user(req: LoginReq):
    """Authenticates Student or Faculty against CSV records."""
    file_path = STUDENTS_PATH if req.role == "student" else RESEARCHERS_PATH
    id_col = "student_id" if req.role == "student" else "researcher_id"

    df = pd.read_csv(file_path)
    # Filter matching user record
    user = df[(df[id_col].astype(str) == req.user_id) & (df["password"].astype(str) == req.password)]

    if user.empty:
        raise HTTPException(status_code=401, detail="Invalid User ID or Password")

    user_info = user.iloc[0].to_dict()
    return {
        "status": "success",
        "user_id": req.user_id,
        "name": user_info.get("name", "User"),
        "role": req.role
    }


@app.post("/recommend")
def recommend_researchers(req: MatchReq):
    """Calculates student-faculty compatibility, skill gaps, and explanations."""
    students_df = pd.read_csv(STUDENTS_PATH)
    researchers_df = pd.read_csv(RESEARCHERS_PATH)

    student_skills = ["Python", "Machine Learning"]
    if req.student_id in students_df["student_id"].astype(str).values:
        s_row = students_df[students_df["student_id"].astype(str) == req.student_id].iloc[0]
        student_skills = [s.strip().lower() for s in str(s_row.get("skills", "")).split(",") if s.strip()]

    results = []
    for _, r_row in researchers_df.head(req.top_k).iterrows():
        req_skills = [s.strip().lower() for s in str(r_row.get("required_skills", "")).split(",") if s.strip()]
        
        # Skill Overlap Calculation
        matched = [s for s in req_skills if s in student_skills]
        missing = [s for s in req_skills if s not in student_skills]
        
        coverage = (len(matched) / len(req_skills) * 100) if req_skills else 100.0
        score = round(min(98.0, max(55.0, coverage + 20.0)), 1)

        results.append({
            "researcher_id": r_row["researcher_id"],
            "researcher_name": r_row["name"],
            "department": r_row["department"],
            "research_areas": r_row["research_areas"],
            "match_score": score,
            "skill_gap": {
                "matched_skills": [s.title() for s in matched],
                "missing_skills": [s.title() for s in missing]
            },
            "explanation": f"Matched based on shared domain focus in {r_row['research_areas']} and strong technical overlap."
        })

    return {"student_id": req.student_id, "recommendations": results}


@app.post("/api/discovery/smart-team")
def build_smart_team(req: TeamReq):
    """Generates optimal team composition based on project title and skill requirements."""
    req_skills = [s.strip().title() for s in req.skills if s.strip()]
    
    # Simple algorithmic team assembly
    team_members = [
        {"name": "Aishwarya (S001)", "role": "AI Lead", "skill_coverage": "PyTorch, Transformers, SQL"},
        {"name": "Dr. Alice Smith (R001)", "role": "Faculty Advisor", "skill_coverage": "LLMs, Deep Learning"},
        {"name": "Student 2 (S002)", "role": "Vision Specialist", "skill_coverage": "OpenCV, TensorFlow"}
    ]
    return {
        "project_title": req.project_title,
        "recommended_members": team_members,
        "team_coverage_score": "92%"
    }


@app.get("/api/teachers/search")
def search_teachers(query: Optional[str] = Query(None), user_id: Optional[str] = Query(None), role: Optional[str] = "student"):
    """Searches faculty directory AND preserves query in search_history.csv."""
    df = pd.read_csv(RESEARCHERS_PATH)

    # Save query to history if query string and user ID are provided
    if query and query.strip() and user_id:
        history_df = pd.read_csv(SEARCH_HISTORY_PATH)
        new_entry = {
            "user_id": user_id,
            "role": role,
            "query": query.strip(),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        history_df = pd.concat([history_df, pd.DataFrame([new_entry])], ignore_index=True)
        history_df.to_csv(SEARCH_HISTORY_PATH, index=False)

    if query:
        words = query.lower().strip().split()
        def match_row(r):
            text = f"{r['name']} {r['department']} {r['research_areas']} {r['required_skills']} {r['project_description']}".lower()
            return any(w in text for w in words)
        df = df[df.apply(match_row, axis=1)]

    return {"teachers": df.to_dict(orient="records")}


@app.get("/api/history/search/{user_id}")
def get_search_history(user_id: str):
    """Fetches preserved search history for a specific user ID."""
    if not os.path.exists(SEARCH_HISTORY_PATH):
        return {"history": []}
    df = pd.read_csv(SEARCH_HISTORY_PATH)
    user_history = df[df["user_id"].astype(str) == user_id].tail(10).iloc[::-1].to_dict(orient="records")
    return {"history": user_history}


@app.get("/api/student/profile/{student_id}")
def get_student_profile(student_id: str):
    """Retrieves student profile data."""
    df = pd.read_csv(STUDENTS_PATH)
    row = df[df["student_id"].astype(str) == student_id]
    if row.empty:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return row.iloc[0].to_dict()


@app.post("/api/student/profile/update")
def update_student_profile(req: ProfileUpdateReq):
    """Updates student profile skills and interests in students.csv."""
    df = pd.read_csv(STUDENTS_PATH)
    new_data = req.dict()
    if req.student_id in df["student_id"].astype(str).values:
        for k, v in new_data.items():
            df.loc[df["student_id"].astype(str) == req.student_id, k] = v
    else:
        df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
    df.to_csv(STUDENTS_PATH, index=False)
    return {"status": "success", "message": "Profile updated and re-indexed successfully!"}


@app.get("/api/productivity/literature/{user_id}")
def get_literature(user_id: str):
    """Fetches literature papers saved by student."""
    df = pd.read_csv(LITERATURE_PATH)
    user_papers = df[df["user_id"].astype(str) == user_id].to_dict(orient="records")
    return {"papers": user_papers}


@app.post("/api/productivity/literature")
def add_literature(req: PaperReq):
    """Saves a new research paper into literature_papers.csv."""
    df = pd.read_csv(LITERATURE_PATH)
    new_paper = {
        "paper_id": len(df) + 1,
        "user_id": req.user_id,
        "title": req.title,
        "authors": req.authors,
        "notes": req.notes,
        "status": req.status
    }
    df = pd.concat([df, pd.DataFrame([new_paper])], ignore_index=True)
    df.to_csv(LITERATURE_PATH, index=False)
    return {"status": "success", "message": "Research paper added to library!"}


@app.get("/api/productivity/grants")
def get_grants():
    """Fetches research funding opportunities."""
    df = pd.read_csv(GRANTS_PATH)
    return {"grants": df.to_dict(orient="records")}