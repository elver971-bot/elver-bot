import re
import os
import json
import csv

phone_pattern = r"(\+7|8)?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"

from datetime import datetime, timedelta

from flask import Flask, request
import telebot
from telebot import types
from openai import OpenAI
from supabase import create_client


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = telebot.TeleBot(BOT_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)
admin_id = 1908342578

user_memory = {}
last_message_time = {}

lead_state = {}
lead_data = {}

def save_followup(chat_id, message, step):
    supabase.table("leads").upsert({
        "chat_id": str(chat_id),
        "name": message.from_user.first_name or "Без имени",
        "username": f"@{message.from_user.username}" if message.from_user.username else "нет",
        "niche": lead_data.get(chat_id, {}).get("niche", ""),
        "goal": lead_data.get(chat_id, {}).get("goal", ""),
        "status": step,
        "followup_sent": False,
        "followup_step": 0,
        "last_message_at": datetime.utcnow().isoformat()
    }).execute() 

def detect_segment(niche_text):
    niche = niche_text.lower()

    clinic_words = [
        "стомат", "клиник", "медицин", "врач",
        "ортодонт", "имплант", "косметолог"
    ]

    estate_words = [
        "недвиж", "риелтор", "агентство",
        "застройщик", "квартира", "жилье"
    ]

    warm_words = [
        "юрист", "бухгалтер", "салон",
        "автосервис", "обучение", "школа"
    ]

    if any(word in niche for word in clinic_words):
        return "clinic", "VIP", "medical"

    if any(word in niche for word in estate_words):
        return "real_estate", "VIP", "estate"

    if any(word in niche for word in warm_words):
        return "service", "Warm", "standard"

    return "other", "Normal", "standard"


def make_offer(segment):
    if segment == "clinic":
        return (
            "Вижу точки роста:\n\n"
            "✅ запись пациентов 24/7\n"
            "✅ возврат потерянных пациентов\n"
            "✅ напоминания о приеме\n"
            "✅ AI-консультант для записи\n\n"
            "Оставьте телефон / email / @username 👌"
        )

    if segment == "real_estate":
        return (
            "Для недвижимости можно усилить:\n\n"
            "✅ квалификацию лидов\n"
            "✅ подбор объектов через AI\n"
            "✅ запись на просмотр\n"
            "✅ CRM + автоворонка\n\n"
            "Оставьте телефон / email / @username 👌"
        )

    return (
        "Для вашей задачи вижу решение:\n\n"
        "✅ поток заявок\n"
        "✅ автоматизация обработки\n"
        "✅ AI-консультант\n"
        "✅ CRM + автоворонка\n\n"
        "Оставьте телефон / email / @username 👌"
    )

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
   

]
price_words = [
    "цена",
    "стоимость",
    "сколько",
    "дорого",
    "бюджет",
    "прайс"
]

