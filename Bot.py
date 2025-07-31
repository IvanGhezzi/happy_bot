import os
import logging
import asyncio
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальная переменная для Google Sheets
sheet = None

def init_google_sheets():
    """Инициализация подключения к Google Sheets"""
    global sheet
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        google_credentials = os.environ["GOOGLE_CREDENTIALS"]
        
        # Записываем credentials в файл
        with open("google_credentials.json", "w") as f:
            f.write(google_credentials)
        
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_credentials.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open("HappierBot").sheet1
        logger.info("Google Sheets подключены успешно")
    except Exception as e:
        logger.error(f"Ошибка подключения к Google Sheets: {e}")
        raise

# Обработчик команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        await update.message.reply_text("Привет! Я работаю.")
        logger.info(f"Команда /start от пользователя {update.effective_user.username}")
    except Exception as e:
        logger.error(f"Ошибка в команде start: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    try:
        user = update.effective_user
        message = update.message.text
        
        # Записываем в таблицу
        if sheet:
            sheet.append_row([user.username or user.first_name, message])
            await update.message.reply_text("Записал в таблицу!")
            logger.info(f"Сообщение от {user.username or user.first_name} записано в таблицу")
        else:
            await update.message.reply_text("Ошибка подключения к таблице!")
            logger.error("Sheet не инициализирован")
            
    except Exception as e:
        logger.error(f"Ошибка в handle_message: {e}")
        await update.message.reply_text("Произошла ошибка при обработке сообщения.")

# Запуск бота
async def main():
    """Основная функция запуска бота"""
    try:
        # Инициализируем Google Sheets
        init_google_sheets()
        
        # Получаем токен бота
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_TOKEN не найден в переменных окружения")
        
        # Создаем приложение
        app = ApplicationBuilder().token(token).build()
        
        # Добавляем обработчики
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("Бот запущен и готов к работе")
        
        # Запускаем polling
        await app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
