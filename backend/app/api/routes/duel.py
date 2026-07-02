import json
import time
import uuid
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import crud
from app.db import get_db
from app.models import ChatMessage, Duel, DuelParticipant, DuelStep, EloHistory, ReplayEvent, User
from app.schemas import (
    DuelCreate,
    DuelCreateResponse,
    DuelJoin,
    DuelOut,
    DuelParticipantOut,
    DuelStartRequest,
    DuelStartResponse,
    DuelSubmitRequest,
    DuelSubmitResult,
)
from app.services.codeforces import CodeforcesService
from app.services.cf_sync import process_duel_cf, verify_cf_handle
from app.services.duel_completion import complete_duel
from app.services.duel_roles import host_and_opponent, is_duel_host
from app.services.elo import tier_for_elo
from app.api.routes.auth import _get_current_user
from app.services.ws_hub import hub


router = APIRouter(prefix="/duel", tags=["duel"])


# ================= HELPERS =================

def _validate_uuid(value: str, field_name: str) -> None:
    try:
        uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} format")


def iso_utc(dt):
    if dt is None:
        return None
    s = dt.isoformat()
    if s.endswith("Z") or "+" in s[10:] or s[10:].count("-") > 0:
        return s
    return s + "Z"


def _participant_payload(db: Session, participant: DuelParticipant) -> DuelParticipantOut:
    user = db.query(User).filter(User.id == participant.user_id).first()
    return DuelParticipantOut(
        user_id=participant.user_id,
        username=user.username if user else participant.user_id,
        cf_rating=participant.current_rating or (user.cf_rating if user else 0),
        joined_at=participant.joined_at,
    )


def _participants(db: Session, duel_id: str) -> List[DuelParticipantOut]:
    rows = (
        db.query(DuelParticipant)
        .filter(DuelParticipant.duel_id == duel_id)
        .order_by(DuelParticipant.joined_at.asc())
        .all()
    )
    return [_participant_payload(db, row) for row in rows]


def _recalculate_room_rating(db: Session, duel: Duel) -> int:
    rows = db.query(DuelParticipant).filter(DuelParticipant.duel_id == duel.id).all()
    if not rows:
        duel.rating_target = 1200
        return 1200

    highest = 0
    for row in rows:
        user = db.query(User).filter(User.id == row.user_id).first()
        rating = row.current_rating or (user.cf_rating if user else 0) or 1200
        if rating > highest:
            highest = rating

    duel.rating_target = highest or 1200
    return duel.rating_target


def _assign_problem_for_room(db: Session, duel: Duel, force: bool = False) -> Duel:
    if duel.problem_id and duel.status == "active" and not force:
        return duel

    target = duel.rating_target or 1200
    problem_list = CodeforcesService.generate_practice(rating=target, count=1)
    if problem_list:
        problem = problem_list[0]
        duel.problem_id = problem.get("problem_id") or f"{problem.get('contest_id')}-{problem.get('index')}"
        duel.problem_name = problem.get("name")
        duel.problem_rating = problem.get("rating")
    return duel


def _serialize_duel(db: Session, duel: Duel) -> DuelOut:
    participants = _participants(db, duel.id)
    opponent_id = None
    if len(participants) >= 2:
        opponent_id = participants[1].user_id

    return DuelOut(
        id=duel.id,
        host_id=duel.host_id,
        opponent_id=opponent_id,
        problem_id=duel.problem_id,
        problem_name=duel.problem_name,
        problem_rating=duel.problem_rating,
        status=duel.status,
        winner_id=duel.winner_id,
        rating_target=duel.rating_target,
        max_participants=duel.max_participants,
        participants_count=len(participants),
        participants=participants,
        started_at=duel.started_at,
        finished_at=duel.finished_at,
    )