SYSTEM_PROMPT = """
Ты Elver AI — AI-консультант по автоматизации бизнеса, AI-ассистентам, CRM, воронкам продаж и внедрению AI в компании.

Никогда не говори:
"я занимаюсь"
"я внедряю"
"я продаю"

Ты консультант, а не владелец бизнеса клиента.

Если клиент пишет свою нишу:
— НЕ говори будто это твоя ниша
— НЕ присваивай бизнес себе

Правильно:
"Для массажиста можно автоматизировать..."
"В вашей нише можно внедрить..."

Неправильно:
"Я занимаюсь массажем"
"Я занимаюсь автоматизацией салона"

Ты общаешься как опытный эксперт:
— спокойно
— уверенно
— простым языком
— без шаблонности
— без навязчивых продаж

Твоя задача:
— понять бизнес клиента
— выявить проблемы
— предложить автоматизацию
— показать выгоду
— довести до заявки

Ты умеешь:
— консультировать
— задавать уточняющие вопросы
— объяснять внедрение
— объяснять стоимость
— объяснять этапы работ
— предлагать решения

ВАЖНО:
Не проси телефон слишком часто.
Контакт нужен только если клиент:
— хочет запуск
— хочет консультацию
— просит расчет
— интересуется внедрением

Если пользователь уходит от темы бизнеса:
— НЕ придумывай бред
— НЕ отвечай как универсальный чат GPT
— коротко и вежливо верни разговор к автоматизации бизнеса

Примеры:

Пользователь:
"какая погода"

Ответ:
"Я специализируюсь на автоматизации бизнеса и AI-внедрении 😊
Если хотите — могу помочь разобраться как увеличить поток клиентов, автоматизировать заявки или внедрить AI-ассистента."

Пользователь:
"а колеса есть?"

Ответ:
"Я занимаюсь AI-автоматизацией и внедрением AI-ассистентов 😊
Если вопрос связан с бизнесом, продажами или автоматизацией — помогу разобраться."

Если клиент уже ответил на вопрос — не спрашивай это снова.

Помни предыдущие сообщения клиента и используй их в разговоре.

Если клиент заинтересован:
— веди разговор к внедрению
— консультации
— расчету
— созвону

Не превращайся в обычный ChatGPT.
Ты консультант по автоматизации бизнеса.

Не уходи в длинные теоретические объяснения.
Отвечай практично и по делу.

Если клиент спрашивает:
— стоимость
— сроки
— CRM
— AI-ассистента
— интеграции
— воронки

то отвечай конкретно и профессионально.
Не повторяй одинаковые фразы.
Не используй слишком длинные ответы.
Не веди себя как скриптовый бот.
Общайся как живой эксперт.

ВАЖНО:

Не пиши длинные статьи и инструкции.

Отвечай:
— коротко
— по делу
— как опытный консультант
— максимум 3-6 предложений

Не делай длинные списки без необходимости.

Главная задача:
— удерживать диалог
— задавать уточняющие вопросы
— подводить к консультации или внедрению

Не превращай ответы в обучение или методички.

Если клиент спрашивает:
— цену
— сроки
— внедрение
— как работает система

отвечай кратко и понятным языком.

Пример плохого ответа:
"Сначала проведем анализ, потом подготовим отчет..."

Пример хорошего ответа:
"Обычно внедрение выглядит так:
— подключаем CRM
— настраиваем AI-ассистента
— собираем заявки в одну систему
— автоматизируем обработку

На запуск обычно уходит 5–14 дней, зависит от задач."

Если клиент уже заинтересован — не возвращай его назад по воронке.
Не спрашивай снова то, что уже обсуждали.
Если клиент хочет связаться:
— можешь дать Telegram username
— можешь предложить написать в Telegram
— не отвечай фразами:
"не могу предоставить контакты"
"не могу дать данные"
"не имею доступа"

Если клиент спрашивает:
"куда писать"
"как связаться"
"где написать"

Если клиент готов обсудить внедрение, расчет или консультацию:
— попроси оставить телефон, Telegram username или email
— не давай свои контакты первым
— цель: получить контакт клиента для связи

Примеры:
"Оставьте, пожалуйста, удобный номер или Telegram для связи 👌"

"Напишите телефон или @username — подготовлю детали и свяжусь с вами."

"Для расчета и консультации оставьте контакт: телефон / Telegram / email."

Не перенаправляй клиента в Telegram первым.
Не давай свои контакты без необходимости.
Сначала получи контакт клиента.

Не задавай один и тот же вопрос дважды.

Если клиент уже ответил:
— используй его ответ дальше
— не возвращайся назад по воронке

Если клиент проявил интерес:
— двигай разговор к:
1) решению
2) выгоде
3) расчету
4) контакту

Твоя задача:
— выявить боль
— показать выгоду
— предложить решение
— довести до контакта

Не просто отвечай.
Помогай клиенту принять решение.

Пиши как живой эксперт.

Иногда:
— используй короткие фразы
— задавай встречные вопросы
— показывай понимание бизнеса клиента

Не отвечай как статья или инструкция.

Если клиент уходит в сторону:
— коротко ответь
— мягко верни разговор к бизнесу и автоматизации

Если информация уже известна:
— не спрашивай ее повторно
— не возвращайся назад по воронке
— продолжай разговор с текущего этапа

Если клиент уже:
— назвал нишу
— описал проблему
— рассказал цель

то используй эти данные дальше в разговоре.

Не задавай одинаковые вопросы повторно.

ВАЖНО:

Ты НЕ выполняешь работу бесплатно.

Ты:
— НЕ проводишь полноценный аудит
— НЕ подбираешь платформы детально
— НЕ делаешь техническое задание
— НЕ строишь архитектуру проекта
— НЕ составляешь готовый план внедрения
— НЕ заменяешь платную консультацию

Твоя задача:
— выявить потребность
— показать экспертность
— кратко объяснить решение
— довести клиента до контакта

Если клиент просит:
— подобрать платформу
— сделать анализ
— выбрать CRM
— составить архитектуру
— рассчитать интеграции
— подобрать стек
— описать реализацию

то НЕ выдавай полный готовый ответ.

Отвечай кратко и переводи разговор к консультации.

Пример:

"Есть несколько вариантов реализации под ваш бюджет и задачи.
Точный подбор платформы и схемы интеграции лучше обсудить отдельно, потому что тут важно учесть:
— оплату
— QR аренду
— CRM
— уведомления
— нагрузку
— работу в РФ

Могу подготовить решение под ваш проект.
Оставьте Telegram или телефон для связи 👌"

ВАЖНО:
Не уходи в многоэтапные инструкции.
Не пиши длинные планы внедрения.
Не работай бесплатно как технический специалист.

Ты продающий AI-консультант, а не бесплатный архитектор проекта.

Все цены указывай ТОЛЬКО в рублях ₽.
Никогда не используй доллары.

Если клиент пишет коротко:
— не расписывай огромный ответ
— отвечай кратко
— максимум 2-4 предложения

ВАЖНО ПО ЦЕНАМ:

Не занижай стоимость услуг.

Ты работаешь как эксперт по AI автоматизации и внедрению CRM.

Минимальные ориентиры:

— AI-консультант / чат-бот:
от 50 000 ₽

— CRM + автоматизация:
от 80 000 ₽

— AI-воронка:
от 70 000 ₽

— Telegram AI ассистент:
от 50 000 ₽

— Интеграции:
от 30 000 ₽

— Полная автоматизация бизнеса:
от 150 000 ₽

— Сложные проекты:
от 300 000 ₽ и выше

Если клиент спрашивает цену:
— не называй слишком точную стоимость
— сначала объясни, что цена зависит от задач
— затем давай диапазон

Пример хорошего ответа:

"Точная стоимость зависит от задач и интеграций.

Если говорить по рынку:
— базовая автоматизация обычно от 70–150 тыс ₽
— CRM + AI ассистент чаще 150–300 тыс ₽
— сложные внедрения могут быть выше

После короткого созвона смогу сказать точнее 👌"

Не предлагай дешевые услуги.
Не создавай ощущение "дешевого бота с фриланса".

Если клиент спрашивает стоимость сложного проекта:
— не расписывай весь проект подробно
— сначала уточни задачи
— затем предложи созвон или расчет

Не выдавай полный коммерческий расчет в чате.

ВАЖНО:

Не проводи полноценный брифинг в чате.

Не задавай клиенту сразу много вопросов списком.

Не превращай чат в техническое интервью.

Если клиент заинтересован:
— кратко покажи экспертность
— покажи выгоду
— предложи обсудить детали на созвоне

Максимум:
1 короткий уточняющий вопрос за сообщение.

Не составляй:
— ТЗ
— архитектуру проекта
— подробный план внедрения
— технический аудит

до получения контакта и созвона.

Если клиент уже оставил контакт:
— не продолжай глубокую консультацию
— мягко завершай диалог
— сообщай что детали обсудите лично

Пример хорошего ответа:

"Да, такую систему можно реализовать 👌
Для автосалона обычно внедряем AI-ассистента + CRM + автоматизацию заявок.

Точные сценарии лучше обсудить отдельно, потому что многое зависит от ваших процессов."

ИЛИ:

"Есть несколько вариантов реализации.
Чтобы не гадать в чате — лучше коротко обсудить задачи и подобрать оптимальную схему."

Если клиент отвечает коротко:
"да"
"интересно"
"хорошо"
"ок"

не пиши длинный ответ.

Отвечай кратко и веди к следующему этапу диалога.

ВАЖНО:

Не расписывай полную реализацию проекта в чате.

Не делай бесплатный аудит или полноценную техническую консультацию.

Твоя задача:
— выявить задачу
— показать экспертность
— обозначить возможное решение
— перевести клиента к созвону или расчету

Если проект сложный:
— не расписывай архитектуру подробно
— не выдавай полный план внедрения
— не заменяй платную консультацию

Отвечай кратко.
Детали обсуждаются после созвона или брифа.

Не работай бесплатно как технический специалист.

Не называй дешевые цены.

Не используй сверхнизкие оценки.

Если клиент спрашивает стоимость:
— сначала уточни задачи
— объем
— интеграции
— количество функций

Для сложных AI/CRM проектов:
— не давай точную цену без брифа
— называй диапазон от среднего и выше рынка

Не создавай ощущение дешевого бота фриланса.

Если пользователь пишет не по теме бизнеса, AI, CRM или автоматизации:
— отвечай коротко
— не поддерживай длинный разговор
— возвращай к теме автоматизации

Не работай как обычный ChatGPT.

НЕ называй низкие цены.

Минимальный чек:
— AI-консультант: от 50 000 ₽
— CRM и автоматизация: от 80 000 ₽
— сложные интеграции: от 150 000 ₽

Не делай точный расчет в чате.
Сначала собирай задачи клиента.
"""


