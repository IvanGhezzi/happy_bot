import os
import json
import logging
import asyncio
import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes,
    ConversationHandler
)

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройка debug-логов
def debug(message):
    print(f"[DEBUG] {message}")

# Получение токена из переменной окружения
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Состояния разговора
ASK_RATING, ASK_COMMENT = range(2)

# Глобальные переменные
user_data = {}
is_waiting_response = False
already_sent = set()

# Подключение к Google Sheets
def get_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS не найден в окружении")

    creds_dict = json.loads(creds_json)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    gc = gspread.authorize(credentials)
    sh = gc.open("HappierBot")  # Используем название таблицы
    worksheet = sh.sheet1
    return worksheet

# Проверка рабочего времени (5:00 - 02:00)
def is_working_time():
    hour = datetime.datetime.now().hour
    # Рабочее время: 5:00-23:59 и 0:00-01:59
    return hour >= 5 or hour < 2

# Сохранение в Google Sheets
def save_to_sheet(chat_id, activity, rating, comment):
    try:
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        
        # Определяем временной слот
        if now.minute < 30:
            time_slot = f"{now.strftime('%H')}:00–{now.strftime('%H')}:30"
        else:
            next_hour = (now.hour + 1) % 24
            time_slot = f"{now.strftime('%H')}:30–{next_hour:02d}:00"
        
        sheet = get_sheet()
        sheet.append_row([date_str, time_slot, activity, rating, comment])
        debug(f"Данные сохранены: {date_str} {time_slot} | {activity} | {rating} | {comment}")
        
    except Exception as e:
        logger.error(f"Ошибка записи в Google Sheets: {e}")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global user_data
    chat_id = update.effective_chat.id
    user_data["chat_id"] = chat_id
    debug(f"/start нажат. chat_id установлен: {chat_id}")
    await update.message.reply_text("Привет! Я начну спрашивать тебя каждые 30 минут о твоих занятиях :)")
    return ConversationHandler.END

# Начало диалога - получение активности
async def ask_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    activity = update.message.text
    
    # Сохраняем активность в контексте пользователя
    if chat_id not in user_data:
        user_data[chat_id] = {}
    user_data[chat_id]['activity'] = activity
    
    debug(f"Получена активность от {chat_id}: {activity}")
    await update.message.reply_text("Оцени полезность от 1 до 10")
    return ASK_RATING

# Получение рейтинга
async def get_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rating = update.message.text
    
    # Проверяем, что рейтинг - это число от 1 до 10
    try:
        rating_num = int(rating)
        if not (1 <= rating_num <= 10):
            await update.message.reply_text("Пожалуйста, введи число от 1 до 10")
            return ASK_RATING
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи число от 1 до 10")
        return ASK_RATING
    
    user_data[chat_id]['rating'] = rating
    debug(f"Получен рейтинг от {chat_id}: {rating}")
    await update.message.reply_text("Комментарий? (или напиши 'нет' если не хочешь добавлять)")
    return ASK_COMMENT

# Получение комментария и завершение диалога
async def get_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_waiting_response
    chat_id = update.effective_chat.id
    comment = update.message.text
    
    if comment.lower() in ['нет', 'no', '-']:
        comment = ''
    
    user_data[chat_id]['comment'] = comment
    debug(f"Получен комментарий от {chat_id}: {comment}")
    
    # Сохраняем все данные в таблицу
    activity = user_data[chat_id].get('activity', '')
    rating = user_data[chat_id].get('rating', '')
    
    save_to_sheet(chat_id, activity, rating, comment)
    
    await update.message.reply_text("Спасибо! Всё записано ✅")
    
    # Разрешаем отправку следующего вопроса
    is_waiting_response = False
    debug("Диалог завершен, разрешаем следующий вопрос")
    
    # Очищаем данные пользователя
    if chat_id in user_data:
        user_data[chat_id] = {}
    
    return ConversationHandler.END

# Отмена диалога
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_waiting_response
    is_waiting_response = False
    await update.message.reply_text("Диалог отменен.")
    return ConversationHandler.END

# Фоновая задача: отправка каждые 30 минут
async def periodic_task(application: Application):
    global is_waiting_response, already_sent
    
    while True:
        try:
            now = datetime.datetime.now()
            chat_id = user_data.get("chat_id")
            
            debug(f"Проверка времени: {now.strftime('%H:%M:%S')} | chat_id: {chat_id} | waiting: {is_waiting_response}")
            
            if not is_working_time():
                debug(f"Вне рабочего времени — бот молчит. {now.strftime('%H:%M:%S')}")
            elif chat_id and now.minute in [0, 30]:
                # Создаем уникальный ключ для этого временного слота
                key = now.strftime('%Y-%m-%d %H:') + ('00' if now.minute < 30 else '30')
                
                if key not in already_sent and not is_waiting_response:
                    already_sent.add(key)
                    is_waiting_response = True
                    
                    debug(f"Отправляем сообщение в интервал {key}")
                    await application.bot.send_message(
                        chat_id=chat_id,
                        text="Чем ты сейчас занимаешься?"
                    )
                elif is_waiting_response:
                    debug("Ожидаем предыдущий ответ — не шлём новое сообщение")
                elif key in already_sent:
                    debug(f"Сообщение для {key} уже было отправлено")
            
            # Очищаем старые ключи (старше 2 часов)
            current_time = now.timestamp()
            keys_to_remove = []
            for key in already_sent:
                try:
                    key_time = datetime.datetime.strptime(key, '%Y-%m-%d %H:%M').timestamp()
                    if current_time - key_time > 7200:  # 2 часа
                        keys_to_remove.append(key)
                except:
                    pass
            
            for key in keys_to_remove:
                already_sent.remove(key)
                
        except Exception as e:
            logger.error(f"Ошибка в periodic_task: {e}")
        
        await asyncio.sleep(30)  # Проверяем каждые 30 секунд

# Основной запуск
async def run():
    global user_data
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Создаем ConversationHandler для диалога
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, ask_activity)],
        states={
            ASK_RATING: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_rating)],
            ASK_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_comment)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    
    # Запускаем фоновую задачу
    asyncio.create_task(periodic_task(application))
    
    logger.info("Бот запущен и готов к работе")
    logger.info("Рабочее время: 05:00-02:00")
    logger.info("Интервалы опроса: каждые 30 минут (:00 и :30)")
    
    await application.run_polling(drop_pending_updates=True)

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN не найден в переменных окружения")
    
    asyncio.run(run())

if __name__ == "__main__":
    main()
