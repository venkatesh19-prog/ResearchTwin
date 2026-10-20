import os
import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from nlp_extractor import extract_keywords_nlp
from recommender import (
    analyze_skill_gap,
    compute_shap_explanation,
    generate_explanation
)

app = FastAPI(title="ResearchTwin API Engine", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STUDENTS_PATH = "students.csv"
RESEARCHERS_PATH = "data/researchers.csv"
MODEL_PATH = "models/researchtwin_logistic.joblib"

FEATURE_COLS = [
    "tfidf_similarity", "semantic_similarity", "research_area_similarity",
    "expertise_similarity", "skill_overlap", "project_similarity",
    "publication_similarity", "department_match"
]

model_pipeline = None


def init_mock_data():
    """Initializes default datasets if missing."""
    if not os.path.exists(STUDENTS_PATH):
        students = [
            {
                "student_id": "S001",
                "name": "Aishwarya",
                "research_areas": "Artificial Intelligence, Machine Learning",
                "expertise": "Deep Learning, NLP",
                "skills": "Python, PyTorch, Transformers, SQL",
                "projects": "ResearchTwin ML Engine",
                "publications": "NLP Research"
            },
            {
                "student_id": "S002",
                "name": "Student 2",
                "research_areas": "Computer Vision, Image Processing",
                "expertise": "CNNs, Object Detection",
                "skills": "Python, OpenCV, TensorFlow",
                "projects": "Vision AI System",
                "publications": "Medical Imaging"
            }
        ]
        pd.DataFrame(students).to_csv(STUDENTS_PATH, index=False)

    os.makedirs(os.path.dirname(RESEARCHERS_PATH), exist_ok=True)
    if not os.path.exists(RESEARCHERS_PATH):
        researchers = [
            {
                "researcher_id": "R001",
                "name": "Dr. Alice Smith",
                "department": "Computer Science & AI",
                "research_areas": "Artificial Intelligence, Natural Language Processing",
                "expertise": "LLMs, Deep Learning, NLP",
                "required_skills": "Python, PyTorch, Transformers",
                "project_description": "Conversational AI and semantic search engines using LLMs."
            },
            {
                "researcher_id": "R002",
                "name": "Dr. Bob Jones",
                "department": "Computer Vision & Medical Imaging",
                "research_areas": "Computer Vision, Deep Learning, Image Processing",
                "expertise": "CNNs, Object Detection",
                "required_skills": "Python, OpenCV, PyTorch, TensorFlow",
                "project_description": "Real-time object detection and diagnostic image segmentation."
            },
            {
                "researcher_id": "R003",
                "name": "Dr. Carol White",
                "department": "Cybersecurity & Networking",
                "research_areas": "Cybersecurity, Network Security, Machine Learning",
                "expertise": "Intrusion Detection",
                "required_skills": "Python, Machine Learning, Linux, Networking",
                "project_description": "ML-based network intrusion detection systems."
            },
            {
                "researcher_id": "R004",
                "name": "Prof. Rajesh Kumar",
                "department": "Data Structures & Analytics",
                "research_areas": "Data Structures, Algorithms, Big Data",
                "expertise": "Advanced DSA, SQL",
                "required_skills": "C++, Java, Python, SQL",
                "project_description": "Optimizing graph algorithms and high-throughput data processing pipelines."
            }
        ]
        pd.DataFrame(researchers).to_csv(RESEARCHERS_PATH, index=False)


@app.on_event("startup")
def startup_event():
    global model_pipeline
    init_mock_data()
    if os.path.exists(MODEL_PATH):
        model_pipeline = joblib.load(MODEL_PATH)


class ProfileUpdateReq(BaseModel):
    student_id: str
    name: Optional[str] = "Student"
    research_areas: str
    expertise: str
    skills: str
    projects: str
    publications: Optional[str] = ""


class ResearcherUpdateReq(BaseModel):
    researcher_id: str
    name: str
    department: str
    research_areas: str
    expertise: str
    required_skills: str
    project_description: str


class MatchReq(BaseModel):
    student_id: str
    top_k: int = 5


class GuidanceReq(BaseModel):
    student_id: str
    researcher_id: str


@app.get("/")
def root():
    return {
        "status": "online",
        "system": "ResearchTwin Engine",
        "model_active": model_pipeline is not None
    }


@app.get("/api/student/profile/{student_id}")
def get_student_profile(student_id: str):
    df = pd.read_csv(STUDENTS_PATH)
    row = df[df["student_id"] == student_id]
    if row.empty:
        return {
            "student_id": student_id,
            "name": "Aishwarya",
            "research_areas": "Artificial Intelligence",
            "expertise": "Machine Learning",
            "skills": "Python, SQL",
            "projects": "ResearchTwin",
            "publications": "None"
        }
    res = row.iloc[0].to_dict()
    res["extracted_keywords"] = extract_keywords_nlp(
        f"{res.get('research_areas', '')} {res.get('skills', '')}"
    )
    return res


@app.post("/api/student/profile/update")
def update_student_profile(req: ProfileUpdateReq):
    df = pd.read_csv(STUDENTS_PATH)
    new_data = req.dict()
    if req.student_id in df["student_id"].values:
        df.loc[df["student_id"] == req.student_id, list(new_data.keys())] = list(new_data.values())
    else:
        df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
    df.to_csv(STUDENTS_PATH, index=False)
    return {
        "status": "success",
        "message": f"Student profile '{req.student_id}' updated and re-indexed!"
    }


@app.get("/api/teachers/search")
def search_teachers(query: Optional[str] = Query(None)):
    df = pd.read_csv(RESEARCHERS_PATH)
    if query:
        words = query.lower().strip().split()

        def match_row(r):
            text = f"{r['name']} {r['department']} {r['research_areas']} {r['expertise']} {r['required_skills']} {r['project_description']}".lower()
            return any(w in text for w in words)

        df = df[df.apply(match_row, axis=1)]

    results = []
    for _, r in df.iterrows():
        req_skills = [s.strip() for s in str(r.get("required_skills", "")).split(",") if s.strip()]
        results.append({
            "researcher_id": r["researcher_id"],
            "name": r["name"],
            "department": r["department"],
            "research_areas": r["research_areas"],
            "expertise": r["expertise"],
            "required_skills": req_skills,
            "project_description": r["project_description"],
            "extracted_topics": extract_keywords_nlp(r["project_description"])
        })
    return {"teachers": results}


@app.post("/api/researcher/profile/update")
def update_researcher_profile(req: ResearcherUpdateReq):
    df = pd.read_csv(RESEARCHERS_PATH)
    new_data = req.dict()
    if req.researcher_id in df["researcher_id"].values:
        df.loc[df["researcher_id"] == req.researcher_id, list(new_data.keys())] = list(new_data.values())
    else:
        df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
    df.to_csv(RESEARCHERS_PATH, index=False)
    return {
        "status": "success",
        "message": f"Researcher profile '{req.researcher_id}' saved!"
    }


@app.post("/recommend")
def recommend_researchers(req: MatchReq):
    students_df = pd.read_csv(STUDENTS_PATH)
    researchers_df = pd.read_csv(RESEARCHERS_PATH)

    student_skills = ["Python", "Machine Learning"]
    if req.student_id in students_df["student_id"].values:
        s_row = students_df[students_df["student_id"] == req.student_id].iloc[0]
        student_skills = [s.strip() for s in str(s_row.get("skills", "")).split(",") if s.strip()]

    results = []
    for _, r_row in researchers_df.head(req.top_k).iterrows():
        req_skills = [s.strip() for s in str(r_row.get("required_skills", "")).split(",") if s.strip()]
        gap_info = analyze_skill_gap(student_skills, req_skills)

        cov = gap_info["skill_coverage_percent"]
        match_score = round(min(98.0, max(50.0, cov + 25.0)), 1)

        explanation = generate_explanation(match_score, gap_info, r_row["name"])
        dummy_feat_vector = np.array([0.8, 0.85, 0.7, 0.75, cov / 100.0, 0.6, 0.5, 1.0])
        shap_explain = compute_shap_explanation(model_pipeline, dummy_feat_vector, FEATURE_COLS)

        results.append({
            "researcher_id": r_row["researcher_id"],
            "researcher_name": r_row["name"],
            "department": r_row["department"],
            "research_areas": r_row["research_areas"],
            "match_score": match_score,
            "skill_gap": gap_info,
            "explanation": explanation,
            "shap_explanation": shap_explain
        })

    return {"student_id": req.student_id, "recommendations": results}


@app.post("/api/request-guidance")
def request_guidance(req: GuidanceReq):
    return {
        "status": "success",
        "message": f"Research guidance application submitted for Student '{req.student_id}' to Faculty '{req.researcher_id}'."
    }