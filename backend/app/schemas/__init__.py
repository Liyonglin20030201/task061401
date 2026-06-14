from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ===== Auth Schemas =====

class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: UUID
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None


# ===== Knowledge Base Schemas =====

class KBCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    access_level: str = "internal"


class KBUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    access_level: Optional[str] = None


class KBOut(BaseModel):
    id: UUID
    name: str
    description: str
    access_level: str
    owner_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class KBAccessGrant(BaseModel):
    user_id: UUID
    permission: str = "read"


# ===== Document Schemas =====

class DocumentOut(BaseModel):
    id: UUID
    kb_id: UUID
    title: str
    file_type: str
    status: str
    version: int
    uploaded_by: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChunkOut(BaseModel):
    id: UUID
    chunk_index: int
    content: str
    token_count: int
    metadata_: Optional[dict] = None

    class Config:
        from_attributes = True


# ===== Chat Schemas =====

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4096)
    conversation_id: Optional[UUID] = None
    kb_id: UUID


class Citation(BaseModel):
    chunk_id: UUID
    score: float
    snippet: str
    document_title: str
    page_info: Optional[str] = None


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    citations: Optional[list] = []
    is_corrected: bool = False
    corrected_content: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: UUID
    kb_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CorrectionRequest(BaseModel):
    corrected_content: str = Field(min_length=1)


# ===== Feedback Schemas =====

class FeedbackCreate(BaseModel):
    message_id: UUID
    rating: int = Field(ge=1, le=5)
    comment: str = ""


class FeedbackOut(BaseModel):
    id: UUID
    message_id: UUID
    user_id: UUID
    rating: int
    comment: str
    created_at: datetime

    class Config:
        from_attributes = True


class FeedbackStats(BaseModel):
    total_feedback: int
    average_rating: float
    rating_distribution: dict
    recent_negative: list


# ===== Admin Schemas =====

class SensitiveWordCreate(BaseModel):
    word: str = Field(min_length=1, max_length=128)
    category: str = "general"


class SensitiveWordOut(BaseModel):
    id: int
    word: str
    category: str
    is_active: bool

    class Config:
        from_attributes = True


class SystemConfigUpdate(BaseModel):
    key: str
    value: dict


class DashboardStats(BaseModel):
    total_users: int
    total_documents: int
    total_conversations: int
    total_messages: int
    avg_rating: float
    documents_by_status: dict
