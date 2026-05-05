import telebot
import os

TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(
        message,
        "Здравствуйте 👋\n\n"
        "Я AI-консультант Elver AI.\n\n"
        "Чем занимается ваш бизнес?"
    )

@bot.message_handler(func=lambda m: True)
def all_messages(message):
    bot.reply_to(message, f"Принял: {message.text}")

print("Bot started...")
bot.infinity_polling(skip_pending=True)
