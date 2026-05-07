import re
import os
from flask import Flask, request
import telebot
from openai import OpenAI
from datetime import datetime
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def save_lead(message):
    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "нет"
    )

    name = message.from_user.first_name or "Без имени"
    text = message.text
    date = datetime.now().strftime("%d.%m.%Y %H:%M")

    # запись в Supabase
    supabase.table("leads").insert({
        "name": name,
        "username": username,
        "phone": text,
        "chat_id": str(message.chat.id)
    }).execute()

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

        # если человек прислал контакт
        phone_pattern = r"\+?\d[\d\-\(\) ]{8,}\d"

        if re.search(phone_pattern, message.text) or "@" in message.text:
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

        if len(user_memory[chat_id]) > 20:
            user_memory[chat_id] = (
                [user_memory[chat_id][0]] + user_memory[chat_id][-19:]
            )

        bot.reply_to(message, answer)

    except Exception as e:
        bot.reply_to(message, f"Ошибка AI: {e}")


from flask import Flask, request

app = Flask(__name__)

WEBHOOK_URL = "https://elver-bot.onrender.com/" + BOT_TOKEN

bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'ok', 200

@app.route('/')
def index():
    return 'Bot is running!', 200

print("Webhook started")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

