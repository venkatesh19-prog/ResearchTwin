"""Research network, clustering, topic, trend and knowledge-graph APIs."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import ClusterRebuildRequest, TopicPredictionRequest
from ..services import research_intelligence
from ..services.rate_limit import (
    NETWORK_MAX,
    NETWORK_WINDOW_SECONDS,
    RECOMMENDATION_MAX,
    RECOMMENDATION_WINDOW_SECONDS,
    enforce_rate_limit,
)
from .deps import get_current_user, require_admin


router = APIRouter(
    prefix="/research-intelligence",
    tags=["Research Intelligence"],
)


def _http_error(exc: research_intelligence.ResearchIntelligenceError):
    raise HTTPException(
        status_code=exc.status_code,
        detail=str(exc),
    ) from exc


@router.get("/network")
def get_research_network(
    http_request: Request,
    min_similarity: float = Query(default=0.1, ge=0.0, le=1.0),
    max_edges: int = Query(default=200, ge=1, le=1000),
    department: str | None = Query(default=None, max_length=150),
    include_isolated: bool = Query(default=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(
        db,
        http_request,
        scope="research-network",
        identities=(("user", str(user.id)),),
        limit=NETWORK_MAX,
        window_seconds=NETWORK_WINDOW_SECONDS,
    )

    try:
        with research_intelligence.network_slot():
            return research_intelligence.network_graph(
                db,
                min_similarity=min_similarity,
                max_edges=max_edges,
                department=department,
                include_isolated=include_isolated,
            )
    except research_intelligence.ResearchIntelligenceBusy as exc:
        raise HTTPException(
            status_code=429,
            detail="Research network analysis is busy. Please retry shortly.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


@router.get("/clusters")
def get_research_clusters(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return research_intelligence.cluster_state(db)


@router.post("/clusters/rebuild")
def rebuild_research_clusters(
    payload: ClusterRebuildRequest,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return research_intelligence.rebuild_clusters(
            db,
            actor=user,
            min_similarity=payload.min_similarity,
            use_semantic=payload.use_semantic,
        )
    except research_intelligence.ResearchIntelligenceError as exc:
        _http_error(exc)


@router.post("/topics/predict")
def predict_research_topics(
    payload: TopicPredictionRequest,
    http_request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(
        db,
        http_request,
        scope="research-topic-prediction",
        identities=(("user", str(user.id)),),
        limit=RECOMMENDATION_MAX,
        window_seconds=RECOMMENDATION_WINDOW_SECONDS,
    )

    try:
        return research_intelligence.predict_topics(
            db,
            text=payload.text,
            top_k=payload.top_k,
        )
    except research_intelligence.ResearchIntelligenceError as exc:
        _http_error(exc)


@router.get("/trends")
def get_research_trends(
    top_k: int = Query(default=10, ge=1, le=50),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return research_intelligence.trend_summary(db, top_k=top_k)


@router.get("/knowledge-graph")
def get_research_knowledge_graph(
    verified_only: bool = Query(default=False),
    researcher_limit: int = Query(default=200, ge=1, le=500),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return research_intelligence.knowledge_graph(
        db,
        verified_only=verified_only,
        researcher_limit=researcher_limit,
    )
