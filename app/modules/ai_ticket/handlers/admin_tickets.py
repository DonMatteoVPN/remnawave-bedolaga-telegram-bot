"""
Админский интерфейс для DonMatteo-AI-Tiket.

Позволяет администраторам:
- Просматривать все AI-тикеты (открытые/закрытые)
- Читать историю сообщений
- Отвечать на тикеты
- Закрывать тикеты
"""

import html as html_module
import structlog
from aiogram import Dispatcher, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.database.models_ai_ticket import ForumTicket, ForumTicketMessage
from app.localization.texts import get_texts
from app.utils.decorators import admin_required, error_handler
from app.modules.ai_ticket.services.forum_service import ForumService
from app.services.system_settings_service import BotConfigurationService

logger = structlog.get_logger(__name__)


class AdminTicketStates(StatesGroup):
    """Состояния для ответа на тикет из админки."""
    waiting_for_reply = State()


@admin_required
@error_handler
async def show_admin_ai_tickets(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Показать список AI-тикетов для администратора."""
    data = callback.data or ''
    
    # Определяем статус и страницу
    show_closed = '_closed' in data
    page = 1
    if '_page_' in data:
        try:
            page = int(data.split('_page_')[-1])
        except ValueError:
            page = 1
    
    # texts для будущего использования
    per_page = 10
    
    # Подсчёт тикетов
    status_filter = 'closed' if show_closed else 'open'
    count_stmt = select(func.count(ForumTicket.id)).where(ForumTicket.status == status_filter)
    total_count = (await db.execute(count_stmt)).scalar() or 0
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page
    
    # Получаем тикеты с пользователями
    stmt = (
        select(ForumTicket)
        .options(joinedload(ForumTicket.user))
        .where(ForumTicket.status == status_filter)
        .order_by(ForumTicket.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    tickets = result.scalars().all()
    
    # Формируем текст
    status_emoji = '🔴' if show_closed else '🟢'
    title = 'Закрытые' if show_closed else 'Открытые'
    text = f'<b>🎫 {title} AI-тикеты</b> {status_emoji}\n'
    text += f'<i>Всего: {total_count} | Стр. {page}/{total_pages}</i>\n\n'
    
    if not tickets:
        text += '<i>Нет тикетов</i>'
    
    # Формируем клавиатуру
    kb_rows = []
    
    for ticket in tickets:
        user_name = ticket.user.full_name if ticket.user else 'Unknown'
        user_name = user_name[:20] + '...' if len(user_name) > 20 else user_name
        ai_icon = '🤖' if ticket.ai_enabled else '👤'
        created = ticket.created_at.strftime('%d.%m') if ticket.created_at else ''
        
        kb_rows.append([
            types.InlineKeyboardButton(
                text=f'{ai_icon} #{ticket.id} {user_name} ({created})',
                callback_data=f'admin_ai_ticket_view_{ticket.id}'
            )
        ])
    
    # Пагинация
    if total_pages > 1:
        nav_row = []
        prefix = 'admin_ai_tickets_closed' if show_closed else 'admin_ai_tickets'
        if page > 1:
            nav_row.append(types.InlineKeyboardButton(text='◀️', callback_data=f'{prefix}_page_{page-1}'))
        nav_row.append(types.InlineKeyboardButton(text=f'{page}/{total_pages}', callback_data='noop'))
        if page < total_pages:
            nav_row.append(types.InlineKeyboardButton(text='▶️', callback_data=f'{prefix}_page_{page+1}'))
        kb_rows.append(nav_row)
    
    # Переключение между открытыми/закрытыми
    if show_closed:
        kb_rows.append([types.InlineKeyboardButton(text='🟢 Открытые тикеты', callback_data='admin_ai_tickets')])
    else:
        kb_rows.append([types.InlineKeyboardButton(text='🔴 Закрытые тикеты', callback_data='admin_ai_tickets_closed')])
    
    kb_rows.append([types.InlineKeyboardButton(text='« Назад', callback_data='admin_support_settings')])
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=kb_rows)
    
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode='HTML')
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode='HTML')
    
    await callback.answer()


@admin_required
@error_handler
async def view_admin_ai_ticket(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Просмотр конкретного AI-тикета администратором."""
    data = callback.data or ''
    
    # Парсим ticket_id и страницу
    parts = data.replace('admin_ai_ticket_view_', '').split('_page_')
    ticket_id = int(parts[0])
    page = int(parts[1]) if len(parts) > 1 else 1
    
    # Получаем тикет с пользователем
    stmt = select(ForumTicket).options(joinedload(ForumTicket.user)).where(ForumTicket.id == ticket_id)
    result = await db.execute(stmt)
    ticket = result.scalars().first()
    
    if not ticket:
        await callback.answer('Тикет не найден', show_alert=True)
        return
    
    # Получаем все сообщения
    stmt_msgs = select(ForumTicketMessage).where(
        ForumTicketMessage.ticket_id == ticket_id
    ).order_by(ForumTicketMessage.created_at.asc())
    msgs_result = await db.execute(stmt_msgs)
    all_messages = msgs_result.scalars().all()
    
    # Пагинация
    per_page = 5
    total_msgs = len(all_messages)
    total_pages = max(1, (total_msgs + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * per_page
    messages = all_messages[start_idx:start_idx + per_page]
    
    # texts для будущего использования
    
    # Информация о тикете
    status_emoji = '🟢' if ticket.status == 'open' else '🔴'
    # ai_emoji используется в тексте
    user_name = ticket.user.full_name if ticket.user else 'Unknown'
    user_tg = f'@{ticket.user.username}' if ticket.user and ticket.user.username else f'ID:{ticket.user.telegram_id}' if ticket.user else '-'
    created = ticket.created_at.strftime('%d.%m.%Y %H:%M') if ticket.created_at else '-'
    
    text = f'<b>🎫 Тикет #{ticket.id}</b> {status_emoji}\n\n'
    text += f'👤 <b>Пользователь:</b> {html_module.escape(user_name)}\n'
    text += f'📱 <b>Telegram:</b> {user_tg}\n'
    text += f'🤖 <b>AI:</b> {"Вкл" if ticket.ai_enabled else "Выкл"}\n'
    text += f'📅 <b>Создан:</b> {created}\n'
    text += f'💬 <b>Сообщений:</b> {total_msgs} | Стр. {page}/{total_pages}\n'
    text += '─' * 25 + '\n\n'
    
    for msg in messages:
        role_icon = '👤' if msg.role == 'user' else ('🤖' if msg.role == 'ai' else '👨‍💻')
        role_name = 'Клиент' if msg.role == 'user' else ('AI' if msg.role == 'ai' else 'Менеджер')
        time_str = msg.created_at.strftime('%d.%m %H:%M') if msg.created_at else ''
        content = html_module.escape(msg.content or '')
        
        text += f'<b>{role_icon} {role_name}</b> <i>({time_str})</i>\n'
        text += f'{content}\n\n'
    
    if not all_messages:
        text += '<i>Нет сообщений</i>'
    
    # Клавиатура
    kb_rows = []
    
    # Пагинация
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(types.InlineKeyboardButton(text='◀️', callback_data=f'admin_ai_ticket_view_{ticket_id}_page_{page-1}'))
        nav_row.append(types.InlineKeyboardButton(text=f'{page}/{total_pages}', callback_data='noop'))
        if page < total_pages:
            nav_row.append(types.InlineKeyboardButton(text='▶️', callback_data=f'admin_ai_ticket_view_{ticket_id}_page_{page+1}'))
        kb_rows.append(nav_row)
    
    # Действия с тикетом
    if ticket.status == 'open':
        kb_rows.append([
            types.InlineKeyboardButton(text='💬 Ответить', callback_data=f'admin_ai_ticket_reply_{ticket_id}'),
            types.InlineKeyboardButton(text='✅ Закрыть', callback_data=f'admin_ai_ticket_close_{ticket_id}'),
        ])
        # AI toggle
        ai_btn = '🔇 Выкл AI' if ticket.ai_enabled else '🤖 Вкл AI'
        kb_rows.append([
            types.InlineKeyboardButton(text=ai_btn, callback_data=f'admin_ai_ticket_toggle_ai_{ticket_id}'),
        ])
    
    # Открыть в топике (если есть)
    if ticket.telegram_topic_id:
        forum_id = BotConfigurationService.get_current_value('SUPPORT_AI_FORUM_ID')
        if forum_id:
            # Ссылка на топик
            kb_rows.append([
                types.InlineKeyboardButton(
                    text='🔗 Открыть в форуме',
                    url=f'https://t.me/c/{str(forum_id)[4:]}/{ticket.telegram_topic_id}'
                )
            ])
    
    kb_rows.append([types.InlineKeyboardButton(text='« К списку', callback_data='admin_ai_tickets')])
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=kb_rows)
    
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode='HTML')
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode='HTML')
    
    await callback.answer()


