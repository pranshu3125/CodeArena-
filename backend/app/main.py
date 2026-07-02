import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session

from . import crud, schemas
from .db import Base, engine, get_db
from .models import ChatMessage, Duel, DuelParticipant, DuelStep, EloHistory, User, UserFocus
from .schemas import CFProblemsResponse
from .services.codeforces import CodeforcesService
from .services.duel_completion import complete_duel
from .services.elo import tier_for_elo
from .services.ws_hub import hub
from .services.matchmaker import run_matchmaker_loop

from .services.cf_poller import run_cf_poller_loop
from .services.metrics import metrics_response, MetricsMiddleware
from .api.routes.auth import router as auth_router
from .api.routes.practice import router as practice_router
from .api.routes.duel import router as duel_router
from .api.routes.matchmaking import router as matchmaking_router

from .api.routes.cf import router as cf_router
from .api.routes.leaderboard import router as leaderboard_router
from .api.routes.quests import router as quests_router
from .api.routes.replay import router as replay_router
from .api.routes.friend_duel import router as friend_duel_router
from .api.routes.open_lobby import router as open_lobby_router
from .api.routes.deck import router as deck_router
from .api.routes.async_challenge import router as async_challenge_router
from .api.routes.cosmetics import router as cosmetics_router
from .api.routes.admin import router as admin_router
from .api.routes.coach import router as coach_router
from .services.research_db import check_config as check_research_db_config

# ================= DB INIT =================
Base.metadata.create_all(bind=engine)

_research_cfg = check_research_db_config()
if not _research_cfg["configured"]:
    _research_issues = list(_research_cfg.get("missing", [])) + list(
        _research_cfg.get("invalid", [])
    )
    logger.warning(
        "Research DB not configured. Env issues: %s. Coach features will return 503.",
        ", ".join(_research_issues),
    )


def iso_utc(dt):
    if dt is None:
        return None
    s = dt.isoformat()
    if s.endswith("Z") or "+" in s[10:] or s[10:].count("-") > 0:
        return s
    return s + "Z"


# ================= APP INIT =================
app = FastAPI(
    title="CodeArena API",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ================= CORS =================
_default_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://code-arena-ievp.vercel.app",
    "https://code-arena-wine.vercel.app",
]

_explicit_origins = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()
]
_frontend_url = os.getenv("FRONTEND_URL", "").strip()
if _frontend_url:
    _explicit_origins.append(_frontend_url)

