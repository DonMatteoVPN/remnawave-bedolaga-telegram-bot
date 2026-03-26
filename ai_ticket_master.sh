#!/bin/bash
#
# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║       AI-TICKET MODULE INTEGRATION MASTER SCRIPT v3.0                        ║
# ║                     DonMatteo-AI-Tiket                                       ║
# ║                                                                              ║
# ║  Полностью автономный скрипт для интеграции модуля AI-Ticket                 ║
# ║  в любую версию Remnawave Bedolaga Telegram Bot                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
#
# Использование:
#   ./ai_ticket_master.sh          # Интерактивное меню
#   ./ai_ticket_master.sh install  # Автоматическая установка
#   ./ai_ticket_master.sh remove   # Удаление интеграции
#   ./ai_ticket_master.sh status   # Проверка статуса
#   ./ai_ticket_master.sh package  # Создать пакет для распространения
#
# ═══════════════════════════════════════════════════════════════════════════════

set -uo pipefail

# ─── Цвета ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# ─── Пути ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${SCRIPT_DIR}"
BACKUP_DIR="${APP_ROOT}/.ai_ticket_backups"
MODULE_DIR="${APP_ROOT}/app/modules/ai_ticket"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# ─── Версия ─────────────────────────────────────────────────────────────────
VERSION="3.0.0"

# ═══════════════════════════════════════════════════════════════════════════
# УТИЛИТЫ ВЫВОДА
# ═══════════════════════════════════════════════════════════════════════════

print_header() {
    echo -e "\n${PURPLE}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${PURPLE}║${NC}  ${CYAN}${BOLD}$1${NC}"
    echo -e "${PURPLE}╚══════════════════════════════════════════════════════════════════════════╝${NC}\n"
}

print_step() { echo -e "${BLUE}▶${NC} $1"; }
print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }
print_info() { echo -e "${CYAN}ℹ${NC} $1"; }

# ═══════════════════════════════════════════════════════════════════════════
# РЕЗЕРВНОЕ КОПИРОВАНИЕ
# ═══════════════════════════════════════════════════════════════════════════

backup_file() {
    local file="$1"
    mkdir -p "${BACKUP_DIR}"
    if [[ -f "$file" ]]; then
        local backup_path="${BACKUP_DIR}/$(basename "$file").${TIMESTAMP}.bak"
        cp "$file" "$backup_path"
        echo "$backup_path"
    fi
}

restore_from_backup() {
    local file="$1"
    local latest=$(ls -t "${BACKUP_DIR}/$(basename "$file")".*.bak 2>/dev/null | head -1)
    if [[ -n "$latest" && -f "$latest" ]]; then
        cp "$latest" "$file"
        return 0
    fi
    return 1
}

# ═══════════════════════════════════════════════════════════════════════════
# ПРОВЕРКА ИНТЕГРАЦИИ
# ═══════════════════════════════════════════════════════════════════════════

