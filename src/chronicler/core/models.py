import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    WAITING = "WAITING"
    WORKING = "WORKING"
    DONE = "DONE"
    FAILED = "FAILED"


class TaskType(str, Enum):
    IMPORT = "IMPORT"
    TRANSCRIBE = "TRANSCRIBE"
    CLEAN = "CLEAN"
    EXPORT = "EXPORT"
    TEST = "TEST"


class Tag(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    color: str | None = None

    model_config = ConfigDict(from_attributes=True)


class Speaker(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str

    model_config = ConfigDict(from_attributes=True)


class TranscriptLine(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    speaker_id: uuid.UUID | None = None
    speaker_name: str | None = None
    start_time: float  # seconds
    end_time: float  # seconds
    text: str

    model_config = ConfigDict(from_attributes=True)


class Chronicle(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str
    description: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    source_file: str | None = None

    tags: list[Tag] = []

    model_config = ConfigDict(from_attributes=True)


class Task(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    progress: int = 0
    data: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    chronicle_id: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)
