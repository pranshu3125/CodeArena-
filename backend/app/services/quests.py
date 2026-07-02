from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models import Duel, DuelStep, Quest, QuestProgress, User


@dataclass
class QuestRollResult:
    daily: list[QuestProgress]
    weekly: list[QuestProgress]


QUEST_SEEDS = [
    # daily
    {
        "slug": "daily_win_2",
        "title_template": "Win 2 ladders today",
        "kind": "daily",
        "rule": {"type": "wins", "target": 2},
        "xp_reward": 150,
    },
    {
        "slug": "daily_win_1",
        "title_template": "Win 1 ladder today",
        "kind": "daily",
        "rule": {"type": "wins", "target": 1},
        "xp_reward": 75,
    },
    {
        "slug": "daily_clear_1600",
        "title_template": "Clear a 1600+ rated step",
        "kind": "daily",
        "rule": {"type": "clear_rating", "min_rating": 1600},
        "xp_reward": 200,
    },
    {
        "slug": "daily_clear_1900",
        "title_template": "Clear a 1900+ rated step",
        "kind": "daily",
        "rule": {"type": "clear_rating", "min_rating": 1900},
        "xp_reward": 350,
    },
    {
        "slug": "daily_no_wa",
        "title_template": "Win a duel without a wrong submission",
        "kind": "daily",
        "rule": {"type": "win_no_wa"},
        "xp_reward": 300,
    },
    {
        "slug": "daily_under_15",
        "title_template": "Win a duel in under 15 minutes",
        "kind": "daily",
        "rule": {"type": "win_under_seconds", "seconds": 900},
        "xp_reward": 250,
    },
    {
        "slug": "daily_beat_higher",
        "title_template": "Beat an opponent rated higher than you",
        "kind": "daily",
        "rule": {"type": "win_vs_higher_elo"},
        "xp_reward": 200,
    },
    # weekly
    {
        "slug": "weekly_win_10",
        "title_template": "Win 10 ladders this week",
        "kind": "weekly",
        "rule": {"type": "wins", "target": 10},
        "xp_reward": 1000,
        "shield_reward": 1,
    },
    {
        "slug": "weekly_streak_5",
        "title_template": "Reach a 5-day streak this week",
        "kind": "weekly",
        "rule": {"type": "streak_reach", "target": 5},
        "xp_reward": 800,
    },
    {
        "slug": "weekly_clear_2100",
        "title_template": "Clear a 2100+ rated step this week",
        "kind": "weekly",
        "rule": {"type": "clear_rating", "min_rating": 2100},
        "xp_reward": 1500,
    },
]


def seed_quests(db: Session) -> None:
    for seed in QUEST_SEEDS:
        existing = db.query(Quest).filter(Quest.slug == seed["slug"]).first()
        if existing:
            continue
        db.add(
            Quest(
                slug=seed["slug"],
                title_template=seed["title_template"],
                kind=seed["kind"],
                rule_json=json.dumps(seed["rule"]),
                xp_reward=seed.get("xp_reward", 0),
                shard_reward=seed.get("shard_reward", 0),
                shield_reward=seed.get("shield_reward", 0),
            )
        )
    db.commit()


def _local_today(tz_name: str | None) -> str:
    now_utc = datetime.now(timezone.utc)
    if tz_name:
        try:
            return now_utc.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
        except ZoneInfoNotFoundError:
            pass
    return now_utc.strftime("%Y-%m-%d")


def _week_anchor(tz_name: str | None) -> str:
    now_utc = datetime.now(timezone.utc)
    if tz_name:
        try:
            local = now_utc.astimezone(ZoneInfo(tz_name))
        except ZoneInfoNotFoundError:
            local = now_utc
    else:
        local = now_utc
    monday = local - timedelta(days=local.weekday())
    return monday.strftime("%Y-%m-%d")


def roll_today_for(db: Session, user: User) -> QuestRollResult:
    """Ensure today's daily quests (3) + this week's weekly (1) exist for the user.

    Returns the active progress rows."""
    daily_pool = (
        db.query(Quest).filter(Quest.kind == "daily").order_by(Quest.id.asc()).all()
    )
    weekly_pool = (
        db.query(Quest).filter(Quest.kind == "weekly").order_by(Quest.id.asc()).all()
    )

    today = _local_today(user.timezone)
    week = _week_anchor(user.timezone)

    # rotate by hash of (user_id, date) to keep stable for the day
    import hashlib

    def _stable_pick(pool: list[Quest], n: int, salt: str) -> list[Quest]:
        if not pool:
            return []
        seeds = sorted(
            pool,
            key=lambda q: hashlib.sha1(f"{user.id}:{salt}:{q.slug}".encode()).hexdigest(),
        )
        return seeds[:n]

    daily_picks = _stable_pick(daily_pool, 3, today)
    weekly_picks = _stable_pick(weekly_pool, 1, week)

    daily_progress: list[QuestProgress] = []
    for q in daily_picks:
        row = (
            db.query(QuestProgress)
            .filter(
                QuestProgress.user_id == user.id,
                QuestProgress.quest_id == q.id,
                QuestProgress.rolled_for_date == today,
            )
            .first()
        )
        if row is None:
            row = QuestProgress(
                user_id=user.id,
                quest_id=q.id,
                rolled_for_date=today,
                progress_json="{}",
            )
            db.add(row)
            db.flush()
        daily_progress.append(row)

    weekly_progress: list[QuestProgress] = []
    for q in weekly_picks:
        row = (
            db.query(QuestProgress)
            .filter(
                QuestProgress.user_id == user.id,
                QuestProgress.quest_id == q.id,
                QuestProgress.rolled_for_date == week,
            )
            .first()
        )
        if row is None:
            row = QuestProgress(
                user_id=user.id,
                quest_id=q.id,
                rolled_for_date=week,
                progress_json="{}",
            )
            db.add(row)
            db.flush()
        weekly_progress.append(row)

    db.commit()
    return QuestRollResult(daily=daily_progress, weekly=weekly_progress)


