from fastapi import FastAPI

from .database import Base, engine
from . import models

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