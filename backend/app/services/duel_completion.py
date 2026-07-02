from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Duel, DuelParticipant, DuelStep, EloHistory, ReplayEvent, User, UserFocus
from app.services.elo import elo_delta, apply_delta, tier_for_elo
from app.services.streak import tick_streak
from app.services.quests import evaluate_after_duel
from app.services.duel_roles import host_and_opponent, is_duel_host
from app.services.ws_hub import hub

log = logging.getLogger("duel_completion")


def _participants(db: Session, duel: Duel) -> list[DuelParticipant]:
    return (
        db.query(DuelParticipant)
        .filter(DuelParticipant.duel_id == duel.id)
        .order_by(DuelParticipant.joined_at.asc())
        .all()
    )


def _steps_solved(db: Session, duel: Duel, user_id: str) -> int:
    rows = db.query(DuelStep).filter(DuelStep.duel_id == duel.id).all()
    parts = _participants(db, duel)
    if not parts:
        return 0
    is_host = is_duel_host(duel, user_id)
    return sum(
        1
        for s in rows
        if (s.host_status if is_host else s.opponent_status) == "solved"
    )


async def complete_duel(
    db: Session, duel: Duel, winner_user_id: str | None
) -> None:
    parts = _participants(db, duel)
    if len(parts) != 2:
        log.warning("complete_duel called with %d participants", len(parts))
        return

    host_part, opp_part = host_and_opponent(duel, parts)
    if not host_part or not opp_part:
        return
    host_user = db.query(User).filter(User.id == host_part.user_id).first()
    opp_user = db.query(User).filter(User.id == opp_part.user_id).first()
    if not host_user or not opp_user:
        return

    if winner_user_id is None:
        host_steps = _steps_solved(db, duel, host_user.id)
        opp_steps = _steps_solved(db, duel, opp_user.id)
        if host_steps > opp_steps:
            winner_user_id = host_user.id
        elif opp_steps > host_steps:
            winner_user_id = opp_user.id

    if winner_user_id is None:
        host_result = opp_result = "draw"
    elif winner_user_id == host_user.id:
        host_result, opp_result = "win", "loss"
    else:
        host_result, opp_result = "loss", "win"

    host_before = host_user.elo or 1200
    opp_before = opp_user.elo or 1200

    host_delta = elo_delta(host_before, opp_before, host_result)
    opp_delta = elo_delta(opp_before, host_before, opp_result)

    # Smurf check: cap gain if CF rating is >500 above internal ELO AND
    # opponent is much weaker. Prevents abuse via fresh CodeArena account.
    SMURF_CF_GAP = 500
    SMURF_ELO_GAP = 300
    SMURF_CAP = 5

    def _maybe_cap(my_user, my_before: int, opp_before_local: int, delta: int) -> int:
        if delta <= 0:
            return delta
        cf_rating = my_user.cf_rating or 0
        if cf_rating - my_before >= SMURF_CF_GAP and my_before - opp_before_local >= SMURF_ELO_GAP:
            return min(delta, SMURF_CAP)
        return delta

    host_delta = _maybe_cap(host_user, host_before, opp_before, host_delta)
    opp_delta = _maybe_cap(opp_user, opp_before, host_before, opp_delta)

    host_user.elo = apply_delta(host_before, host_delta)
    opp_user.elo = apply_delta(opp_before, opp_delta)

    if host_result == "win":
        host_user.duel_wins = (host_user.duel_wins or 0) + 1
    if host_result == "loss":
        host_user.duel_losses = (host_user.duel_losses or 0) + 1
    if opp_result == "win":
        opp_user.duel_wins = (opp_user.duel_wins or 0) + 1
    if opp_result == "loss":
        opp_user.duel_losses = (opp_user.duel_losses or 0) + 1

    db.add(
        EloHistory(
            user_id=host_user.id,
            duel_id=duel.id,
            elo_before=host_before,
            elo_after=host_user.elo,
            delta=host_delta,
            opponent_id=opp_user.id,
            result=host_result,
        )
    )
    db.add(
        EloHistory(
            user_id=opp_user.id,
            duel_id=duel.id,
            elo_before=opp_before,
            elo_after=opp_user.elo,
            delta=opp_delta,
            opponent_id=host_user.id,
            result=opp_result,
        )
    )

    duel.status = "complete"
    duel.winner_id = winner_user_id
    duel.finished_at = datetime.utcnow()

    # Streak ticks (after ELO so streak.timezone defaults work)
    tick_streak(db, host_user, duel.finished_at)
    tick_streak(db, opp_user, duel.finished_at)

    # Quest evaluation
    try:
        evaluate_after_duel(db, host_user, duel, host_result, opp_before)
        evaluate_after_duel(db, opp_user, duel, opp_result, host_before)
    except Exception:
        log.exception("quest evaluation failed for duel %s", duel.id)

    # Detect tier promotion/demotion for each side
    def _tier_change(before: int, after: int) -> str | None:
        bt = tier_for_elo(before).key
        at = tier_for_elo(after).key
        if bt == at:
            return None
        # promoted upward if min_elo of new tier > max_elo of old
        return "promoted" if tier_for_elo(after).min_elo > tier_for_elo(before).max_elo else "demoted"

    host_change = _tier_change(host_before, host_user.elo)
    opp_change = _tier_change(opp_before, opp_user.elo)

    promotion_for: str | None = None
    if host_change == "promoted":
        promotion_for = host_user.id
    elif opp_change == "promoted":
        promotion_for = opp_user.id

    new_tier: str | None = None
    if promotion_for == host_user.id:
        new_tier = tier_for_elo(host_user.elo).key
    elif promotion_for == opp_user.id:
        new_tier = tier_for_elo(opp_user.elo).key

    demotion_for: str | None = None
    if host_change == "demoted":
        demotion_for = host_user.id
    elif opp_change == "demoted":
        demotion_for = opp_user.id

    elo_changes = {
        host_user.id: {
            "before": host_before,
            "after": host_user.elo,
            "delta": host_delta,
        },
        opp_user.id: {
            "before": opp_before,
            "after": opp_user.elo,
            "delta": opp_delta,
        },
    }

    payload = {
        "winner_id": winner_user_id,
        "promotion_for": promotion_for,
        "new_tier": new_tier,
        "demotion_for": demotion_for,
        "elo_changes": elo_changes,
    }

    # Persist a duel_complete ReplayEvent so /replay can reconstruct the ending
    ts_offset_ms = (
        int((duel.finished_at - duel.started_at).total_seconds() * 1000)
        if duel.started_at and duel.finished_at
        else 0
    )
    db.add(
        ReplayEvent(
            duel_id=duel.id,
            ts_offset_ms=ts_offset_ms,
            user_id=None,
            event_type="duel_complete",
            payload_json=json.dumps(payload),
        )
    )

    _track_focus(db, host_user, duel)
    _track_focus(db, opp_user, duel)

    db.commit()

    await hub.broadcast("duel", duel.id, {"type": "duel_complete", "payload": payload})
    return payload


def _track_focus(db: Session, user: User, duel: Duel) -> None:
    now = datetime.utcnow()
    tags_seen: set[str] = set()
    for step in duel.steps:
        if not step.problem_tags_json:
            continue
        try:
            tags = json.loads(step.problem_tags_json)
            if isinstance(tags, list):
                tags_seen.update(t.lower().strip() for t in tags if isinstance(t, str))
        except (json.JSONDecodeError, TypeError):
            continue

    for tag in tags_seen:
        existing = (
            db.query(UserFocus)
            .filter(UserFocus.user_id == user.id, UserFocus.tag == tag)
            .first()
        )
        if existing:
            existing.practice_count += 1
            existing.last_practiced_at = now
        else:
            db.add(UserFocus(user_id=user.id, tag=tag, practice_count=1, last_practiced_at=now))
