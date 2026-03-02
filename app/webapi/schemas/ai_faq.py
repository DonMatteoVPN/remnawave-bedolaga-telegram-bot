from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AIFaqArticleResponse(BaseModel):
    id: int
    title: str
    content: str
    keywords: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AIFaqArticleCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    keywords: str | None = Field(default=None, max_length=1024)
    is_active: bool = True


class AIFaqArticleUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    keywords: str | None = Field(default=None, max_length=1024)
    is_active: bool | None = None
