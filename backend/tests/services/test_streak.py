from datetime import datetime, timedelta, timezone

import pytest

from app.db import Base, engine, SessionLocal
from app.models import Streak, User
from app.services.streak import tick_streak


@pytest.fixture(scope="module", autouse=True)
def _create_tables():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _make_user(db, username: str, tz=None) -> User:
    tz = tz or "UTC"
    u = User(username=username, email=None, hashed_password="x", cf_handle=None, timezone=tz, elo=1200)
    db.add(u)
    db.flush()
    db.refresh(u)
    return u


def test_first_duel_starts_streak_at_1(db):
    user = _make_user(db, "tester_first")
    result = tick_streak(db, user, datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc))
    assert result.current_count == 1
    assert result.broke is False
    assert result.used_shield is False
    assert result.incremented is True


def test_same_day_no_change(db):
    user = _make_user(db, "tester_same")
    tick_streak(db, user, datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc))
    result = tick_streak(db, user, datetime(2026, 5, 22, 22, 0, tzinfo=timezone.utc))
    assert result.current_count == 1
    assert result.incremented is False


def test_next_day_increments(db):
    user = _make_user(db, "tester_next")
    tick_streak(db, user, datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc))
    result = tick_streak(db, user, datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc))
    assert result.current_count == 2
    assert result.incremented is True


def test_two_day_gap_breaks_without_shield(db):
    user = _make_user(db, "tester_break")
    tick_streak(db, user, datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc))
    tick_streak(db, user, datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc))
    # skip 5/24 then play 5/25
    result = tick_streak(db, user, datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc))
    assert result.broke is True
    assert result.current_count == 1


def test_seven_day_milestone_grants_shield(db):
    user = _make_user(db, "tester_shield")
    base = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
    for d in range(7):
        tick_streak(db, user, base + timedelta(days=d))
    row = db.query(Streak).filter(Streak.user_id == user.id).first()
    assert row.current_count == 7
    assert row.shields_remaining == 1


def test_shield_absorbs_missed_day(db):
    user = _make_user(db, "tester_absorb")
    base = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
    # play days 0..6 → reach 7-day streak, earn 1 shield
    for d in range(7):
        tick_streak(db, user, base + timedelta(days=d))
    # skip day 7, return day 8 → 1 missed day, shield should absorb it
    result = tick_streak(db, user, base + timedelta(days=8))
    assert result.used_shield is True
    assert result.broke is False
    assert result.current_count == 8

    row = db.query(Streak).filter(Streak.user_id == user.id).first()
    assert row.shields_remaining == 0
