from datetime import datetime
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .db import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=True)
    hashed_password = Column(String(255), nullable=True)

    xp = Column(Integer, default=0)
    cf_handle = Column(String(100), nullable=True, index=True)
    cf_rating = Column(Integer, default=0)
    cf_rank = Column(String(50), nullable=True)
    solved_count = Column(Integer, default=0)

    role = Column(String(16), default="user", nullable=False)  # user | moderator | admin | superadmin
    is_suspended = Column(Boolean, default=False, nullable=False)

    elo = Column(Integer, default=1200, nullable=False)
    timezone = Column(String(64), nullable=True)

    duel_wins = Column(Integer, default=0)
    duel_losses = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    submissions = relationship("Submission", back_populates="user", cascade="all, delete-orphan")
    rooms = relationship("Room", back_populates="host")
    chat_messages = relationship("ChatMessage", back_populates="user")
    practice_items = relationship("PracticeSheetItem", back_populates="user", cascade="all, delete-orphan")
    duel_participations = relationship("DuelParticipant", back_populates="user", cascade="all, delete-orphan")
    focus_progress = relationship("UserFocus", back_populates="user", cascade="all, delete-orphan")


class Duel(Base):
    __tablename__ = "duels"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    host_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    max_participants = Column(Integer, default=5, nullable=False)
    rating_target = Column(Integer, default=1200, nullable=False)

    problem_id = Column(String(128), nullable=True)
    problem_name = Column(String(255), nullable=True)
    problem_rating = Column(Integer, nullable=True)

    status = Column(String(32), default="waiting", nullable=False)  # waiting, active, finished
    winner_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    format = Column(String(32), default="speedrun_ladder", nullable=False)
    time_cap_seconds = Column(Integer, default=2700, nullable=False)

    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    participants = relationship("DuelParticipant", back_populates="duel", cascade="all, delete-orphan")
    submissions = relationship("Submission", back_populates="duel")
    chat_messages = relationship("ChatMessage", back_populates="duel")
    steps = relationship("DuelStep", back_populates="duel", cascade="all, delete-orphan")