# ---------- evaluation ----------


def _max_step_rating_solved(db: Session, duel: Duel, user_id: str) -> int:
    """Highest-rated step this user solved in this duel (0 if none)."""
    from app.models import DuelParticipant

    parts = (
        db.query(DuelParticipant)
        .filter(DuelParticipant.duel_id == duel.id)
        .order_by(DuelParticipant.joined_at.asc())
        .all()
    )
    if not parts:
        return 0
    from app.services.duel_roles import is_duel_host

    is_host = is_duel_host(duel, user_id)
    steps = db.query(DuelStep).filter(DuelStep.duel_id == duel.id).all()
    ratings = [
        s.rating
        for s in steps
        if (s.host_status if is_host else s.opponent_status) == "solved"
    ]
    return max(ratings) if ratings else 0


def _had_wa_in_duel(db: Session, duel_id: str, user_id: str) -> bool:
    from app.models import ReplayEvent

    rows = (
        db.query(ReplayEvent)
        .filter(
            ReplayEvent.duel_id == duel_id,
            ReplayEvent.user_id == user_id,
            ReplayEvent.event_type == "verdict",
        )
        .all()
    )
    for r in rows:
        try:
            payload = json.loads(r.payload_json or "{}")
            if payload.get("verdict") not in ("AC", "RUNNING", "PENDING"):
                return True
        except Exception:
            pass
    return False


def evaluate_after_duel(
    db: Session,
    user: User,
    duel: Duel,
    result: str,  # "win" | "loss" | "draw"
    opponent_elo: int,
) -> list[QuestProgress]:
    """Update quest progress for this user given the duel outcome. Returns completed progress rows."""
    roll = roll_today_for(db, user)
    active = roll.daily + roll.weekly

    duration_s = (
        int((duel.finished_at - duel.started_at).total_seconds())
        if duel.finished_at and duel.started_at
        else 0
    )

    completed: list[QuestProgress] = []
    for progress in active:
        if progress.completed_at is not None:
            continue
        quest = db.query(Quest).filter(Quest.id == progress.quest_id).first()
        if not quest:
            continue
        try:
            rule = json.loads(quest.rule_json)
            prog = json.loads(progress.progress_json or "{}")
        except Exception:
            continue

        rtype = rule.get("type")
        bumped = False

        if rtype == "wins":
            target = int(rule.get("target", 1))
            if result == "win":
                cur = int(prog.get("count", 0)) + 1
                prog["count"] = cur
                bumped = True
                if cur >= target:
                    progress.completed_at = datetime.utcnow()
                    completed.append(progress)
            prog.setdefault("target", target)

        elif rtype == "clear_rating":
            min_rating = int(rule.get("min_rating", 0))
            max_solved = _max_step_rating_solved(db, duel, user.id)
            if max_solved >= min_rating:
                progress.completed_at = datetime.utcnow()
                prog["best_rating_solved"] = max_solved
                completed.append(progress)
                bumped = True

        elif rtype == "win_no_wa":
            if result == "win" and not _had_wa_in_duel(db, duel.id, user.id):
                progress.completed_at = datetime.utcnow()
                completed.append(progress)
                bumped = True

        elif rtype == "win_under_seconds":
            max_s = int(rule.get("seconds", 1_000_000))
            if result == "win" and 0 < duration_s <= max_s:
                progress.completed_at = datetime.utcnow()
                completed.append(progress)
                prog["duration_s"] = duration_s
                bumped = True

        elif rtype == "win_vs_higher_elo":
            if result == "win" and opponent_elo > (user.elo or 1200):
                progress.completed_at = datetime.utcnow()
                completed.append(progress)
                bumped = True

        elif rtype == "streak_reach":
            target = int(rule.get("target", 1))
            from app.models import Streak
            row = db.query(Streak).filter(Streak.user_id == user.id).first()
            cur = (row.current_count if row else 0) or 0
            if cur >= target:
                progress.completed_at = datetime.utcnow()
                prog["streak_at_completion"] = cur
                completed.append(progress)
                bumped = True

        if bumped:
            progress.progress_json = json.dumps(prog)

    db.commit()
    return completed
