import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import telebot
from openai import OpenAI

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)


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
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message.text},
            ],
            temperature=0.7,
            max_tokens=500,
        )

        answer = response.choices[0].message.content
        bot.reply_to(message, answer)

    except Exception as e:
        bot.reply_to(message, f"Ошибка AI: {e}")


print("Bot started")
bot.infinity_polling(skip_pending=True)
