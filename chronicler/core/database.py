import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


chronicle_tags = Table(
    "chronicle_tags",
    Base.metadata,
    Column("chronicle_id", String(36), ForeignKey("chronicles.id"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tags.id"), primary_key=True),
)


class DBTag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True)
    color: Mapped[str | None] = mapped_column(String(50))


class DBChronicle(Base):
    __tablename__ = "chronicles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(1000))
    kind: Mapped[str] = mapped_column(String(100), default="Unknown")
    status: Mapped[str] = mapped_column(String(50), default="Imported")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    source_file: Mapped[str | None] = mapped_column(String(1024))
    project_path: Mapped[str | None] = mapped_column(String(1024))
    duration: Mapped[str | None] = mapped_column(String(50))
    speakers_count: Mapped[int] = mapped_column(default=0)

    tags: Mapped[list[DBTag]] = relationship(secondary=chronicle_tags, lazy="selectin")


class DBTask(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    priority: Mapped[int] = mapped_column(default=0)
    progress: Mapped[int] = mapped_column(default=0)
    data: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    chronicle_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("chronicles.id"))
    claimed_by: Mapped[str | None] = mapped_column(String(36))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)


class DBKnownSpeaker(Base):
    __tablename__ = "known_speakers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True)
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_used: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
