import uuid
from datetime import datetime
from typing import Optional, List, Any

from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    Enum,
    Boolean,
    BigInteger,
    Index,
    JSON,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field

from .base import Base


class Conversation(Base):
    __tablename__ = "conversations"
    conversation_id = Column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    type = Column(
        Enum("direct", "group", name="conversation_type"),
        nullable=False,
        default="direct",
    )
    name = Column(String, nullable=True)
    tenant_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_seq = Column(BigInteger, default=0)

    members = relationship(
        "ConversationMember",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    messages = relationship(
        "IMMessage", back_populates="conversation", cascade="all, delete-orphan"
    )


class ConversationMember(Base):
    __tablename__ = "conversation_members"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(
        String, ForeignKey("conversations.conversation_id"), nullable=False, index=True
    )
    user_id = Column(String, nullable=False, index=True)
    role = Column(
        Enum("owner", "member", "assistant", name="conversation_member_role"),
        nullable=False,
        default="member",
    )
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_read_message_id = Column(String, nullable=True)
    last_read_seq = Column(BigInteger, default=0)
    muted = Column(Boolean, default=False)
    tenant_id = Column(String, nullable=True, index=True)

    conversation = relationship("Conversation", back_populates="members")


class IMMessage(Base):
    __tablename__ = "im_messages"
    message_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(
        String, ForeignKey("conversations.conversation_id"), nullable=False, index=True
    )
    sender_id = Column(String, nullable=False, index=True)
    type = Column(
        Enum(
            "text",
            "image",
            "file",
            "audio",
            "video",
            "system",
            "ai",
            "stream_chunk",
            name="message_type",
        ),
        nullable=False,
        default="text",
    )
    content = Column(JSON, nullable=False)
    reply_to = Column(String, nullable=True)
    client_msg_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    seq = Column(BigInteger, nullable=True, index=True)
    edited_at = Column(DateTime, nullable=True)
    status = Column(
        Enum("sent", "delivered", "read", name="message_status"),
        nullable=False,
        default="sent",
    )
    tenant_id = Column(String, nullable=True, index=True)
    # 流式消息字段（可选）
    stream_id = Column(String, nullable=True, index=True)
    chunk_index = Column(Integer, nullable=True)
    is_end = Column(Boolean, default=False)

    conversation = relationship("Conversation", back_populates="messages")


Index("idx_messages_conv_seq", IMMessage.conversation_id, IMMessage.seq)
IMMessage.__table_args__ = (
    UniqueConstraint(
        "conversation_id", "sender_id", "client_msg_id", name="uq_msg_idempotent"
    ),
)


class MessageReceipt(Base):
    __tablename__ = "message_receipts"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(
        String, ForeignKey("im_messages.message_id"), nullable=False, index=True
    )
    conversation_id = Column(
        String, ForeignKey("conversations.conversation_id"), nullable=False, index=True
    )
    user_id = Column(String, nullable=False, index=True)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    tenant_id = Column(String, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_receipt_msg_user"),
    )


class ConversationCreateRequest(BaseModel):
    type: str = Field("direct", pattern="^(direct|group)$")
    name: Optional[str] = None
    member_ids: List[str] = Field(..., min_items=1)
    tenant_id: Optional[str] = None


class ConversationInfo(BaseModel):
    conversation_id: str
    type: str
    name: Optional[str]
    created_at: datetime
    updated_at: datetime
    last_message: Optional["MessageInList"] = None
    unread_count: Optional[int] = None

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    conversations: List[ConversationInfo]


class MessageCreateRequest(BaseModel):
    conversation_id: str
    type: str = Field("text", pattern="^(text|image|audio|video|system|ai)$")
    content: Any
    reply_to: Optional[str] = None
    client_msg_id: Optional[str] = None
    tenant_id: Optional[str] = None


class MessageInList(BaseModel):
    message_id: str
    sender_id: str
    type: str
    content: Any
    created_at: datetime
    seq: int | None = None
    reply_to: Optional[str] = None

    class Config:
        from_attributes = True


class MessageCreateResponse(BaseModel):
    message: MessageInList


class MessageListResponse(BaseModel):
    conversation_id: str
    messages: List[MessageInList]
