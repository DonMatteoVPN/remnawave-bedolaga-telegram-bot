import contextlib
import html
import re

import structlog
from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User
from app.localization.texts import get_texts
from app.services.support_settings_service import SupportSettingsService
from app.states import SupportSettingsStates
from app.utils.decorators import admin_required, error_handler


logger = structlog.get_logger(__name__)


def _get_support_settings_keyboard(language: str) -> types.InlineKeyboardMarkup:
    texts = get_texts(language)
    mode = SupportSettingsService.get_system_mode()
    menu_enabled = SupportSettingsService.is_support_menu_enabled()
    admin_notif = SupportSettingsService.get_admin_ticket_notifications_enabled()
    user_notif = SupportSettingsService.get_user_ticket_notifications_enabled()
    sla_enabled = SupportSettingsService.get_sla_enabled()
    sla_minutes = SupportSettingsService.get_sla_minutes()

    rows: list[list[types.InlineKeyboardButton]] = []

    status_enabled = texts.t('ADMIN_SUPPORT_SETTINGS_STATUS_ENABLED', 'Включены')
    status_disabled = texts.t('ADMIN_SUPPORT_SETTINGS_STATUS_DISABLED', 'Отключены')

    def mode_button(label_key: str, default: str, active: bool) -> str:
        prefix = '🔘' if active else '⚪'
        return f'{prefix} {texts.t(label_key, default)}'

    rows.append(
        [
            types.InlineKeyboardButton(
                text=(
                    f'{"✅" if menu_enabled else "🚫"} '
                    f'{texts.t("ADMIN_SUPPORT_SETTINGS_MENU_LABEL", "Пункт «Техподдержка» в меню")}'
                ),
                callback_data='admin_support_toggle_menu',
            )
        ]
    )

    rows.append(
        [
            types.InlineKeyboardButton(
                text=mode_button('ADMIN_SUPPORT_SETTINGS_MODE_TICKETS', 'Тикеты', mode == 'tickets'),
                callback_data='admin_support_mode_tickets',
            ),
            types.InlineKeyboardButton(
                text=mode_button('ADMIN_SUPPORT_SETTINGS_MODE_CONTACT', 'Контакт', mode == 'contact'),
                callback_data='admin_support_mode_contact',
            ),
            types.InlineKeyboardButton(
                text=mode_button('ADMIN_SUPPORT_SETTINGS_MODE_BOTH', 'Оба', mode == 'both'),
                callback_data='admin_support_mode_both',
            ),
        ]
    )
    
    # >>> AI_TICKET_INTEGRATION_START
    # DonMatteo-AI-Tiket - отдельная кнопка для режима AI
    rows.append(
        [
            types.InlineKeyboardButton(
                text=mode_button('ADMIN_SUPPORT_SETTINGS_MODE_AI_TIKET', '🤖 DonMatteo AI-Тикет', mode == 'ai_tiket'),
                callback_data='admin_support_mode_ai_tiket',
            ),
        ]
    )
    # DonMatteo-AI-Tiket: Показываем кнопки настроек AI когда режим ai_tiket активен
    if mode == 'ai_tiket':
        rows.append(
            [
                types.InlineKeyboardButton(
                    text='🤖 AI-Провайдеры',
                    callback_data='ai_providers_list',
                ),
                types.InlineKeyboardButton(
                    text='📚 FAQ-Статьи',
                    callback_data='ai_faq_list',
                ),
            ]
        )
        rows.append(
            [
                types.InlineKeyboardButton(
                    text='💬 Системный промпт',
                    callback_data='aip_prompt',
                ),
                types.InlineKeyboardButton(
                    text='🎯 Forum Group ID',
                    callback_data='ai_forum_id_settings',
                ),
            ]
        )
    # <<< AI_TICKET_INTEGRATION_END

    rows.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_SUPPORT_SETTINGS_EDIT_DESCRIPTION', '📝 Изменить описание'),
                callback_data='admin_support_edit_desc',
            )
        ]
    )

    # Notifications block
    rows.append(
        [
            types.InlineKeyboardButton(
                text=(
                    f'{"🔔" if admin_notif else "🔕"} '
                    f'{texts.t("ADMIN_SUPPORT_SETTINGS_ADMIN_NOTIFICATIONS", "Админ-уведомления")}: '
                    f'{status_enabled if admin_notif else status_disabled}'
                ),
                callback_data='admin_support_toggle_admin_notifications',
            )
        ]
    )
    rows.append(
        [
            types.InlineKeyboardButton(
                text=(
                    f'{"🔔" if user_notif else "🔕"} '
                    f'{texts.t("ADMIN_SUPPORT_SETTINGS_USER_NOTIFICATIONS", "Пользовательские уведомления")}: '
                    f'{status_enabled if user_notif else status_disabled}'
                ),
                callback_data='admin_support_toggle_user_notifications',
            )
        ]
    )

    # SLA block
    rows.append(
        [
            types.InlineKeyboardButton(
                text=(
                    f'{"⏰" if sla_enabled else "⏹️"} '
                    f'{texts.t("ADMIN_SUPPORT_SETTINGS_SLA_LABEL", "SLA")}: '
                    f'{status_enabled if sla_enabled else status_disabled}'
                ),
                callback_data='admin_support_toggle_sla',
            )
        ]
    )
    rows.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_SUPPORT_SETTINGS_SLA_TIME', '⏳ Время SLA: {minutes} мин').format(
                    minutes=sla_minutes
                ),
                callback_data='admin_support_set_sla_minutes',
            )
        ]
    )

    # Moderators
    moderators = SupportSettingsService.get_moderators()
    mod_count = len(moderators)
    rows.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_SUPPORT_SETTINGS_MODERATORS_COUNT', '🧑‍⚖️ Модераторы: {count}').format(
                    count=mod_count
                ),
                callback_data='admin_support_list_moderators',
            )
        ]
    )
    rows.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_SUPPORT_SETTINGS_ADD_MODERATOR', '➕ Назначить модератора'),
                callback_data='admin_support_add_moderator',
            ),
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_SUPPORT_SETTINGS_REMOVE_MODERATOR', '➖ Удалить модератора'),
                callback_data='admin_support_remove_moderator',
            ),
        ]
    )

    rows.append([types.InlineKeyboardButton(text=texts.BACK, callback_data='admin_submenu_support')])

    return types.InlineKeyboardMarkup(inline_keyboard=rows)


