import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class ProjectBase(DeclarativeBase):
    pass


class DBProjectMetadata(ProjectBase):
    """
    Reserved key/value table for per-chronicle provenance (source tool, import settings,
    schema notes).
    """

    __tablename__ = "metadata"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(String)


class DBSpeaker(ProjectBase):
    __tablename__ = "speakers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255))


class DBTranscriptLine(ProjectBase):
    __tablename__ = "transcript_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    speaker_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("speakers.id"))
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(String)

    speaker: Mapped[DBSpeaker | None] = relationship(lazy="selectin")


class DBAudioSource(ProjectBase):
    __tablename__ = "audio_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename: Mapped[str] = mapped_column(String(1024), unique=True)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    speaker_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("speakers.id"))

    transcription_state: Mapped[str] = mapped_column(String(20), default="PENDING")
    transcription_error: Mapped[str | None] = mapped_column(String)
    transcribed_at: Mapped[datetime | None] = mapped_column(DateTime)
    transcribed_hash: Mapped[str | None] = mapped_column(String(64))
    transcription_language: Mapped[str | None] = mapped_column(String(16))
    transcription_model: Mapped[str | None] = mapped_column(String(64))

    normalization_state: Mapped[str] = mapped_column(String(20), default="PENDING")
    normalization_error: Mapped[str | None] = mapped_column(String)
    normalized_at: Mapped[datetime | None] = mapped_column(DateTime)
    normalized_hash: Mapped[str | None] = mapped_column(String(64))
    normalized_filename: Mapped[str | None] = mapped_column(String(1024))
    loudness_before: Mapped[float | None] = mapped_column(Float)
    loudness_after: Mapped[float | None] = mapped_column(Float)

    speaker: Mapped[DBSpeaker | None] = relationship(lazy="selectin")


class DBSummary(ProjectBase):
    __tablename__ = "summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(String)
    model: Mapped[str | None] = mapped_column(String(255))
    provider: Mapped[str | None] = mapped_column(String(64))
    prompt_template: Mapped[str | None] = mapped_column(String)
    language: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