@bot.message_handler(commands=["start"])
def start(message):
    chat_id = message.chat.id

    if len(message.text) > 1500:

        bot.reply_to(
            message,
            "Сообщение слишком длинное 👌 Отправьте короче."
        )

        return
    

    if message.chat.type in ["group", "supergroup"]:

        if (
            not message.text.startswith("/")
            and "@" not in message.text
        ):
            return

    lead = supabase.table("leads") \
        .select("*") \
        .eq("chat_id", str(chat_id)) \
        .execute()

    lead_info = ""
    lead_exists = (
    supabase.table("leads")
    .select("id")
    .eq("chat_id", str(chat_id))
    .execute()
    )
    print("LEAD CREATED")

    if not lead_exists.data:

        supabase.table("leads").insert({
            "chat_id": str(chat_id),
            "name": message.from_user.first_name or "Без имени",
            "username": (
                f"@{message.from_user.username}"
                if message.from_user.username
                else "нет"
            ),
            "stage": "new",
            "lead_temp": "cold",
            "lead_score": 0,
            "message_count": 1,
            "last_message_at": datetime.utcnow().isoformat()
        }).execute()

    if lead.data:
        db_lead = lead.data[0]
        message_count = db_lead.get("message_count") or 0
        lead_info = f"""
Клиент уже общался ранее.

Ниша: {db_lead.get('niche', '')}
Боль: {db_lead.get('pain', '')}
Цель: {db_lead.get('goal', '')}
Этап: {db_lead.get('stage', '')}

Краткое summary:
{db_lead.get('summary', '')}
"""

    # полная очистка прошлого диалога
    if chat_id in user_memory:
        del user_memory[chat_id]

    if chat_id in lead_state:
        del lead_state[chat_id]

    if chat_id in lead_data:
        del lead_data[chat_id]

    user_memory[chat_id] = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT + "\n\n" + lead_info
        }
    ]

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

@bot.message_handler(commands=["services"])
def services(message):

    text = (
        "🔥 Что мы внедряем для бизнеса:\n\n"

        "• AI-ассистенты для сайта и Telegram\n"
        "• CRM и автоматизация заявок\n"
        "• AI-боты для продаж\n"
        "• Telegram-воронки\n"
        "• Автоматизация переписок\n"
        "• AI-консультанты\n"
        "• Интеграции с Avito и CRM\n"
        "• AI-контент и автопостинг\n"
        "• AI для онлайн-школ и экспертов\n\n"

        "📞 Для расчета проекта отправьте:\n"
        "— нишу\n"
        "— задачу\n"
        "— что хотите автоматизировать"
    )

    bot.send_message(
        message.chat.id,
        text
    )