@admin_required
@error_handler
async def start_admin_reply(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    """Начать ответ на тикет из админки."""
    data = callback.data or ''
    ticket_id = int(data.replace('admin_ai_ticket_reply_', ''))
    
    await state.update_data(admin_reply_ticket_id=ticket_id)
    await state.set_state(AdminTicketStates.waiting_for_reply)
    
    text = (
        f'<b>💬 Ответ на тикет #{ticket_id}</b>\n\n'
        'Введите текст ответа пользователю.\n'
        '<i>Сообщение будет отправлено клиенту и скопировано в форум-топик.</i>'
    )
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='❌ Отмена', callback_data=f'admin_ai_ticket_view_{ticket_id}')]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode='HTML')
    await callback.answer()


@admin_required
@error_handler
async def handle_admin_reply(message: types.Message, db_user: User, db: AsyncSession, state: FSMContext):
    """Обработка ответа админа на тикет."""
    data = await state.get_data()
    ticket_id = data.get('admin_reply_ticket_id')
    
    if not ticket_id:
        await message.answer('❌ Ошибка: тикет не найден')
        await state.clear()
        return
    
    reply_text = message.text or ''
    if not reply_text.strip():
        await message.answer('❌ Введите текст ответа')
        return
    
    # Получаем тикет с пользователем
    stmt = select(ForumTicket).options(joinedload(ForumTicket.user)).where(ForumTicket.id == ticket_id)
    result = await db.execute(stmt)
    ticket = result.scalars().first()
    
    if not ticket or not ticket.user:
        await message.answer('❌ Тикет или пользователь не найден')
        await state.clear()
        return
    
    texts = get_texts(ticket.user.language or 'ru')
    
    # Сохраняем сообщение
    await ForumService.save_message(
        db=db,
        ticket_id=ticket_id,
        role='manager',
        content=reply_text,
    )
    
    # Отключаем AI
    if ticket.ai_enabled:
        await ForumService.disable_ai(db, ticket_id)
    
    await db.commit()
    
    # Отправляем пользователю
    try:
        notification_text = texts.t(
            'TICKET_REPLY_NOTIFICATION',
            '🎫 Получен ответ по тикету #{ticket_id}\n\n{reply_preview}\n\nНажмите кнопку ниже, чтобы перейти к тикету:'
        ).format(ticket_id=ticket_id, reply_preview=reply_text[:200])
        
        user_kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=texts.t('VIEW_TICKET', '👁️ Посмотреть тикет'), callback_data=f'view_forum_ticket_{ticket_id}')],
            [types.InlineKeyboardButton(text=texts.t('REPLY_TO_TICKET', '💬 Ответить'), callback_data=f'reply_forum_ticket_{ticket_id}')],
        ])
        
        await message.bot.send_message(
            chat_id=ticket.user.telegram_id,
            text=notification_text,
            reply_markup=user_kb,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error('admin_ai_ticket.send_to_user_failed', error=str(e), ticket_id=ticket_id)
        await message.answer(f'⚠️ Не удалось отправить пользователю: {e}')
    
    # Копируем в форум-топик
    forum_id = BotConfigurationService.get_current_value('SUPPORT_AI_FORUM_ID')
    if forum_id and ticket.telegram_topic_id:
        try:
            await message.bot.send_message(
                chat_id=int(forum_id),
                message_thread_id=ticket.telegram_topic_id,
                text=f'👨‍💼 <b>Ответ из админки:</b>\n\n{reply_text}',
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error('admin_ai_ticket.copy_to_forum_failed', error=str(e))
    
    await state.clear()
    await message.answer(f'✅ Ответ на тикет #{ticket_id} отправлен!')


@admin_required
@error_handler
async def close_admin_ai_ticket(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Закрыть тикет из админки."""
    data = callback.data or ''
    ticket_id = int(data.replace('admin_ai_ticket_close_', ''))
    
    stmt = select(ForumTicket).options(joinedload(ForumTicket.user)).where(ForumTicket.id == ticket_id)
    result = await db.execute(stmt)
    ticket = result.scalars().first()
    
    if not ticket:
        await callback.answer('Тикет не найден', show_alert=True)
        return
    
    await ForumService.close_ticket(db, ticket_id, bot=callback.bot)
    await db.commit()
    
    # Уведомляем пользователя
    if ticket.user:
        try:
            texts = get_texts(ticket.user.language or 'ru')
            await callback.bot.send_message(
                chat_id=ticket.user.telegram_id,
                text=texts.t('TICKET_CLOSED_NOTIFICATION', '✅ Ваше обращение #{ticket_id} закрыто. Спасибо!').format(ticket_id=ticket_id),
                parse_mode='HTML'
            )
        except Exception:
            pass
    
    await callback.answer(f'✅ Тикет #{ticket_id} закрыт')
    
    # Обновляем просмотр
    callback.data = f'admin_ai_ticket_view_{ticket_id}'
    await view_admin_ai_ticket(callback, db_user, db)


@admin_required
@error_handler
async def toggle_admin_ai_ticket(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Переключить AI для тикета из админки."""
    data = callback.data or ''
    ticket_id = int(data.replace('admin_ai_ticket_toggle_ai_', ''))
    
    stmt = select(ForumTicket).where(ForumTicket.id == ticket_id)
    result = await db.execute(stmt)
    ticket = result.scalars().first()
    
    if not ticket:
        await callback.answer('Тикет не найден', show_alert=True)
        return
    
    if ticket.ai_enabled:
        await ForumService.disable_ai(db, ticket_id)
        msg = '🔇 AI отключён'
    else:
        await ForumService.enable_ai(db, ticket_id)
        msg = '🤖 AI включён'
    
    await db.commit()
    await callback.answer(msg)
    
    # Обновляем просмотр
    callback.data = f'admin_ai_ticket_view_{ticket_id}'
    await view_admin_ai_ticket(callback, db_user, db)


def register_admin_ticket_handlers(dp: Dispatcher) -> None:
    """Регистрация админских обработчиков AI-тикетов."""
    # Список тикетов
    dp.callback_query.register(show_admin_ai_tickets, F.data == 'admin_ai_tickets')
    dp.callback_query.register(show_admin_ai_tickets, F.data == 'admin_ai_tickets_closed')
    dp.callback_query.register(show_admin_ai_tickets, F.data.startswith('admin_ai_tickets_page_'))
    dp.callback_query.register(show_admin_ai_tickets, F.data.startswith('admin_ai_tickets_closed_page_'))
    
    # Просмотр тикета
    dp.callback_query.register(view_admin_ai_ticket, F.data.startswith('admin_ai_ticket_view_'))
    
    # Ответ на тикет
    dp.callback_query.register(start_admin_reply, F.data.startswith('admin_ai_ticket_reply_'))
    dp.message.register(handle_admin_reply, AdminTicketStates.waiting_for_reply)
    
    # Закрытие тикета
    dp.callback_query.register(close_admin_ai_ticket, F.data.startswith('admin_ai_ticket_close_'))
    
    # Toggle AI
    dp.callback_query.register(toggle_admin_ai_ticket, F.data.startswith('admin_ai_ticket_toggle_ai_'))
