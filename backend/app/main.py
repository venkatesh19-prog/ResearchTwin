import os
from fastapi import FastAPI

from .database import Base, engine
from . import models
from fastapi.middleware.cors import CORSMiddleware
from .api.researchers import router as researcher_router
from .api.students import router as student_router


# --------------------------------------------------
# DATABASE INITIALIZATION
# --------------------------------------------------

Base.metadata.create_all(bind=engine)


# --------------------------------------------------
# FASTAPI APPLICATION
# --------------------------------------------------

app = FastAPI(
    title="ResearchTwin API",
    description="Backend API for the AI-powered Researcher-Student Collaboration System",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(["http://127.0.0.1:5500", "http://localhost:5500"] + [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "").split(",") if origin.strip()])),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
# --------------------------------------------------
# ROUTERS
# --------------------------------------------------

app.include_router(researcher_router)
app.include_router(student_router)


# --------------------------------------------------
# ROOT ENDPOINT
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "ResearchTwin API is running",
        "status": "success"
    }


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }