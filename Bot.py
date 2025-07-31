import os
import json
import logging
import asyncio
import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка debug-логов
def debug(message):
    print(f"[DEBUG] {message}")

# Получение токена из переменной окружения
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Подключение к Google Sheets
def get_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS not найден в окружении")

    creds_dict = json.loads(creds_json)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key(creds_dict["sheet_id"])  # Добавь ключ таблицы как параметр в JSON
    worksheet = sh.sheet1
    return worksheet

# Интервалы отправки
INTERVALS = [0, 30]
already_sent = set()

# Словарь для хранения chat_id
user_data = {}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data["chat_id"] = chat_id
    await context.bot.send_message(chat_id=chat_id, text="Привет! Я начну спрашивать тебя каждые 30 минут 🙂")

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Запись в таблицу
    try:
        sheet = get_sheet()
        sheet.append_row([now, chat_id, text])
    except Exception as e:
        logger.error(f"Ошибка записи в Google Sheets: {e}")

# Фоновая задача: отправка каждые 30 минут
async def periodic_task(application: Application):
    while True:
        now = datetime.datetime.now()
        hour_minute = (now.hour, now.minute)

        chat_id = user_data.get("chat_id")
        debug(f"Проверка времени: {now.strftime('%H:%M:%S')} | chat_id: {chat_id}")

        if hour_minute[1] in INTERVALS:
            key = f"{now.hour}:{now.minute}"
            if key not in already_sent:
                already_sent.add(key)

                # Очищаем ключи, если начался новый час
                if now.minute == 0:
                    already_sent.clear()

                if chat_id:
                    await application.bot.send_message(
                        chat_id=chat_id,
                        text="Чем ты сейчас занимаешься?\nОцени полезность от 1 до 10\nДобавь комментарий, если хочешь."
                    )
                    debug(f"Отправляем сообщение в интервал {now.strftime('%Y-%m-%d %H:%M')}")
        await asyncio.sleep(20)

# Основной запуск
async def run():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск фоновой задачи
    application.job_queue.run_repeating(lambda _: asyncio.create_task(periodic_task(application)), interval=60, first=1)

    await application.run_polling()

def main():
    asyncio.run(run())

if __name__ == "__main__":
    main()
