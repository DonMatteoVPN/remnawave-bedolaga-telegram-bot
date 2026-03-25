"""
Integration Registry - Центральный реестр всех интеграционных точек модуля AI-Ticket.

Используется мастер-скриптом для:
1. Точечной интеграции модуля в оригинальные файлы
2. Отката изменений и восстановления оригиналов
3. Проверки статуса интеграции
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class IntegrationPoint:
    """Описание точки интеграции в оригинальный файл."""
    file_path: str                          # Путь к файлу относительно /app
    marker_start: str                       # Маркер начала вставки (комментарий в коде)
    marker_end: str                         # Маркер конца вставки
    code_block: str                         # Код для вставки
    insert_type: Literal['after', 'before', 'replace']  # Тип вставки
    search_pattern: str | None = None       # Паттерн для поиска места вставки (если не по маркеру)
    description: str = ''                   # Описание что делает эта интеграция


# Уникальные маркеры для идентификации интегрированного кода
AI_TICKET_MARKER_START = '# >>> AI_TICKET_INTEGRATION_START'
AI_TICKET_MARKER_END = '# <<< AI_TICKET_INTEGRATION_END'


# ═══════════════════════════════════════════════════════════════════════════
# РЕЕСТР ВСЕХ ТОЧЕК ИНТЕГРАЦИИ
# ═══════════════════════════════════════════════════════════════════════════

INTEGRATION_POINTS: list[IntegrationPoint] = [
    # ─────────────────────────────────────────────────────────────────────────
    # 1. bot.py - Регистрация manager handlers для Forum-группы
    # ─────────────────────────────────────────────────────────────────────────
    IntegrationPoint(
        file_path='app/bot.py',
        marker_start=AI_TICKET_MARKER_START,
        marker_end=AI_TICKET_MARKER_END,
        search_pattern='tickets.register_handlers(dp)',
        insert_type='after',
        code_block='''
    # >>> AI_TICKET_INTEGRATION_START
    # DonMatteo-AI-Tiket: register manager-side Forum group handler
    if settings.SUPPORT_AI_FORUM_ID:
        from app.modules.ai_ticket.handlers.manager import register_manager_handlers

        register_manager_handlers(dp)
        logger.info('AI-Tiket manager handler registered', forum_id=settings.SUPPORT_AI_FORUM_ID)
    # <<< AI_TICKET_INTEGRATION_END
''',
        description='Регистрация обработчика сообщений менеджеров в Forum-группе'
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # 2. handlers/admin/support_settings.py - Регистрация AI admin handlers
    # ─────────────────────────────────────────────────────────────────────────
    IntegrationPoint(
        file_path='app/handlers/admin/support_settings.py',
        marker_start=AI_TICKET_MARKER_START,
        marker_end=AI_TICKET_MARKER_END,
        search_pattern='def register_handlers(dp: Dispatcher):',
        insert_type='after',
        code_block='''
    # >>> AI_TICKET_INTEGRATION_START
    # DonMatteo-AI-Tiket: multi-provider, FAQ, prompt handlers
    from app.modules.ai_ticket.handlers.ai_provider_admin import register_ai_provider_handlers
    from app.modules.ai_ticket.handlers.faq_admin import register_faq_handlers

    register_ai_provider_handlers(dp)
    register_faq_handlers(dp)
    # <<< AI_TICKET_INTEGRATION_END
''',
        description='Регистрация админ-хендлеров для провайдеров и FAQ'
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # 3. handlers/tickets.py - Маршрутизация на AI-тикеты
    # ─────────────────────────────────────────────────────────────────────────
    IntegrationPoint(
        file_path='app/handlers/tickets.py',
        marker_start=AI_TICKET_MARKER_START,
        marker_end=AI_TICKET_MARKER_END,
        search_pattern="mode = SupportSettingsService.get_system_mode()",
        insert_type='after',
        code_block='''
    # >>> AI_TICKET_INTEGRATION_START
    from app.config import settings
    
    # Фоллбек: если режим ai_tiket, но ID форума не настроен — откатываемся на стандартные тикеты
    if mode == 'ai_tiket' and not settings.SUPPORT_AI_FORUM_ID:
        logger.warning('tickets.ai_forum_id_not_set_fallback_to_standard', user_id=callback.from_user.id)
        mode = 'tickets'

    if mode == 'ai_tiket':
        from app.modules.ai_ticket.handlers.client import handle_ai_ticket_message

        await callback.answer()
        service_name = settings.BOT_USERNAME or 'Техподдержка'
        
        if settings.SUPPORT_AI_ENABLED:
            prompt_text = (
                f'AI-ассистент <b>{service_name}</b>\\n\\n'
                'Напишите ваш вопрос — AI ответит моментально.'
            )
        else:
            prompt_text = (
                f'<b>{service_name}</b>\\n\\n'
                'Напишите ваш вопрос — менеджеры ответят в ближайшее время.'
            )
            
        cancel_kb = get_ticket_cancel_keyboard(db_user.language)
        
        try:
            await callback.message.edit_text(prompt_text, reply_markup=cancel_kb, parse_mode='HTML')
        except TelegramBadRequest:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(prompt_text, reply_markup=cancel_kb, parse_mode='HTML')
            
        await state.set_state('ai_ticket_waiting_message')
        return
    # <<< AI_TICKET_INTEGRATION_END
''',
        description='Маршрутизация создания тикета на AI-систему'
    ),
]


# ═══════════════════════════════════════════════════════════════════════════
# ЗАВИСИМОСТИ МОДУЛЯ (файлы, которые должны существовать)
# ═══════════════════════════════════════════════════════════════════════════

MODULE_FILES = [
    'app/modules/ai_ticket/__init__.py',
    'app/modules/ai_ticket/handlers/__init__.py',
    'app/modules/ai_ticket/handlers/client.py',
    'app/modules/ai_ticket/handlers/manager.py',
    'app/modules/ai_ticket/handlers/ai_provider_admin.py',
    'app/modules/ai_ticket/handlers/faq_admin.py',
    'app/modules/ai_ticket/services/__init__.py',
    'app/modules/ai_ticket/services/ai_manager.py',
    'app/modules/ai_ticket/services/forum_service.py',
    'app/modules/ai_ticket/services/prompt_service.py',
    'app/modules/ai_ticket/utils/formatting.py',
    'app/modules/ai_ticket/utils/keyboards.py',
    'app/modules/ai_ticket/utils/media_sender.py',
    'app/database/models_ai_ticket.py',
]

MIGRATION_FILES = [
    'migrations/alembic/versions/0014_add_ai_ticket_tables.py',
    'migrations/alembic/versions/0015_add_media_to_forum_ticket_messages.py',
    'migrations/alembic/versions/0016_add_ai_faq_media.py',
]

CONFIG_KEYS = [
    'SUPPORT_AI_ENABLED',
    'SUPPORT_AI_FORUM_ID',
]


def get_all_integration_points() -> list[IntegrationPoint]:
    """Возвращает все точки интеграции."""
    return INTEGRATION_POINTS


def get_module_files() -> list[str]:
    """Возвращает список файлов модуля."""
    return MODULE_FILES


def get_migration_files() -> list[str]:
    """Возвращает список файлов миграций."""
    return MIGRATION_FILES