@admin_required
@error_handler
async def show_support_settings(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)
    desc = SupportSettingsService.get_support_info_text(db_user.language)
    await callback.message.edit_text(
        texts.t('ADMIN_SUPPORT_SETTINGS_TITLE', '🛟 <b>Настройки поддержки</b>')
        + '\n\n'
        + texts.t(
            'ADMIN_SUPPORT_SETTINGS_DESCRIPTION',
            'Режим работы и видимость в меню. Ниже текущее описание меню поддержки:',
        )
        + '\n\n'
        + desc,
        reply_markup=_get_support_settings_keyboard(db_user.language),
        parse_mode='HTML',
    )
    await callback.answer()


@admin_required
@error_handler
async def toggle_support_menu(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    current = SupportSettingsService.is_support_menu_enabled()
    SupportSettingsService.set_support_menu_enabled(not current)
    await show_support_settings(callback, db_user, db)


@admin_required
@error_handler
async def toggle_admin_notifications(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    current = SupportSettingsService.get_admin_ticket_notifications_enabled()
    SupportSettingsService.set_admin_ticket_notifications_enabled(not current)
    await show_support_settings(callback, db_user, db)


@admin_required
@error_handler
async def toggle_user_notifications(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    current = SupportSettingsService.get_user_ticket_notifications_enabled()
    SupportSettingsService.set_user_ticket_notifications_enabled(not current)
    await show_support_settings(callback, db_user, db)


@admin_required
@error_handler
async def toggle_sla(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    current = SupportSettingsService.get_sla_enabled()
    SupportSettingsService.set_sla_enabled(not current)
    await show_support_settings(callback, db_user, db)


class SupportAdvancedStates(StatesGroup):
    waiting_for_sla_minutes = State()
    waiting_for_moderator_id = State()


@admin_required
@error_handler
async def start_set_sla_minutes(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    texts = get_texts(db_user.language)
    await callback.message.edit_text(
        texts.t(
            'ADMIN_SUPPORT_SLA_SETUP_PROMPT',
            '⏳ <b>Настройка SLA</b>\n\nВведите количество минут ожидания ответа (целое число > 0):',
        ),
        parse_mode='HTML',
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text=texts.BACK, callback_data='admin_support_settings')]]
        ),
    )
    await state.set_state(SupportAdvancedStates.waiting_for_sla_minutes)
    await callback.answer()


@admin_required
@error_handler
async def handle_sla_minutes(message: types.Message, db_user: User, db: AsyncSession, state: FSMContext):
    texts = get_texts(db_user.language)
    text = (message.text or '').strip()
    try:
        minutes = int(text)
        if minutes <= 0 or minutes > 1440:
            raise ValueError
    except Exception:
        await message.answer(texts.t('ADMIN_SUPPORT_SLA_INVALID', '❌ Введите корректное число минут (1-1440)'))
        return
    SupportSettingsService.set_sla_minutes(minutes)
    await state.clear()
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=texts.t('DELETE_MESSAGE', '🗑 Удалить'), callback_data='admin_support_delete_msg'
                )
            ]
        ]
    )
    await message.answer(texts.t('ADMIN_SUPPORT_SLA_SAVED', '✅ Значение SLA сохранено'), reply_markup=markup)