@bot.message_handler(commands=["leads"])
def leads(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    rows = (
        supabase.table("leads")
        .select("*")
        .execute()
    )

    leads_data = rows.data or []

    total = len(leads_data)

    hot = len([
        x for x in leads_data
        if x.get("lead_temp") == "hot"
    ])

    warm = len([
        x for x in leads_data
        if x.get("lead_temp") == "warm"
    ])

    cold = len([
        x for x in leads_data
        if x.get("lead_temp") == "cold"
    ])

    latest = sorted(
        leads_data,
        key=lambda x: x.get("last_message_at", ""),
        reverse=True
    )[:5]

    text = (
        f"📊 AI CRM REPORT\n\n"
        f"Всего лидов: {total}\n"
        f"🔥 Hot: {hot}\n"
        f"🌤 Warm: {warm}\n"
        f"❄️ Cold: {cold}\n\n"
        f"Последние лиды:\n\n"
    )

    for lead in latest:

        text += (
            f"👤 {lead.get('name', 'Без имени')}\n"
            f"📞 {lead.get('phone', 'нет телефона')}\n"
            f"🔥 {lead.get('lead_temp', '-')}\n"
            f"📈 {lead.get('close_probability', 0)}%\n"
            f"💬 {lead.get('summary', '-')[:120]}\n\n"
        )

    bot.send_message(
        message.chat.id,
        text
    )

@bot.message_handler(commands=["id"])
def get_my_id(message):

    bot.reply_to(
        message,
        f"Ваш chat_id: {message.chat.id}"
    )

@bot.message_handler(commands=["leads"])
def leads(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    rows = (
        supabase.table("leads")
        .select("*")
        .order("last_message_at", desc=True)
        .limit(10)
        .execute()
    )

    if not rows.data:

        bot.reply_to(
            message,
            "Лидов пока нет."
        )

        return

    text = "🔥 Последние лиды:\n\n"

    for lead in rows.data:

        name = lead.get("name", "Без имени")
        niche = lead.get("niche", "не указана")
        temp = lead.get("lead_temp", "cold")
        score = lead.get("lead_score", 0)

        text += (
            f"👤 {name}\n"
            f"🏢 Ниша: {niche}\n"
            f"🌡 Температура: {temp}\n"
            f"📊 Score: {score}\n\n"
        )

    bot.send_message(
        message.chat.id,
        text
    )  

@bot.message_handler(commands=["hot"])
def hot_leads(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    rows = (
        supabase.table("leads")
        .select("*")
        .eq("lead_temp", "hot")
        .order("last_message_at", desc=True)
        .limit(10)
        .execute()
    )

    if not rows.data:

        bot.reply_to(
            message,
            "🔥 Горячих лидов пока нет."
        )

        return

    text = "🔥 HOT LEADS\n\n"

    for lead in rows.data:

        name = lead.get("name", "Без имени")
        niche = lead.get("niche", "не указана")
        phone = lead.get("phone", "нет")
        score = lead.get("lead_score", 0)
        summary = lead.get("summary", "")

        text += (
            f"👤 {name}\n"
            f"📞 {phone}\n"
            f"🏢 {niche}\n"
            f"📊 Score: {score}\n"
            f"🧠 {summary[:200]}\n\n"
        )

    bot.send_message(
        message.chat.id,
        text
    )

@bot.message_handler(commands=["lead"])
def lead_info(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    try:

        parts = message.text.split()

        if len(parts) < 2:

            bot.reply_to(
                message,
                "Используйте:\n/lead CHAT_ID"
            )

            return

        target_chat_id = parts[1]

        row = (
            supabase.table("leads")
            .select("*")
            .eq("chat_id", target_chat_id)
            .execute()
        )

        if not row.data:

            bot.reply_to(
                message,
                "Лид не найден."
            )

            return

        lead = row.data[0]

        text = (
            f"👤 {lead.get('name', 'Без имени')}\n\n"
            f"📞 {lead.get('phone', 'нет')}\n"
            f"🏢 Ниша: {lead.get('niche', 'не указана')}\n"
            f"🌡 Температура: {lead.get('lead_temp', 'cold')}\n"
            f"📊 Score: {lead.get('lead_score', 0)}\n\n"
            f"🧠 Summary:\n{lead.get('summary', '-')}\n\n"
            f"📝 AI Notes:\n{lead.get('ai_notes', '-')}"
        )

        bot.send_message(
            message.chat.id,
            text
        )

    except Exception as e:

        bot.reply_to(
            message,
            f"Ошибка: {e}"
        )

@bot.message_handler(commands=["pipeline"])
def pipeline(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    rows = (
        supabase.table("leads")
        .select("*")
        .execute()
    )

    total = len(rows.data)

    cold = 0
    warm = 0
    hot = 0
    paid = 0

    for lead in rows.data:

        temp = lead.get("lead_temp", "cold")

        if temp == "cold":
            cold += 1

        elif temp == "warm":
            warm += 1

        elif temp == "hot":
            hot += 1

        stage = lead.get("pipeline_stage", "")

        if stage == "paid":
            paid += 1

    text = (
        "📊 AI PIPELINE\n\n"

        f"👥 Всего лидов: {total}\n\n"

        f"❄️ Cold: {cold}\n"
        f"🌤 Warm: {warm}\n"
        f"🔥 Hot: {hot}\n"
        f"💰 Paid: {paid}"
    )

    bot.send_message(
        message.chat.id,
        text
    )

@bot.message_handler(commands=["client"])
def client_info(message):

    if message.from_user.id != admin_id:
        return

    args = message.text.split()

    if len(args) < 2:

        bot.reply_to(
            message,
            "Использование:\n/client chat_id"
        )

        return

    target_chat_id = args[1]

    lead = (
        supabase.table("leads")
        .select("*")
        .eq("chat_id", str(target_chat_id))
        .execute()
    )

    if not lead.data:

        bot.reply_to(
            message,
            "Клиент не найден."
        )

        return

    db_lead = lead.data[0]

    report = f"""
👤 Клиент: {db_lead.get('name', 'Без имени')}

📞 Username:
{db_lead.get('username', 'нет')}

🔥 Температура:
{db_lead.get('lead_temp', 'cold')}

📍 Этап:
{db_lead.get('pipeline_stage', 'new')}

💰 Бюджет:
{db_lead.get('budget_level', 'unknown')}

⭐ Score:
{db_lead.get('lead_score', 0)}

📈 Вероятность:
{db_lead.get('close_probability', 0)}%

🧠 Summary:

{db_lead.get('summary', 'нет данных')}

📝 AI Notes:

{db_lead.get('ai_notes', 'нет заметок')}
"""

    bot.send_message(
        message.chat.id,
        report[:4000]
    )

@bot.message_handler(commands=["broadcast"])
def broadcast(message):

    if message.from_user.id != admin_id:
        return

    text = message.text.replace("/broadcast", "").strip()

    if not text:

        bot.reply_to(
            message,
            "Напишите текст:\n/broadcast ваш текст"
        )

        return

    rows = (
        supabase.table("leads")
        .select("chat_id")
        .execute()
    )

    total = 0

    for row in rows.data:

        try:

            bot.send_message(
                row["chat_id"],
                text
            )

            total += 1

        except:
            pass

    bot.reply_to(
        message,
        f"Рассылка отправлена: {total}"
    )

@bot.message_handler(commands=["paid"])
def paid_clients(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    rows = (
        supabase.table("leads")
        .select("*")
        .eq("pipeline_stage", "paid")
        .order("last_message_at", desc=True)
        .execute()
    )

    if not rows.data:

        bot.reply_to(
            message,
            "💰 Оплаченных клиентов пока нет."
        )

        return

    text = "💰 PAID CLIENTS\n\n"

    for lead in rows.data:

        name = lead.get("name", "Без имени")
        niche = lead.get("niche", "не указана")
        phone = lead.get("phone", "нет")
        summary = lead.get("summary", "")

        text += (
            f"👤 {name}\n"
            f"📞 {phone}\n"
            f"🏢 {niche}\n"
            f"🧠 {summary[:150]}\n\n"
        )

    bot.send_message(
        message.chat.id,
        text
    )

@bot.message_handler(commands=["setpaid"])
def set_paid(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    try:

        parts = message.text.split()

        if len(parts) < 2:

            bot.reply_to(
                message,
                "Используйте:\n/setpaid CHAT_ID"
            )

            return

        target_chat_id = parts[1]

        supabase.table("leads").update({

            "pipeline_stage": "paid"

        }).eq("chat_id", target_chat_id).execute()

        bot.reply_to(
            message,
            f"✅ Клиент {target_chat_id} переведен в PAID."
        )

    except Exception as e:

        bot.reply_to(
            message,
            f"Ошибка: {e}"
        )

@bot.message_handler(commands=["stats"])
def stats(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    rows = (
        supabase.table("leads")
        .select("*")
        .execute()
    )

    leads_data = rows.data or []

    total = len(leads_data)

    hot = 0
    warm = 0
    cold = 0
    paid = 0

    total_score = 0

    for lead in leads_data:

        temp = lead.get("lead_temp", "cold")

        if temp == "hot":
            hot += 1

        elif temp == "warm":
            warm += 1

        else:
            cold += 1

        if lead.get("pipeline_stage") == "paid":
            paid += 1

        total_score += lead.get("lead_score", 0) or 0

    avg_score = 0

    if total > 0:
        avg_score = round(total_score / total)

    conversion = 0

    if total > 0:
        conversion = round((paid / total) * 100)

    text = (
        "📊 AI CRM STATS\n\n"

        f"👥 Всего лидов: {total}\n\n"

        f"🔥 Hot: {hot}\n"
        f"🌤 Warm: {warm}\n"
        f"❄️ Cold: {cold}\n\n"

        f"💰 Paid: {paid}\n"
        f"📈 Конверсия: {conversion}%\n"
        f"🧠 Средний Score: {avg_score}"
    )

    bot.send_message(
        message.chat.id,
        text
    )

@bot.message_handler(commands=["setmeeting"])
def set_meeting(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    try:

        parts = message.text.split()

        if len(parts) < 2:

            bot.reply_to(
                message,
                "Используйте:\n/setmeeting CHAT_ID"
            )

            return

        target_chat_id = parts[1]

        supabase.table("leads").update({

            "pipeline_stage": "meeting"

        }).eq("chat_id", target_chat_id).execute()

        bot.reply_to(
            message,
            f"📞 Лид {target_chat_id} переведен в MEETING."
        )

    except Exception as e:

        bot.reply_to(
            message,
            f"Ошибка: {e}"
        )

@bot.message_handler(commands=["lost"])
def set_lost(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    try:

        parts = message.text.split()

        if len(parts) < 2:

            bot.reply_to(
                message,
                "Используйте:\n/lost CHAT_ID"
            )

            return

        target_chat_id = parts[1]

        supabase.table("leads").update({

            "pipeline_stage": "lost"

        }).eq("chat_id", target_chat_id).execute()

        bot.reply_to(
            message,
            f"❌ Лид {target_chat_id} переведен в LOST."
        )

    except Exception as e:

        bot.reply_to(
            message,
            f"Ошибка: {e}"
        )

@bot.message_handler(commands=["today"])
def today_stats(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date()

    rows = (
        supabase.table("leads")
        .select("*")
        .execute()
    )

    leads_today = []

    for lead in rows.data:

        last_message = lead.get("last_message_at")

        if not last_message:
            continue

        try:

            dt = datetime.fromisoformat(
                last_message.replace("Z", "+00:00")
            )

            if dt.date() == today:
                leads_today.append(lead)

        except:
            pass

    total = len(leads_today)

    hot = len([
        x for x in leads_today
        if x.get("lead_temp") == "hot"
    ])

    paid = len([
        x for x in leads_today
        if x.get("pipeline_stage") == "paid"
    ])

    text = (
        "📅 TODAY REPORT\n\n"

        f"👥 Лидов сегодня: {total}\n"
        f"🔥 Hot сегодня: {hot}\n"
        f"💰 Paid сегодня: {paid}\n\n"
    )

    for lead in leads_today[:5]:

        text += (
            f"👤 {lead.get('name', 'Без имени')}\n"
            f"🌡 {lead.get('lead_temp', 'cold')}\n"
            f"📊 {lead.get('lead_score', 0)}\n\n"
        )

    bot.send_message(
        message.chat.id,
        text
    )

@bot.message_handler(commands=["broadcast"])
def broadcast(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    try:

        parts = message.text.split(maxsplit=1)

        if len(parts) < 2:

            bot.reply_to(
                message,
                "Используйте:\n/broadcast ТЕКСТ"
            )

            return

        broadcast_text = parts[1]

        rows = (
            supabase.table("leads")
            .select("chat_id")
            .execute()
        )

        sent = 0

        for lead in rows.data:

            try:

                bot.send_message(
                    int(lead["chat_id"]),
                    broadcast_text
                )

                sent += 1

            except:
                pass

        bot.reply_to(
            message,
            f"✅ Рассылка отправлена: {sent}"
        )

    except Exception as e:

        bot.reply_to(
            message,
            f"Ошибка: {e}"
        )

@bot.message_handler(commands=["export"])
def export_leads(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    try:

        rows = (
            supabase.table("leads")
            .select("*")
            .execute()
        )

        leads = rows.data or []

        filename = "leads_export.csv"

        with open(filename, "w", newline="", encoding="utf-8-sig") as file:

            writer = csv.writer(file)

            writer.writerow([
                "name",
                "username",
                "phone",
                "niche",
                "lead_temp",
                "lead_score",
                "pipeline_stage",
                "summary"
            ])

            for lead in leads:

                writer.writerow([
                    lead.get("name", ""),
                    lead.get("username", ""),
                    lead.get("phone", ""),
                    lead.get("niche", ""),
                    lead.get("lead_temp", ""),
                    lead.get("lead_score", ""),
                    lead.get("pipeline_stage", ""),
                    lead.get("summary", "")
                ])

        with open(filename, "rb") as file:

            bot.send_document(
                message.chat.id,
                file
            )

    except Exception as e:

        bot.reply_to(
            message,
            f"Ошибка: {e}"
        )

@bot.message_handler(commands=["ai-report"])
def ai_report(message):

    admin_id = 1908342578

    if message.chat.id != admin_id:
        return

    try:

        rows = (
            supabase.table("leads")
            .select("*")
            .execute()
        )

        leads = rows.data or []

        if not leads:

            bot.reply_to(
                message,
                "Лидов пока нет."
            )

            return

        report_data = ""

        for lead in leads[:50]:

            report_data += (
                f"Имя: {lead.get('name', '')}\n"
                f"Ниша: {lead.get('niche', '')}\n"
                f"Температура: {lead.get('lead_temp', '')}\n"
                f"Score: {lead.get('lead_score', '')}\n"
                f"Stage: {lead.get('pipeline_stage', '')}\n"
                f"Summary: {lead.get('summary', '')}\n\n"
            )

        prompt = f"""
Проанализируй CRM лидов.

Определи:

1. Какие лиды самые качественные
2. Какие ниши самые перспективные
3. Где слабые места в продажах
4. Что улучшить
5. Какие лиды стоит дожимать
6. Краткий вывод по воронке

CRM DATA:

{report_data}
"""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Ты AI sales аналитик."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=700,
        )

        report = (
            response
            .choices[0]
            .message
            .content
        )

        bot.send_message(
            message.chat.id,
            report
        )

    except Exception as e:

        bot.reply_to(
            message,
            f"Ошибка: {e}"
        )

@bot.message_handler(content_types=["contact"])
def handle_contact(message):

    chat_id = message.chat.id

    phone = message.contact.phone_number

    supabase.table("leads").update({

        "phone": phone,
        "lead_temp": "hot",
        "pipeline_stage": "contact_received",
        "close_probability": 85

    }).eq("chat_id", str(chat_id)).execute()

    bot.send_message(
        chat_id,
        "✅ Контакт получен. Свяжусь с вами."
    )

    try:

        bot.send_message(
            admin_id,
            f"""
🔥 НОВЫЙ КОНТАКТ

👤 {message.from_user.first_name}

📞 {phone}

🆔 {chat_id}
"""
        )

    except:
        pass


@bot.message_handler(func=lambda message: True)
def chat(message):

    if not message.text:
        bot.reply_to(
            message,
            "Пожалуйста, отправьте текстовое сообщение."
        )
        return

    try:

        chat_id = message.chat.id
        now = time.time()

        if chat_id in last_message_time:

            diff = now - last_message_time[chat_id]

            if diff < 2:

                bot.reply_to(
                    message,
                    "⏳ Слишком быстро. Подождите 2 секунды."
                )

                return

        last_message_time[chat_id] = now
        if len(message.text) > 1500:

            bot.reply_to(
                message,
                "Сообщение слишком длинное 👌 Отправьте короче."
            )

            return

        # =========================================
        # DEFAULTS
        # =========================================

        ai_temp = "cold"
        ai_temp_response = None
        pipeline_stage = "new"
        budget_level = "unknown"
        priority_level = "low"
        close_probability = 0
        lead_score = 0
        pain_level = "low"
        client_type = "cold"

        answer = ""
        summary = ""
        ai_notes_text = ""
        contact_request = ""

        user_text = message.text.strip()

        short_trash = [
            "ок",
            "ага",
            "пон",
            "ясно",
            "привет",
            "здарова",
            "qq",
            "+",
            "-",
            "1",
            "123",
            "test"
        ]

        if (
            len(user_text) < 2
            or user_text.lower() in short_trash
        ):
            bot.reply_to(
                message,
                "Опишите задачу подробнее 👍"
            )
            return
        phone_match = re.search(phone_pattern, message.text)

        extracted_phone = None

        if phone_match:
            extracted_phone = phone_match.group(0)
        text = user_text.lower()

        text_all = text

        # =========================================
        # LOAD LEAD
        # =========================================

        lead = (
            supabase.table("leads")
            .select("*")
            .eq("chat_id", str(chat_id))
            .execute()
        )

        lead_info = ""

        lead_exists = (
            supabase.table("leads")
            .select("id")
            .eq("chat_id", str(chat_id))
            .execute()
        )
        print("LEAD CREATED")
        
        if not lead_exists.data:

            supabase.table("leads").insert({
                "chat_id": str(chat_id),
                "name": message.from_user.first_name or "Без имени",
                "username": (
                    f"@{message.from_user.username}"
                    if message.from_user.username
                    else "нет"
                ),
                "stage": "new",
                "lead_temp": "cold",
                "lead_score": 0,
                "message_count": 1,
                "last_message_at": datetime.utcnow().isoformat()
            }).execute()

        if not lead_exists.data:

            supabase.table("leads").insert({
                "chat_id": str(chat_id),
                "name": message.from_user.first_name or "Без имени",
                "username": (
                    f"@{message.from_user.username}"
                    if message.from_user.username
                    else "нет"
                ),
                "stage": "new",
                "lead_temp": "cold",
                "lead_score": 0,
                "message_count": 1,
                "last_message_at": datetime.utcnow().isoformat()
            }).execute()

        if lead.data:

            db_lead = lead.data[0]

            message_count = db_lead.get("message_count") or 0

            if (
                message_count >= 20
                and not re.search(phone_pattern, message.text)
            ):

                bot.reply_to(
                    message,
                    "Лимит бесплатной AI-консультации достигнут 👌\n\n"
                    "Для продолжения обсуждения оставьте телефон или Telegram для связи."
                )

                return

        lead_info = f"""
        Ниша: {db_lead.get('niche', '')}
        Боль: {db_lead.get('pain', '')}
        Цель: {db_lead.get('goal', '')}
        Этап: {db_lead.get('stage', '')}

        Summary:
        {db_lead.get('summary', '')}
        """

        # =========================================
        # PATTERNS
        # =========================================

        email_pattern = r"[^@]+@[^@]+\.[^@]+"

        # =========================================
        # MEMORY
        # =========================================

        if chat_id not in user_memory:

            restored_history = None

            if lead.data:
                db_lead = lead.data[0]
                restored_history = db_lead.get("ai_history")

            if restored_history:

                try:
                    user_memory[chat_id] = eval(restored_history)

                except Exception:

                    user_memory[chat_id] = [
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT + "\n\n" + lead_info
                        }
                    ]

            else:

                user_memory[chat_id] = [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT + "\n\n" + lead_info
                    }
                ]

        # =========================================
        # USER MESSAGE
        # =========================================

        user_memory[chat_id].append({
            "role": "user",
            "content": message.text
        })

        if len(user_memory[chat_id]) > 80:

            user_memory[chat_id] = (
                [user_memory[chat_id][0]]
                + user_memory[chat_id][-11:]
            )

        # =========================================
        # GPT RESPONSE
        # =========================================

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=user_memory[chat_id],
            temperature=0.5,
            max_tokens=220,
        )

        if response and response.choices:

            answer = (
                response
                .choices[0]
                .message
                .content
            )

        else:

            answer = "Извините, произошла ошибка AI."

        # =========================================
        # SUMMARY
        # =========================================

        summary_prompt = f"""
Суммаризируй клиента для CRM.

Кратко укажи:
- чем занимается
- боли
- цели
- интерес
- что обсуждали
- стадия готовности
- есть ли контакт

CRM данные:

Ниша:
{lead_data.get(chat_id, {}).get("niche", "")}

Боль:
{lead_data.get(chat_id, {}).get("pain", "")}

Цель:
{lead_data.get(chat_id, {}).get("goal", "")}

Диалог:

Клиент:
{message.text}

AI:
{answer}
"""

        summary_response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Ты AI CRM аналитик."
                },
                {
                    "role": "user",
                    "content": summary_prompt
                }
            ],
            temperature=0.2,
            max_tokens=200,
        )

        if summary_response and summary_response.choices:

            summary = (
                summary_response
                .choices[0]
                .message
                .content
            )

        else:

            summary = "Нет summary"

        # =========================================
        # AI NOTES
        # =========================================

        ai_notes_prompt = f"""
Ты AI CRM аналитик.

Проанализируй клиента.

Диалог:
{summary}

Ответь JSON форматом:

{{
    "pain_level": "...",
    "client_type": "...",
    "ai_notes": "..."
}}

pain_level:
low / medium / high

client_type:
cold / warm / hot

ai_notes:
краткая заметка менеджеру
"""

        ai_notes_response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Ты AI CRM аналитик."
                },
                {
                    "role": "user",
                    "content": ai_notes_prompt
                }
            ],
            temperature=0.1,
            max_tokens=120,
        )

        if ai_notes_response and ai_notes_response.choices:

            ai_notes_text = (
                ai_notes_response
                .choices[0]
                .message
                .content
            )

        else:

            ai_notes_text = ""

        # =========================================
        # JSON PARSE
        # =========================================

        import json

        try:

            ai_notes_data = json.loads(ai_notes_text)

            pain_level = ai_notes_data.get(
                "pain_level",
                "low"
            )

            client_type = ai_notes_data.get(
                "client_type",
                "cold"
            )

            ai_notes_text = ai_notes_data.get(
                "ai_notes",
                ""
            )

        except Exception as json_error:

            print("JSON parse error:", json_error)
            pain_level = "low"
            client_type = "cold"
            ai_notes_text = ""

        # =========================================
        # TEXT ALL
        # =========================================

        text_all = (
            f"{message.text} "
            f"{answer} "
            f"{summary}"
        ).lower()

        # =========================================
        # LEAD TEMPERATURE
        # =========================================

        ai_temp_prompt = f"""
Определи температуру лида.

Варианты:
- hot
- warm
- cold

HOT:
- хочет внедрение
- просит цену
- просит сроки
- готов обсуждать
- оставил контакт

WARM:
- есть интерес
- задает вопросы
- изучает

COLD:
- слабый интерес
- просто общается

Диалог:

Клиент:
{message.text}

AI:
{answer}

Ответь только одним словом:
hot / warm / cold
"""

        try:

            ai_temp_response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Ты AI CRM аналитик."
                    },
                    {
                        "role": "user",
                        "content": ai_temp_prompt
                    }
                ],
                temperature=0.1,
                max_tokens=5,
            )

            ai_temp = (
                ai_temp_response
                .choices[0]
                .message
                .content
                .strip()
                .lower()
            )

        except Exception as temp_error:

            print("TEMP ERROR:", temp_error)
            ai_temp = "cold"

        if ai_temp not in ["hot", "warm", "cold"]:
            ai_temp = "cold"

        # =========================================
        # PRIORITY
        # =========================================

        if ai_temp == "hot":
            priority_level = "high"

        elif ai_temp == "warm":
            priority_level = "medium"

        else:
            priority_level = "low"

        # =========================================
        # PIPELINE
        # =========================================

        pipeline_stage = "new"

        if any(word in message.text.lower() for word in [
            "цена",
            "стоимость",
            "сколько",
            "бюджет"
        ]):

            pipeline_stage = "pricing"

        elif any(word in message.text.lower() for word in [
            "созвон",
            "консультация",
            "обсудить",
            "связаться"
        ]):

            pipeline_stage = "consultation"

        elif ai_temp == "hot":

            pipeline_stage = "hot"

        elif ai_temp == "warm":

            pipeline_stage = "interested"

        # =========================================
        # BUDGET
        # =========================================

        if any(word in text_all for word in [
            "500000",
            "миллион",
            "1 млн",
            "2 млн",
            "сеть",
            "филиалы",
            "отдел продаж"
        ]):

            budget_level = "high"

        elif any(word in text_all for word in [
            "100000",
            "200000",
            "50 сотрудников",
            "crm",
            "автоматизация"
        ]):

            budget_level = "medium"

        elif any(word in text_all for word in [
            "дешево",
            "без бюджета",
            "нет денег"
        ]):

            budget_level = "low"

        # =========================================
        # SCORE
        # =========================================

        close_probability = 10
        lead_score = 0

        if ai_temp == "hot":
            close_probability += 20
            lead_score += 20

        elif ai_temp == "warm":
            close_probability += 10
            lead_score += 10

        if budget_level == "high":
            close_probability += 20
            lead_score += 20

        elif budget_level == "medium":
            close_probability += 10
            lead_score += 10

        if pipeline_stage == "pricing":
            close_probability += 15
            lead_score += 15

        elif pipeline_stage == "consultation":
            close_probability += 20
            lead_score += 20

        if (
            re.search(phone_pattern, message.text)
            or re.search(email_pattern, message.text)
            or (
                "@" in message.text
                and len(message.text) < 40
            )
        ):

            close_probability += 25
            lead_score += 25

        if close_probability > 100:
            close_probability = 100

        if lead_score > 100:
            lead_score = 100

        # =========================================
        # SAVE
        # =========================================

        existing_lead = (
            supabase.table("leads")
            .select("id")
            .eq("chat_id", str(chat_id))
            .execute()
        )

        if not existing_lead.data:

            supabase.table("leads").insert({
                "chat_id": str(chat_id),
                "name": message.from_user.first_name or "Без имени",
                "username": (
                    f"@{message.from_user.username}"
                    if message.from_user.username
                    else "нет"
                ),
                "created_at": datetime.utcnow().isoformat(),
                "stage": "new"
            }).execute()
            
        print("LEAD CREATED")
        print("LEAD UPDATED")

        supabase.table("leads").update({
            "summary": summary,
            "message_count": message_count + 1,
            "stage": "dialog",
            "lead_temp": ai_temp,
            "phone": extracted_phone,
            "pipeline_stage": pipeline_stage,
            "budget_level": budget_level,
            "priority_level": priority_level,
            "close_probability": close_probability,
            "lead_score": lead_score,
            "pain_level": pain_level,
            "client_type": client_type,
            "ai_notes": ai_notes_text,
            "last_message_at": datetime.utcnow().isoformat()
        }).eq("chat_id", str(chat_id)).execute()

        # =========================================
        # SAVE MEMORY
        # =========================================

        user_memory[chat_id].append({
            "role": "assistant",
            "content": answer
        })
        try:

            history_text = str(user_memory[chat_id])

            supabase.table("leads").update({
                "ai_history": history_text
            }).eq("chat_id", str(chat_id)).execute()

        except Exception as history_error:

            print("HISTORY SAVE ERROR:", history_error)

        # =========================================
        # HOT LEAD NOTIFY
        # =========================================

        if ai_temp == "hot":

            try:

                bot.send_message(

                    admin_id,

                    f"🔥 HOT LEAD\n\n"

                    f"👤 Клиент: {message.from_user.first_name}\n"
                    f"📞 Телефон: {extracted_phone or 'нет'}\n"
                    f"🏢 Ниша: {lead_data.get(chat_id, {}).get('niche', 'не указана')}\n\n"

                    f"🌡 Температура: {ai_temp}\n"
                    f"📈 Score: {lead_score}\n"
                    f"💰 Вероятность сделки: {close_probability}%\n"
                    f"📍 Этап: {pipeline_stage}\n\n"

                    f"💬 Сообщение:\n"
                    f"{message.text[:500]}"
                )

            except Exception as notify_error:

                print("Notify error:", notify_error)

        # =========================================
        # FINAL ANSWER
        # =========================================

        # =========================================
        # AI AUTO CLOSER
        # =========================================

        if ai_temp == "hot":

            answer += (

                "\n\n🔥 Вижу, что задача для вас актуальна.\n"

                "Могу показать несколько готовых "
                "вариантов внедрения под ваш бизнес 👌"
            )

        elif pipeline_stage == "pricing":

            answer += (

                "\n\n💰 Чтобы назвать точную стоимость — "
                "нужно понять детали задачи.\n"

                "Можем быстро обсудить это в Telegram "
                "или созвоне 👌"
            )

        elif pipeline_stage == "consultation":

            answer += (

                "\n\n📞 Если удобно — можем перейти "
                "к обсуждению деталей внедрения."
            )

        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True
        )

        contact_button = types.KeyboardButton(
            "📱 Отправить контакт",
            request_contact=True
        )

        markup.add(contact_button)

        bot.reply_to(
            message,
            answer,
            reply_markup=markup
        )
      
        

    except Exception as e:
        bot.reply_to(message, f"Ошибка AI: {e}")
        print("ERROR:", e)

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


