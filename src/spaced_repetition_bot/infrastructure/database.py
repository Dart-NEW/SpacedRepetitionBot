"""SQLAlchemy database configuration and record models."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class PhraseCardRecord(Base):
    """Database record for phrase cards."""

    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    source_text: Mapped[str] = mapped_column(Text)
    target_text: Mapped[str] = mapped_column(Text)
    source_lang: Mapped[str] = mapped_column(String(16))
    target_lang: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
    learning_status: Mapped[str] = mapped_column(String(32))
    archived_reason: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    review_tracks: Mapped[list["ReviewTrackRecord"]] = relationship(
        back_populates="card",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ReviewTrackRecord(Base):
    """Database record for directional review progress."""

    __tablename__ = "review_tracks"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    card_id: Mapped[str] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[str] = mapped_column(String(16))
    step_index: Mapped[int] = mapped_column(Integer)
    next_review_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    last_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    completed_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    card: Mapped[PhraseCardRecord] = relationship(
        back_populates="review_tracks"
    )


class UserSettingsRecord(Base):
    """Database record for user settings."""

    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    default_source_lang: Mapped[str] = mapped_column(String(16))
    default_target_lang: Mapped[str] = mapped_column(String(16))
    default_translation_direction: Mapped[str] = mapped_column(String(16))
    timezone: Mapped[str] = mapped_column(String(64))
    notification_time_local: Mapped[Time] = mapped_column(Time)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_notification_local_date: Mapped[Date | None] = mapped_column(
        Date, nullable=True
    )


class TelegramQuizSessionRecord(Base):
    """Database record for active Telegram quiz sessions."""

    __tablename__ = "telegram_quiz_sessions"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[str] = mapped_column(
        ForeignKey("cards.id", ondelete="CASCADE")
    )
    direction: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True))


def build_engine(database_url: str) -> Engine:
    """Build the SQLAlchemy engine."""

    if database_url == "sqlite:///:memory:":
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
    return create_engine(database_url)


def build_session_factory(engine: Engine) -> sessionmaker:
    """Create a SQLAlchemy session factory."""

    return sessionmaker(bind=engine, expire_on_commit=False)


def initialize_database(engine: Engine) -> None:
    """Create all tables for the MVP schema."""

    Base.metadata.create_all(engine)
