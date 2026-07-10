from datetime import datetime
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Float, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing import List, Optional

class Base(DeclarativeBase):
    pass

# Association table for Chronicles and Tags
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
    color: Mapped[Optional[str]] = mapped_column(String(50))

class DBChronicle(Base):
    __tablename__ = "chronicles"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    source_file: Mapped[Optional[str]] = mapped_column(String(1024))
    
    tags: Mapped[List[DBTag]] = relationship(secondary=chronicle_tags, lazy="selectin")

class DBTask(Base):
    __tablename__ = "tasks"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type: Mapped[str] = mapped_column(String(50)) # e.g., IMPORT, TRANSCRIBE
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    priority: Mapped[int] = mapped_column(default=0)
    data: Mapped[Optional[str]] = mapped_column(String) # JSON data
    error: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    chronicle_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("chronicles.id"))
