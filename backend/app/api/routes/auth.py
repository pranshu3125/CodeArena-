import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional

_PWHASH_PREFIX = "$pbkdf2-sha256$100000$"
_PWHASH_ITERS = 100_000

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db import get_db
from app.schemas import UserCreate, UserLogin, TokenResponse, UserOut
from app.services.codeforces import CodeforcesService, get_user_info, get_user_solved_problems
from app.services.cf_sync import verify_cf_handle
from app.models import SolvedProblem, User

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()

TOKEN_EXPIRE_HOURS = 24
SECRET_KEY = os.getenv("SECRET_KEY", "")

if not SECRET_KEY or SECRET_KEY == "codearena-dev-secret":
    import sys
    print("WARNING: SECRET_KEY is not set or is using the insecure default.", file=sys.stderr)
    print("Set SECRET_KEY environment variable to a cryptographically random string.", file=sys.stderr)


class CFHandleUpdate(BaseModel):
    cf_handle: str


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PWHASH_ITERS)
    return _PWHASH_PREFIX + base64.b64encode(salt + key).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith(_PWHASH_PREFIX):
        raw = base64.b64decode(hashed_password[len(_PWHASH_PREFIX):].encode("utf-8"))
        salt, key = raw[:16], raw[16:]
        expected = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, _PWHASH_ITERS)
        return hmac.compare_digest(key, expected)
    return hashlib.sha256(plain_password.encode("utf-8")).hexdigest() == hashed_password


def _sign(value: str) -> str:
    return hmac.new(SECRET_KEY.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def create_token(user_id: str, username: str) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "exp": int(time.time()) + (TOKEN_EXPIRE_HOURS * 3600),
    }
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    sig = _sign(body)
    return f"{body}.{sig}"


def verify_token(token: str) -> Optional[str]:
    try:
        body, sig = token.split(".", 1)
        expected_sig = _sign(body)
        if not hmac.compare_digest(sig, expected_sig):
            return None

        padding = "=" * (-len(body) % 4)
        payload_json = base64.urlsafe_b64decode((body + padding).encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)

        if int(payload.get("exp", 0)) < int(time.time()):
            return None

        return payload.get("sub")
    except Exception:
        return None


def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    user_id = verify_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        # 401 (not 404) so the frontend interceptor clears stale localStorage
        # and redirects to /login. This happens when the DB was reset (e.g.
        # SQLite → Postgres migration) but the browser still has an old JWT.
        raise HTTPException(status_code=401, detail="Session expired — please log in again")

    return user


@router.post("/register", response_model=UserOut)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    existing_username = db.query(User).filter(User.username == user_in.username).first()
    existing_email = db.query(User).filter(User.email == user_in.email).first() if user_in.email else None

    if existing_username:
        raise HTTPException(status_code=400, detail="Username already taken")
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
        cf_handle=user_in.cf_handle,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/login", response_model=TokenResponse)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    identifier = (user_in.email or user_in.username or "").strip()
    if not identifier:
        raise HTTPException(status_code=422, detail="Email or username is required")

    user = (
        db.query(User)
        .filter(or_(User.username == identifier, User.email == identifier))
        .first()
    )

    if not user or not user.hashed_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(user.id, user.username)
    return TokenResponse(access_token=token)


@router.get("/me")
def get_me(current_user: User = Depends(_get_current_user), db: Session = Depends(get_db)):
    from app.models import Streak

    streak = db.query(Streak).filter(Streak.user_id == current_user.id).first()
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "cf_handle": current_user.cf_handle,
        "cf_rating": current_user.cf_rating,
        "elo": current_user.elo,
        "xp": current_user.xp,
        "role": current_user.role,
        "duel_wins": current_user.duel_wins,
        "duel_losses": current_user.duel_losses,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "streak": {
            "current_count": streak.current_count if streak else 0,
            "longest_count": streak.longest_count if streak else 0,
            "shields_remaining": streak.shields_remaining if streak else 0,
        },
    }


@router.put("/cf-handle")
def update_cf_handle(
    payload: CFHandleUpdate,
    current_user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    cf_handle = payload.cf_handle.strip()
    if not cf_handle:
        raise HTTPException(status_code=400, detail="CF handle cannot be empty")

    try:
        valid, err = verify_cf_handle(cf_handle)
    except Exception:
        valid, err = False, "Codeforces API unreachable"
    if not valid:
        import logging
        logging.getLogger("auth").warning(
            "CF handle %s verification failed: %s — saving anyway for local dev", cf_handle, err
        )

    info = None
    try:
        info = CodeforcesService.fetch_user_rating(cf_handle)
    except Exception:
        pass
    if info:
        current_user.cf_rating = info.get("current_rating", 0) or 0
        current_user.cf_rank = info.get("rank", "unrated")

    current_user.cf_handle = cf_handle
    current_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)

    return {"message": "CF handle updated successfully", "cf_handle": cf_handle}


@router.post("/sync-cf")
def sync_cf(
    current_user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    handle = current_user.cf_handle
    if not handle:
        raise HTTPException(status_code=400, detail="Set your Codeforces handle first")

    try:
        info = get_user_info(handle)
        solved_list = get_user_solved_problems(handle)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Codeforces handle")

    current_user.cf_rating = info.get("rating", 0)
    current_user.cf_rank = info.get("rank", "unrated")
    current_user.solved_count = len(solved_list)
    current_user.updated_at = datetime.utcnow()

    db.query(SolvedProblem).filter(SolvedProblem.user_id == current_user.id).delete(synchronize_session=False)

    for contest_id, index, name, rating in solved_list:
        db.add(
            SolvedProblem(
                user_id=current_user.id,
                contest_id=contest_id,
                problem_index=index,
                problem_name=name,
                rating=rating,
            )
        )

    db.commit()
    db.refresh(current_user)

    return {
        "handle": handle,
        "rating": current_user.cf_rating,
        "rank": current_user.cf_rank,
        "solved_count": current_user.solved_count,
    }