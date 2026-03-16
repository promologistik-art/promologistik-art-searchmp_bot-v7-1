import io
import csv
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import ADMIN_IDS, ADMIN_USERNAMES
from storage.database import (
    get_all_users, get_user_data, update_user_data,
    load_viewed_categories, get_db_path
)
from categories import load_cached_categories


# Декоратор для проверки прав админа
def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        user_id = user.id
        username = user.username or ""
        
        # Проверка на админа
        is_admin = (user_id in ADMIN_IDS or 
                   username in ADMIN_USERNAMES or 
                   get_user_data(user_id).get('is_admin', False))
        
        if not is_admin:
            if update.callback_query:
                await update.callback_query.edit_message_text("❌ У вас нет прав администратора.")
            else:
                await update.message.reply_text("❌ У вас нет прав администратора.")
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapper


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главная админ-панель"""
    user = update.effective_user
    
    # Проверка прав
    is_admin = (user.id in ADMIN_IDS or 
               user.username in ADMIN_USERNAMES or 
               get_user_data(user.id).get('is_admin', False))
    
    if not is_admin:
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return

    text = (
        "👑 **Админ-панель**\n\n"
        f"• Администратор: {user.first_name}\n"
        f"• ID: {user.id}\n"
        f"• Username: @{user.username}\n\n"
        "📋 **Доступные команды:**\n\n"
        "**👥 Управление пользователями:**\n"
        "/admin_users - список всех пользователей\n"
        "/admin_user <id> - информация о пользователе\n"
        "/admin_add <id> [дней] - добавить подписку\n"
        "/admin_remove <id> - снять подписку\n"
        "/admin_quota <id> <лимит> - установить спец. лимит\n"
        "/admin_make_admin <id> - сделать админом\n"
        "/admin_remove_admin <id> - убрать админа\n\n"
        "**📊 Статистика:**\n"
        "/admin_stats - общая статистика бота\n"
        "/admin_export - экспорт пользователей (CSV)\n\n"
        "**🔄 Управление категориями:**\n"
        "/admin_update_cats - принудительное обновление\n"
        "/admin_cats_stats - статистика категорий\n\n"
        "**📢 Рассылка:**\n"
        "/admin_broadcast - начать рассылку (отправьте текст)\n"
        "/admin_broadcast_photo - рассылка с фото\n\n"
        "**⚙️ Система:**\n"
        "/admin_logs - последние ошибки\n"
        "/admin_restart - перезапуск бота\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("🔄 Категории", callback_data="admin_cats")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast_menu")],
        [InlineKeyboardButton("⚙️ Система", callback_data="admin_system")]
    ]
    
    await update.message.reply_text(
        text, 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


@admin_required
async def admin_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех пользователей"""
    query = update.callback_query
    await query.answer()
    
    users = get_all_users()
    
    # Статистика
    total = len(users)
    admins = 0
    subscribers = 0
    free_users = 0
    
    for user_id, data in users.items():
        if data.get('is_admin') or str(user_id) in [str(a) for a in ADMIN_IDS]:
            admins += 1
        if data.get('subscription_active') or data.get('custom_quota'):
            subscribers += 1
        else:
            free_users += 1
    
    # Последние 10 активных пользователей
    recent_users = sorted(
        users.items(), 
        key=lambda x: x[1].get('last_activity', ''), 
        reverse=True
    )[:10]
    
    text = (
        f"👥 **Всего пользователей: {total}**\n"
        f"👑 Админов: {admins}\n"
        f"💰 С подпиской: {subscribers}\n"
        f"🆓 Бесплатных: {free_users}\n\n"
        "**Последние активные:**\n"
    )
    
    for user_id, data in recent_users:
        name = data.get('full_name', 'Без имени')
        username = data.get('username', 'нет')
        last_act = data.get('last_activity', 'никогда')
        if isinstance(last_act, str) and len(last_act) > 10:
            last_act = last_act[:10]
        
        text += f"• {name} (@{username}) - ID: {user_id} - {last_act}\n"
    
    keyboard = [
        [InlineKeyboardButton("📥 Экспорт в CSV", callback_data="admin_export")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


@admin_required
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Общая статистика бота"""
    query = update.callback_query
    await query.answer()
    
    users = get_all_users()
    viewed = load_viewed_categories()
    categories = load_cached_categories()
    
    # Подсчет запросов
    total_queries = sum(u.get('total_queries', 0) for u in users.values())
    today_queries = 0
    week_queries = 0
    
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    
    # Здесь должна быть логика подсчета запросов за период
    # Упрощенно:
    active_today = 0
    active_week = 0
    
    for user_id, data in users.items():
        last_act = data.get('last_activity', '')
        if isinstance(last_act, str):
            try:
                act_date = datetime.fromisoformat(last_act).date()
                if act_date == today:
                    active_today += 1
                if act_date >= week_ago:
                    active_week += 1
            except:
                pass
    
    text = (
        "📊 **Общая статистика**\n\n"
        f"👥 Пользователей: {len(users)}\n"
        f"📊 Категорий в базе: {len(categories) if categories else 0}\n"
        f"🟣 Просмотрено категорий: {len(viewed)}\n\n"
        f"📈 **Запросы:**\n"
        f"• Всего запросов: {total_queries}\n"
        f"• Сегодня: {today_queries}\n"
        f"• За неделю: {week_queries}\n\n"
        f"🔥 **Активность:**\n"
        f"• Сегодня: {active_today} пользователей\n"
        f"• За неделю: {active_week} пользователей\n"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


@admin_required
async def admin_export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экспорт пользователей в CSV"""
    query = update.callback_query
    await query.answer()
    
    users = get_all_users()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Заголовки
    writer.writerow(['ID', 'Username', 'Имя', 'Всего запросов', 
                     'Бесплатных использовано', 'Подписка до', 'Админ', 'Последняя активность'])
    
    for user_id, data in users.items():
        writer.writerow([
            user_id,
            data.get('username', ''),
            data.get('full_name', ''),
            data.get('total_queries', 0),
            data.get('free_queries_used', 0),
            data.get('subscription_until', ''),
            'Да' if data.get('is_admin') else 'Нет',
            data.get('last_activity', '')
        ])
    
    output.seek(0)
    
    await query.message.reply_document(
        document=io.BytesIO(output.getvalue().encode('utf-8-sig')),
        filename=f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        caption="📊 Экспорт пользователей"
    )


@admin_required
async def admin_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о конкретном пользователе"""
    if not context.args:
        await update.message.reply_text("Использование: /admin_user <ID пользователя>")
        return
    
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом")
        return
    
    data = get_user_data(user_id)
    if not data:
        await update.message.reply_text(f"❌ Пользователь с ID {user_id} не найден")
        return
    
    text = (
        f"👤 **Информация о пользователе**\n\n"
        f"• ID: `{user_id}`\n"
        f"• Username: @{data.get('username', 'нет')}\n"
        f"• Имя: {data.get('full_name', 'нет')}\n\n"
        f"📊 **Статистика:**\n"
        f"• Всего запросов: {data.get('total_queries', 0)}\n"
        f"• Бесплатных использовано: {data.get('free_queries_used', 0)}/{data.get('free_queries_total', 3)}\n\n"
        f"💰 **Подписка:**\n"
        f"• Активна: {'✅' if data.get('subscription_active') else '❌'}\n"
        f"• Действует до: {data.get('subscription_until', 'нет')}\n"
        f"• Спец. лимит: {data.get('custom_quota', 'нет')}\n\n"
        f"👑 Админ: {'✅' if data.get('is_admin') else '❌'}\n"
        f"⏱ Последняя активность: {data.get('last_activity', 'нет')}"
    )
    
    await update.message.reply_text(text, parse_mode='Markdown')

