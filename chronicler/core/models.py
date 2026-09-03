import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    WORKING = "WORKING"
    DONE = "DONE"
    FAILED = "FAILED"


class SourceState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class TaskType(str, Enum):
    IMPORT = "IMPORT"
    TRANSCRIBE = "TRANSCRIBE"
    NORMALIZE = "NORMALIZE"
    SUMMARIZE = "SUMMARIZE"
    PROCESS = "PROCESS"
    CLEAN = "CLEAN"
    EXPORT = "EXPORT"
    TEST = "TEST"


class Tag(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    color: str | None = None

    model_config = ConfigDict(from_attributes=True)


class KnownSpeaker(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    uses: int = 0
    first_seen: datetime = Field(default_factory=datetime.now)
    last_used: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(from_attributes=True)


class Speaker(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str

    model_config = ConfigDict(from_attributes=True)


class TranscriptLine(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    speaker_id: uuid.UUID | None = None
    speaker_name: str | None = None
    chronicle_id: uuid.UUID | None = None
    start_time: float
    end_time: float
    text: str

    model_config = ConfigDict(from_attributes=True)


class Chronicle(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str
    description: str | None = None
    kind: str = "Unknown"
    status: str = "Imported"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    source_file: str | None = None
    project_path: str | None = None
    duration: str | None = None
    speakers_count: int = 0

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
    chronicle_id: uuid.UUID | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    attempts: int = 0
    max_attempts: int = 3

    model_config = ConfigDict(from_attributes=True)


class AudioSource(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    filename: str
    path: str | None = None
    content_hash: str | None = None
    size_bytes: int | None = None
    duration_seconds: float | None = None
    added_at: datetime = Field(default_factory=datetime.now)
    missing: bool = False

    speaker_id: uuid.UUID | None = None
    speaker_name: str | None = None

    transcription_state: SourceState = SourceState.PENDING
    transcription_error: str | None = None
    transcribed_at: datetime | None = None
    transcribed_hash: str | None = None
    transcription_language: str | None = None
    transcription_model: str | None = None

    normalization_state: SourceState = SourceState.PENDING
    normalization_error: str | None = None
    normalized_at: datetime | None = None
    normalized_hash: str | None = None
    normalized_filename: str | None = None
    loudness_before: float | None = None
    loudness_after: float | None = None

    model_config = ConfigDict(from_attributes=True)

    @property
    def is_transcribed(self) -> bool:
        """True only when the transcribed content is still the content on disk."""
        return (
            self.transcription_state == SourceState.DONE
            and self.transcribed_hash is not None
            and self.transcribed_hash == self.content_hash
        )

    @property
    def is_normalized(self) -> bool:
        """True only when the normalized content is still the content on disk."""
        return (
            self.normalization_state == SourceState.DONE
            and self.normalized_hash is not None
            and self.normalized_hash == self.content_hash
            and self.normalized_filename is not None
        )


class ServerInfo(BaseModel):
    version: str
    chronicle_count: int | None = None
    capabilities: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class Summary(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    number: int
    title: str | None = None
    content: str
    model: str | None = None
    provider: str | None = None
    prompt_template: str | None = None
    language: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    chunk_count: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
