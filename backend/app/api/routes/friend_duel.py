from __future__ import annotations

import json
import random
import string
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Duel, DuelParticipant, DuelStep, FriendRoom, User
from app.services.ws_hub import hub
from app.services.elo import tier_for_elo
from app.api.routes.auth import _get_current_user

router = APIRouter(prefix="/friend-duel", tags=["friend-duel"])


RATING_PRESETS = {
    "chill":  (-300, -200, -100, 0, 100),
    "medium": (-200, -100, 0, 100, 200),
    "hard":   (-100, 0, 100, 200, 300),
}


def _generate_code(db: Session) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(20):
        code = "".join(random.choices(alphabet, k=6))
        if not db.query(FriendRoom).filter(FriendRoom.code == code).first():
            return code
    raise HTTPException(status_code=500, detail="could not generate unique room code")


class CreateRoomRequest(BaseModel):
    rating_preset: str = "medium"
    deck_tags: Optional[List[str]] = None


class JoinRoomRequest(BaseModel):
    code: str


def _serialize_room(room: FriendRoom, db: Session) -> dict:
    host = db.query(User).filter(User.id == room.host_id).first()
    return {
        "id": room.id,
        "code": room.code,
        "host": {
            "user_id": room.host_id,
            "username": host.username if host else room.host_id,
            "elo": (host.elo if host else 1200),
            "tier": tier_for_elo(host.elo if host else 1200).key,
        },
        "rating_preset": room.rating_preset,
        "deck_tags": json.loads(room.deck_tags_json or "[]"),
        "status": room.status,
        "duel_id": room.duel_id,
        "created_at": room.created_at.isoformat() if room.created_at else None,
        "expires_at": room.expires_at.isoformat() if room.expires_at else None,
    }


@router.post("")
def create_room(
    body: CreateRoomRequest,
    current_user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    if body.rating_preset not in RATING_PRESETS:
        raise HTTPException(status_code=400, detail="Invalid rating preset")
    if not current_user.cf_handle:
        raise HTTPException(
            status_code=400, detail="Link your Codeforces handle to host a duel."
        )

    # cancel any prior waiting rooms from this host
    db.query(FriendRoom).filter(
        FriendRoom.host_id == current_user.id, FriendRoom.status == "waiting"
    ).update({"status": "cancelled"})

    code = _generate_code(db)
    deck = list(body.deck_tags or [])[:3]
    room = FriendRoom(
        id=str(uuid.uuid4()),
        code=code,
        host_id=current_user.id,
        rating_preset=body.rating_preset,
        deck_tags_json=json.dumps(deck),
        status="waiting",
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
    db.add(room)
    db.commit()
    return _serialize_room(room, db)


@router.get("/by-code/{code}")
def get_by_code(code: str, db: Session = Depends(get_db)):
    room = db.query(FriendRoom).filter(FriendRoom.code == code.upper()).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return _serialize_room(room, db)


@router.post("/join")
async def join_room(
    body: JoinRoomRequest,
    current_user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.cf_handle:
        raise HTTPException(
            status_code=400, detail="Link your Codeforces handle to join a duel."
        )

    room = (
        db.query(FriendRoom)
        .filter(FriendRoom.code == body.code.upper(), FriendRoom.status == "waiting")
        .first()
    )
    if not room:
        raise HTTPException(status_code=404, detail="Room not found or already started")
    if room.host_id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't join your own room")

    host_user = db.query(User).filter(User.id == room.host_id).first()
    if not host_user:
        raise HTTPException(status_code=500, detail="Host user not found")
    if not host_user.cf_handle:
        raise HTTPException(status_code=400, detail="Host has not linked a CF handle")

    base_elo = min(host_user.elo or 1200, current_user.elo or 1200)
    preset = RATING_PRESETS[room.rating_preset]
    rounded = max(800, (base_elo // 100) * 100)
    step_ratings = [max(800, rounded + offset) for offset in preset]

    deck = json.loads(room.deck_tags_json or "[]")

    # pick problems honoring custom rating curve (we replicate picker logic per step)
    from app.services.problem_picker import get_all_problems

    pool = get_all_problems()
    if not pool:
        raise HTTPException(status_code=503, detail="Codeforces problemset unavailable")

    chosen = []
    used: set[str] = set()
    deck_set = {t.lower() for t in deck}
    rng = random.Random()
    for target in step_ratings:
        candidates = [
            p
            for p in pool
            if abs(p.rating - target) <= 50 and p.problem_id not in used
        ]
        if deck_set:
            tagged = [c for c in candidates if any(t.lower() in deck_set for t in c.tags)]
            if tagged:
                candidates = tagged
        if not candidates:
            candidates = [
                p
                for p in pool
                if abs(p.rating - target) <= 150 and p.problem_id not in used
            ]
        if not candidates:
            raise HTTPException(status_code=503, detail="problem pool too thin")
        p = rng.choice(candidates)
        chosen.append(p)
        used.add(p.problem_id)

    duel = Duel(
        host_id=host_user.id,
        format="speedrun_ladder",
        max_participants=2,
        rating_target=base_elo,
        status="active",
        started_at=datetime.utcnow(),
        problem_id=chosen[2].problem_id,
        problem_name=chosen[2].name,
        problem_rating=chosen[2].rating,
        time_cap_seconds=2700,
    )
    db.add(duel)
    db.flush()

    joined_at = datetime.utcnow()
    db.add(
        DuelParticipant(
            duel_id=duel.id,
            user_id=host_user.id,
            current_rating=host_user.elo or 1200,
            joined_at=joined_at,
        )
    )
    db.add(
        DuelParticipant(
            duel_id=duel.id,
            user_id=current_user.id,
            current_rating=current_user.elo or 1200,
            joined_at=joined_at + timedelta(milliseconds=1),
        )
    )

    for idx, p in enumerate(chosen):
        db.add(
            DuelStep(
                duel_id=duel.id,
                step_index=idx,
                rating=p.rating,
                problem_id=p.problem_id,
                problem_contest_id=p.contest_id,
                problem_index=p.index,
                problem_name=p.name,
                problem_tags_json=json.dumps(p.tags),
            )
        )

    room.status = "started"
    room.duel_id = duel.id
    db.commit()

    # broadcast match_found to the host's user channel so they navigate to the duel
    await hub.broadcast(
        "user",
        host_user.id,
        {
            "type": "friend_duel_started",
            "payload": {
                "duel_id": duel.id,
                "opponent": {
                    "user_id": current_user.id,
                    "username": current_user.username,
                    "elo": current_user.elo or 1200,
                    "tier": tier_for_elo(current_user.elo or 1200).key,
                },
            },
        },
    )

    return {"duel_id": duel.id, "room": _serialize_room(room, db)}


@router.delete("/{room_id}")
def cancel_room(
    room_id: str,
    current_user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    room = (
        db.query(FriendRoom)
        .filter(FriendRoom.id == room_id, FriendRoom.host_id == current_user.id)
        .first()
    )
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    room.status = "cancelled"
    db.commit()
    return {"ok": True}
