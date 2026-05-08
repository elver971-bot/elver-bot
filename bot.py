import re
import os
from datetime import datetime

from flask import Flask, request
import telebot
from openai import OpenAI
from supabase import create_client


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = telebot.TeleBot(BOT_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

user_memory = {}
finished_leads = set()
lead_state = {}
lead_data = {}

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
    "интересует",
    "да",
    "ок",
    "хорошо",
    "можно",
    "согласен",
]

SYSTEM_PROMPT = """
Ты — Elver AI.
Эксперт по автоматизации бизнеса, продаж и внедрению AI.

Главная цель:
получить контакт клиента:
- телефон
- Telegram @username
- email

Если клиент проявил интерес —
сначала возьми контакт.

Отвечай:
- коротко
- по делу
- экспертно
- дружелюбно
- один вопрос за сообщение
"""


@bot.message_handler(commands=["start"])
def start(message):
    chat_id = message.chat.id

    lead_state[chat_id] = "wait_niche"
    lead_data[chat_id] = {}

    bot.send_message(
        chat_id,
        "Здравствуйте 👋\n\n"
        "Я Elver AI.\n"
        "Помогу понять, что можно автоматизировать в вашем бизнесе.\n\n"
        "Чем вы занимаетесь?\n"
        "Коротко: ниша / бизнес / направление."
    )


@bot.message_handler(func=lambda message: True)
def chat(message):
    try:
        chat_id = message.chat.id
        text = message.text.lower()

        phone_pattern = r"\+?\d[\d\-\(\) ]{8,}\d"
        email_pattern = r"[^@]+@[^@]+\.[^@]+"

        # если человек уже в воронке
        if chat_id in lead_state:
            step = lead_state[chat_id]

            if step == "wait_niche":
                lead_data[chat_id]["niche"] = message.text
                lead_state[chat_id] = "wait_pain"

                bot.reply_to(
                    message,
                    "Что сейчас больше всего мешает росту?\n\n"
                    "Например:\n"
                    "— мало заявок\n"
                    "— дорогая реклама\n"
                    "— слабые продажи"
                )
                return

            if step == "wait_pain":
                lead_data[chat_id]["pain"] = message.text
                lead_state[chat_id] = "wait_goal"

                bot.reply_to(
                    message,
                    "Что хотите автоматизировать в первую очередь?"
                )
                return

            if step == "wait_goal":
                lead_data[chat_id]["goal"] = message.text
                lead_state[chat_id] = "wait_contact"

                pain = lead_data[chat_id]["pain"].lower()
                goal = lead_data[chat_id]["goal"].lower()

                score = 50

                if any(word in pain for word in [
                    "нет заявок",
                    "мало клиентов",
                    "дорого",
                    "ручной",
                    "долго",
                    "теряем",
                ]):
                    score += 20

                if any(word in goal for word in [
                    "рост",
                    "заявки",
                    "автоматизация",
                    "масштаб",
                    "продажи",
                ]):
                    score += 30

                lead_data[chat_id]["score"] = score

                bot.reply_to(
                    message,
                    "Для вашей задачи вижу хорошее решение:\n\n"
                    "✅ усилить поток клиентов\n"
                    "✅ автоматизировать обработку заявок\n"
                    "✅ убрать ручную рутину\n\n"
                    "Под ваш бизнес можно собрать комплекс:\n"
                    "• продающий сайт / воронку\n"
                    "• рекламу\n"
                    "• AI-консультанта\n"
                    "• CRM + автоматизацию\n\n"
                    "Оставьте телефон / email / @username 👌"
                )
                return

            if step == "wait_contact":
                if (
                    re.search(phone_pattern, message.text)
                    or re.search(email_pattern, message.text)
                    or "@" in message.text
                ):
                    supabase.table("leads").insert({
                        "name": message.from_user.first_name or "Без имени",
                        "username": f"@{message.from_user.username}" if message.from_user.username else "нет",
                        "phone": message.text,
                        "chat_id": str(chat_id),
                        "niche": lead_data[chat_id].get("niche", ""),
                        "pain": lead_data[chat_id].get("pain", ""),
                        "goal": lead_data[chat_id].get("goal", ""),
                        "score": lead_data[chat_id].get("score", 0),
                        "status": "new"
                    }).execute()

                    bot.send_message(
                        1908342578,
                        f"🔥 Новый лид\n\n"
                        f"Имя: {message.from_user.first_name}\n"
                        f"Username: @{message.from_user.username}\n"
                        f"Ниша: {lead_data[chat_id]['niche']}\n"
                        f"Боль: {lead_data[chat_id]['pain']}\n"
                        f"Цель: {lead_data[chat_id]['goal']}\n"
                        f"Контакт: {message.text}"
                    )

                    del lead_state[chat_id]
                    del lead_data[chat_id]
                    finished_leads.add(chat_id)

                    bot.reply_to(
                        message,
                        "Принял 👌\n\n"
                        "Подготовлю конкретное предложение и свяжусь с вами 🚀"
                    )
                    return

                bot.reply_to(
                    message,
                    "Нужен контакт для связи:\nтелефон / email / @username 👌"
                )
                return

        # запуск воронки
        if text == "да" and chat_id not in lead_state:
            lead_state[chat_id] = "wait_niche"
            lead_data[chat_id] = {}

            bot.reply_to(
                message,
                "Отлично 👌\n\n"
                "Чем вы занимаетесь?\n"
                "Коротко: ниша / бизнес / направление."
            )
            return

        # если проявил интерес
        if (
            any(word in text for word in lead_words)
            and chat_id not in lead_state
            and chat_id not in finished_leads
        ):
            bot.reply_to(
                message,
                "Готовы начать диагностику?\n\nНапишите: да"
            )
            return

        # обычный AI чат
        if chat_id not in user_memory:
            user_memory[chat_id] = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ]

        user_memory[chat_id].append({
            "role": "user",
            "content": message.text
        })

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=user_memory[chat_id],
            temperature=0.7,
            max_tokens=500,
        )

        answer = response.choices[0].message.content

        user_memory[chat_id].append({
            "role": "assistant",
            "content": answer
        })

        bot.reply_to(message, answer)

    except Exception as e:
        bot.reply_to(message, f"Ошибка AI: {e}")


app = Flask(__name__)

WEBHOOK_URL = "https://elver-bot.onrender.com/" + BOT_TOKEN

bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)


@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "ok", 200


@app.route("/")
def index():
    return "Bot is running!", 200


print("Webhook started")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)