def _serialize_duel_state(db: Session, duel_id: str):
    duel = db.query(Duel).filter(Duel.id == duel_id).first()
    if not duel:
        return {"exists": False}

    step_rows = (
        db.query(DuelStep)
        .filter(DuelStep.duel_id == duel.id)
        .order_by(DuelStep.step_index.asc())
        .all()
    )

    steps = [
        {
            "step_index": s.step_index,
            "rating": s.rating,
            "problem": {
                "contest_id": s.problem_contest_id,
                "index": s.problem_index,
                "name": s.problem_name,
                "rating": s.rating,
                "problem_id": s.problem_id,
                "tags": (json.loads(s.problem_tags_json) if s.problem_tags_json else []),
            },
            "host_status": s.host_status,
            "opponent_status": s.opponent_status,
        }
        for s in step_rows
    ]

    participant_rows = (
        db.query(DuelParticipant)
        .filter(DuelParticipant.duel_id == duel.id)
        .order_by(DuelParticipant.joined_at.asc())
        .all()
    )

    def _p(row, is_host: bool):
        user = db.query(User).filter(User.id == row.user_id).first()
        current_step = next(
            (
                s.step_index
                for s in step_rows
                if (s.host_status if is_host else s.opponent_status) == "pending"
            ),
            len(step_rows),
        )
        elo = (user.elo if user else 1200) or 1200
        cf_handle = (user.cf_handle if user else None) or None
        cf_valid, cf_error = (True, None)
        if cf_handle:
            cf_valid, cf_error = verify_cf_handle(cf_handle)
        return {
            "user_id": row.user_id,
            "username": user.username if user else row.user_id,
            "cf_handle": cf_handle,
            "cf_valid": cf_valid,
            "cf_error": cf_error,
            "elo": elo,
            "tier": tier_for_elo(elo).key,
            "current_step": current_step,
            "last_verdict": None,
            "joined_at": iso_utc(row.joined_at),
        }

    host_row, opp_row = host_and_opponent(duel, participant_rows)
    host_payload = _p(host_row, True) if host_row else None
    opp_payload = _p(opp_row, False) if opp_row else None

    return {
        "exists": True,
        "id": duel.id,
        "status": duel.status,
        "host": host_payload,
        "opponent": opp_payload,
        "steps": steps,
        "started_at": iso_utc(duel.started_at),
        "finished_at": iso_utc(duel.finished_at),
        "time_cap_seconds": duel.time_cap_seconds,
        "winner_id": duel.winner_id,
    }


# ================= SPECIFIC ROUTES FIRST =================