@admin_required
@error_handler
async def start_add_moderator(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    texts = get_texts(db_user.language)
    await callback.message.edit_text(
        texts.t(
            'ADMIN_SUPPORT_ASSIGN_MODERATOR_PROMPT',
            '🧑‍⚖️ <b>Назначение модератора</b>\n\nОтправьте Telegram ID пользователя (число)',
        ),
        parse_mode='HTML',
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text=texts.BACK, callback_data='admin_support_settings')]]
        ),
    )
    await state.set_state(SupportAdvancedStates.waiting_for_moderator_id)
    await callback.answer()


@admin_required
@error_handler
async def start_remove_moderator(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    texts = get_texts(db_user.language)
    await callback.message.edit_text(
        texts.t(
            'ADMIN_SUPPORT_REMOVE_MODERATOR_PROMPT',
            '🧑‍⚖️ <b>Удаление модератора</b>\n\nОтправьте Telegram ID пользователя (число)',
        ),
        parse_mode='HTML',
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text=texts.BACK, callback_data='admin_support_settings')]]
        ),
    )
    await state.set_state(SupportAdvancedStates.waiting_for_moderator_id)
    # We'll reuse the same state; next message will decide action via flag
    await state.update_data(action='remove_moderator')
    await callback.answer()


@admin_required
@error_handler
async def handle_moderator_id(message: types.Message, db_user: User, db: AsyncSession, state: FSMContext):
    texts = get_texts(db_user.language)
    data = await state.get_data()
    action = data.get('action', 'add')
    text = (message.text or '').strip()
    try:
        tid = int(text)
    except Exception:
        await message.answer(texts.t('ADMIN_SUPPORT_INVALID_TELEGRAM_ID', '❌ Введите корректный Telegram ID (число)'))
        return
    if action == 'remove_moderator':
        ok = SupportSettingsService.remove_moderator(tid)
        msg = (
            texts.t('ADMIN_SUPPORT_MODERATOR_REMOVED_SUCCESS', '✅ Модератор {tid} удалён').format(tid=tid)
            if ok
            else texts.t('ADMIN_SUPPORT_MODERATOR_REMOVED_FAIL', '❌ Не удалось удалить модератора')
        )
    else:
        ok = SupportSettingsService.add_moderator(tid)
        msg = (
            texts.t('ADMIN_SUPPORT_MODERATOR_ADDED_SUCCESS', '✅ Пользователь {tid} назначен модератором').format(
                tid=tid
            )
            if ok
            else texts.t('ADMIN_SUPPORT_MODERATOR_ADDED_FAIL', '❌ Не удалось назначить модератора')
        )
    await state.clear()
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=texts.t('DELETE_MESSAGE', '🗑 Удалить'), callback_data='admin_support_delete_msg'
                )
            ]
        ]
    )
    await message.answer(msg, reply_markup=markup)


