"""
Client-side handler для модуля DonMatteo-AI-Tiket.

Перехватывает сообщения пользователя при SUPPORT_SYSTEM_MODE == 'ai_tiket',
создаёт Forum-топики, вызывает AI, маршрутизирует ответы.
Поддержка фото-вложений.
"""

import structlog
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import StateFilter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database.models import User
from app.modules.ai_ticket.services import ai_manager
from app.modules.ai_ticket.services.forum_service import ForumService
from app.modules.ai_ticket.services import prompt_service
from app.localization.texts import get_texts
from app.modules.ai_ticket.utils.keyboards import get_manager_kb, get_user_navigation_kb, get_user_reply_kb
from app.modules.ai_ticket.utils.formatting import sanitize_ai_response
from app.services.system_settings_service import BotConfigurationService

logger = structlog.get_logger(__name__)

router = Router(name='ai_ticket_client')


async def handle_ai_ticket_message(
    message: types.Message,
    bot: Bot,
    db: AsyncSession,
    db_user: User,
) -> None:
    """Основная точка входа для AI-поддержки (callback из _ai_ticket_message_proxy). Поддерживает фото."""
    logger.info('ai_ticket_client.handle_message_started', chat_id=message.chat.id, user_id=db_user.id)
    user_text = message.text or message.caption or ''

    # Извлекаем медиа
    media_type = None
    media_file_id = None
    if message.photo:
        media_type = 'photo'
        media_file_id = message.photo[-1].file_id

    # Пустое сообщение без медиа — не обрабатываем
    if not user_text.strip() and not media_file_id:
        return

    # 1. Создаём/получаем тикет
    texts = get_texts(db_user.language)
    try:
        ticket = await ForumService.get_or_create_ticket(db, bot, db_user.id, db_user.full_name)
    except Exception as e:
        logger.error('ai_ticket_client.ticket_init_failed', error=str(e), user_id=db_user.id)
        await message.answer(texts.t('TICKET_CREATE_ERROR', '⚠️ Ошибка инициализации тикета. Мы скоро свяжемся с вами.'))
        return

    # 2. ID форум-группы (опциональный — без него AI всё равно отвечает)
    forum_group_id_str = BotConfigurationService.get_current_value('SUPPORT_AI_FORUM_ID')
    forum_group_id = int(forum_group_id_str) if forum_group_id_str else None
    if not forum_group_id:
        logger.warning('ai_ticket_client.no_forum_id — форум-группа не настроена, пересылка менеджерам отключена')

    # 3. Проверяем состояние AI
    ai_enabled_global = BotConfigurationService.get_current_value('SUPPORT_AI_ENABLED')
    if isinstance(ai_enabled_global, str):
        ai_enabled_global = ai_enabled_global.lower() in ('true', '1', 'on', 'yes')

    should_run_ai = ticket.ai_enabled and ai_enabled_global

    # 4. Сохраняем сообщение пользователя с медиа
    await ForumService.save_message(
        db=db,
        ticket_id=ticket.id,
        role='user',
        content=user_text or '[фото]',
        media_type=media_type,
        media_file_id=media_file_id,
    )

    # 5. Пересылаем сообщение в форум-топик менеджеру (с медиа + кнопки управления)
    try:
        if media_type == 'photo' and media_file_id:
            caption_text = f"👤 <b>Сообщение от пользователя {db_user.full_name}:</b>\n\n{user_text}" if user_text else f"👤 <b>Фото от пользователя {db_user.full_name}</b>"
            await bot.send_photo(
                chat_id=forum_group_id,
                message_thread_id=ticket.telegram_topic_id,
                photo=media_file_id,
                caption=caption_text,
                parse_mode='HTML',
                reply_markup=get_manager_kb(ticket.id, ai_enabled=ticket.ai_enabled),
            )
        else:
            await bot.send_message(
                chat_id=forum_group_id,
                message_thread_id=ticket.telegram_topic_id,
                text=f"👤 <b>Сообщение от пользователя {db_user.full_name}:</b>\n\n{user_text}",
                parse_mode='HTML',
                reply_markup=get_manager_kb(ticket.id, ai_enabled=ticket.ai_enabled),
            )
    except Exception as e:
        logger.error('ai_ticket_client.forward_to_manager_failed', error=str(e))

    # 6. Мгновенная обратная связь пользователю
    status_text = texts.t('AI_TICKET_MESSAGE_RECEIVED', '⏳ <b>Ваше сообщение получено.</b>')
    if should_run_ai:
        status_text += "\n<i>ИИ-ассистент обдумывает ответ...</i>"
    else:
        status_text += "\n<i>Менеджеры уведомлены и скоро ответят.</i>"

    status_msg = await message.answer(
        status_text,
        parse_mode='HTML',
        reply_markup=get_user_reply_kb(ticket.id, lang=db_user.language, show_call_manager=False)
    )

    if not should_run_ai:
        # AI отключён — уведомляем менеджера в топике
        if forum_group_id and ticket.telegram_topic_id:
            try:
                await bot.send_message(
                    chat_id=forum_group_id,
                    message_thread_id=ticket.telegram_topic_id,
                    text='⚠️ <b>AI-ассистент отключён.</b>\nПожалуйста, ответьте пользователю вручную или включите AI.',
                    parse_mode='HTML',
                    reply_markup=get_manager_kb(ticket.id, lang='ru', ai_enabled=False),
                )
            except Exception as e:
                logger.error('ai_ticket_client.manager_ai_disabled_notify_failed', error=str(e))
        await db.commit()
        return

    # 7. AI обработка с фоллбеком
    try:
        await ai_manager.ensure_providers_exist(db)
        system_prompt = await prompt_service.get_system_prompt(db)

        # FAQ и контекст пользователя
        faq_articles = await ForumService.get_active_faq_articles(db)
        faq_context = ForumService.format_faq_context(faq_articles)
        if faq_context:
            system_prompt += f'\n\n## БАЗА ЗНАНИЙ:\n{faq_context}'

        user_context_parts: list[str] = []
        user_context_parts.append(f'ID Пользователя: {db_user.id}')
        user_context_parts.append(f'Имя: {db_user.full_name}')
        user_context_parts.append(f'Язык: {db_user.language}')
        if hasattr(db_user, 'balance_kopeks'):
            user_context_parts.append(f'Баланс: {(db_user.balance_kopeks or 0) / 100:.2f} руб.')
            
        subscription = db_user.subscription
        if subscription:
            user_context_parts.append(f'Статус подписки: {subscription.status}')
            if subscription.end_date:
                user_context_parts.append(f'Действует до: {subscription.end_date.strftime("%Y-%m-%d %H:%M")}')
            if subscription.traffic_limit_gb and subscription.traffic_used_gb is not None:
                user_context_parts.append(f'Трафик: использовано {subscription.traffic_used_gb:.2f} ГБ из {subscription.traffic_limit_gb} ГБ')
            if subscription.device_limit:
                user_context_parts.append(f'Лимит устройств: {subscription.device_limit}')
                
        # Получаем данные об устройствах из RemnaWave
        try:
            from app.handlers.subscription.devices import get_current_devices_detailed
            devices_info = await get_current_devices_detailed(db_user)
            connected_count = devices_info.get("count", 0)
            user_context_parts.append(f'Текущее количество подключенных устройств (HWID): {connected_count}')
        except Exception as e:
            logger.warning('ai_ticket_client.get_devices_failed', error=str(e))

        if user_context_parts:
            system_prompt += '\n\n## КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:\n' + '\n'.join(user_context_parts)

        # История и генерация
        history = await ForumService.get_conversation_history(db, ticket.id)
        messages_ai = [{'role': 'system', 'content': system_prompt}] + history

        ai_response = await ai_manager.generate_ai_response(db=db, messages=messages_ai)

        if ai_response:
            # Проверяем триггер автовызова менеджера
            if '[CALL_MANAGER]' in ai_response:
                # Отключаем ИИ
                ticket.ai_enabled = False
                await db.commit()
                
                # Сообщаем менеджеру в топике
                if forum_group_id and ticket.telegram_topic_id:
                    try:
                        await bot.send_message(
                            chat_id=forum_group_id,
                            message_thread_id=ticket.telegram_topic_id,
                            text='⚠️ <b>АВТОВЫЗОВ:</b> ИИ не смог найти ответ в FAQ и перевел тикет на менеджера. AI-ассистент отключён.',
                            parse_mode='HTML',
                            reply_markup=get_manager_kb(ticket.id, lang='ru', ai_enabled=False)
                        )
                    except Exception as e:
                        logger.error('ai_ticket_client.manager_notify_failed', error=str(e))
                
                # Сообщаем пользователю стандартным текстом, скрывая кнопку вызова менеджера
                msg_text = texts.t('AI_TICKET_MANAGER_AUTO_CALLED', '🤖 <b>AI-ассистент:</b>\nК сожалению, я не знаю точного ответа на ваш вопрос. Я передал ваше обращение менеджеру, пожалуйста, ожидайте ответа специалиста.')
                await status_msg.edit_text(
                    msg_text,
                    parse_mode='HTML',
                    reply_markup=get_user_navigation_kb(ticket.id, lang=db_user.language, show_call_manager=False)
                )
                
                # Если сработал автовызов, выходим и не отправляем [CALL_MANAGER] как обычный ответ
                await db.commit()
                return

            # Формальный ответ от ИИ (только если не было CALL_MANAGER)
            await ForumService.save_message(db=db, ticket_id=ticket.id, role='ai', content=ai_response)
            safe_response = sanitize_ai_response(ai_response)

            await status_msg.edit_text(
                f'🤖 <b>AI-ассистент:</b>\n\n{safe_response}',
                parse_mode='HTML',
                reply_markup=get_user_reply_kb(ticket.id, lang=db_user.language, show_call_manager=ticket.ai_enabled)
            )

            # Дублируем в форум
            try:
                await bot.send_message(
                    chat_id=forum_group_id,
                    message_thread_id=ticket.telegram_topic_id,
                    text=f'🤖 <b>AI-Ответ</b>:\n\n{safe_response}',
                    parse_mode='HTML',
                )
            except Exception as e:
                logger.error('ai_ticket_client.forum_copy_failed', error=str(e))
        else:
            # AI не сработал
            await status_msg.edit_text(
                texts.t('AI_TICKET_UNAVAILABLE', "🤖 <b>AI-ассистент временно недоступен.</b>\n\nВаше сообщение передано менеджерам. Ожидайте ответа специалиста."),
                parse_mode='HTML',
                reply_markup=get_user_reply_kb(ticket.id, lang=db_user.language, show_call_manager=ticket.ai_enabled)
            )

    except Exception as e:
        logger.error('ai_ticket_client.ai_processing_failed', error=str(e))
        try:
            await status_msg.edit_text(
                texts.t('AI_TICKET_ERROR', "⚠️ <b>Сообщение доставлено поддержке.</b>\n\nМы ответим вам в ближайшее время."),
                parse_mode='HTML',
                reply_markup=get_user_reply_kb(ticket.id, lang=db_user.language, show_call_manager=ticket.ai_enabled)
            )
        except Exception:
            pass

    await db.commit()


