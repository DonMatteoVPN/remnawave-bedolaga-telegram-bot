"""
Web API routes for AI FAQ management.

Tag: ai-faq
Prefix: /ai-faq
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models_ai_ticket import AIFaqArticle
from ..dependencies import get_db_session, require_api_token
from ..schemas.ai_faq import (
    AIFaqArticleCreateRequest,
    AIFaqArticleResponse,
    AIFaqArticleUpdateRequest,
)


router = APIRouter()


@router.get('', response_model=list[AIFaqArticleResponse])
async def list_faq_articles(
    _: Any = Security(require_api_token),
    active_only: bool = Query(default=False, description='Fetch only active articles'),
    db: AsyncSession = Depends(get_db_session),
) -> list[AIFaqArticleResponse]:
    """Get all FAQ articles."""
    stmt = select(AIFaqArticle)
    if active_only:
        stmt = stmt.where(AIFaqArticle.is_active == True)  # noqa: E712
    stmt = stmt.order_by(AIFaqArticle.id.desc())
    
    result = await db.execute(stmt)
    articles = result.scalars().all()
    
    return [
        AIFaqArticleResponse(
            id=a.id,
            title=a.title,
            content=a.content,
            keywords=a.keywords,
            is_active=a.is_active,
            created_at=a.created_at,
            updated_at=a.updated_at,
        ) for a in articles
    ]


@router.get('/{article_id}', response_model=AIFaqArticleResponse)
async def get_faq_article(
    article_id: int,
    _: Any = Security(require_api_token),
    db: AsyncSession = Depends(get_db_session),
) -> AIFaqArticleResponse:
    """Get a specific FAQ article by ID."""
    stmt = select(AIFaqArticle).where(AIFaqArticle.id == article_id)
    result = await db.execute(stmt)
    article = result.scalars().first()
    
    if not article:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'FAQ article not found')
        
    return AIFaqArticleResponse(
        id=article.id,
        title=article.title,
        content=article.content,
        keywords=article.keywords,
        is_active=article.is_active,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )


@router.post('', response_model=AIFaqArticleResponse, status_code=status.HTTP_201_CREATED)
async def create_faq_article(
    payload: AIFaqArticleCreateRequest,
    _: Any = Security(require_api_token),
    db: AsyncSession = Depends(get_db_session),
) -> AIFaqArticleResponse:
    """Create a new FAQ article."""
    article = AIFaqArticle(
        title=payload.title,
        content=payload.content,
        keywords=payload.keywords,
        is_active=payload.is_active,
    )
    db.add(article)
    await db.commit()
    await db.refresh(article)
    
    return AIFaqArticleResponse(
        id=article.id,
        title=article.title,
        content=article.content,
        keywords=article.keywords,
        is_active=article.is_active,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )


@router.put('/{article_id}', response_model=AIFaqArticleResponse)
async def update_faq_article(
    article_id: int,
    payload: AIFaqArticleUpdateRequest,
    _: Any = Security(require_api_token),
    db: AsyncSession = Depends(get_db_session),
) -> AIFaqArticleResponse:
    """Update an existing FAQ article."""
    stmt = select(AIFaqArticle).where(AIFaqArticle.id == article_id)
    result = await db.execute(stmt)
    article = result.scalars().first()
    
    if not article:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'FAQ article not found')
        
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(article, key, value)
        
    await db.commit()
    await db.refresh(article)
    
    return AIFaqArticleResponse(
        id=article.id,
        title=article.title,
        content=article.content,
        keywords=article.keywords,
        is_active=article.is_active,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )


@router.delete('/{article_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_faq_article(
    article_id: int,
    _: Any = Security(require_api_token),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a FAQ article."""
    stmt = select(AIFaqArticle).where(AIFaqArticle.id == article_id)
    result = await db.execute(stmt)
    article = result.scalars().first()
    
    if not article:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'FAQ article not found')
        
    await db.delete(article)
    await db.commit()
