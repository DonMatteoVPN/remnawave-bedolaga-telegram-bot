"""
FAQ Admin Handler — CRUD for AI FAQ articles in the admin panel.

Accessible from the support settings menu when DonMatteo-AI-Tiket mode is active.
"""

import structlog
from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import AsyncSessionLocal
from app.database.models import User
from app.database.models_ai_ticket import AIFaqArticle
from app.localization.texts import get_texts
from app.utils.decorators import admin_required, error_handler

logger = structlog.get_logger(__name__)


class FAQStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_content = State()
    waiting_for_keywords = State()
    editing_content = State()


# --------------- List all FAQ articles ---------------

@admin_required
@error_handler
async def show_faq_list(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Show list of FAQ articles."""
    stmt = select(AIFaqArticle).order_by(AIFaqArticle.id)
    result = await db.execute(stmt)
    articles = result.scalars().all()

    rows: list[list[types.InlineKeyboardButton]] = []

    if not articles:
        text = '📚 <b>База знаний (FAQ)</b>\n\nСтатьи отсутствуют. Добавьте первую!'
    else:
        text_parts = ['📚 <b>База знаний (FAQ)</b>\n']
        for article in articles:
            status = '✅' if article.is_active else '❌'
            text_parts.append(f'{status} <b>{article.title}</b> (ID: {article.id})')
            rows.append([
                types.InlineKeyboardButton(
                    text=f'📝 {article.title[:30]}',
                    callback_data=f'ai_faq_view:{article.id}',
                ),
                types.InlineKeyboardButton(
                    text='🗑',
                    callback_data=f'ai_faq_delete:{article.id}',
                ),
            ])
        text = '\n'.join(text_parts)

    rows.append([
        types.InlineKeyboardButton(
            text='➕ Добавить статью',
            callback_data='ai_faq_add',
        )
    ])
    rows.append([
        types.InlineKeyboardButton(
            text='🔙 Назад',
            callback_data='admin_support_settings',
        )
    ])

    await callback.message.edit_text(
        text,
        parse_mode='HTML',
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


# --------------- Add new article ---------------

@admin_required
@error_handler
async def start_add_article(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    """Start adding a new FAQ article — ask for title."""
    await callback.message.edit_text(
        '📝 <b>Новая статья FAQ</b>\n\nВведите заголовок статьи:',
        parse_mode='HTML',
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text='🔙 Отмена', callback_data='admin_support_ai_faq')]
        ]),
    )
    await state.set_state(FAQStates.waiting_for_title)
    await callback.answer()


@admin_required
@error_handler
async def handle_faq_title(message: types.Message, db_user: User, db: AsyncSession, state: FSMContext):
    """Received the title — now ask for content."""
    title = (message.text or '').strip()
    if not title:
        await message.answer('❌ Заголовок не может быть пустым.')
        return
    await state.update_data(faq_title=title)
    await message.answer(
        f'📝 Заголовок: <b>{title}</b>\n\nТеперь введите текст статьи:',
        parse_mode='HTML',
    )
    await state.set_state(FAQStates.waiting_for_content)


@admin_required
@error_handler
async def handle_faq_content(message: types.Message, db_user: User, db: AsyncSession, state: FSMContext):
    """Received content — now ask for keywords (optional)."""
    content = message.html_text or message.text or ''
    if not content.strip():
        await message.answer('❌ Содержание не может быть пустым.')
        return
    await state.update_data(faq_content=content)
    await message.answer(
        '🏷 Введите ключевые слова через запятую (или отправьте «-» для пропуска):',
    )
    await state.set_state(FAQStates.waiting_for_keywords)


@admin_required
@error_handler
async def handle_faq_keywords(message: types.Message, db_user: User, db: AsyncSession, state: FSMContext):
    """Received keywords — save the article."""
    data = await state.get_data()
    keywords_text = (message.text or '').strip()
    keywords = '' if keywords_text == '-' else keywords_text

    article = AIFaqArticle(
        title=data['faq_title'],
        content=data['faq_content'],
        keywords=keywords,
        is_active=True,
    )
    db.add(article)
    await db.commit()
    await state.clear()

    await message.answer(
        f'✅ Статья «{article.title}» добавлена в базу знаний!',
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text='📚 К списку FAQ', callback_data='admin_support_ai_faq')]
        ]),
    )


# --------------- View / Toggle article ---------------

@admin_required
@error_handler
async def view_article(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """View a single FAQ article with toggle active/inactive option."""
    article_id = int(callback.data.split(':')[1])
    stmt = select(AIFaqArticle).where(AIFaqArticle.id == article_id)
    result = await db.execute(stmt)
    article = result.scalars().first()

    if not article:
        await callback.answer('Статья не найдена', show_alert=True)
        return

    status = '✅ Активна' if article.is_active else '❌ Неактивна'
    text = (
        f'📄 <b>{article.title}</b>\n'
        f'Статус: {status}\n'
        f'Ключевые слова: {article.keywords or "—"}\n\n'
        f'{article.content}'
    )

    toggle_text = '❌ Деактивировать' if article.is_active else '✅ Активировать'
    rows = [
        [types.InlineKeyboardButton(text=toggle_text, callback_data=f'ai_faq_toggle:{article.id}')],
        [types.InlineKeyboardButton(text='🔙 Назад', callback_data='admin_support_ai_faq')],
    ]
    # Truncate if too long for Telegram
    if len(text) > 4000:
        text = text[:3997] + '…'
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=types.InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@admin_required
@error_handler
async def toggle_article(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Toggle active status of a FAQ article."""
    article_id = int(callback.data.split(':')[1])
    stmt = select(AIFaqArticle).where(AIFaqArticle.id == article_id)
    result = await db.execute(stmt)
    article = result.scalars().first()

    if not article:
        await callback.answer('Статья не найдена', show_alert=True)
        return

    article.is_active = not article.is_active
    await db.commit()

    await callback.answer(f'{"Активирована" if article.is_active else "Деактивирована"}')
    # Refresh the view
    await view_article(callback, db_user, db)


# --------------- Delete article ---------------

@admin_required
@error_handler
async def delete_article(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Delete a FAQ article."""
    article_id = int(callback.data.split(':')[1])
    stmt = delete(AIFaqArticle).where(AIFaqArticle.id == article_id)
    await db.execute(stmt)
    await db.commit()
    await callback.answer('🗑 Статья удалена')
    # Refresh the list
    await show_faq_list(callback, db_user, db)


# --------------- Registration ---------------

def register_faq_handlers(dp: Dispatcher) -> None:
    dp.callback_query.register(show_faq_list, F.data == 'admin_support_ai_faq')
    dp.callback_query.register(start_add_article, F.data == 'ai_faq_add')
    dp.callback_query.register(view_article, F.data.startswith('ai_faq_view:'))
    dp.callback_query.register(toggle_article, F.data.startswith('ai_faq_toggle:'))
    dp.callback_query.register(delete_article, F.data.startswith('ai_faq_delete:'))
    dp.message.register(handle_faq_title, FAQStates.waiting_for_title)
    dp.message.register(handle_faq_content, FAQStates.waiting_for_content)
    dp.message.register(handle_faq_keywords, FAQStates.waiting_for_keywords)
