import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import telebot
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
# Google Sheets
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credentials.json",
    scope
)

gs_client = gspread.authorize(creds)

sheet = gs_client.open_by_key(
    "19WfH3kS4C4PPku25-N1tbB_wxlb04iIIPku3r5sKbq0"
).sheet1


def save_lead(message):
    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "нет"
    )

    name = message.from_user.first_name or "Без имени"
    text = message.text
    date = datetime.now().strftime("%d.%m.%Y %H:%M")

    # запись в таблицу
    sheet.append_row([
        date,
        name,
        username,
        text
    ])

    # уведомление тебе
    bot.send_message(
        1908342578,
        f"🔥 Новый лид\n\n"
        f"Имя: {name}\n"
        f"Username: {username}\n"
        f"Контакт: {text}\n"
        f"Дата: {date}"
    )

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)
user_memory = {}
lead_words = [
    "интересно",
    "хочу",
    "давайте",
    "цена",
    "стоимость",
    "сколько",
    "почем",
    "подключить",
    "связаться",
    "нужна",
    "готов",
    "заинтересован",
    "интересует"
]
def save_lead(message):
    name = message.from_user.first_name or "Без имени"
    username = message.from_user.username or "нет username"
    chat_id = message.chat.id
    text = message.text

    with open("leads.txt", "a", encoding="utf-8") as f:
        f.write(
            f"Имя: {name}\n"
            f"Username: @{username}\n"
            f"Chat ID: {chat_id}\n"
            f"Контакт: {text}\n"
            f"{'-'*30}\n"
        )

# чтобы Render видел открытый порт
def run_web():
    port = int(os.environ.get("PORT", 10000))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is alive")

    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


threading.Thread(target=run_web, daemon=True).start()


SYSTEM_PROMPT = """
Ты — Elver AI, эксперт по автоматизации бизнеса и внедрению AI.

Твоя задача:
- быстро понять бизнес клиента
- показать экспертность с первого ответа
- выявить потери денег / времени / заявок
- предложить решение
- мягко подвести клиента к заявке или консультации

Как отвечать:
1) коротко и уверенно
2) показывать понимание ниши клиента
3) говорить по делу
4) задавать ОДИН точный вопрос за сообщение
5) вести диалог к продаже

Стиль:
- экспертно
- дружелюбно
- современно
- без воды
- без канцелярита

Примеры:
Если пишет "у меня салон красоты":
ответь примерно так:
"Здравствуйте 👋

Салон красоты — одна из лучших ниш для автоматизации.

Обычно там теряют клиентов в 3 местах:
• пропущенные звонки
• запись вручную в сообщениях
• отсутствие возврата клиентов

Подскажите: запись у вас сейчас идёт через телефон, WhatsApp или соцсети?"

Если пишет про магазин:
сфокусируйся на заявках, повторных продажах и поддержке клиентов.

Если пишет про услуги:
сфокусируйся на заявках, скорости ответа и автоматизации продаж.

Главная цель:
выявить задачу клиента и довести до консультации Elver AI.
"""


@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "Здравствуйте 👋\n\nЯ Elver AI.\nПомогу понять, что можно автоматизировать в вашем бизнесе.\n\nНапишите, чем занимаетесь."
    )


@bot.message_handler(func=lambda message: True)
def chat(message):
    try:
        chat_id = message.chat.id
        text = message.text.lower()

        import re

          # если человек прислал контакт
            phone_pattern = r"\+?\d[\d\-\(\) ]{8,}\d"

                 if (
                   re.search(phone_pattern, message.text)
               or "@" in message.text
              ):
            save_lead(message)

            bot.reply_to(
                message,
                "Принял 👌\n\nСпасибо. Я изучу задачу и свяжусь с вами с конкретным предложением по автоматизации 🚀"
            )
            return

        # если проявил интерес
        if any(word in text for word in lead_words):
            bot.reply_to(
                message,
                "Отлично. Оставьте номер телефона или @username — я свяжусь с вами и предложу решение под ваш бизнес 🚀"
            )
            return

        # память диалога
        if chat_id not in user_memory:
            user_memory[chat_id] = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ]

        user_memory[chat_id].append(
            {"role": "user", "content": message.text}
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=user_memory[chat_id],
            temperature=0.7,
            max_tokens=500,
        )

        answer = response.choices[0].message.content

        user_memory[chat_id].append(
            {"role": "assistant", "content": answer}
        )

        # ограничиваем историю
        if len(user_memory[chat_id]) > 20:
            user_memory[chat_id] = (
                [user_memory[chat_id][0]] + user_memory[chat_id][-19:]
            )

        bot.reply_to(message, answer)

    except Exception as e:
        bot.reply_to(message, f"Ошибка AI: {e}")


print("Bot started")
bot.infinity_polling(skip_pending=True)
