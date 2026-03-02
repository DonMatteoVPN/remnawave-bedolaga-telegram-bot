"""
Manager-side handler for the DonMatteo-AI-Tiket module.

Listens for messages in the Forum group. When a manager
replies in a ticket topic, forwards the reply to the user
and auto-disables AI for that ticket.
"""

import structlog
from aiogram import Bot, Dispatcher, F, Router, types
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.database import AsyncSessionLocal
from app.modules.ai_ticket.services.forum_service import ForumService

logger = structlog.get_logger(__name__)

router = Router(name='ai_ticket_manager')


async def handle_manager_message(message: types.Message, bot: Bot) -> None:
    """
    A manager sent a message inside the Forum group.
    If it's in a ticket topic — forward to the user and disable AI.
    """
    forum_group_id = settings.SUPPORT_AI_FORUM_ID
    if not forum_group_id:
        return

    # Only process messages in the configured forum group
    if str(message.chat.id) != str(forum_group_id):
        return

    # Must be inside a topic (not the general topic)
    topic_id = message.message_thread_id
    if not topic_id:
        return

    # Ignore messages from the bot itself
    if message.from_user and message.from_user.id == bot.id:
        return

    text = message.text or message.caption or ''
    if not text.strip():
        return

    # Commands in the topic
    if text.startswith('/'):
        await _handle_topic_command(message, bot, topic_id, text)
        return

    # Find the ticket for this topic
    async with AsyncSessionLocal() as db:
        ticket = await ForumService.get_ticket_by_topic_id(db, topic_id)
        if not ticket:
            return  # Not a ticket topic

        manager_name = message.from_user.full_name if message.from_user else 'Менеджер'

        # Save manager message
        await ForumService.save_message(
            db=db,
            ticket_id=ticket.id,
            role='manager',
            content=text,
            message_id=message.message_id,
        )

        # Disable AI automatically
        if ticket.ai_enabled:
            await ForumService.disable_ai(db, ticket.id)
            # Notify in the topic
            try:
                await bot.send_message(
                    chat_id=message.chat.id,
                    message_thread_id=topic_id,
                    text='ℹ️ AI-ассистент автоматически отключён (менеджер ответил).',
                )
            except Exception:
                pass

        # Forward to the user
        try:
            await bot.send_message(
                chat_id=ticket.user_id,
                text=f'👨‍💼 <b>{manager_name}:</b>\n\n{text}',
                parse_mode='HTML',
            )
        except Exception as e:
            logger.error(
                'ai_ticket_manager.forward_to_user_failed',
                error=str(e),
                user_id=ticket.user_id,
            )
            await message.reply('⚠️ Не удалось доставить сообщение пользователю.')

        await db.commit()


async def _handle_topic_command(
    message: types.Message,
    bot: Bot,
    topic_id: int,
    text: str,
) -> None:
    """Handle manager commands inside a ticket topic."""
    command = text.strip().lower()

    async with AsyncSessionLocal() as db:
        ticket = await ForumService.get_ticket_by_topic_id(db, topic_id)
        if not ticket:
            return

        if command == '/close':
            await ForumService.close_ticket(db, ticket.id)
            await db.commit()
            try:
                await bot.send_message(
                    chat_id=ticket.user_id,
                    text='✅ Ваше обращение закрыто. Спасибо за обратную связь!',
                )
            except Exception:
                pass
            await message.reply('✅ Тикет закрыт.')

        elif command == '/ai_on':
            await ForumService.enable_ai(db, ticket.id)
            await db.commit()
            await message.reply('🤖 AI-ассистент включён для этого тикета.')

        elif command == '/ai_off':
            await ForumService.disable_ai(db, ticket.id)
            await db.commit()
            await message.reply('🔇 AI-ассистент выключен для этого тикета.')

        elif command == '/help':
            await message.reply(
                '<b>Команды тикета:</b>\n'
                '/close — закрыть тикет\n'
                '/ai_on — включить AI\n'
                '/ai_off — выключить AI\n'
                '/help — эта справка',
                parse_mode='HTML',
            )


def register_manager_handlers(dp: Dispatcher) -> None:
    """
    Register the manager message handler.
    It listens to ALL messages in the forum group and filters by topic_id.
    """
    # This handler must ONLY trigger in the configured forum group
    forum_group_id = settings.SUPPORT_AI_FORUM_ID
    if not forum_group_id:
        logger.warning('ai_ticket_manager.no_forum_id_configured')
        return

    dp.message.register(
        handle_manager_message,
        F.chat.id == int(forum_group_id),
    )
