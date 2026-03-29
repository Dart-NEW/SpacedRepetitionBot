"""SQLAlchemy database configuration and record models."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    create_engine,
    event,
    inspect,
    text,
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
    __table_args__ = (
        Index("ix_cards_user_created_at", "user_id", "created_at"),
        Index(
            "ix_cards_user_learning_status",
            "user_id",
            "learning_status",
        ),
    )

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
    __table_args__ = (
        Index("ix_review_tracks_card_direction", "card_id", "direction"),
        Index("ix_review_tracks_next_review_at", "next_review_at"),
    )

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
    pending_reviews_json: Mapped[str] = mapped_column(
        Text, default="[]", server_default="[]"
    )
    total_prompts: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )
    due_reviews_total: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )
    answered_prompts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    correct_prompts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    incorrect_prompts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    awaiting_start: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )
    message_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )


def build_engine(database_url: str) -> Engine:
    """Build the SQLAlchemy engine."""

    if database_url == "sqlite:///:memory:":
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        _configure_sqlite_engine(engine, enable_wal=False)
        return engine
    if database_url.startswith("sqlite"):
        engine = create_engine(
            database_url,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
        )
        _configure_sqlite_engine(engine, enable_wal=True)
        return engine
    return create_engine(database_url)


def build_session_factory(engine: Engine) -> sessionmaker:
    """Create a SQLAlchemy session factory."""

    return sessionmaker(bind=engine, expire_on_commit=False)


def initialize_database(engine: Engine) -> None:
    """Create all tables for the MVP schema."""

    Base.metadata.create_all(engine)
    _upgrade_database_schema(engine)


def _configure_sqlite_engine(engine: Engine, *, enable_wal: bool) -> None:
    """Apply SQLite pragmas that improve concurrent local usage."""

    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA cache_size=-20000")
        if enable_wal:
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def _upgrade_database_schema(engine: Engine) -> None:
    """Apply lightweight schema upgrades for existing local databases."""

    inspector = inspect(engine)
    if "telegram_quiz_sessions" not in inspector.get_table_names():
        return
    columns = {
        column["name"]
        for column in inspector.get_columns("telegram_quiz_sessions")
    }
    upgrades = {
        "pending_reviews_json": "TEXT NOT NULL DEFAULT '[]'",
        "total_prompts": "INTEGER NOT NULL DEFAULT 1",
        "due_reviews_total": "INTEGER NOT NULL DEFAULT 1",
        "answered_prompts": "INTEGER NOT NULL DEFAULT 0",
        "correct_prompts": "INTEGER NOT NULL DEFAULT 0",
        "incorrect_prompts": "INTEGER NOT NULL DEFAULT 0",
        "awaiting_start": "BOOLEAN NOT NULL DEFAULT 1",
        "message_id": "INTEGER",
    }
    with engine.begin() as connection:
        for column_name, ddl in upgrades.items():
            if column_name in columns:
                continue
            connection.execute(
                text(
                    "ALTER TABLE telegram_quiz_sessions "
                    f"ADD COLUMN {column_name} {ddl}"
                )
            )
