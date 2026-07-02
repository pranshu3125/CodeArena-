import json
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db


class UpdateRoleRequest(BaseModel):
    role: str


class ToggleSuspendRequest(BaseModel):
    suspended: bool = True
from app.models import (
    AsyncChallenge,
    Duel,
    DuelParticipant,
    DuelStep,
    EloHistory,
    FriendRoom,
    MatchmakingQueueEntry,
    Quest,
    QuestProgress,
    ReplayEvent,
    Streak,
    Submission,
    User,
)
from app.api.routes.auth import _get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])

RBAC_ROLES = ("moderator", "admin", "superadmin")


def _require_role(*minimum_roles: str):
    """Dependency factory: checks that the current user has one of the given roles."""

    def _check(current_user: User = Depends(_get_current_user)) -> User:
        if current_user.role not in minimum_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        if current_user.is_suspended:
            raise HTTPException(status_code=403, detail="Account is suspended")
        return current_user

    return _check


# ──────────────────────────────────────────────
#  DASHBOARD / OVERVIEW
# ──────────────────────────────────────────────


@router.get("/overview")
def admin_overview(
    admin: User = Depends(_require_role("moderator", "admin", "superadmin")),
    db: Session = Depends(get_db),
):
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_duels = db.query(func.count(Duel.id)).scalar() or 0
    active_duels = db.query(func.count(Duel.id)).filter(Duel.status == "active").scalar() or 0
    total_submissions = db.query(func.count(Submission.id)).scalar() or 0
    users_in_queue = db.query(func.count(MatchmakingQueueEntry.id)).scalar() or 0
    total_quests = db.query(func.count(Quest.id)).scalar() or 0

    # Users registered in the last 24h
    since = datetime.utcnow() - timedelta(hours=24)
    new_users_24h = (
        db.query(func.count(User.id)).filter(User.created_at >= since).scalar() or 0
    )

    # Duels in the last 24h
    duels_24h = (
        db.query(func.count(Duel.id)).filter(Duel.created_at >= since).scalar() or 0
    )

    # Top 5 highest ELO
    top_users = (
        db.query(User)
        .order_by(User.elo.desc())
        .limit(5)
        .all()
    )

    return {
        "total_users": total_users,
        "total_duels": total_duels,
        "active_duels": active_duels,
        "total_submissions": total_submissions,
        "users_in_queue": users_in_queue,
        "total_quests": total_quests,
        "new_users_24h": new_users_24h,
        "duels_24h": duels_24h,
        "top_users": [
            {
                "id": u.id,
                "username": u.username,
                "elo": u.elo,
                "role": u.role,
                "cf_handle": u.cf_handle,
            }
            for u in top_users
        ],
    }


# ──────────────────────────────────────────────
#  USERS
# ──────────────────────────────────────────────


@router.get("/users")
def list_users(
    q: Optional[str] = Query(None, description="Search username, email, or cf_handle"),
    role: Optional[str] = Query(None, description="Filter by role"),
    sort: str = Query("created_at", description="Sort field"),
    order: str = Query("desc", description="asc or desc"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(_require_role("moderator", "admin", "superadmin")),
    db: Session = Depends(get_db),
):
    query = db.query(User)

    if q:
        like = f"%{q}%"
        query = query.filter(
            User.username.ilike(like) | User.email.ilike(like) | User.cf_handle.ilike(like)
        )
    if role:
        query = query.filter(User.role == role)

    sort_col = getattr(User, sort, User.created_at)
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = query.count()
    rows = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "cf_handle": u.cf_handle,
                "elo": u.elo,
                "role": u.role,
                "is_suspended": u.is_suspended,
                "duel_wins": u.duel_wins,
                "duel_losses": u.duel_losses,
                "xp": u.xp,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in rows
        ],
    }


