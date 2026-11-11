import logging
import os

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .database import (
    Base,
    SchemaRevisionError,
    engine,
    get_db,
    verify_schema_revision,
)
from . import models
from .middleware import RequestBodyLimitMiddleware, SecurityHeadersMiddleware
from .api import admin as admin_api
from .api.analytics import router as analytics_router
from .api.research_intelligence import router as research_intelligence_router
from .api.verification import router as verification_router
from .api.researchers import router as researcher_router
from .api.search_history import router as search_history_router
from .api.students import router as student_router
from .api.auth import router as auth_router
from .api.profiles import router as profile_router
from .api.roadmap import router as roadmap_router
from .api.collaboration import router as collaboration_router
from .api.opportunities import router as opportunity_router
from .api.workspaces import router as workspace_router
from .api.teams import router as team_router
from .api.literature import router as literature_router
from .api.proposals import router as proposal_router
from .api.theses import router as thesis_router
from .api.publications import router as publication_router
from .api.institutions import router as institution_router
from .api.labs import router as lab_router
from .services import recommendation
from .services.rate_limit import is_rate_limit_ready


logger = logging.getLogger("researchtwin.database")
readiness_logger = logging.getLogger("researchtwin.readiness")


# --------------------------------------------------
# DATABASE INITIALIZATION
# --------------------------------------------------

# PostgreSQL schemas are created only by reviewed Alembic migrations; local
# SQLite keeps create_all so development and the test suite stay simple.
if engine.dialect.name == "sqlite":
    Base.metadata.create_all(bind=engine)


# --------------------------------------------------
# FASTAPI APPLICATION
# --------------------------------------------------

app = FastAPI(
    title="ResearchTwin API",
    description="Backend API for the AI-powered Researcher-Student Collaboration System",
    version="1.0.0"
)

app.add_middleware(RequestBodyLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(["http://127.0.0.1:5500", "http://localhost:5500"] + [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "").split(",") if origin.strip()])),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
# --------------------------------------------------
# ROUTERS
# --------------------------------------------------

# The verification router is registered before the researchers router so the
# static /researchers/verification-summary path is not read as a researcher id.
app.include_router(verification_router)
app.include_router(analytics_router)
app.include_router(research_intelligence_router)
app.include_router(researcher_router)
app.include_router(search_history_router)
app.include_router(student_router)
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(roadmap_router)
app.include_router(collaboration_router)
app.include_router(workspace_router)
app.include_router(team_router)
app.include_router(opportunity_router)
app.include_router(literature_router)
app.include_router(proposal_router)
app.include_router(thesis_router)
app.include_router(publication_router)
app.include_router(institution_router)
app.include_router(lab_router)
app.include_router(admin_api.router)


# --------------------------------------------------
# DATABASE FAILURE HANDLING
# --------------------------------------------------

@app.exception_handler(recommendation.RecommendationBusy)
async def recommendation_busy_handler(
    request: Request, exc: recommendation.RecommendationBusy
):
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Recommendation service is at capacity. Please retry shortly."
        },
        headers={"Retry-After": str(exc.retry_after)},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    # Constraint names and SQL stay in the log; clients get a stable conflict.
    logger.warning(
        "Integrity conflict while handling %s %s (%s)",
        request.method,
        request.url.path,
        type(exc.orig).__name__,
    )
    return JSONResponse(
        status_code=409,
        content={"detail": "Request conflicts with existing data"},
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    logger.error(
        "Database error while handling %s %s (%s)",
        request.method,
        request.url.path,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database unavailable"},
    )


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
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("Health check database probe failed (%s)", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy"},
        )

    return {
        "status": "healthy"
    }


# --------------------------------------------------
# READINESS CHECK
# --------------------------------------------------

@app.get("/ready")
@app.get("/readiness")
def readiness_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        readiness_logger.error(
            "Readiness database probe failed (%s)", type(exc).__name__
        )
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready"},
        )

    try:
        verify_schema_revision(db)
    except SchemaRevisionError as exc:
        readiness_logger.error("Readiness schema revision check failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready"},
        )

    try:
        recommendation.verify_serving_artifacts()
    except recommendation.RecommendationError as exc:
        readiness_logger.error(
            "Readiness model artifact check failed: %s", exc
        )
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready"},
        )

    if not is_rate_limit_ready(db):
        readiness_logger.error(
            "Readiness request-protection configuration is incomplete"
        )
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready"},
        )

    return {
        "status": "ready"
    }
