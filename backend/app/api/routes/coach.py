from functools import wraps

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import EloHistory, Streak, User, UserFocus
from app.services import coach as coach_service

router = APIRouter(prefix="/coach", tags=["coach"])


def _handle_db_error(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except (psycopg2.Error, RuntimeError):
            raise HTTPException(
                status_code=503,
                detail="Research database is temporarily unavailable. Coach features will return once the database is reachable.",
            )
    return wrapper


def _find_platform_user(db: Session, cf_handle: str) -> User | None:
    normalized = (cf_handle or "").strip().lower()
    if not normalized:
        return None
    return (
        db.query(User)
        .filter(func.lower(User.cf_handle) == normalized)
        .first()
    )


def _fetch_focus_progress(db: Session, cf_handle: str) -> list[dict]:
    user = _find_platform_user(db, cf_handle)
    if not user:
        return []
    records = (
        db.query(UserFocus)
        .filter(UserFocus.user_id == user.id)
        .all()
    )
    return [
        {
            "tag": r.tag,
            "practice_count": r.practice_count,
            "last_practiced_at": r.last_practiced_at.isoformat() if r.last_practiced_at else None,
        }
        for r in records
    ]


def _platform_profile(db: Session, cf_handle: str) -> dict | None:
    user = _find_platform_user(db, cf_handle)
    if not user:
        return None
    focus = _fetch_focus_progress(db, cf_handle)
    recent_duels = (
        db.query(EloHistory)
        .filter(EloHistory.user_id == user.id)
        .order_by(EloHistory.created_at.desc())
        .limit(10)
        .all()
    )
    streak = (
        db.query(Streak)
        .filter(Streak.user_id == user.id)
        .first()
    )
    recent_results = [entry.result for entry in recent_duels]
    recent_delta_sum = sum(entry.delta for entry in recent_duels)
    recent_win_rate = (
        round(sum(1 for result in recent_results if result == "win") / len(recent_results), 2)
        if recent_results
        else None
    )
    return {
        "user_id": user.id,
        "username": user.username,
        "cf_handle": user.cf_handle,
        "current_rating": user.cf_rating or user.elo or 1200,
        "platform_elo": user.elo or 1200,
        "duel_wins": user.duel_wins or 0,
        "duel_losses": user.duel_losses or 0,
        "xp": user.xp or 0,
        "focus_progress": focus,
        "recent_results": recent_results,
        "recent_duel_count": len(recent_results),
        "recent_delta_sum": recent_delta_sum,
        "recent_win_rate": recent_win_rate,
        "current_streak": streak.current_count if streak else 0,
        "longest_streak": streak.longest_count if streak else 0,
        "streak_shields": streak.shields_remaining if streak else 0,
    }


@router.get("/skill-graph")
@_handle_db_error
def skill_graph(limit: int = Query(default=100, ge=10, le=500)):
    return coach_service.get_skill_graph_data(limit=limit)


@router.get("/health")
def health():
    return coach_service.get_health()


@router.get("/research/overview")
@_handle_db_error
def research_overview():
    return coach_service.get_research_overview()


@router.get("/research/findings")
@_handle_db_error
def research_findings(
    category: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    return coach_service.get_research_findings(category=category, limit=limit)


@router.get("/research/hypotheses")
@_handle_db_error
def research_hypotheses(limit: int = Query(default=20, ge=1, le=100)):
    return coach_service.get_research_hypotheses(limit=limit)


@router.get("/research/categories")
@_handle_db_error
def research_categories():
    return coach_service.get_research_categories()


@router.get("/{cf_handle}/summary")
@_handle_db_error
def coach_summary(cf_handle: str, db: Session = Depends(get_db)):
    profile = _platform_profile(db, cf_handle)
    result = coach_service.get_coach_summary(
        cf_handle,
        focus_progress=(profile or {}).get("focus_progress"),
        platform_profile=profile,
    )
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=result.get("error", "user not found"))
    return result


@router.get("/{cf_handle}/skills")
@_handle_db_error
def skill_analysis(cf_handle: str, db: Session = Depends(get_db)):
    profile = _platform_profile(db, cf_handle)
    result = coach_service.get_skill_analysis(
        cf_handle,
        focus_progress=(profile or {}).get("focus_progress"),
        platform_profile=profile,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{cf_handle}/learning-path")
@_handle_db_error
def learning_path(cf_handle: str, db: Session = Depends(get_db)):
    profile = _platform_profile(db, cf_handle)
    result = coach_service.get_learning_path_recommendation(
        cf_handle,
        platform_profile=profile,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{cf_handle}/breakthrough")
@_handle_db_error
def breakthrough_analysis(cf_handle: str, db: Session = Depends(get_db)):
    profile = _platform_profile(db, cf_handle)
    result = coach_service.get_breakthrough_analysis(
        cf_handle,
        platform_profile=profile,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{cf_handle}/focus")
def focus_progress(cf_handle: str, db: Session = Depends(get_db)):
    user = _find_platform_user(db, cf_handle)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    records = (
        db.query(UserFocus)
        .filter(UserFocus.user_id == user.id)
        .order_by(UserFocus.last_practiced_at.desc().nullslast())
        .all()
    )
    return {
        "cf_handle": cf_handle,
        "focus_progress": [
            {"tag": r.tag, "practice_count": r.practice_count, "last_practiced_at": r.last_practiced_at.isoformat() if r.last_practiced_at else None}
            for r in records
        ],
    }


@router.get("/{cf_handle}/problems")
@_handle_db_error
def recommended_problems(
    cf_handle: str,
    count: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    profile = _platform_profile(db, cf_handle)
    result = coach_service.get_recommended_problems(
        cf_handle,
        count=count,
        platform_profile=profile,
    )
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=result.get("error", "user not found"))
    return result