@router.post("/create", response_model=DuelCreateResponse)
def create_duel(data: DuelCreate, db: Session = Depends(get_db)):
    _validate_uuid(data.host_id, "host_id")

    if data.rating and (data.rating < 800 or data.rating > 3500):
        raise HTTPException(status_code=400, detail="Rating must be between 800 and 3500")

    host = db.query(User).filter(User.id == data.host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="User not found")

    duel = Duel(
        id=str(uuid.uuid4()),
        host_id=data.host_id,
        max_participants=data.max_participants,
        rating_target=host.cf_rating or data.rating or 1200,
        status="waiting",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(duel)
    db.flush()

    db.add(
        DuelParticipant(
            duel_id=duel.id,
            user_id=host.id,
            current_rating=host.cf_rating or data.rating or 1200,
            joined_at=datetime.utcnow(),
        )
    )
    db.flush()

    _recalculate_room_rating(db, duel)
    _assign_problem_for_room(db, duel, force=True)

    db.commit()
    db.refresh(duel)

    return DuelCreateResponse(
        duel_id=duel.id,
        problem_id=duel.problem_id or "",
        problem_name=duel.problem_name,
        rating=duel.problem_rating,
        status=duel.status,
        participants_count=1,
        max_participants=duel.max_participants,
        rating_target=duel.rating_target,
    )


@router.get("/host/{host_id}", response_model=DuelOut)
def get_latest_duel_by_host(host_id: str, db: Session = Depends(get_db)):
    _validate_uuid(host_id, "host_id")

    duel = (
        db.query(Duel)
        .filter(
            Duel.host_id == host_id,
            Duel.status.in_(["waiting", "active"]),
        )
        .order_by(Duel.created_at.desc())
        .first()
    )

    if not duel:
        raise HTTPException(status_code=404, detail="No active or waiting duel found for this host")

    return _serialize_duel(db, duel)


@router.post("/join", response_model=DuelOut)
def join_duel(data: DuelJoin, db: Session = Depends(get_db)):
    _validate_uuid(data.duel_id, "duel_id")
    _validate_uuid(data.opponent_id, "opponent_id")

    duel = db.query(Duel).filter(Duel.id == data.duel_id).first()
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")

    if duel.status != "waiting":
        raise HTTPException(status_code=400, detail="Duel is not accepting players")

    participants = (
        db.query(DuelParticipant)
        .filter(DuelParticipant.duel_id == duel.id)
        .all()
    )

    if any(p.user_id == data.opponent_id for p in participants):
        return _serialize_duel(db, duel)

    if len(participants) >= duel.max_participants:
        raise HTTPException(status_code=400, detail="Duel room is full")

    if duel.host_id == data.opponent_id:
        raise HTTPException(status_code=400, detail="Cannot join your own duel")

    user = db.query(User).filter(User.id == data.opponent_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.add(
        DuelParticipant(
            duel_id=duel.id,
            user_id=user.id,
            current_rating=user.cf_rating or 1200,
            joined_at=datetime.utcnow(),
        )
    )
    db.flush()

    _recalculate_room_rating(db, duel)
    _assign_problem_for_room(db, duel, force=True)

    db.commit()
    db.refresh(duel)

    return _serialize_duel(db, duel)


@router.post("/start", response_model=DuelStartResponse)
def start_duel(payload: DuelStartRequest, db: Session = Depends(get_db)):
    _validate_uuid(payload.duel_id, "duel_id")
    _validate_uuid(payload.user_id, "user_id")

    duel = db.query(Duel).filter(Duel.id == payload.duel_id).first()
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")

    if duel.host_id != payload.user_id:
        raise HTTPException(status_code=403, detail="Only host can start the duel")

    participants = (
        db.query(DuelParticipant)
        .filter(DuelParticipant.duel_id == duel.id)
        .all()
    )
    if len(participants) < 2:
        raise HTTPException(status_code=400, detail="Waiting for at least one opponent")

    if duel.status != "waiting":
        raise HTTPException(status_code=400, detail="Duel already started or finished")

    _recalculate_room_rating(db, duel)
    _assign_problem_for_room(db, duel, force=True)

    duel.status = "active"
    duel.started_at = datetime.utcnow()
    duel.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(duel)

    return DuelStartResponse(
        duel_id=duel.id,
        status=duel.status,
        problem_id=duel.problem_id or "",
        problem_name=duel.problem_name,
        message="Duel started! First correct submission wins.",
        participants_count=len(participants),
    )


@router.post("/submit", response_model=DuelSubmitResult)
def submit_solution(payload: DuelSubmitRequest, db: Session = Depends(get_db)):
    _validate_uuid(payload.duel_id, "duel_id")
    _validate_uuid(payload.user_id, "user_id")

    duel = db.query(Duel).filter(Duel.id == payload.duel_id).first()
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")

    participant_rows = (
        db.query(DuelParticipant)
        .filter(DuelParticipant.duel_id == duel.id)
        .all()
    )
    participant_user_ids = [p.user_id for p in participant_rows]

    if payload.user_id not in participant_user_ids:
        raise HTTPException(status_code=403, detail="Not a participant")

    if duel.status == "finished":
        raise HTTPException(status_code=400, detail="Duel is finished")

    if duel.status != "active":
        raise HTTPException(status_code=400, detail=f"Duel is {duel.status}, submissions not allowed")

    user = crud.get_user_by_id(db, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.cf_handle:
        raise HTTPException(
            status_code=400,
            detail="Set your Codeforces handle using /auth/cf-handle before submitting",
        )

    if not duel.problem_id:
        _assign_problem_for_room(db, duel, force=True)
        db.commit()
        db.refresh(duel)

    result_data = CodeforcesService.check_problem_solved(user.cf_handle, duel.problem_id)
    if result_data is None:
        raise HTTPException(status_code=503, detail="Codeforces API unavailable, please retry")

    verdict = result_data.get("verdict", "UNKNOWN")
    success = result_data.get("solved", False)

    submit_result = DuelSubmitResult(
        duel_id=duel.id,
        user_id=user.id,
        success=success,
        verdict=verdict,
        winner_id=None,
    )

    if success:
        duel.status = "finished"
        duel.winner_id = user.id
        duel.finished_at = datetime.utcnow()
        duel.updated_at = datetime.utcnow()
        submit_result.winner_id = user.id

        for p in participant_rows:
            participant_user = db.query(User).filter(User.id == p.user_id).first()
            if not participant_user:
                continue
            if p.user_id == user.id:
                participant_user.duel_wins += 1
            else:
                participant_user.duel_losses += 1

    db.commit()
    db.refresh(duel)

    return submit_result


@router.get("/recent/me")
def recent_duels(
    limit: int = 10,
    current_user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(EloHistory)
        .filter(EloHistory.user_id == current_user.id)
        .order_by(EloHistory.created_at.desc())
        .limit(min(max(limit, 1), 50))
        .all()
    )
    out = []
    for h in rows:
        opp = (
            db.query(User).filter(User.id == h.opponent_id).first()
            if h.opponent_id
            else None
        )
        duel = db.query(Duel).filter(Duel.id == h.duel_id).first()
        steps_solved = 0
        if duel:
            is_host = bool(is_duel_host(duel, current_user.id))
            step_rows = db.query(DuelStep).filter(DuelStep.duel_id == duel.id).all()
            steps_solved = sum(
                1
                for s in step_rows
                if (s.host_status if is_host else s.opponent_status) == "solved"
            )
        out.append(
            {
                "id": h.duel_id,
                "opponent": opp.username if opp else "—",
                "result": h.result if h.result in ("win", "loss", "draw") else "win",
                "delta": h.delta,
                "steps_cleared": steps_solved,
                "duration_seconds": (
                    int((duel.finished_at - duel.started_at).total_seconds())
                    if (duel and duel.finished_at and duel.started_at)
                    else 0
                ),
                "ended_at": (
                    duel.finished_at.isoformat()
                    if duel and duel.finished_at
                    else h.created_at.isoformat()
                ),
            }
        )
    return out


# ================= WILDCARD ROUTES LAST =================

@router.get("/{duel_id}/state")
def get_duel_state(duel_id: str, db: Session = Depends(get_db)):
    state = _serialize_duel_state(db, duel_id)
    if not state.get("exists"):
        raise HTTPException(status_code=404, detail="Duel not found")
    return state


@router.post("/{duel_id}/sync")
async def sync_duel_verdicts(duel_id: str, db: Session = Depends(get_db)):
    duel = db.query(Duel).filter(Duel.id == duel_id).first()
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")
    if duel.status != "active":
        raise HTTPException(status_code=400, detail="Duel is not active")

    await process_duel_cf(db, duel, broadcast=True)
    db.refresh(duel)
    state = _serialize_duel_state(db, duel_id)
    return {"sync": True, "state": state}


@router.post("/{duel_id}/forfeit")
async def forfeit_duel(
    duel_id: str,
    current_user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    duel = db.query(Duel).filter(Duel.id == duel_id).first()
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")
    if duel.status != "active":
        raise HTTPException(status_code=400, detail="Duel is not active")

    parts = (
        db.query(DuelParticipant)
        .filter(DuelParticipant.duel_id == duel.id)
        .order_by(DuelParticipant.joined_at.asc())
        .all()
    )
    if not any(p.user_id == current_user.id for p in parts):
        raise HTTPException(status_code=403, detail="Not a participant")

    other = next((p for p in parts if p.user_id != current_user.id), None)
    winner_id = other.user_id if other else None
    payload = await complete_duel(db, duel, winner_user_id=winner_id)
    return {"ok": True, "winner_id": winner_id, "payload": payload}


@router.get("/{duel_id}/problem")
def get_duel_problem(duel_id: str, user_id: str, db: Session = Depends(get_db)):
    _validate_uuid(duel_id, "duel_id")
    _validate_uuid(user_id, "user_id")

    duel = db.query(Duel).filter(Duel.id == duel_id).first()
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")

    participants = (
        db.query(DuelParticipant)
        .filter(DuelParticipant.duel_id == duel.id)
        .all()
    )
    if user_id not in [p.user_id for p in participants]:
        raise HTTPException(status_code=403, detail="Not a participant")

    if not duel.problem_id:
        _assign_problem_for_room(db, duel, force=True)
        db.commit()
        db.refresh(duel)

    return {
        "problem_id": duel.problem_id,
        "problem_name": duel.problem_name,
        "rating": duel.problem_rating,
        "tags": [],
        "time_limit": None,
        "memory_limit": None,
        "status": duel.status,
    }


@router.get("/{duel_id}/chat")
def get_chat_messages(
    duel_id: str,
    db: Session = Depends(get_db),
):
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.duel_id == duel_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return {"messages": jsonable_encoder(messages)}


class SendChatMessageRequest(BaseModel):
    user_id: str
    message: str


@router.post("/{duel_id}/chat")
def send_chat_message(
    duel_id: str,
    body: SendChatMessageRequest,
    db: Session = Depends(get_db),
):
    user_id = body.user_id
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    chat_msg = ChatMessage(
        id=str(uuid.uuid4()),
        duel_id=duel_id,
        user_id=user_id,
        message=message.strip(),
        created_at=datetime.utcnow(),
    )
    db.add(chat_msg)
    db.commit()
    db.refresh(chat_msg)
    
    return {"message": jsonable_encoder(chat_msg)}


@router.get("/activity")
def get_activity_events(
    db: Session = Depends(get_db),
):
    # Get recent replay events for the last 24 hours
    since = datetime.utcnow() - timedelta(hours=24)
    events = (
        db.query(ReplayEvent)
        .filter(ReplayEvent.created_at >= since)
        .order_by(ReplayEvent.created_at.desc())
        .all()
    )
    
    activity_events = []
    for event in events:
        try:
            payload = json.loads(event.payload_json or "{}")
            username = "unknown"
            if event.user_id:
                user = db.query(User).filter(User.id == event.user_id).first()
                if user:
                    username = user.username
            
            activity_events.append({
                "type": event.event_type,
                "user_id": event.user_id,
                "username": username,
                "timestamp": event.created_at.isoformat() + "Z",
                "data": payload,
            })
        except Exception:
            continue
    
    return {"events": activity_events}


# ================= PURE WILDCARD — ABSOLUTE LAST =================

@router.get("/{duel_id}", response_model=DuelOut)
def get_duel(duel_id: str, db: Session = Depends(get_db)):
    _validate_uuid(duel_id, "duel_id")

    duel = db.query(Duel).filter(Duel.id == duel_id).first()
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")

    return _serialize_duel(db, duel)