class DuelParticipant(Base):
    __tablename__ = "duel_participants"
    __table_args__ = (
        UniqueConstraint("duel_id", "user_id", name="uq_duel_participant_duel_user"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    duel_id = Column(String(36), ForeignKey("duels.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    current_rating = Column(Integer, default=0, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="duel_participations")
    duel = relationship("Duel", back_populates="participants")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    duel_id = Column(String(36), ForeignKey("duels.id"), nullable=True)
    room_id = Column(String(36), ForeignKey("rooms.id"), nullable=True)
    problem_id = Column(String(128), nullable=False)
    language = Column(String(16), nullable=False)
    code = Column(Text, nullable=False)
    status = Column(String(32), default="queued")
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    runtime_ms = Column(Integer, nullable=True)
    memory_kb = Column(Integer, nullable=True)
    score = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="submissions")
    duel = relationship("Duel", back_populates="submissions")
    room = relationship("Room", back_populates="submissions")


class Room(Base):
    __tablename__ = "rooms"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    host_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    title = Column(String(128), nullable=True)
    problem_id = Column(String(128), nullable=True)
    max_participants = Column(Integer, default=4)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    host = relationship("User", back_populates="rooms")
    submissions = relationship("Submission", back_populates="room")
    chat_messages = relationship("ChatMessage", back_populates="room")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    room_id = Column(String(36), ForeignKey("rooms.id"), nullable=True)
    duel_id = Column(String(36), ForeignKey("duels.id"), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    room = relationship("Room", back_populates="chat_messages")
    duel = relationship("Duel", back_populates="chat_messages")
    user = relationship("User", back_populates="chat_messages")


class Problem(Base):
    __tablename__ = "problems"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    contest_id = Column(Integer, nullable=True, index=True)
    index = Column(String(10), nullable=False)
    name = Column(String(255), nullable=False)
    rating = Column(Integer, nullable=True)
    tags = Column(Text, nullable=True)
    time_limit = Column(Integer, nullable=True)
    memory_limit = Column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<Problem {self.contest_id}-{self.index} {self.name}>"


class SolvedProblem(Base):
    __tablename__ = "solved_problems"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    contest_id = Column(Integer)
    problem_index = Column(String)
    problem_name = Column(String)
    rating = Column(Integer)
    solved_at = Column(DateTime, default=datetime.utcnow)


class PracticeSheetItem(Base):
    __tablename__ = "practice_sheet_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    sheet_type = Column(String(32), index=True, nullable=False)  # div2, div3, personal, custom
    query_signature = Column(String(255), index=True, nullable=False)

    problem_id = Column(String(128), index=True, nullable=False)
    contest_id = Column(Integer, index=True, nullable=True)
    problem_index = Column(String(16), nullable=True)
    problem_name = Column(String(255), nullable=False)
    rating = Column(Integer, nullable=True)
    tags_json = Column(Text, nullable=True)

    status = Column(String(32), default="new", nullable=False)  # new, seen, solved, archived
    is_active = Column(Boolean, default=True, nullable=False)

    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="practice_items")

class DuelStep(Base):
    __tablename__ = "duel_steps"
    __table_args__ = (UniqueConstraint("duel_id", "step_index", name="uq_duel_step"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    duel_id = Column(String(36), ForeignKey("duels.id"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    rating = Column(Integer, nullable=False)

    problem_id = Column(String(128), nullable=False)
    problem_contest_id = Column(Integer, nullable=False)
    problem_index = Column(String(8), nullable=False)
    problem_name = Column(String(255), nullable=False)
    problem_tags_json = Column(Text, nullable=True)

    host_status = Column(String(16), default="pending", nullable=False)
    host_solved_at = Column(DateTime, nullable=True)
    opponent_status = Column(String(16), default="pending", nullable=False)
    opponent_solved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    duel = relationship("Duel", back_populates="steps")


class MatchmakingQueueEntry(Base):
    __tablename__ = "matchmaking_queue"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    mode = Column(String(32), default="speedrun_ladder", nullable=False)
    elo_at_enqueue = Column(Integer, nullable=False)
    deck_tags_json = Column(Text, nullable=True)
    enqueued_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=True)


class EloHistory(Base):
    __tablename__ = "elo_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    duel_id = Column(String(36), ForeignKey("duels.id"), nullable=False, index=True)
    elo_before = Column(Integer, nullable=False)
    elo_after = Column(Integer, nullable=False)
    delta = Column(Integer, nullable=False)
    opponent_id = Column(String(36), nullable=True)
    result = Column(String(8), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Streak(Base):
    __tablename__ = "streaks"

    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    current_count = Column(Integer, default=0, nullable=False)
    longest_count = Column(Integer, default=0, nullable=False)
    last_duel_local_date = Column(String(10), nullable=True)  # YYYY-MM-DD in user's tz
    shields_remaining = Column(Integer, default=0, nullable=False)
    timezone = Column(String(64), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Quest(Base):
    __tablename__ = "quests"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    slug = Column(String(64), unique=True, nullable=False, index=True)
    title_template = Column(String(255), nullable=False)
    kind = Column(String(16), nullable=False)  # daily | weekly
    rule_json = Column(Text, nullable=False)
    xp_reward = Column(Integer, default=0, nullable=False)
    shard_reward = Column(Integer, default=0, nullable=False)
    shield_reward = Column(Integer, default=0, nullable=False)


class QuestProgress(Base):
    __tablename__ = "quest_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "quest_id", "rolled_for_date", name="uq_quest_progress"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    quest_id = Column(String(36), ForeignKey("quests.id"), nullable=False, index=True)
    rolled_for_date = Column(String(10), nullable=False)  # YYYY-MM-DD local
    progress_json = Column(Text, nullable=False, default="{}")
    completed_at = Column(DateTime, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReplayEvent(Base):
    __tablename__ = "replay_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    duel_id = Column(String(36), ForeignKey("duels.id"), nullable=False, index=True)
    ts_offset_ms = Column(Integer, nullable=False)
    user_id = Column(String(36), nullable=True)
    event_type = Column(String(32), nullable=False)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class CosmeticUnlock(Base):
    __tablename__ = "cosmetic_unlocks"
    __table_args__ = (
        UniqueConstraint("user_id", "axis", "key", name="uq_cosmetic_unlock"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    axis = Column(String(16), nullable=False)  # banner | glyph
    key = Column(String(32), nullable=False)
    source = Column(String(32), nullable=True)  # tier_promo | quest | default
    unlocked_at = Column(DateTime, default=datetime.utcnow)


class EquippedCosmetic(Base):
    __tablename__ = "equipped_cosmetics"

    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    banner_key = Column(String(32), default="default", nullable=False)
    glyph_key = Column(String(32), default="default", nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Deck(Base):
    __tablename__ = "decks"

    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    tags_json = Column(Text, default="[]", nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FriendRoom(Base):
    __tablename__ = "friend_rooms"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    code = Column(String(8), unique=True, nullable=False, index=True)
    host_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    rating_preset = Column(String(16), default="medium", nullable=False)  # chill | medium | hard
    deck_tags_json = Column(Text, default="[]", nullable=False)
    duel_id = Column(String(36), nullable=True)  # populated when started
    status = Column(String(16), default="waiting", nullable=False)  # waiting | started | cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)


class AsyncChallenge(Base):
    __tablename__ = "async_challenges"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    sender_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    recipient_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(24), default="sent", nullable=False)
    # sent | sender_done | accepted | complete | expired
    problem_seed_json = Column(Text, nullable=False, default="[]")
    sender_steps_cleared = Column(Integer, default=0, nullable=False)
    recipient_steps_cleared = Column(Integer, default=0, nullable=False)
    sender_duration_s = Column(Integer, default=0, nullable=False)
    recipient_duration_s = Column(Integer, default=0, nullable=False)
    sender_started_at = Column(DateTime, nullable=True)
    sender_finished_at = Column(DateTime, nullable=True)
    recipient_started_at = Column(DateTime, nullable=True)
    recipient_finished_at = Column(DateTime, nullable=True)
    winner_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)


class UserFocus(Base):
    __tablename__ = "user_focus"
    __table_args__ = (UniqueConstraint("user_id", "tag", name="uq_user_focus_tag"),)

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    tag = Column(String(64), nullable=False)
    practice_count = Column(Integer, default=0, nullable=False)
    last_practiced_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="focus_progress")
