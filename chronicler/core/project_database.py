import uuid

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class ProjectBase(DeclarativeBase):
    pass


class DBProjectMetadata(ProjectBase):
    """Reserved key/value table for per-chronicle provenance (source tool, import
    settings, schema notes). Nothing reads or writes it yet - it's kept in sync with
    the baseline migration that already creates the table rather than dropped, so the
    ORM metadata and the on-disk schema don't disagree. See TODO.md Phase 2.
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