@admin_required
@error_handler
async def list_moderators(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)
    moderators = SupportSettingsService.get_moderators()
    if not moderators:
        await callback.answer(texts.t('ADMIN_SUPPORT_MODERATORS_EMPTY', 'Список пуст'), show_alert=True)
        return
    text = (
        texts.t('ADMIN_SUPPORT_MODERATORS_TITLE', '🧑‍⚖️ <b>Модераторы</b>')
        + '\n\n'
        + '\n'.join([f'• <code>{tid}</code>' for tid in moderators])
    )
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text=texts.BACK, callback_data='admin_support_settings')]]
    )
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=markup)
    await callback.answer()


@admin_required
@error_handler
async def set_mode_tickets(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    SupportSettingsService.set_system_mode('tickets')
    await show_support_settings(callback, db_user, db)


@admin_required
@error_handler
async def set_mode_contact(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    SupportSettingsService.set_system_mode('contact')
    await show_support_settings(callback, db_user, db)


@admin_required
@error_handler
async def set_mode_both(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    SupportSettingsService.set_system_mode('both')
    await show_support_settings(callback, db_user, db)


# >>> AI_TICKET_INTEGRATION_START
@admin_required
@error_handler
async def set_mode_ai_tiket(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Установить режим DonMatteo AI-Tiket."""
    from app.config import settings
    from app.services.system_settings_service import BotConfigurationService
    
    SupportSettingsService.set_system_mode('ai_tiket')
    
    # Включаем AI автоматически при выборе этого режима
    settings.SUPPORT_AI_ENABLED = True
    await BotConfigurationService.set_value(db, 'SUPPORT_AI_ENABLED', 'True')
    
    await show_support_settings(callback, db_user, db)


class AIForumSettingsStates(StatesGroup):
    """Состояния для настройки Forum ID."""
    waiting_for_forum_id = State()


@admin_required
@error_handler
async def show_ai_forum_settings(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    """Показать настройки Forum ID."""
    from app.services.system_settings_service import BotConfigurationService
    
    current_forum_id = BotConfigurationService.get_current_value('SUPPORT_AI_FORUM_ID') or 'Не задан'
    
    text = (
        '<b>🎯 Настройка Forum Group ID</b>\n\n'
        f'<b>Текущий ID:</b> <code>{current_forum_id}</code>\n\n'
        '<i>Это ID Telegram-группы с форумами, куда будут пересылаться тикеты.\n'
        'Формат: -100xxxxxxxxxx\n\n'
        'Бот должен быть администратором группы с правами на создание топиков.</i>'
    )
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='✏️ Изменить Forum ID', callback_data='ai_forum_id_edit')],
        [types.InlineKeyboardButton(text='🧪 Проверить подключение', callback_data='ai_forum_id_test')],
        [types.InlineKeyboardButton(text='« Назад', callback_data='admin_support_settings')],
    ])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode='HTML')


@admin_required
@error_handler
async def start_edit_forum_id(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    """Начать редактирование Forum ID."""
    await state.set_state(AIForumSettingsStates.waiting_for_forum_id)
    
    text = (
        '<b>✏️ Введите Forum Group ID</b>\n\n'
        'Формат: <code>-100xxxxxxxxxx</code>\n\n'
        '<i>Как получить ID:\n'
        '1. Создайте группу с темами (Enable Topics)\n'
        '2. Добавьте бота @getmyid_bot в группу\n'
        '3. Скопируйте Chat ID</i>'
    )
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='❌ Отмена', callback_data='ai_forum_id_settings')],
    ])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode='HTML')


@admin_required
@error_handler
async def handle_forum_id_input(message: types.Message, db_user: User, db: AsyncSession, state: FSMContext):
    """Обработка ввода Forum ID."""
    from app.services.system_settings_service import BotConfigurationService
    from app.config import settings
    
    forum_id = message.text.strip()
    
    # Валидация формата
    if not forum_id.startswith('-100') or not forum_id[1:].isdigit():
        await message.answer(
            '❌ Неверный формат ID.\n'
            'Правильный формат: <code>-100xxxxxxxxxx</code>',
            parse_mode='HTML'
        )
        return
    
    # Сохраняем
    settings.SUPPORT_AI_FORUM_ID = forum_id
    await BotConfigurationService.set_value(db, 'SUPPORT_AI_FORUM_ID', forum_id)
    
    await state.clear()
    
    await message.answer(
        f'✅ Forum ID сохранён: <code>{forum_id}</code>\n\n'
        'Теперь тикеты будут пересылаться в эту группу.',
        parse_mode='HTML'
    )


@admin_required
@error_handler
async def test_forum_connection(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    """Проверить подключение к Forum группе."""
    from app.services.system_settings_service import BotConfigurationService
    
    forum_id_str = BotConfigurationService.get_current_value('SUPPORT_AI_FORUM_ID')
    
    if not forum_id_str:
        await callback.answer('❌ Forum ID не задан!', show_alert=True)
        return
    
    try:
        forum_id = int(forum_id_str)
        # Пробуем создать тестовый топик
        from aiogram import Bot
        bot: Bot = callback.bot
        
        topic = await bot.create_forum_topic(
            chat_id=forum_id,
            name='🧪 Тест подключения'
        )
        
        await bot.send_message(
            chat_id=forum_id,
            message_thread_id=topic.message_thread_id,
            text='✅ Подключение успешно!\n\nЭтот топик можно удалить.'
        )
        
        await callback.answer('✅ Подключение успешно! Тестовый топик создан.', show_alert=True)
        
    except Exception as e:
        logger.error('ai_forum_test_failed', error=str(e))
        await callback.answer(f'❌ Ошибка: {str(e)[:100]}', show_alert=True)
# <<< AI_TICKET_INTEGRATION_END


@admin_required
@error_handler
async def start_edit_desc(callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext):
    texts = get_texts(db_user.language)
    current_desc_html = SupportSettingsService.get_support_info_text(db_user.language)
    # plain text for display-only code block
    current_desc_plain = re.sub(r'<[^>]+>', '', current_desc_html)

    kb_rows: list[list[types.InlineKeyboardButton]] = []
    kb_rows.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_SUPPORT_SEND_DESCRIPTION', '📨 Прислать текст'),
                callback_data='admin_support_send_desc',
            )
        ]
    )
    # Подготовим блок контакта (отдельным инлайном)
    from app.config import settings

    support_contact_display = settings.get_support_contact_display()
    kb_rows.append([types.InlineKeyboardButton(text=texts.BACK, callback_data='admin_support_settings')])

    text_parts = [
        texts.t('ADMIN_SUPPORT_EDIT_DESCRIPTION_TITLE', '📝 <b>Редактирование описания поддержки</b>'),
        '',
        texts.t('ADMIN_SUPPORT_EDIT_DESCRIPTION_CURRENT', 'Текущее описание:'),
        '',
        f'<code>{html.escape(current_desc_plain)}</code>',
    ]
    if support_contact_display:
        text_parts += [
            '',
            texts.t('ADMIN_SUPPORT_EDIT_DESCRIPTION_CONTACT_TITLE', '<b>Контакт для режима «Контакт»</b>'),
            f'<code>{html.escape(support_contact_display)}</code>',
            '',
            texts.t('ADMIN_SUPPORT_EDIT_DESCRIPTION_CONTACT_HINT', 'Добавьте в описание при необходимости.'),
        ]
    await callback.message.edit_text(
        '\n'.join(text_parts), reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode='HTML'
    )
    await state.set_state(SupportSettingsStates.waiting_for_desc)
    await callback.answer()


@admin_required
@error_handler
async def handle_new_desc(message: types.Message, db_user: User, db: AsyncSession, state: FSMContext):
    texts = get_texts(db_user.language)
    new_text = message.html_text or message.text
    SupportSettingsService.set_support_info_text(db_user.language, new_text)
    await state.clear()
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=texts.t('DELETE_MESSAGE', '🗑 Удалить'), callback_data='admin_support_delete_msg'
                )
            ]
        ]
    )
    await message.answer(texts.t('ADMIN_SUPPORT_DESCRIPTION_UPDATED', '✅ Описание обновлено.'), reply_markup=markup)


@admin_required
@error_handler
async def send_desc_copy(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    # send plain text for easy copying
    texts = get_texts(db_user.language)
    current_desc_html = SupportSettingsService.get_support_info_text(db_user.language)
    current_desc_plain = re.sub(r'<[^>]+>', '', current_desc_html)
    # attach delete button to the sent message
    markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=texts.t('DELETE_MESSAGE', '🗑 Удалить'), callback_data='admin_support_delete_msg'
                )
            ]
        ]
    )
    if len(current_desc_plain) <= 4000:
        await callback.message.answer(current_desc_plain, reply_markup=markup)
    else:
        # split long messages (attach delete only to the last chunk)
        chunk = 0
        while chunk < len(current_desc_plain):
            next_chunk = current_desc_plain[chunk : chunk + 4000]
            is_last = (chunk + 4000) >= len(current_desc_plain)
            await callback.message.answer(next_chunk, reply_markup=(markup if is_last else None))
            chunk += 4000
    await callback.answer(texts.t('ADMIN_SUPPORT_DESCRIPTION_SENT', 'Текст отправлен ниже'))


@error_handler
async def delete_sent_message(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    # Allow admins and moderators to delete informational notifications
    try:
        may_delete = settings.is_admin(callback.from_user.id) or SupportSettingsService.is_moderator(
            callback.from_user.id
        )
    except Exception:
        may_delete = False
    texts = get_texts(db_user.language if db_user else 'ru')
    if not may_delete:
        await callback.answer(texts.ACCESS_DENIED, show_alert=True)
        return
    try:
        await callback.message.delete()
    finally:
        with contextlib.suppress(Exception):
            await callback.answer(texts.t('ADMIN_SUPPORT_MESSAGE_DELETED', 'Сообщение удалено'))


def register_handlers(dp: Dispatcher):
    dp.callback_query.register(show_support_settings, F.data == 'admin_support_settings')
    dp.callback_query.register(toggle_support_menu, F.data == 'admin_support_toggle_menu')
    dp.callback_query.register(set_mode_tickets, F.data == 'admin_support_mode_tickets')
    dp.callback_query.register(set_mode_contact, F.data == 'admin_support_mode_contact')
    dp.callback_query.register(set_mode_both, F.data == 'admin_support_mode_both')
    # >>> AI_TICKET_INTEGRATION_START
    dp.callback_query.register(set_mode_ai_tiket, F.data == 'admin_support_mode_ai_tiket')
    # DonMatteo-AI-Tiket: настройки Forum ID
    dp.callback_query.register(show_ai_forum_settings, F.data == 'ai_forum_id_settings')
    dp.callback_query.register(start_edit_forum_id, F.data == 'ai_forum_id_edit')
    dp.callback_query.register(test_forum_connection, F.data == 'ai_forum_id_test')
    dp.message.register(handle_forum_id_input, AIForumSettingsStates.waiting_for_forum_id)
    # DonMatteo-AI-Tiket: регистрация админ-хендлеров для провайдеров и FAQ
    from app.modules.ai_ticket.handlers.ai_provider_admin import register_ai_provider_handlers
    from app.modules.ai_ticket.handlers.faq_admin import register_faq_handlers
    register_ai_provider_handlers(dp)
    register_faq_handlers(dp)
    # <<< AI_TICKET_INTEGRATION_END
    dp.callback_query.register(start_edit_desc, F.data == 'admin_support_edit_desc')
    dp.callback_query.register(send_desc_copy, F.data == 'admin_support_send_desc')
    dp.callback_query.register(delete_sent_message, F.data == 'admin_support_delete_msg')
    dp.callback_query.register(toggle_admin_notifications, F.data == 'admin_support_toggle_admin_notifications')
    dp.callback_query.register(toggle_user_notifications, F.data == 'admin_support_toggle_user_notifications')
    dp.callback_query.register(toggle_sla, F.data == 'admin_support_toggle_sla')
    dp.callback_query.register(start_set_sla_minutes, F.data == 'admin_support_set_sla_minutes')
    dp.callback_query.register(start_add_moderator, F.data == 'admin_support_add_moderator')
    dp.callback_query.register(start_remove_moderator, F.data == 'admin_support_remove_moderator')
    dp.callback_query.register(list_moderators, F.data == 'admin_support_list_moderators')
    dp.message.register(handle_new_desc, SupportSettingsStates.waiting_for_desc)
    dp.message.register(handle_sla_minutes, SupportAdvancedStates.waiting_for_sla_minutes)
    dp.message.register(handle_moderator_id, SupportAdvancedStates.waiting_for_moderator_id)
