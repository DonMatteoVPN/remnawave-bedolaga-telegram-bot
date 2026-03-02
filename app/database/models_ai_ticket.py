import uuid
from datetime import datetime, UTC

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.database.models import Base


class ForumTicketStatus(str, Enum):
    OPEN = 'open'
    CLOSED = 'closed'
    ESCALATED = 'escalated'


class ForumTicketMessageRole(str, Enum):
    USER = 'user'
    AI = 'ai'
    MANAGER = 'manager'
    SYSTEM = 'system'


class ForumTicket(Base):
    __tablename__ = 'forum_tickets'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    telegram_topic_id = Column(Integer, nullable=True, index=True)
    status = Column(String, default=ForumTicketStatus.OPEN, nullable=False)
    ai_enabled = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship('User', backref='forum_tickets')
    messages = relationship('ForumTicketMessage', backref='ticket', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<ForumTicket id={self.id} user_id={self.user_id} status={self.status}>"


class ForumTicketMessage(Base):
    __tablename__ = 'forum_ticket_messages'

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey('forum_tickets.id', ondelete='CASCADE'), nullable=False, index=True)
    role = Column(String, nullable=False)  # ForumTicketMessageRole
    content = Column(Text, nullable=False)
    message_id = Column(Integer, nullable=True)
    # Медиа-вложения (фото)
    media_type = Column(String(50), nullable=True)  # 'photo', 'document' и т.д.
    media_file_id = Column(String(512), nullable=True)  # Telegram file_id

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    def __repr__(self):
        return f"<ForumTicketMessage id={self.id} ticket_id={self.ticket_id} role={self.role}>"


class AIFaqArticle(Base):
    __tablename__ = 'ai_faq_articles'

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    keywords = Column(String(1024), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    def __repr__(self):
        return f"<AIFaqArticle id={self.id} title={self.title}>"


class AIProviderConfig(Base):
    """
    Multi-provider AI configuration.
    Each row = one provider (groq, openai, anthropic, google, openrouter).
    Supports multiple API keys with automatic rotation on rate limits.
    """
    __tablename__ = 'ai_provider_configs'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)  # groq, openai, anthropic, google, openrouter
    enabled = Column(Boolean, default=False, nullable=False)
    priority = Column(Integer, default=0, nullable=False)  # lower = tried first

    api_keys = Column(JSON, default=list, nullable=False)  # ["sk-...", "sk-..."]
    active_key_index = Column(Integer, default=0, nullable=False)

    selected_model = Column(String(255), nullable=True)
    available_models = Column(JSON, default=list, nullable=False)  # cached from last test_connection

    base_url = Column(String(512), nullable=True)  # custom endpoint override

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    def __repr__(self):
        return f"<AIProviderConfig name={self.name} enabled={self.enabled} priority={self.priority}>"

