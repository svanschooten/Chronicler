from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
import uuid

class Tag(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    color: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class Speaker(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    
    model_config = ConfigDict(from_attributes=True)

class TranscriptLine(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    speaker_id: Optional[uuid.UUID] = None
    start_time: float # seconds
    end_time: float # seconds
    text: str
    
    model_config = ConfigDict(from_attributes=True)

class Chronicle(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    source_file: Optional[str] = None
    
    tags: List[Tag] = []
    
    model_config = ConfigDict(from_attributes=True)