has_integration() {
    local file="$1"
    if [[ -f "$file" ]]; then
        if grep -qE "AI_TICKET_INTEGRATION|DonMatteo-AI-Tiket|from app.modules.ai_ticket|models_ai_ticket|'ai_tiket'" "$file" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

is_module_present() {
    [[ -d "${MODULE_DIR}" ]] && \
    [[ -f "${MODULE_DIR}/handlers/client.py" ]] && \
    [[ -f "${MODULE_DIR}/services/ai_manager.py" ]]
}

# ═══════════════════════════════════════════════════════════════════════════
# УМНЫЙ PYTHON ПАТЧЕР v3.0
# ═══════════════════════════════════════════════════════════════════════════

create_smart_patcher() {
    cat > "${APP_ROOT}/.ai_patcher.py" << 'PATCHER_SCRIPT'
#!/usr/bin/env python3
"""
AI-Ticket Smart Integration Patcher v3.0
Умный патчер который адаптируется к любой версии бота.
"""
import sys
import re
import json
import os
from pathlib import Path
from typing import Optional, Tuple

MARKER_START = "# >>> AI_TICKET_INTEGRATION_START"
MARKER_END = "# <<< AI_TICKET_INTEGRATION_END"

def log(msg: str):
    print(f"  {msg}")

def has_marker(content: str) -> bool:
    return MARKER_START in content or 'DonMatteo-AI-Tiket' in content

def remove_markers(content: str) -> str:
    """Удаляет блоки между маркерами."""
    lines = content.split('\n')
    result = []
    skip = False
    
    for line in lines:
        if MARKER_START in line or ('DonMatteo-AI-Tiket' in line and '---' in line):
            skip = True
            continue
        if skip and (MARKER_END in line or ('End' in line and '---' in line and 'guard' in line.lower())):
            skip = False
            continue
        if not skip:
            result.append(line)
    
    return '\n'.join(result)

def find_insert_point(content: str, patterns: list) -> Tuple[int, str]:
    """Находит точку вставки по списку паттернов."""
    lines = content.split('\n')
    for pattern in patterns:
        for i, line in enumerate(lines):
            if pattern in line:
                return i, line
    return -1, ""

def indent_block(block: str, indent: str) -> str:
    """Добавляет отступ к блоку кода."""
    lines = block.split('\n')
    return '\n'.join(indent + line if line.strip() else line for line in lines)

# ═══════════════════════════════════════════════════════════════════════════
# ПАТЧИНГ ОТДЕЛЬНЫХ ФАЙЛОВ
# ═══════════════════════════════════════════════════════════════════════════

def patch_config_py(filepath: Path, action: str) -> bool:
    """Патчит config.py - добавляет настройки SUPPORT_AI_*"""
    if not filepath.exists():
        return False
    
    content = filepath.read_text(encoding='utf-8')
    
    if action == 'remove':
        if has_marker(content):
            content = remove_markers(content)
            # Удаляем ai_tiket из комментария режимов
            content = content.replace(", ai_tiket", "")
            content = content.replace("ai_tiket, ", "")
            filepath.write_text(content, encoding='utf-8')
            log(f"REMOVED: config.py")
            return True
        return False
    
    # ADD
    if 'SUPPORT_AI_ENABLED' in content:
        log(f"SKIP: config.py - already has AI settings")
        return False
    
    # Ищем где вставить (после SUPPORT_SYSTEM_MODE или SUPPORT_MENU_ENABLED)
    insert_patterns = [
        "SUPPORT_SYSTEM_MODE:",
        "SUPPORT_MENU_ENABLED:",
        "SUPPORT_USERNAME:"
    ]
    
    lines = content.split('\n')
    insert_idx = -1
    
    for i, line in enumerate(lines):
        for pattern in insert_patterns:
            if pattern in line:
                insert_idx = i
                break
        if insert_idx >= 0:
            break
    
    if insert_idx < 0:
        log(f"WARNING: config.py - no suitable insert point found")
        return False
    
    # Обновляем комментарий о режимах если есть
    for i, line in enumerate(lines):
        if "SUPPORT_SYSTEM_MODE" in line and "# one of:" in line and "ai_tiket" not in line:
            lines[i] = line.replace("both", "both, ai_tiket")
    
    # Вставляем настройки AI после найденной строки
    ai_settings = '''    # >>> AI_TICKET_INTEGRATION_START
    # DonMatteo-AI-Tiket settings
    SUPPORT_AI_ENABLED: bool = False
    SUPPORT_AI_FORUM_ID: str | None = None  # Telegram Forum group ID (-100xxx)
    # <<< AI_TICKET_INTEGRATION_END'''
    
    # Находим конец блока настроек поддержки
    for i in range(insert_idx + 1, min(insert_idx + 10, len(lines))):
        if lines[i].strip().startswith('#') and 'SLA' in lines[i]:
            insert_idx = i - 1
            break
        elif lines[i].strip() and not lines[i].strip().startswith('SUPPORT'):
            insert_idx = i - 1
            break
    
    lines.insert(insert_idx + 1, ai_settings)
    content = '\n'.join(lines)
    filepath.write_text(content, encoding='utf-8')
    log(f"PATCHED: config.py")
    return True


def patch_bot_py(filepath: Path, action: str) -> bool:
    """Патчит bot.py - добавляет регистрацию manager handlers"""
    if not filepath.exists():
        return False
    
    content = filepath.read_text(encoding='utf-8')
    
    if action == 'remove':
        if has_marker(content):
            content = remove_markers(content)
            filepath.write_text(content, encoding='utf-8')
            log(f"REMOVED: bot.py")
            return True
        return False
    
    # ADD
    if 'register_manager_handlers' in content or (MARKER_START in content):
        log(f"SKIP: bot.py - already integrated")
        return False
    
    # Ищем tickets.register_handlers(dp)
    insert_patterns = [
        "tickets.register_handlers(dp)",
        "tickets.register_handlers(",
        "from app.handlers import tickets"
    ]
    
    idx, found_line = find_insert_point(content, insert_patterns)
    if idx < 0:
        log(f"WARNING: bot.py - no tickets registration found")
        return False
    
    lines = content.split('\n')
    
    # Определяем отступ
    indent = "    "
    if found_line:
        match = re.match(r'^(\s*)', found_line)
        if match:
            indent = match.group(1)
    
    integration_code = f'''
{indent}# >>> AI_TICKET_INTEGRATION_START
{indent}# DonMatteo-AI-Tiket: register manager-side Forum group handler
{indent}if settings.SUPPORT_AI_FORUM_ID:
{indent}    from app.modules.ai_ticket.handlers.manager import register_manager_handlers
{indent}    register_manager_handlers(dp)
{indent}    logger.info('🤖 AI-Tiket менеджер-обработчик зарегистрирован', forum_id=settings.SUPPORT_AI_FORUM_ID)
{indent}# <<< AI_TICKET_INTEGRATION_END'''
    
    # Вставляем после tickets.register_handlers
    for i, line in enumerate(lines):
        if 'tickets.register_handlers' in line:
            lines.insert(i + 1, integration_code)
            break
    
    content = '\n'.join(lines)
    filepath.write_text(content, encoding='utf-8')
    log(f"PATCHED: bot.py")
    return True


def patch_tickets_py(filepath: Path, action: str) -> bool:
    """Патчит tickets.py - добавляет маршрутизацию AI-Ticket"""
    if not filepath.exists():
        return False
    
    content = filepath.read_text(encoding='utf-8')
    
    if action == 'remove':
        if has_marker(content):
            content = remove_markers(content)
            filepath.write_text(content, encoding='utf-8')
            log(f"REMOVED: tickets.py")
            return True
        return False
    
    # ADD
    if 'ai_ticket_waiting_message' in content or 'handle_ai_ticket_message' in content:
        log(f"SKIP: tickets.py - already integrated")
        return False
    
    lines = content.split('\n')
    modified = False
    
    # 1. Найти функцию show_ticket_priority_selection и добавить routing guard
    routing_guard = '''    # >>> AI_TICKET_INTEGRATION_START
    # --- DonMatteo-AI-Tiket routing guard ---
    from app.services.support_settings_service import SupportSettingsService
    from app.config import settings
    
    mode = SupportSettingsService.get_system_mode()
    
    # Фоллбек: если режим ai_tiket, но ID форума не настроен
    if mode == 'ai_tiket' and not settings.SUPPORT_AI_FORUM_ID:
        logger.warning('tickets.ai_forum_id_not_set_fallback', user_id=callback.from_user.id)
        mode = 'tickets'

    if mode == 'ai_tiket':
        from app.modules.ai_ticket.handlers.client import handle_ai_ticket_message

        await callback.answer()
        service_name = settings.BOT_USERNAME or 'Техподдержка'
        
        if settings.SUPPORT_AI_ENABLED:
            prompt_text = (
                f'🤖 <b>{service_name}</b>\\n\\n'
                'Напишите ваш вопрос или опишите проблему — '
                'AI-ассистент ответит моментально.'
            )
        else:
            prompt_text = (
                f'👤 <b>{service_name}</b>\\n\\n'
                'Напишите ваш вопрос или опишите проблему — '
                'наши менеджеры ответят вам в ближайшее время.'
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
    # --- End routing guard ---
    # <<< AI_TICKET_INTEGRATION_END

'''
    
    # Ищем show_ticket_priority_selection
    for i, line in enumerate(lines):
        if 'async def show_ticket_priority_selection' in line:
            # Ищем первую строку после docstring
            j = i + 1
            in_docstring = False
            while j < len(lines):
                if '"""' in lines[j] or "'''" in lines[j]:
                    if in_docstring:
                        j += 1
                        break
                    else:
                        in_docstring = True
                        if lines[j].count('"""') == 2 or lines[j].count("'''") == 2:
                            j += 1
                            break
                j += 1
            
            # Пропускаем пустые строки и находим первый код
            while j < len(lines) and not lines[j].strip():
                j += 1
            
            # Вставляем routing guard
            lines.insert(j, routing_guard)
            modified = True
            break
    
    # 2. Добавить функцию fallback
    fallback_func = '''
# >>> AI_TICKET_INTEGRATION_START
async def _create_standard_ticket_fallback(
    message: types.Message,
    db: AsyncSession,
    db_user: User,
    user_text: str,
) -> None:
    """Фоллбек: создать стандартный тикет когда AI-Ticket Forum недоступен."""
    logger.info('tickets.fallback_creating_standard_ticket', user_id=db_user.id)
    texts = get_texts(db_user.language)
    
    media_type = None
    media_file_id = None
    media_caption = None
    if message.photo:
        media_type = 'photo'
        media_file_id = message.photo[-1].file_id
        media_caption = message.caption
    
    try:
        title = user_text[:100] if user_text else 'Обращение в поддержку'
        if len(user_text) > 100:
            title = title.rstrip() + '...'
        
        ticket = await TicketCRUD.create_ticket(
            db, db_user.id, title, user_text or '(вложение)', 'normal',
            media_type=media_type, media_file_id=media_file_id, media_caption=media_caption,
        )
        
        import html
        safe_title = html.escape(title if len(title) <= 200 else (title[:197] + '...'))
        creation_text = (
            f'✅ <b>Тикет #{ticket.id} создан</b>\\n\\n'
            f'📝 Заголовок: {safe_title}\\n'
            f'📊 Статус: {ticket.status_emoji} {texts.t("TICKET_STATUS_OPEN", "Открыт")}\\n'
            f'📅 Создан: {format_local_datetime(ticket.created_at, "%d.%m.%Y %H:%M")}\\n'
            + ('📎 Вложение: фото\\n' if media_type == 'photo' else '')
            + '\\n<i>⚠️ AI-ассистент временно недоступен, тикет передан менеджерам.</i>'
        )
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=texts.t('VIEW_TICKET', '👁️ Посмотреть тикет'), callback_data=f'view_ticket_{ticket.id}')],
            [types.InlineKeyboardButton(text=texts.t('BACK_TO_MENU', '🏠 В главное меню'), callback_data='back_to_menu')],
        ])
        await message.answer(creation_text, reply_markup=keyboard, parse_mode='HTML')
        await notify_admins_about_new_ticket(ticket, db)
        
    except Exception as e:
        logger.error('tickets.fallback_create_failed', error=str(e), user_id=db_user.id)
        await message.answer(texts.t('TICKET_CREATE_ERROR', '❌ Произошла ошибка.'))
# <<< AI_TICKET_INTEGRATION_END

'''
    
    # Вставляем fallback перед show_my_tickets
    if '_create_standard_ticket_fallback' not in content:
        for i, line in enumerate(lines):
            if 'async def show_my_tickets(' in line:
                lines.insert(i, fallback_func)
                modified = True
                break
    
    # 3. Добавить регистрацию AI-Ticket handlers в register_handlers
    handlers_registration = '''
    # >>> AI_TICKET_INTEGRATION_START
    # --- DonMatteo-AI-Tiket handlers ---
    from app.modules.ai_ticket.handlers.client import register_client_handlers
    from aiogram.filters import StateFilter
    register_client_handlers(dp)
    
    @dp.message(StateFilter('ai_ticket_waiting_message'))
    async def _ai_ticket_message_proxy(message: types.Message, state: FSMContext, db: AsyncSession, db_user: User):
        from app.modules.ai_ticket.handlers.client import handle_ai_ticket_message
        logger.info('ai_ticket_proxy.triggered', user_id=db_user.id)
        await handle_ai_ticket_message(message, message.bot, db, db_user)
    # <<< AI_TICKET_INTEGRATION_END
'''
    
    if 'register_client_handlers' not in content:
        for i, line in enumerate(lines):
            if 'def register_handlers(' in line:
                # Ищем конец функции
                j = i + 1
                indent_level = 0
                while j < len(lines):
                    if lines[j].strip() and not lines[j].startswith(' ') and not lines[j].startswith('\t'):
                        break
                    j += 1
                lines.insert(j - 1, handlers_registration)
                modified = True
                break
    
    if modified:
        content = '\n'.join(lines)
        filepath.write_text(content, encoding='utf-8')
        log(f"PATCHED: tickets.py")
        return True
    
    return False


def patch_models_py(filepath: Path, action: str) -> bool:
    """Патчит models.py - импортирует модели AI-Ticket"""
    if not filepath.exists():
        return False
    
    content = filepath.read_text(encoding='utf-8')
    
    if action == 'remove':
        if 'models_ai_ticket' in content:
            lines = [l for l in content.split('\n') if 'models_ai_ticket' not in l and 'AI_TICKET' not in l]
            filepath.write_text('\n'.join(lines), encoding='utf-8')
            log(f"REMOVED: models.py")
            return True
        return False
    
    # ADD
    if 'models_ai_ticket' in content:
        log(f"SKIP: models.py - already imports ai_ticket models")
        return False
    
    import_line = '''
# >>> AI_TICKET_INTEGRATION_START
# DonMatteo-AI-Tiket: импорт моделей для регистрации в SQLAlchemy
import app.database.models_ai_ticket  # noqa: F401, E402
# <<< AI_TICKET_INTEGRATION_END
'''
    
    content = content.rstrip() + '\n' + import_line
    filepath.write_text(content, encoding='utf-8')
    log(f"PATCHED: models.py")
    return True


def patch_support_settings_service_py(filepath: Path, action: str) -> bool:
    """Патчит support_settings_service.py - добавляет режим ai_tiket"""
    if not filepath.exists():
        return False
    
    content = filepath.read_text(encoding='utf-8')
    
    if action == 'remove':
        content = content.replace("'ai_tiket', ", "")
        content = content.replace(", 'ai_tiket'", "")
        content = content.replace("'ai_tiket'", "")
        filepath.write_text(content, encoding='utf-8')
        log(f"REMOVED: support_settings_service.py")
        return True
    
    # ADD
    if "'ai_tiket'" in content:
        log(f"SKIP: support_settings_service.py - already has ai_tiket")
        return False
    
    # Заменяем все места где перечисляются режимы
    replacements = [
        ("{'tickets', 'contact', 'both'}", "{'tickets', 'contact', 'both', 'ai_tiket'}"),
        ("{'tickets', 'both'}", "{'tickets', 'both', 'ai_tiket'}"),
        ("('tickets', 'contact', 'both')", "('tickets', 'contact', 'both', 'ai_tiket')"),
    ]
    
    modified = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            modified = True
    
    if modified:
        filepath.write_text(content, encoding='utf-8')
        log(f"PATCHED: support_settings_service.py")
        return True
    
    return False


def patch_system_settings_service_py(filepath: Path, action: str) -> bool:
    """Патчит system_settings_service.py - добавляет опцию ai_tiket"""
    if not filepath.exists():
        return False
    
    content = filepath.read_text(encoding='utf-8')
    
    if action == 'remove':
        lines = [l for l in content.split('\n') if 'ai_tiket' not in l and 'AI_TICKET' not in l]
        filepath.write_text('\n'.join(lines), encoding='utf-8')
        log(f"REMOVED: system_settings_service.py")
        return True
    
    # ADD
    if "'ai_tiket'" in content:
        log(f"SKIP: system_settings_service.py - already has ai_tiket")
        return False
    
    # Ищем SUPPORT_SYSTEM_MODE в CHOICES
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if "'SUPPORT_SYSTEM_MODE'" in line and '[' in line:
            # Ищем закрывающую скобку
            j = i
            while j < len(lines) and '],' not in lines[j]:
                j += 1
            # Вставляем перед ],
            if j < len(lines):
                indent = "            "
                lines.insert(j, f"{indent}# >>> AI_TICKET_INTEGRATION_START")
                lines.insert(j + 1, f"{indent}ChoiceOption('ai_tiket', '🤖 DonMatteo-AI-Tiket'),")
                lines.insert(j + 2, f"{indent}# <<< AI_TICKET_INTEGRATION_END")
                content = '\n'.join(lines)
                filepath.write_text(content, encoding='utf-8')
                log(f"PATCHED: system_settings_service.py")
                return True
    
    return False


def patch_admin_tickets_py(filepath: Path, action: str) -> bool:
    """Патчит cabinet admin_tickets.py - добавляет валидацию режима ai_tiket"""
    if not filepath.exists():
        return False
    
    content = filepath.read_text(encoding='utf-8')
    
    if action == 'remove':
        content = content.replace(", 'ai_tiket'", "")
        content = content.replace("'ai_tiket', ", "")
        content = content.replace(", or ai_tiket", "")
        filepath.write_text(content, encoding='utf-8')
        log(f"REMOVED: admin_tickets.py")
        return True
    
    # ADD
    if "'ai_tiket'" in content:
        log(f"SKIP: admin_tickets.py - already has ai_tiket")
        return False
    
    replacements = [
        ("('tickets', 'contact', 'both')", "('tickets', 'contact', 'both', 'ai_tiket')"),
        ("tickets, contact, both'", "tickets, contact, both, or ai_tiket'"),
    ]
    
    modified = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            modified = True
    
    if modified:
        filepath.write_text(content, encoding='utf-8')
        log(f"PATCHED: admin_tickets.py")
        return True
    
    return False


def patch_locales(locales_dir: Path, action: str) -> int:
    """Патчит JSON файлы локализации."""
    AI_TICKET_LOCALES = {
        'ru': {
            "ADMIN_SUPPORT_SETTINGS_MODE_AI_TIKET": "🤖 AI Тикет",
            "AI_TICKET_MESSAGE_RECEIVED": "📩 <b>Ваше сообщение получено!</b>\n\nНаш ИИ-ассистент уже анализирует ваш вопрос.\n\nПожалуйста, подождите.",
            "AI_TICKET_UNAVAILABLE": "⚠️ <b>ИИ временно недоступен</b>\n\nВаше сообщение передано менеджеру.",
            "AI_TICKET_ERROR": "❌ <b>Произошла ошибка</b>\n\nВаше обращение передано техподдержке.",
            "AI_TICKET_MANAGER_CALLED": "👨‍💻 <b>Менеджер вызван</b>\n\nОн ответит вам в ближайшее время.",
            "AI_TICKET_CALL_MANAGER": "🆘 Вызвать менеджера",
            "AI_TICKET_STATUS_OPEN": "Открыт",
            "AI_TICKET_STATUS_CLOSED": "Закрыт",
            "AI_TICKET_SPAM_CALLED": "🤖 <b>AI-ассистент:</b>\nПередаю ваш вопрос менеджеру для уточнения.",
            "AI_TICKET_MANAGER_AUTO_CALLED": "🤖 <b>AI-ассистент:</b>\nПередаю вопрос специалисту."
        },
        'en': {
            "ADMIN_SUPPORT_SETTINGS_MODE_AI_TIKET": "🤖 AI Ticket",
            "AI_TICKET_MESSAGE_RECEIVED": "📩 <b>Message received!</b>\n\nOur AI assistant is analyzing your question.\n\nPlease wait.",
            "AI_TICKET_UNAVAILABLE": "⚠️ <b>AI Temporarily Unavailable</b>\n\nYour message has been forwarded to a manager.",
            "AI_TICKET_ERROR": "❌ <b>An error occurred</b>\n\nYour request has been forwarded to support.",
            "AI_TICKET_MANAGER_CALLED": "👨‍💻 <b>Manager called</b>\n\nThey will respond shortly.",
            "AI_TICKET_CALL_MANAGER": "🆘 Call Manager",
            "AI_TICKET_STATUS_OPEN": "Open",
            "AI_TICKET_STATUS_CLOSED": "Closed",
            "AI_TICKET_SPAM_CALLED": "🤖 <b>AI Assistant:</b>\nForwarding to manager for clarification.",
            "AI_TICKET_MANAGER_AUTO_CALLED": "🤖 <b>AI Assistant:</b>\nForwarding to specialist."
        },
        'ua': {
            "ADMIN_SUPPORT_SETTINGS_MODE_AI_TIKET": "🤖 AI Тікет",
            "AI_TICKET_MESSAGE_RECEIVED": "📩 <b>Повідомлення отримано!</b>\n\nНаш ІІ-асистент аналізує ваше питання.",
            "AI_TICKET_UNAVAILABLE": "⚠️ <b>ІІ тимчасово недоступний</b>\n\nПовідомлення передано менеджеру.",
            "AI_TICKET_ERROR": "❌ <b>Сталася помилка</b>\n\nЗвернення передано техпідтримці.",
            "AI_TICKET_MANAGER_CALLED": "👨‍💻 <b>Менеджера викликано</b>",
            "AI_TICKET_CALL_MANAGER": "🆘 Викликати менеджера",
            "AI_TICKET_STATUS_OPEN": "Відкритий",
            "AI_TICKET_STATUS_CLOSED": "Закритий"
        },
        'zh': {
            "ADMIN_SUPPORT_SETTINGS_MODE_AI_TIKET": "🤖 AI工单",
            "AI_TICKET_MESSAGE_RECEIVED": "📩 <b>消息已收到！</b>\n\nAI助手正在分析您的问题。",
            "AI_TICKET_UNAVAILABLE": "⚠️ <b>AI暂时不可用</b>\n\n消息已转发给经理。",
            "AI_TICKET_ERROR": "❌ <b>发生错误</b>\n\n请求已转发给技术支持。",
            "AI_TICKET_MANAGER_CALLED": "👨‍💻 <b>已呼叫经理</b>",
            "AI_TICKET_CALL_MANAGER": "🆘 呼叫经理",
            "AI_TICKET_STATUS_OPEN": "开放",
            "AI_TICKET_STATUS_CLOSED": "关闭"
        },
        'fa': {
            "ADMIN_SUPPORT_SETTINGS_MODE_AI_TIKET": "🤖 تیکت هوش مصنوعی",
            "AI_TICKET_MESSAGE_RECEIVED": "📩 <b>پیام دریافت شد!</b>\n\nدستیار AI در حال تحلیل سوال شماست.",
            "AI_TICKET_UNAVAILABLE": "⚠️ <b>AI موقتاً در دسترس نیست</b>\n\nپیام به مدیر ارسال شد.",
            "AI_TICKET_ERROR": "❌ <b>خطایی رخ داد</b>\n\nدرخواست به پشتیبانی ارسال شد.",
            "AI_TICKET_MANAGER_CALLED": "👨‍💻 <b>مدیر فراخوانده شد</b>",
            "AI_TICKET_CALL_MANAGER": "🆘 فراخواندن مدیر",
            "AI_TICKET_STATUS_OPEN": "باز",
            "AI_TICKET_STATUS_CLOSED": "بسته"
        }
    }
    
    if not locales_dir.exists():
        return 0
    
    count = 0
    for locale_file in locales_dir.glob('*.json'):
        lang = locale_file.stem
        
        try:
            with open(locale_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            continue
        
        if action == 'remove':
            keys_to_remove = [k for k in data.keys() if k.startswith('AI_TICKET_') or k == 'ADMIN_SUPPORT_SETTINGS_MODE_AI_TIKET']
            if keys_to_remove:
                for k in keys_to_remove:
                    del data[k]
                with open(locale_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                log(f"REMOVED locales: {lang}.json")
                count += 1
        else:
            if 'AI_TICKET_MESSAGE_RECEIVED' in data:
                continue
            
            locales_to_add = AI_TICKET_LOCALES.get(lang, AI_TICKET_LOCALES['en'])
            data.update(locales_to_add)
            
            with open(locale_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log(f"PATCHED locales: {lang}.json")
            count += 1
    
    return count


def fix_pagination_py(filepath: Path) -> bool:
    """Исправляет синтаксис Python 3.12 для совместимости с 3.11"""
    if not filepath.exists():
        return False
    
    content = filepath.read_text(encoding='utf-8')
    
    # Проверяем нужно ли исправление
    if 'class PaginationResult[T]:' not in content:
        return False
    
    # Заменяем синтаксис
    old_code = '''from math import ceil
from typing import Any, TypeVar


T = TypeVar('T')


class PaginationResult[T]:
    def __init__(self, items: list[T], total_count: int, page: int, per_page: int):'''
    
    new_code = '''from math import ceil
from typing import Any, Generic, TypeVar, List


T = TypeVar('T')


class PaginationResult(Generic[T]):
    """Результат пагинации - совместимо с Python 3.11+"""
    def __init__(self, items: List[T], total_count: int, page: int, per_page: int):'''
    
    if old_code in content:
        content = content.replace(old_code, new_code)
        # Также исправляем функцию paginate_list
        content = content.replace(
            'def paginate_list[T](items: list[T],',
            'def paginate_list(items: List[T],'
        )
        filepath.write_text(content, encoding='utf-8')
        log(f"FIXED: pagination.py (Python 3.11 compatibility)")
        return True
    
    return False


def fix_migration_conflict(app_root: Path) -> bool:
    """Исправляет конфликты миграций."""
    migrations_dir = app_root / 'migrations/alembic/versions'
    if not migrations_dir.exists():
        return False
    
    # Ищем нашу миграцию ai_ticket
    ai_ticket_migration = None
    for f in migrations_dir.glob('*ai_ticket*.py'):
        ai_ticket_migration = f
        break
    
    if not ai_ticket_migration:
        return False
    
    content = ai_ticket_migration.read_text(encoding='utf-8')
    
    # Находим максимальный номер миграции
    max_revision = 0
    for f in migrations_dir.glob('*.py'):
        if f.name.startswith('__'):
            continue
        try:
            num = int(f.name.split('_')[0])
            if num > max_revision:
                max_revision = num
        except:
            pass
    
    # Проверяем текущий revision
    match = re.search(r"revision:\s*str\s*=\s*['\"](\d+)['\"]", content)
    if match:
        current_rev = int(match.group(1))
        if current_rev <= max_revision and 'ai_ticket' in ai_ticket_migration.name:
            # Нужно обновить revision
            new_rev = max_revision + 1
            new_down_rev = max_revision
            
            content = re.sub(
                r"revision:\s*str\s*=\s*['\"](\d+)['\"]",
                f"revision: str = '{new_rev:04d}'",
                content
            )
            content = re.sub(
                r"down_revision:\s*Union\[str,\s*None\]\s*=\s*['\"](\d+)['\"]",
                f"down_revision: Union[str, None] = '{new_down_rev:04d}'",
                content
            )
            content = re.sub(
                r"Revision ID:\s*\d+",
                f"Revision ID: {new_rev:04d}",
                content
            )
            content = re.sub(
                r"Revises:\s*\d+",
                f"Revises: {new_down_rev:04d}",
                content
            )
            
            # Переименовываем файл
            new_name = f"{new_rev:04d}_add_ai_ticket_tables.py"
            new_path = migrations_dir / new_name
            ai_ticket_migration.write_text(content, encoding='utf-8')
            if ai_ticket_migration.name != new_name:
                ai_ticket_migration.rename(new_path)
            
            log(f"FIXED: migration conflict (now revision {new_rev:04d})")
            return True
    
    return False


# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 3:
        print("Usage: patcher.py <action> <app_root>")
        sys.exit(1)
    
    action = sys.argv[1]
    app_root = Path(sys.argv[2])
    
    print(f"\n{'='*60}")
    print(f"  AI-Ticket Smart Patcher v3.0 - {action.upper()}")
    print(f"{'='*60}\n")
    
    if action == 'check':
        files_to_check = ['app/config.py', 'app/bot.py', 'app/handlers/tickets.py']
        integrated = sum(1 for f in files_to_check if (app_root / f).exists() and has_marker((app_root / f).read_text()))
        print(f"INTEGRATED_FILES={integrated}")
        sys.exit(0 if integrated > 0 else 1)
    
    # Патчим файлы
    files_to_patch = [
        ('app/config.py', patch_config_py),
        ('app/bot.py', patch_bot_py),
        ('app/handlers/tickets.py', patch_tickets_py),
        ('app/database/models.py', patch_models_py),
        ('app/services/support_settings_service.py', patch_support_settings_service_py),
        ('app/services/system_settings_service.py', patch_system_settings_service_py),
        ('app/cabinet/routes/admin_tickets.py', patch_admin_tickets_py),
    ]
    
    patched = 0
    for rel_path, patch_func in files_to_patch:
        fp = app_root / rel_path
        try:
            if patch_func(fp, action):
                patched += 1
        except Exception as e:
            log(f"ERROR patching {rel_path}: {e}")
    
    # Патчим локали
    locales_dir = app_root / 'app/localization/locales'
    patched += patch_locales(locales_dir, action)
    
    # Исправляем pagination.py для Python 3.11
    if action == 'add':
        pagination_path = app_root / 'app/utils/pagination.py'
        if fix_pagination_py(pagination_path):
            patched += 1
        
        # Исправляем конфликты миграций
        if fix_migration_conflict(app_root):
            patched += 1
    
    print(f"\n{'='*60}")
    print(f"  Total files modified: {patched}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
PATCHER_SCRIPT

    chmod +x "${APP_ROOT}/.ai_patcher.py"
}

# ═══════════════════════════════════════════════════════════════════════════
# КОМАНДА: СТАТУС
# ═══════════════════════════════════════════════════════════════════════════

cmd_status() {
    print_header "СТАТУС ИНТЕГРАЦИИ AI-TICKET v${VERSION}"
    
    # Модуль
    echo -e "${BOLD}Модуль:${NC}"
    if is_module_present; then
        print_success "AI-Ticket модуль найден: ${MODULE_DIR}"
    else
        print_error "AI-Ticket модуль НЕ найден"
    fi
    
    # Модели БД
    echo ""
    echo -e "${BOLD}База данных:${NC}"
    if [[ -f "${APP_ROOT}/app/database/models_ai_ticket.py" ]]; then
        print_success "models_ai_ticket.py"
    else
        print_warning "models_ai_ticket.py отсутствует"
    fi
    
    # Миграции
    if ls "${APP_ROOT}/migrations/alembic/versions/"*ai_ticket* 1>/dev/null 2>&1; then
        print_success "Миграции AI-Ticket найдены"
    else
        print_warning "Миграции AI-Ticket отсутствуют"
    fi
    
    # Интеграция в файлы
    echo ""
    echo -e "${BOLD}Интеграция в файлы:${NC}"
    
    local files=(
        "app/bot.py"
        "app/config.py"
        "app/handlers/tickets.py"
        "app/database/models.py"
        "app/services/support_settings_service.py"
        "app/services/system_settings_service.py"
    )
    
    for file in "${files[@]}"; do
        local fp="${APP_ROOT}/${file}"
        if [[ -f "$fp" ]]; then
            if has_integration "$fp"; then
                print_success "$(basename "$file")"
            else
                print_warning "$(basename "$file") - НЕ интегрирован"
            fi
        else
            print_error "$(basename "$file") - не найден"
        fi
    done
    
    # Локали
    echo ""
    echo -e "${BOLD}Локализации:${NC}"
    local locales_ok=0
    local locales_total=0
    local locales_dir="${APP_ROOT}/app/localization/locales"
    for locale in ru en ua zh fa; do
        if [[ -f "${locales_dir}/${locale}.json" ]]; then
            ((locales_total++)) || true
            if grep -q "AI_TICKET_MESSAGE_RECEIVED" "${locales_dir}/${locale}.json" 2>/dev/null; then
                ((locales_ok++)) || true
            fi
        fi
    done
    if [[ $locales_ok -gt 0 ]]; then
        print_success "AI-Ticket локализации: ${locales_ok}/${locales_total} языков"
    else
        print_warning "AI-Ticket локализации отсутствуют"
    fi
    
    # Резервные копии
    echo ""
    echo -e "${BOLD}Резервные копии:${NC}"
    if [[ -d "${BACKUP_DIR}" ]] && [[ "$(ls -A ${BACKUP_DIR} 2>/dev/null)" ]]; then
        local count=$(ls -1 "${BACKUP_DIR}"/*.bak 2>/dev/null | wc -l)
        print_success "${count} файл(ов) в ${BACKUP_DIR}"
    else
        print_info "Резервные копии отсутствуют"
    fi
    
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════
# КОМАНДА: УСТАНОВКА
# ═══════════════════════════════════════════════════════════════════════════

cmd_install() {
    print_header "УСТАНОВКА AI-TICKET ИНТЕГРАЦИИ v${VERSION}"
    
    # Проверяем наличие модуля
    if ! is_module_present; then
        print_error "Модуль AI-Ticket не найден!"
        print_info "Убедитесь, что папка app/modules/ai_ticket скопирована в проект"
        exit 1
    fi
    print_success "Модуль AI-Ticket найден"
    
    # Создаём резервные копии
    print_step "Создание резервных копий..."
    local files_to_backup=(
        "app/bot.py"
        "app/config.py"
        "app/handlers/tickets.py"
        "app/database/models.py"
        "app/services/support_settings_service.py"
        "app/services/system_settings_service.py"
        "app/cabinet/routes/admin_tickets.py"
        "app/utils/pagination.py"
    )
    
    for file in "${files_to_backup[@]}"; do
        local fp="${APP_ROOT}/${file}"
        if [[ -f "$fp" ]]; then
            backup_file "$fp" >/dev/null
        fi
    done
    print_success "Резервные копии созданы"
    
    # Создаём умный патчер
    print_step "Подготовка умного патчера..."
    create_smart_patcher
    
    # Патчим файлы
    print_step "Патчинг файлов..."
    python3 "${APP_ROOT}/.ai_patcher.py" add "${APP_ROOT}"
    
    # Копируем модели БД если нужно
    if [[ ! -f "${APP_ROOT}/app/database/models_ai_ticket.py" ]]; then
        if [[ -f "${MODULE_DIR}/models_ai_ticket.py" ]]; then
            cp "${MODULE_DIR}/models_ai_ticket.py" "${APP_ROOT}/app/database/"
            print_success "Скопирован models_ai_ticket.py"
        fi
    fi
    
    # Очистка
    rm -f "${APP_ROOT}/.ai_patcher.py"
    
    echo ""
    print_header "УСТАНОВКА ЗАВЕРШЕНА"
    print_success "AI-Ticket модуль интегрирован!"
    echo ""
    print_info "Следующие шаги:"
    echo "  1. Выполните миграции: alembic upgrade head"
    echo "  2. Перезапустите бота"
    echo "  3. В админке выберите режим '🤖 AI Тикет'"
    echo "  4. Укажите ID Forum-группы"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════
# КОМАНДА: УДАЛЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════

cmd_remove() {
    print_header "УДАЛЕНИЕ AI-TICKET ИНТЕГРАЦИИ"
    
    echo -e "${YELLOW}Это удалит интеграцию из всех файлов.${NC}"
    echo -e "${YELLOW}Сам модуль останется в ${MODULE_DIR}${NC}"
    echo ""
    read -p "Продолжить? (y/n): " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Отменено"
        exit 0
    fi
    
    create_smart_patcher
    
    print_step "Удаление интеграции..."
    python3 "${APP_ROOT}/.ai_patcher.py" remove "${APP_ROOT}"
    
    rm -f "${APP_ROOT}/.ai_patcher.py"
    
    echo ""
    print_header "УДАЛЕНИЕ ЗАВЕРШЕНО"
    print_success "Интеграция AI-Ticket удалена"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════
# КОМАНДА: ПАКЕТ
# ═══════════════════════════════════════════════════════════════════════════

cmd_package() {
    print_header "СОЗДАНИЕ ПАКЕТА ДЛЯ РАСПРОСТРАНЕНИЯ"
    
    if ! is_module_present; then
        print_error "Модуль AI-Ticket не найден"
        exit 1
    fi
    
    local pkg_dir="${APP_ROOT}/ai_ticket_package"
    local pkg_name="ai_ticket_v${VERSION}_${TIMESTAMP}.tar.gz"
    
    print_step "Подготовка файлов..."
    
    rm -rf "${pkg_dir}"
    mkdir -p "${pkg_dir}/app/modules"
    mkdir -p "${pkg_dir}/app/database"
    mkdir -p "${pkg_dir}/migrations/alembic/versions"
    
    # Копируем модуль
    rsync -a --exclude='__pycache__' --exclude='*.pyc' "${MODULE_DIR}" "${pkg_dir}/app/modules/"
    
    # Копируем модели БД
    if [[ -f "${APP_ROOT}/app/database/models_ai_ticket.py" ]]; then
        cp "${APP_ROOT}/app/database/models_ai_ticket.py" "${pkg_dir}/app/database/"
    fi
    
    # Копируем миграции
    cp "${APP_ROOT}/migrations/alembic/versions/"*ai_ticket* "${pkg_dir}/migrations/alembic/versions/" 2>/dev/null || true
    
    # Копируем мастер-скрипт
    cp "${APP_ROOT}/ai_ticket_master.sh" "${pkg_dir}/"
    
    # README
    cat > "${pkg_dir}/README.md" << 'README'
# AI-Ticket Module for Remnawave Bedolaga Bot
## DonMatteo-AI-Tiket v3.0

### Быстрая установка

```bash
# 1. Распакуйте в корень проекта
tar -xzf ai_ticket_v*.tar.gz -C /path/to/bot/

# 2. Запустите интеграцию
cd /path/to/bot
chmod +x ai_ticket_master.sh
./ai_ticket_master.sh install

# 3. Миграции
alembic upgrade head

# 4. Перезапустите бота
```

### Команды

```bash
./ai_ticket_master.sh install  # Установить
./ai_ticket_master.sh remove   # Удалить
./ai_ticket_master.sh status   # Статус
./ai_ticket_master.sh package  # Создать пакет
```

### Настройка

1. В боте: Админка → Поддержка → Режим "🤖 AI Тикет"
2. Укажите ID Forum-группы для менеджеров
3. Настройте AI-провайдеров (API ключи)
README

    # Архивируем
    print_step "Создание архива..."
    cd "${pkg_dir}" && tar -czf "../${pkg_name}" .
    rm -rf "${pkg_dir}"
    
    echo ""
    print_success "Пакет создан: ${pkg_name}"
    print_info "Размер: $(du -h "${APP_ROOT}/${pkg_name}" | cut -f1)"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════
# КОМАНДА: СПРАВКА
# ═══════════════════════════════════════════════════════════════════════════

cmd_help() {
    echo ""
    echo -e "${CYAN}${BOLD}AI-TICKET MASTER SCRIPT v${VERSION}${NC}"
    echo ""
    echo "Команды:"
    echo -e "  ${GREEN}install${NC}   - Интегрировать модуль"
    echo -e "  ${GREEN}remove${NC}    - Удалить интеграцию"
    echo -e "  ${GREEN}status${NC}    - Показать статус"
    echo -e "  ${GREEN}package${NC}   - Создать пакет"
    echo -e "  ${GREEN}help${NC}      - Справка"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════
# ИНТЕРАКТИВНОЕ МЕНЮ
# ═══════════════════════════════════════════════════════════════════════════

cmd_menu() {
    while true; do
        clear
        echo ""
        echo -e "${PURPLE}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${PURPLE}║${NC}          ${CYAN}${BOLD}AI-TICKET MODULE INTEGRATION${NC}                                 ${PURPLE}║${NC}"
        echo -e "${PURPLE}║${NC}                ${YELLOW}DonMatteo-AI-Tiket v${VERSION}${NC}                            ${PURPLE}║${NC}"
        echo -e "${PURPLE}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "  ${BOLD}Выберите действие:${NC}"
        echo ""
        echo -e "    ${GREEN}1)${NC} Проверить статус"
        echo -e "    ${GREEN}2)${NC} Установить интеграцию"
        echo -e "    ${GREEN}3)${NC} Удалить интеграцию"
        echo -e "    ${GREEN}4)${NC} Создать пакет"
        echo -e "    ${GREEN}5)${NC} Справка"
        echo ""
        echo -e "    ${RED}0)${NC} Выход"
        echo ""
        read -p "  Ваш выбор [0-5]: " choice
        
        case $choice in
            1) cmd_status; read -p "Нажмите Enter..." ;;
            2) cmd_install; read -p "Нажмите Enter..." ;;
            3) cmd_remove; read -p "Нажмите Enter..." ;;
            4) cmd_package; read -p "Нажмите Enter..." ;;
            5) cmd_help; read -p "Нажмите Enter..." ;;
            0) echo ""; print_info "До свидания!"; exit 0 ;;
            *) print_error "Неверный выбор" ;;
        esac
    done
}

# ═══════════════════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ═══════════════════════════════════════════════════════════════════════════

main() {
    if [[ $# -eq 0 ]]; then
        cmd_menu
        exit 0
    fi
    
    case "$1" in
        install)  cmd_install ;;
        remove|uninstall) cmd_remove ;;
        status)   cmd_status ;;
        package)  cmd_package ;;
        help|--help|-h) cmd_help ;;
        *)
            print_error "Неизвестная команда: $1"
            cmd_help
            exit 1
            ;;
    esac
}

main "$@"