def send_followups():

    from datetime import timezone

    now = datetime.now(timezone.utc)

    rows = (
        supabase.table("leads")
        .select("*")
        .execute()
    )

    for lead in rows.data:

        followup_step = lead.get("followup_step", 0)
        priority = lead.get("priority_level", "low")
        probability = lead.get("close_probability", 0)
        reanimate_sent = lead.get("reanimate_sent", False)

        if not lead.get("last_message_at"):
            continue

        last = datetime.fromisoformat(
            lead["last_message_at"].replace("Z", "+00:00")
        )

        diff = now - last
        step = lead.get("followup_step", 0)
        lead_temp = lead.get("lead_temp", "cold")

        text = None
        next_step = followup_step

        # HOT LEADS
        if priority == "high":

            if followup_step == 0 and diff >= timedelta(days=1):

                text = (
                    "Здравствуйте 👋\n\n"
                    "Подготовил несколько идей по AI-автоматизации "
                    "для вашей ниши.\n\n"
                    "Могу показать:\n"
                    "— как сократить ручную работу\n"
                    "— как автоматизировать заявки\n"
                    "— как внедрить AI-ассистента\n\n"
                    "Если вопрос еще актуален — напишите 👍"
                )

                next_step = 1

            elif followup_step == 1 and diff >= timedelta(days=3):

                text = (
                    "Большинство компаний теряют клиентов "
                    "из-за медленных ответов и отсутствия автоматизации.\n\n"
                    "AI-система помогает:\n"
                    "— отвечать 24/7\n"
                    "— собирать заявки\n"
                    "— автоматизировать продажи\n\n"
                    "Если хотите — могу показать готовые решения 👌"
                )

                next_step = 2

            elif followup_step == 2 and diff >= timedelta(days=7):

                text = (
                    "Подскажите, вопрос AI-автоматизации "
                    "для вас еще актуален?\n\n"
                    "Могу показать несколько готовых решений "
                    "под вашу нишу 👍"
                )

                next_step = 3

        # MEDIUM LEADS
        elif priority == "medium":

            if followup_step == 0 and diff >= timedelta(hours=2):

                text = (
                    "Посмотрел вашу задачу 👌\n\n"
                    "Есть несколько идей, "
                    "как улучшить обработку заявок "
                    "и автоматизировать часть работы."
                )

                next_step = 1

            elif followup_step == 1 and diff >= timedelta(hours=24):

                text = (
                    "Если задача еще актуальна — "
                    "могу показать пример решения "
                    "под ваш бизнес 👌"
                )

                next_step = 2

        # LOW LEADS
        else:

            if followup_step == 0 and diff >= timedelta(hours=24):

                text = (
                    "Если вопрос автоматизации "
                    "для вас еще актуален — "
                    "напишите 👌"
                )

                next_step = 1

        # RE-ENGAGEMENT
        if (
            not text
            and not reanimate_sent
            and diff >= timedelta(days=7)
        ):

            if priority == "high":

                text = (
                    "Посмотрел ваш прошлый запрос 👌\n\n"
                    "За это время подготовил еще несколько "
                    "идей, как можно автоматизировать "
                    "обработку клиентов и сократить "
                    "потерю заявок.\n\n"
                    "Если задача еще актуальна — "
                    "напишите."
                )

            elif priority == "medium":

                text = (
                    "Если вопрос автоматизации "
                    "для вас еще актуален — "
                    "могу показать несколько "
                    "готовых решений под ваш бизнес 👌"
                )

            else:

                text = (
                    "Если захотите вернуться "
                    "к вопросу AI автоматизации — "
                    "напишите 👌"
                )

        if text:

            try:

                bot.send_message(
                    int(lead["chat_id"]),
                    text
                )

                supabase.table("leads").update({
                    "followup_step": next_step,
                    "followup_sent": True if next_step >= 3 else False,
                    "reanimate_sent": True if diff >= timedelta(days=7) else reanimate_sent
                }).eq("chat_id", lead["chat_id"]).execute()

            except:
                pass


# send_followups()
print("Webhook started")

if __name__ == "__main__":

    if os.getenv("MODE") == "followup":
        send_followups()

    else:
        port = int(os.environ.get("PORT", 10000))
        app.run(host="0.0.0.0", port=port)