async def handle_call_manager(
    callback: types.CallbackQuery,
    bot: Bot,
    db: AsyncSession,
    db_user: User,
) -> None:
    """Пользователь нажал 'Позвать менеджера' — отключаем AI и уведомляем."""
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

    # Убираем кнопку вызова менеджера
    try:
        await callback.message.edit_reply_markup(
            reply_markup=get_user_navigation_kb(ticket_id, lang=db_user.language, show_call_manager=False)
        )
    except Exception:
        pass

    # Уведомляем в форум-топик
    forum_group_id_str = BotConfigurationService.get_current_value('SUPPORT_AI_FORUM_ID')
    if forum_group_id_str:
        from app.database.models_ai_ticket import ForumTicket
        stmt = select(ForumTicket).where(ForumTicket.id == ticket_id)
        result = await db.execute(stmt)
        ticket = result.scalars().first()
        if ticket and ticket.telegram_topic_id:
            try:
                await bot.send_message(
                    chat_id=int(forum_group_id_str),
                    message_thread_id=ticket.telegram_topic_id,
                    text='⚠️ <b>Клиент вызвал менеджера.</b> AI-ассистент отключён.',
                    parse_mode='HTML',
                    reply_markup=get_manager_kb(ticket_id, lang='ru', ai_enabled=False)
                )
            except Exception as e:
                logger.error('ai_ticket_client.manager_notify_failed', error=str(e))

    texts = get_texts(db_user.language)
    await callback.message.answer(
        texts.t('AI_TICKET_MANAGER_CALLED', '👨‍💻 Менеджер подключится к вашему обращению в ближайшее время. AI-ассистент отключён.'),
        reply_markup=get_user_navigation_kb(ticket_id, lang=db_user.language, show_call_manager=False)
    )
    await callback.answer()


def register_client_handlers(dp: Dispatcher) -> None:
    """Регистрация callback 'Вызвать менеджера'."""
    dp.callback_query.register(
        handle_call_manager,
        F.data.startswith('ai_ticket_call_manager:'),
    )
