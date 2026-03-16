#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Версия 160326 - Бот для анализа товаров на Ozon
Главный файл запуска
"""

import sys

from telegram.error import TimedOut
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)
from bot.handlers.admin_panel import (
    admin_panel, 
    admin_users_list, 
    admin_stats, 
    admin_export_csv, 
    admin_back, 
    admin_user_info_command
)

from config import (
    BOT_TOKEN, ADMIN_IDS, ADMIN_USERNAMES,
    CRITERIA_CHOICE, CRITERIA_REVENUE, CRITERIA_PRICE,
    CRITERIA_COMPETITORS, CRITERIA_VOLUME, UPLOAD_CATEGORIES
)
from config import logger
from storage.database import get_user_data, load_viewed_categories
from categories import load_cached_categories, collect_categories
from criteria import (
    criteria_start, criteria_choice_handler, criteria_revenue_input,
    criteria_price_input, criteria_competitors_input, criteria_volume_input,
    criteria_cancel
)
from services.analysis_service import analyze_command
from bot.handlers.upload_handler import upload_command, process_upload, upload_cancel
from bot.handlers.start_handler import (
    start, help_command, status_command, list_command,
    button_handler, after_analysis_handler, upload_button_handler,
    source_handler, switch_source_handler, show_categories_page
)
from admin_notify import add_user_access, list_users, user_info
import socket
socket.setdefaulttimeout(30)

def main():
    # В Windows консоль может быть не UTF-8 (например, cp1251) и падать на эмодзи.
    # Пытаемся переключить stdout/stderr на UTF-8, чтобы бот мог стартовать.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 60)
    print("БОТ ДЛЯ АНАЛИЗА OZON")
    print("=" * 60)
    print("✅ Первые 3 запроса бесплатно")
    print("✅ Загрузка своих категорий через Excel")
    print("✅ Админы имеют безлимит")
    print("✅ Управление пользователями")
    print("=" * 60)

    # Увеличенные таймауты Telegram API (актуально для отправки/скачивания файлов)
    request = HTTPXRequest(
        connect_timeout=60,
        read_timeout=180,
        write_timeout=180,
        pool_timeout=60,
    )
    app = Application.builder().token(BOT_TOKEN).request(request).build()

    async def error_handler(update, context):
        err = context.error
        logger.exception("Unhandled error", exc_info=err)
        # Пользователю показываем коротко, чтобы не было "молчания"
        try:
            if isinstance(err, TimedOut):
                text = "⏱ Таймаут Telegram. Попробуйте ещё раз через минуту."
            else:
                text = "❌ Произошла ошибка. Попробуйте ещё раз."
            if update and getattr(update, "effective_message", None):
                await update.effective_message.reply_text(text)
        except Exception:
            pass

    app.add_error_handler(error_handler)

    # Диалог настройки критериев
    crit_conv = ConversationHandler(
        entry_points=[CommandHandler('criteria', criteria_start)],
        states={
            CRITERIA_CHOICE: [CallbackQueryHandler(criteria_choice_handler)],
            CRITERIA_REVENUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, criteria_revenue_input)],
            CRITERIA_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, criteria_price_input)],
            CRITERIA_COMPETITORS: [MessageHandler(filters.TEXT & ~filters.COMMAND, criteria_competitors_input)],
            CRITERIA_VOLUME: [MessageHandler(filters.TEXT & ~filters.COMMAND, criteria_volume_input)],
        },
        fallbacks=[CommandHandler('cancel', criteria_cancel)],
    )

    # Диалог загрузки категорий
    upload_conv = ConversationHandler(
        entry_points=[CommandHandler('upload', upload_command)],
        states={
            UPLOAD_CATEGORIES: [
                MessageHandler(filters.Document.FileExtension("xlsx"), process_upload),
                MessageHandler(filters.Document.FileExtension("xls"), process_upload),
                MessageHandler(filters.ALL & ~filters.COMMAND,
                               lambda u, c: u.message.reply_text("❌ Пожалуйста, загрузите файл Excel (.xlsx или .xls)"))
            ],
        },
        fallbacks=[CommandHandler('cancel', upload_cancel)],
    )

    # Команды для всех пользователей
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("update", collect_categories))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("analyze", lambda u, c: analyze_command(u, c, ADMIN_IDS, ADMIN_USERNAMES)))

    # Админ-команды (уже существующие)
    app.add_handler(CommandHandler("add_user", add_user_access))
    app.add_handler(CommandHandler("users", list_users))
    app.add_handler(CommandHandler("user", user_info))

    # НОВЫЕ админ-команды (исправлено)
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("admin_user", admin_user_info_command))  # правильное имя функции

    # Диалоги
    app.add_handler(crit_conv)
    app.add_handler(upload_conv)

    # Обработчики кнопок (основные)
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(page_|jump_|sel_|do_)"))
    app.add_handler(CallbackQueryHandler(after_analysis_handler, pattern="^after_"))
    app.add_handler(CallbackQueryHandler(source_handler, pattern="^src_"))
    app.add_handler(CallbackQueryHandler(switch_source_handler, pattern="^switch_"))
    app.add_handler(CallbackQueryHandler(upload_button_handler, pattern="^(use_user_cats|goto_list|upload_again)$"))

    # НОВЫЕ обработчики кнопок для админ-панели (только ОДИН раз!)
    app.add_handler(CallbackQueryHandler(admin_users_list, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_export_csv, pattern="^admin_export$"))
    app.add_handler(CallbackQueryHandler(admin_back, pattern="^admin_back$"))

    # Добавьте в секцию CallbackQueryHandler:
    app.add_handler(CallbackQueryHandler(admin_users_list, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_export_csv, pattern="^admin_export$"))


    # Диалоги
    app.add_handler(crit_conv)
    app.add_handler(upload_conv)

    # Обработчики кнопок
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(page_|jump_|sel_|do_)"))
    app.add_handler(CallbackQueryHandler(after_analysis_handler, pattern="^after_"))
    app.add_handler(CallbackQueryHandler(source_handler, pattern="^src_"))
    app.add_handler(CallbackQueryHandler(switch_source_handler, pattern="^switch_"))
    app.add_handler(CallbackQueryHandler(upload_button_handler, pattern="^(use_user_cats|goto_list|upload_again)$"))

    print("🚀 Бот запущен! Отправьте /start")
    print("=" * 60)

    app.run_polling()


if __name__ == "__main__":
    main()