_allow_origin_regex = r"https://.*\.vercel\.app$"
allowed_origins = list(dict.fromkeys(_default_origins + _explicit_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(MetricsMiddleware)

# ================= ROUTES =================
app.include_router(auth_router)
app.include_router(practice_router)
app.include_router(duel_router)
app.include_router(matchmaking_router)
app.include_router(cf_router)
app.include_router(leaderboard_router)
app.include_router(quests_router)
app.include_router(replay_router)
app.include_router(friend_duel_router)
app.include_router(open_lobby_router)
app.include_router(deck_router)
app.include_router(async_challenge_router)
app.include_router(cosmetics_router)
app.include_router(admin_router)
app.include_router(coach_router)


# ================= BASIC ENDPOINTS =================
@app.get("/")
def root():
    return {"status": "ok", "service": "CodeArena backend"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(content=metrics_response(), media_type="text/plain")


# ================= CODEFORCES =================
def _normalize_problem(problem):
    if hasattr(problem, "model_dump"):
        problem = problem.model_dump()
    return {
        "contest_id": problem.get("contestId", problem.get("contest_id")),
        "index": problem.get("index"),
        "name": problem.get("name"),
        "rating": problem.get("rating"),
        "tags": problem.get("tags") or [],
        "time_limit": problem.get("timeLimit", problem.get("time_limit")),
        "memory_limit": problem.get("memoryLimit", problem.get("memory_limit")),
        "problem_id": problem.get("problem_id")
        or (
            f"{problem.get('contestId', problem.get('contest_id'))}-{problem.get('index')}"
            if problem.get("index") is not None
            else None
        ),
    }


@app.get("/cf/problems", response_model=CFProblemsResponse)
def cf_problems():
    try:
        problems = CodeforcesService.fetch_problemset()
        mapped = [_normalize_problem(p) for p in problems[:50]]
        return {"problems": mapped}
    except Exception as e:
        print(e)
        return {"problems": []}


# ================= SUBMISSIONS =================
@app.post("/submissions/submit", response_model=schemas.SubmissionOut)
async def submit(sub_in: schemas.SubmissionCreate, db: Session = Depends(get_db)):
    user = crud.get_user_by_id(db, sub_in.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    sub = crud.create_submission(db, sub_in, user_id=sub_in.user_id)

    try:
        import redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.Redis.from_url(redis_url)
        r.publish(
            "submission_queue",
            json.dumps({
                "submission_id": sub.id,
                "user_id": sub_in.user_id,
                "problem_id": sub_in.problem_id,
                "language": sub_in.language,
            }),
        )
    except Exception as e:
        print(f"Redis publish failed: {e}")

    return sub


# ================= PROFILE + HISTORY =================
from .api.routes.auth import _get_current_user  # noqa: E402


@app.get("/profile/me/elo-history")
def my_elo_history(
    limit: int = 50,
    current_user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(EloHistory)
        .filter(EloHistory.user_id == current_user.id)
        .order_by(EloHistory.created_at.desc())
        .limit(min(max(limit, 1), 200))
        .all()
    )
    rows.reverse()
    return [
        {
            "elo_before": h.elo_before,
            "elo_after": h.elo_after,
            "delta": h.delta,
            "result": h.result,
            "created_at": iso_utc(h.created_at),
        }
        for h in rows
    ]


@app.get("/profile/by-handle/{username}")
def public_profile_by_username(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    from .models import Streak as _Streak
    streak = db.query(_Streak).filter(_Streak.user_id == user.id).first()
    elo_rows = (
        db.query(EloHistory)
        .filter(EloHistory.user_id == user.id)
        .order_by(EloHistory.created_at.desc())
        .limit(50)
        .all()
    )
    elo_rows.reverse()

    elo_val = user.elo or 1200
    return {
        "user_id": user.id,
        "username": user.username,
        "cf_handle": user.cf_handle,
        "elo": elo_val,
        "tier": tier_for_elo(elo_val).key,
        "duel_wins": user.duel_wins or 0,
        "duel_losses": user.duel_losses or 0,
        "xp": user.xp or 0,
        "level": int(((user.xp or 0) / 100) ** 0.5),
        "streak": {
            "current_count": streak.current_count if streak else 0,
            "longest_count": streak.longest_count if streak else 0,
            "shields_remaining": streak.shields_remaining if streak else 0,
        },
        "elo_history": [
            {
                "elo_after": h.elo_after,
                "delta": h.delta,
                "result": h.result,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in elo_rows
        ],
    }


# ================= WEBSOCKETS =================
@app.websocket("/ws/duel/{duel_id}")
async def duel_ws(websocket: WebSocket, duel_id: str):
    from .services.emote import check_and_record, valid_glyph
    from .api.routes.duel import _serialize_duel_state
    from .models import ChatMessage

    await websocket.accept()
    await hub.subscribe("duel", duel_id, websocket)
    # Track WebSocket usage for abandonment detection
    ws_key = f"duel:{duel_id}:{websocket.client.host}"
    _websocket_last_seen[ws_key] = time.time()
    
    db = next(get_db())
    try:
        state = _serialize_duel_state(db, duel_id)
        await websocket.send_json({"type": "state", "payload": {"state": state}})
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong"})
                # Update last seen time
                _websocket_last_seen[ws_key] = time.time()
                continue
            try:
                payload = json.loads(msg)
                # Update last seen time on any message
                _websocket_last_seen[ws_key] = time.time()
            except Exception:
                continue
            if payload.get("type") == "emote":
                user_id = payload.get("user_id")
                glyph = payload.get("glyph")
                if not user_id or not glyph or not valid_glyph(glyph):
                    continue
                if not check_and_record(user_id):
                    await websocket.send_json({
                        "type": "system",
                        "payload": {"message": "emote rate limit"},
                    })
                    continue
                await hub.broadcast("duel", duel_id, {
                    "type": "emote",
                    "payload": {"user_id": user_id, "glyph": glyph, "sent_at": time.time()},
                })
            elif payload.get("type") == "chat":
                user_id = payload.get("user_id")
                message = payload.get("message")
                if not user_id or not message or not message.strip():
                    continue
                chat_msg = ChatMessage(
                    id=str(uuid.uuid4()),
                    duel_id=duel_id,
                    user_id=user_id,
                    message=message.strip(),
                    created_at=datetime.utcnow(),
                )
                db.add(chat_msg)
                db.commit()
                await hub.broadcast("duel", duel_id, {
                    "type": "chat_message",
                    "payload": {
                        "id": chat_msg.id,
                        "user_id": chat_msg.user_id,
                        "message": chat_msg.message,
                        "created_at": chat_msg.created_at.isoformat() + "Z",
                    },
                })
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe("duel", duel_id, websocket)
        # Track disconnection time
        _websocket_last_seen[ws_key] = time.time()
        db.close()


@app.websocket("/ws/queue/{user_id}")
async def queue_ws(websocket: WebSocket, user_id: str):
    await websocket.accept()
    await hub.subscribe("queue", user_id, websocket)
    # Track WebSocket usage for abandonment detection
    ws_key = f"queue:{user_id}:{websocket.client.host}"
    _websocket_last_seen[ws_key] = time.time()
    
    try:
        await websocket.send_json({"type": "connected", "payload": {"user_id": user_id}})
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong"})
                # Update last seen time
                _websocket_last_seen[ws_key] = time.time()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe("queue", user_id, websocket)
        # Track disconnection time
        _websocket_last_seen[ws_key] = time.time()


@app.websocket("/ws/user/{user_id}")
async def user_ws(websocket: WebSocket, user_id: str):
    await websocket.accept()
    await hub.subscribe("user", user_id, websocket)
    # Track WebSocket usage for abandonment detection
    ws_key = f"user:{user_id}:{websocket.client.host}"
    _websocket_last_seen[ws_key] = time.time()
    
    try:
        await websocket.send_json({"type": "connected", "payload": {"user_id": user_id}})
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong"})
                # Update last seen time
                _websocket_last_seen[ws_key] = time.time()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe("user", user_id, websocket)
        # Track disconnection time
        _websocket_last_seen[ws_key] = time.time()


# ================= BACKGROUND WORKERS =================
_background_tasks: list[asyncio.Task] = []
_websocket_last_seen: dict[str, float] = {}
CHECK_INTERVAL = 30  # seconds
ABANDON_THRESHOLD = 90  # seconds - if no message for this long, consider abandoned


async def _check_abandoned_duels() -> None:
    """Periodically check for inactive duels and auto-forfeit for disconnected players."""
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        db = next(get_db())
        try:
            current_time = time.time()
            for ws_key, last_seen in list(_websocket_last_seen.items()):
                if current_time - last_seen <= ABANDON_THRESHOLD:
                    continue
                if not ws_key.startswith("duel:"):
                    continue
                key_parts = ws_key.split(":", 2)
                if len(key_parts) < 2:
                    continue
                duel_id = key_parts[1]
                remote_user_id = key_parts[2] if len(key_parts) > 2 else None

                duel = db.query(Duel).filter(Duel.id == duel_id).first()
                if not duel or duel.status != "active":
                    continue

                participant_rows = db.query(DuelParticipant).filter(DuelParticipant.duel_id == duel_id).all()
                active_ids = [p.user_id for p in participant_rows]
                if not active_ids:
                    continue

                others = [p.user_id for p in participant_rows if p.user_id != remote_user_id]
                if others:
                    winner_id = others[0]
                    await complete_duel(db, duel, winner_user_id=winner_id)
                    await hub.broadcast("duel", duel_id, {
                        "type": "duel_abandoned",
                        "payload": {
                            "winner_id": winner_id,
                            "reason": "opponent_disconnected",
                        },
                    })
                else:
                    duel.status = "complete"
                    duel.finished_at = datetime.utcnow()
                    db.commit()

                _websocket_last_seen.pop(ws_key, None)
        except Exception as exc:
            print(f"Error checking abandoned duels: {exc}")
        finally:
            db.close()


async def _track_websocket_usage() -> None:
    """Track WebSocket activity for abandonment detection."""
    while True:
        try:
            current_time = time.time()
            old_keys = [k for k, v in _websocket_last_seen.items() if current_time - v > 300]
            for k in old_keys:
                _websocket_last_seen.pop(k, None)
        except Exception as exc:
            print(f"Error tracking websocket usage: {exc}")
        await asyncio.sleep(CHECK_INTERVAL)


@app.on_event("startup")
async def _start_workers() -> None:
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key or secret_key == "codearena-dev-secret":
        print("FATAL: SECRET_KEY environment variable is not set or is using the insecure default")
        print("Set SECRET_KEY to a cryptographically random string in the environment or .env file")
        return

    try:
        from .services.quests import seed_quests
        db = next(get_db())
        try:
            seed_quests(db)
        finally:
            db.close()
    except Exception as e:
        print(f"quest seed failed: {e}")

    _background_tasks.append(asyncio.create_task(run_matchmaker_loop()))
    _background_tasks.append(asyncio.create_task(run_cf_poller_loop()))
    _background_tasks.append(asyncio.create_task(_track_websocket_usage()))
    _background_tasks.append(asyncio.create_task(_check_abandoned_duels()))


@app.on_event("shutdown")
async def _stop_workers() -> None:
    for t in _background_tasks:
        t.cancel()