@router.get("/users/{user_id}")
def get_user_detail(
    user_id: str,
    admin: User = Depends(_require_role("moderator", "admin", "superadmin")),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    streak = db.query(Streak).filter(Streak.user_id == user.id).first()
    elo_history = (
        db.query(EloHistory)
        .filter(EloHistory.user_id == user.id)
        .order_by(EloHistory.created_at.desc())
        .limit(100)
        .all()
    )
    recent_duels = (
        db.query(EloHistory)
        .filter(EloHistory.user_id == user.id)
        .order_by(EloHistory.created_at.desc())
        .limit(20)
        .all()
    )
    duel_ids = [h.duel_id for h in recent_duels]
    duels_map = {}
    if duel_ids:
        for d in db.query(Duel).filter(Duel.id.in_(duel_ids)).all():
            duels_map[d.id] = d

    submissions = (
        db.query(Submission)
        .filter(Submission.user_id == user.id)
        .order_by(Submission.created_at.desc())
        .limit(50)
        .all()
    )

    quest_progress = (
        db.query(QuestProgress)
        .filter(QuestProgress.user_id == user.id)
        .order_by(QuestProgress.created_at.desc())
        .all()
    )

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "cf_handle": user.cf_handle,
        "cf_rating": user.cf_rating,
        "cf_rank": user.cf_rank,
        "solved_count": user.solved_count,
        "elo": user.elo,
        "role": user.role,
        "is_suspended": user.is_suspended,
        "duel_wins": user.duel_wins,
        "duel_losses": user.duel_losses,
        "xp": user.xp,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "streak": {
            "current_count": streak.current_count if streak else 0,
            "longest_count": streak.longest_count if streak else 0,
            "shields_remaining": streak.shields_remaining if streak else 0,
        },
        "elo_history": [
            {
                "elo_before": h.elo_before,
                "elo_after": h.elo_after,
                "delta": h.delta,
                "result": h.result,
                "opponent_id": h.opponent_id,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in elo_history
        ],
        "recent_duels": [
            {
                "id": h.duel_id,
                "result": h.result,
                "delta": h.delta,
                "opponent_id": h.opponent_id,
                "status": duels_map.get(h.duel_id).status if duels_map.get(h.duel_id) else None,
                "finished_at": (
                    duels_map.get(h.duel_id).finished_at.isoformat()
                    if duels_map.get(h.duel_id) and duels_map.get(h.duel_id).finished_at
                    else None
                ),
            }
            for h in recent_duels
        ],
        "submissions": [
            {
                "id": s.id,
                "problem_id": s.problem_id,
                "language": s.language,
                "status": s.status,
                "runtime_ms": s.runtime_ms,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in submissions
        ],
        "quest_progress": [
            {
                "quest_id": qp.quest_id,
                "progress_json": qp.progress_json,
                "completed_at": qp.completed_at.isoformat() if qp.completed_at else None,
                "claimed_at": qp.claimed_at.isoformat() if qp.claimed_at else None,
            }
            for qp in quest_progress
        ],
    }


@router.patch("/users/{user_id}/role")
def update_user_role(
    user_id: str,
    body: UpdateRoleRequest,
    admin: User = Depends(_require_role("admin", "superadmin")),
    db: Session = Depends(get_db),
):
    new_role = body.role.strip()
    if new_role not in ("user", "moderator", "admin", "superadmin"):
        raise HTTPException(status_code=422, detail="Invalid role")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if new_role == "superadmin" and admin.role != "superadmin":
        raise HTTPException(status_code=403, detail="Only superadmins can assign superadmin")

    user.role = new_role
    db.commit()
    return {"ok": True, "role": new_role}


@router.patch("/users/{user_id}/suspend")
def toggle_suspend_user(
    user_id: str,
    body: ToggleSuspendRequest,
    admin: User = Depends(_require_role("moderator", "admin", "superadmin")),
    db: Session = Depends(get_db),
):
    suspended = body.suspended
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if admin.role == "moderator" and user.role in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Cannot suspend higher-privilege users")

    user.is_suspended = suspended
    db.commit()
    return {"ok": True, "is_suspended": suspended}


# ──────────────────────────────────────────────
#  DUELS
# ──────────────────────────────────────────────


@router.get("/duels")
def list_duels(
    status: Optional[str] = Query(None, description="Filter by status"),
    q: Optional[str] = Query(None, description="Search by duel ID or problem name"),
    sort: str = Query("created_at"),
    order: str = Query("desc"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(_require_role("moderator", "admin", "superadmin")),
    db: Session = Depends(get_db),
):
    query = db.query(Duel)

    if status:
        query = query.filter(Duel.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(Duel.id.ilike(like) | Duel.problem_name.ilike(like))

    sort_col = getattr(Duel, sort, Duel.created_at)
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = query.count()
    rows = query.offset(offset).limit(limit).all()

    result = []
    for d in rows:
        participant_count = (
            db.query(func.count(DuelParticipant.id))
            .filter(DuelParticipant.duel_id == d.id)
            .scalar() or 0
        )
        result.append(
            {
                "id": d.id,
                "status": d.status,
                "format": d.format,
                "problem_name": d.problem_name,
                "problem_rating": d.problem_rating,
                "participant_count": participant_count,
                "winner_id": d.winner_id,
                "started_at": d.started_at.isoformat() if d.started_at else None,
                "finished_at": d.finished_at.isoformat() if d.finished_at else None,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
        )

    return {"total": total, "offset": offset, "limit": limit, "duels": result}


@router.get("/duels/{duel_id}")
def get_duel_detail(
    duel_id: str,
    admin: User = Depends(_require_role("moderator", "admin", "superadmin")),
    db: Session = Depends(get_db),
):
    duel = db.query(Duel).filter(Duel.id == duel_id).first()
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")

    participants = (
        db.query(DuelParticipant)
        .filter(DuelParticipant.duel_id == duel.id)
        .order_by(DuelParticipant.joined_at.asc())
        .all()
    )
    steps = (
        db.query(DuelStep)
        .filter(DuelStep.duel_id == duel.id)
        .order_by(DuelStep.step_index.asc())
        .all()
    )
    submissions = (
        db.query(Submission)
        .filter(Submission.duel_id == duel.id)
        .order_by(Submission.created_at.desc())
        .all()
    )
    elo_changes = (
        db.query(EloHistory)
        .filter(EloHistory.duel_id == duel.id)
        .all()
    )

    return {
        "id": duel.id,
        "status": duel.status,
        "format": duel.format,
        "time_cap_seconds": duel.time_cap_seconds,
        "host_id": duel.host_id,
        "winner_id": duel.winner_id,
        "problem_id": duel.problem_id,
        "problem_name": duel.problem_name,
        "problem_rating": duel.problem_rating,
        "started_at": duel.started_at.isoformat() if duel.started_at else None,
        "finished_at": duel.finished_at.isoformat() if duel.finished_at else None,
        "created_at": duel.created_at.isoformat() if duel.created_at else None,
        "participants": [
            {
                "user_id": p.user_id,
                "current_rating": p.current_rating,
                "joined_at": p.joined_at.isoformat() if p.joined_at else None,
            }
            for p in participants
        ],
        "steps": [
            {
                "step_index": s.step_index,
                "rating": s.rating,
                "problem_id": s.problem_id,
                "problem_name": s.problem_name,
                "problem_tags": json.loads(s.problem_tags_json) if s.problem_tags_json else [],
                "host_status": s.host_status,
                "opponent_status": s.opponent_status,
            }
            for s in steps
        ],
        "submissions": [
            {
                "id": sub.id,
                "user_id": sub.user_id,
                "problem_id": sub.problem_id,
                "language": sub.language,
                "status": sub.status,
                "runtime_ms": sub.runtime_ms,
                "created_at": sub.created_at.isoformat() if sub.created_at else None,
            }
            for sub in submissions
        ],
        "elo_changes": [
            {
                "user_id": e.user_id,
                "elo_before": e.elo_before,
                "elo_after": e.elo_after,
                "delta": e.delta,
                "result": e.result,
                "opponent_id": e.opponent_id,
            }
            for e in elo_changes
        ],
    }


# ──────────────────────────────────────────────
#  SUBMISSIONS
# ──────────────────────────────────────────────


@router.get("/submissions")
def list_submissions(
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Search by problem_id or user_id"),
    sort: str = Query("created_at"),
    order: str = Query("desc"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(_require_role("moderator", "admin", "superadmin")),
    db: Session = Depends(get_db),
):
    query = db.query(Submission)

    if status:
        query = query.filter(Submission.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(
            Submission.problem_id.ilike(like) | Submission.user_id.ilike(like)
        )

    sort_col = getattr(Submission, sort, Submission.created_at)
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = query.count()
    rows = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "submissions": [
            {
                "id": s.id,
                "user_id": s.user_id,
                "duel_id": s.duel_id,
                "problem_id": s.problem_id,
                "language": s.language,
                "status": s.status,
                "runtime_ms": s.runtime_ms,
                "memory_kb": s.memory_kb,
                "score": s.score,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in rows
        ],
    }


# ──────────────────────────────────────────────
#  RANKINGS (admin curated view)
# ──────────────────────────────────────────────


@router.get("/rankings")
def admin_rankings(
    sort: str = Query("elo", description="elo | wins | xp"),
    order: str = Query("desc"),
    limit: int = Query(100, ge=1, le=500),
    admin: User = Depends(_require_role("moderator", "admin", "superadmin")),
    db: Session = Depends(get_db),
):
    sort_map = {"elo": User.elo, "wins": User.duel_wins, "xp": User.xp}
    sort_col = sort_map.get(sort, User.elo)

    query = db.query(User)
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    rows = query.limit(limit).all()

    return {
        "sort": sort,
        "order": order,
        "rankings": [
            {
                "rank": i + 1,
                "id": u.id,
                "username": u.username,
                "elo": u.elo,
                "role": u.role,
                "duel_wins": u.duel_wins,
                "duel_losses": u.duel_losses,
                "xp": u.xp,
                "cf_handle": u.cf_handle,
                "cf_rating": u.cf_rating,
            }
            for i, u in enumerate(rows)
        ],
    }
