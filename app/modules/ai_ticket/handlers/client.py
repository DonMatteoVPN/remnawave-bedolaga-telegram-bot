"""
Client-side handler for the DonMatteo-AI-Tiket module.

Intercepts user messages when SUPPORT_SYSTEM_MODE == 'ai_tiket',
creates Forum topics, calls AI, and routes replies.
"""

import structlog
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User
from app.modules.ai_ticket.services import ai_manager
from app.modules.ai_ticket.services.forum_service import ForumService
from app.modules.ai_ticket.services import prompt_service
from app.utils.decorators import error_handler

logger = structlog.get_logger(__name__)

router = Router(name='ai_ticket_client')


async def handle_ai_ticket_message(
    message: types.Message,
    bot: Bot,
    db: AsyncSession,
    db_user: User,
) -> None:
    """
    Main entry point: user sends a message to support in ai_tiket mode.
    
    1. Get or create a ForumTicket (and a Forum Topic in the manager group).
    2. Save the user message to DB.
    3. Forward the message into the Forum topic.
    4. If AI is enabled — generate a response, send to user and topic.
    """
    user_text = message.text or message.caption or ''
    if not user_text.strip():
        pass

    user_display = db_user.full_name or f'User {db_user.telegram_id}'

    # 1. Get or create ticket
    try:
        ticket = await ForumService.get_or_create_ticket(
            db=db,
            bot=bot,
            user_id=db_user.id,
            user_display_name=user_display,
        )
    except ValueError as e:
        logger.error('ai_ticket_client.no_forum_id', error=str(e))
        await message.answer(
            '⚠️ Система поддержки временно недоступна. Попробуйте позже.'
        )
        return
    except Exception as e:
        logger.error('ai_ticket_client.ticket_creation_failed', error=str(e))
        await message.answer(
            '⚠️ Не удалось создать обращение. Попробуйте позже.'
        )
        return

    forum_group_id = int(settings.SUPPORT_AI_FORUM_ID)

    # 2. Save user message
    await ForumService.save_message(
        db=db,
        ticket_id=ticket.id,
        role='user',
        content=user_text,
        message_id=message.message_id,
    )

    # 3. Forward to the Forum topic for managers
    try:
        await bot.send_message(
            chat_id=forum_group_id,
            message_thread_id=ticket.telegram_topic_id,
            text=f'👤 <b>{user_display}</b>:\n\n{user_text}',
            parse_mode='HTML',
        )
    except Exception as e:
        logger.error('ai_ticket_client.forward_failed', error=str(e), ticket_id=ticket.id)

    # 4. AI response (if enabled)
    if ticket.ai_enabled and settings.SUPPORT_AI_ENABLED:
        # Ensure provider rows exist in DB
        await ai_manager.ensure_providers_exist(db)

        # Build system prompt (stock or custom override)
        system_prompt = await prompt_service.get_system_prompt(db)

        # Get FAQ context
        faq_articles = await ForumService.get_active_faq_articles(db)
        faq_context = ForumService.format_faq_context(faq_articles)
        if faq_context:
            system_prompt += f'\n\n## БАЗА ЗНАНИЙ (используй для ответов):\n{faq_context}'

        # User context (balance, subscription info)
        user_context_parts: list[str] = []
        if hasattr(db_user, 'balance'):
            balance_rub = (db_user.balance or 0) / 100
            user_context_parts.append(f'Баланс: {balance_rub:.2f} руб.')
        if user_context_parts:
            system_prompt += '\n\n## КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:\n' + '\n'.join(user_context_parts)

        # Build conversation history
        history = await ForumService.get_conversation_history(db, ticket.id)
        messages = [{'role': 'system', 'content': system_prompt}] + history

        # Call AI with multi-provider failover
        ai_response = await ai_manager.generate_ai_response(db=db, messages=messages)

        if ai_response:
            # Save AI message
            await ForumService.save_message(
                db=db,
                ticket_id=ticket.id,
                role='ai',
                content=ai_response,
            )

            # Send to user
            call_manager_kb = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text='👨‍💼 Позвать менеджера',
                            callback_data=f'ai_ticket_call_manager:{ticket.id}',
                        )
                    ]
                ]
            )
            await message.answer(
                f'🤖 <b>AI-ассистент:</b>\n\n{ai_response}',
                parse_mode='HTML',
                reply_markup=call_manager_kb,
            )

            # Duplicate AI response in Forum topic
            try:
                await bot.send_message(
                    chat_id=forum_group_id,
                    message_thread_id=ticket.telegram_topic_id,
                    text=f'🤖 <b>AI:</b>\n\n{ai_response}',
                    parse_mode='HTML',
                )
            except Exception as e:
                logger.error('ai_ticket_client.ai_forward_failed', error=str(e))
        else:
            # AI failed — notify user
            await message.answer(
                '📨 Ваше сообщение получено. Менеджер ответит вам в ближайшее время.'
            )

    await db.commit()


async def handle_call_manager(
    callback: types.CallbackQuery,
    bot: Bot,
    db: AsyncSession,
    db_user: User,
) -> None:
    """User pressed 'Позвать менеджера' — disable AI and notify."""
    data = callback.data or ''
    parts = data.split(':')
    if len(parts) != 2:
        await callback.answer('Ошибка', show_alert=True)
        return

    try:
        ticket_id = int(parts[1])
    except ValueError:
        await callback.answer('Ошибка', show_alert=True)
        return

    await ForumService.disable_ai(db, ticket_id)
    await db.commit()

    # Notify in Forum topic
    forum_group_id = settings.SUPPORT_AI_FORUM_ID
    if forum_group_id:
        from app.database.models_ai_ticket import ForumTicket
        from sqlalchemy import select

        stmt = select(ForumTicket).where(ForumTicket.id == ticket_id)
        result = await db.execute(stmt)
        ticket = result.scalars().first()
        if ticket and ticket.telegram_topic_id:
            try:
                await bot.send_message(
                    chat_id=int(forum_group_id),
                    message_thread_id=ticket.telegram_topic_id,
                    text='⚠️ <b>Клиент вызвал менеджера.</b> AI-ассистент отключён для этого тикета.',
                    parse_mode='HTML',
                )
            except Exception as e:
                logger.error('ai_ticket_client.manager_notify_failed', error=str(e))

    await callback.message.answer(
        '👨‍💼 Менеджер подключится к вашему обращению в ближайшее время. AI-ассистент отключён.'
    )
    await callback.answer()


def register_client_handlers(dp: Dispatcher) -> None:
    """Register the 'Call manager' callback. 
    Note: The main message handler is registered dynamically 
    in the routing layer (tickets.py) based on the active mode.
    """
    dp.callback_query.register(
        handle_call_manager,
        F.data.startswith('ai_ticket_call_manager:'),
    )
