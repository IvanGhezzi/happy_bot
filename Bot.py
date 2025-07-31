import os
import asyncio
import datetime
import logging

import gspread
import nest_asyncio
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

nest_asyncio.apply()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Авторизация Google Sheets
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
google_credentials = os.environ.get("GOOGLE_CREDENTIALS")
credentials = ServiceAccountCredentials.from_json_keyfile_dict(eval(google_credentials), scope)
gc = gspread.authorize(credentials)
sheet = gc.open("HappierBot").sheet1

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([now, str(update.message.chat.id), text])
    await update.message.reply_text("Принято!")

async def run_bot():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    await application.run_polling()

def main():
    asyncio.run(run_bot())

if __name__ == '__main__':
    main()
