"""AI-Ticket Module - Независимая миграция

Revision ID: ai_ticket_001
Revises: 0049
Create Date: 2026-03-26

DonMatteo-AI-Tiket модуль - Независимая миграция.
Создаёт все таблицы модуля AI-Ticket:
- forum_tickets (тикеты в Forum-группе)
- forum_ticket_messages (сообщения тикетов с медиа)
- ai_faq_articles (FAQ-статьи)
- ai_faq_media (медиа-вложения FAQ)
- ai_provider_configs (конфигурация AI-провайдеров)

Использует checkfirst для идемпотентности - можно запускать многократно.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Уникальный revision ID для AI-Ticket модуля
revision: str = 'ai_ticket_001'
# Зависимость от последней стабильной миграции основного бота
down_revision: Union[str, None] = '0049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    """Проверка существования таблицы."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return inspector.has_table(name)


def _has_column(table_name: str, column_name: str) -> bool:
    """Проверка существования колонки в таблице."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(table_name):
        return False
    columns = [c['name'] for c in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Создание всех таблиц AI-Ticket модуля."""
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 1. forum_tickets - Тикеты в Forum-группе
    # ═══════════════════════════════════════════════════════════════════════════
    if not _has_table('forum_tickets'):
        op.create_table(
            'forum_tickets',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('telegram_topic_id', sa.Integer(), nullable=True, index=True),
            sa.Column('status', sa.String(50), server_default='open', nullable=False),
            sa.Column('ai_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. forum_ticket_messages - Сообщения тикетов (с поддержкой медиа)
    # ═══════════════════════════════════════════════════════════════════════════
    if not _has_table('forum_ticket_messages'):
        op.create_table(
            'forum_ticket_messages',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('forum_tickets.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('role', sa.String(50), nullable=False),  # user, ai, manager, system
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('message_id', sa.Integer(), nullable=True),  # Telegram message_id
            # Медиа-поля
            sa.Column('media_type', sa.String(50), nullable=True),  # photo, document
            sa.Column('media_file_id', sa.String(512), nullable=True),  # Telegram file_id
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    else:
        # Добавляем медиа-поля если таблица уже существует
        if not _has_column('forum_ticket_messages', 'media_type'):
            op.add_column('forum_ticket_messages', sa.Column('media_type', sa.String(50), nullable=True))
        if not _has_column('forum_ticket_messages', 'media_file_id'):
            op.add_column('forum_ticket_messages', sa.Column('media_file_id', sa.String(512), nullable=True))

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. ai_faq_articles - FAQ-статьи для AI-ассистента
    # ═══════════════════════════════════════════════════════════════════════════
    if not _has_table('ai_faq_articles'):
        op.create_table(
            'ai_faq_articles',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('keywords', sa.String(1024), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. ai_faq_media - Медиа-вложения для FAQ-статей
    # ═══════════════════════════════════════════════════════════════════════════
    if not _has_table('ai_faq_media'):
        op.create_table(
            'ai_faq_media',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('article_id', sa.Integer(), sa.ForeignKey('ai_faq_articles.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('media_type', sa.String(20), nullable=False),  # photo, video, animation
            sa.Column('file_id', sa.String(512), nullable=False),  # Telegram file_id
            sa.Column('caption', sa.String(1024), nullable=True),  # Описание для AI
            sa.Column('tag', sa.String(50), nullable=False, unique=True),  # Уникальный тег: setup_android
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. ai_provider_configs - Конфигурация AI-провайдеров (мульти-провайдер)
    # ═══════════════════════════════════════════════════════════════════════════
    if not _has_table('ai_provider_configs'):
        op.create_table(
            'ai_provider_configs',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('name', sa.String(50), unique=True, nullable=False, index=True),  # groq, openai, anthropic, google, openrouter
            sa.Column('enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
            sa.Column('priority', sa.Integer(), server_default='0', nullable=False),  # lower = tried first
            sa.Column('api_keys', sa.JSON(), server_default='[]', nullable=False),  # ["sk-...", "sk-..."]
            sa.Column('active_key_index', sa.Integer(), server_default='0', nullable=False),
            sa.Column('selected_model', sa.String(255), nullable=True),
            sa.Column('available_models', sa.JSON(), server_default='[]', nullable=False),  # cached from test_connection
            sa.Column('base_url', sa.String(512), nullable=True),  # custom endpoint override
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    """Удаление всех таблиц AI-Ticket модуля."""
    # Удаляем в обратном порядке из-за зависимостей
    op.drop_table('ai_provider_configs')
    op.drop_table('ai_faq_media')
    op.drop_table('ai_faq_articles')
    op.drop_table('forum_ticket_messages')
    op.drop_table('forum_tickets')
