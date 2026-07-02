import uuid
from datetime import datetime, timezone

import pytest

from app.db import Base, engine, SessionLocal
from app.models import Duel, DuelParticipant, Quest, QuestProgress, User
from app.services.quests import evaluate_after_duel, seed_quests, roll_today_for


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


def _unique_user(db) -> User:
    uid = uuid.uuid4().hex[:8]
    u = User(username=f"q_{uid}", email=None, hashed_password="x", elo=1200)
    db.add(u)
    db.flush()
    db.refresh(u)
    return u


def _make_duel(db, user1_id: str, user2_id: str) -> Duel:
    duel = Duel(
        host_id=user1_id,
        status="complete",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        format="speedrun_ladder",
    )
    db.add(duel)
    db.flush()
    db.add(DuelParticipant(duel_id=duel.id, user_id=user1_id, current_rating=1200))
    db.add(DuelParticipant(duel_id=duel.id, user_id=user2_id, current_rating=1200))
    db.flush()
    db.refresh(duel)
    return duel


class TestQuestEvaluation:
    def test_seed_quests_creates_templates(self, db):
        seed_quests(db)
        count = db.query(Quest).count()
        assert count >= 10

    def test_seed_quests_is_idempotent(self, db):
        count1 = db.query(Quest).count()
        seed_quests(db)
        count2 = db.query(Quest).count()
        assert count1 == count2

    def test_roll_today_for_creates_quests(self, db):
        seed_quests(db)
        user = _unique_user(db)
        result = roll_today_for(db, user)
        assert len(result.daily) == 3
        assert len(result.weekly) == 1

    def test_evaluate_win_returns_list(self, db):
        seed_quests(db)
        user = _unique_user(db)
        opp = _unique_user(db)
        duel = _make_duel(db, user.id, opp.id)
        completed = evaluate_after_duel(db, user, duel, "win", 1200)
        assert isinstance(completed, list)

    def test_evaluate_loss_returns_empty(self, db):
        seed_quests(db)
        user = _unique_user(db)
        opp = _unique_user(db)
        duel = _make_duel(db, user.id, opp.id)
        completed = evaluate_after_duel(db, user, duel, "loss", 1200)
        assert isinstance(completed, list)

    def test_quest_claim_marks_completed(self, db):
        seed_quests(db)
        user = _unique_user(db)
        opp = _unique_user(db)
        duel = _make_duel(db, user.id, opp.id)
        completed = evaluate_after_duel(db, user, duel, "win", 1200)
        for c in completed:
            assert c.completed_at is not None
            assert c.claimed_at is None
