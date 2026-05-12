import re
import os
from datetime import datetime, timedelta

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
"""


@bot.message_handler(commands=["start"])
def start(message):
    chat_id = message.chat.id

    lead = supabase.table("leads") \
        .select("*") \
        .eq("chat_id", str(chat_id)) \
        .execute()

    lead_info = ""

    if lead.data:
        db_lead = lead.data[0]

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


@bot.message_handler(func=lambda message: True)
def chat(message):
    try:
        chat_id = message.chat.id
        text = message.text.lower()

        lead = supabase.table("leads") \
            .select("*") \
            .eq("chat_id", str(chat_id)) \
            .execute()

        lead_info = ""

        if lead.data:
            db_lead = lead.data[0]

            lead_info = f"""
Ниша: {db_lead.get('niche', '')}
Боль: {db_lead.get('pain', '')}
Цель: {db_lead.get('goal', '')}
Этап: {db_lead.get('stage', '')}

Summary:
{db_lead.get('summary', '')}
"""
       
        phone_pattern = r"\+?\d[\d\-\(\) ]{8,}\d"
        email_pattern = r"[^@]+@[^@]+\.[^@]+"

        # если человек уже в воронке
        if chat_id in lead_state:
            step = lead_state[chat_id]

    #         if step == "wait_niche":
    #             lead_data[chat_id]["niche"] = message.text
    #             lead_state[chat_id] = "wait_pain"

    #             bot.reply_to(
    #                 message,
    #                 "Что сейчас больше всего мешает росту?\n\n"
    #                 "Например:\n"
    #                 "— мало заявок\n"
    #                 "— дорогая реклама\n"
    #                 "— слабые продажи"
    #             )
    #             return

    #         if step == "wait_pain":
    #             lead_data[chat_id]["pain"] = message.text
    #             lead_state[chat_id] = "wait_goal"

    #             bot.reply_to(
    #                 message,
    #                 "Что хотите автоматизировать в первую очередь?"
    #             )
    #             return

    #         if step == "wait_goal":
    #             lead_data[chat_id]["goal"] = message.text
    #             segment, priority, offer_type = detect_segment(
    #                 lead_data[chat_id]["niche"]
    #             )
    #             lead_data[chat_id]["segment"] = segment
    #             lead_data[chat_id]["priority"] = priority
    #             lead_data[chat_id]["offer_type"] = offer_type
    #             lead_state[chat_id] = "wait_contact"

    #             pain = lead_data[chat_id]["pain"].lower()
    #             goal = lead_data[chat_id]["goal"].lower()

    #             score = 50

    #             if any(word in pain for word in [
    #                 "нет заявок",
    #                 "мало клиентов",
    #                 "дорого",
    #                 "ручной",
    #                 "долго",
    #                 "теряем",
    #             ]):
    #                 score += 20

    #             if any(word in goal for word in [
    #                 "рост",
    #                 "заявки",
    #                 "автоматизация",
    #                 "масштаб",
    #                 "продажи",
    #             ]):
    #                 score += 30

    #             lead_data[chat_id]["score"] = score
    #             save_followup(chat_id, message, "wait_contact")

    #             offer = make_offer(segment)

    #             bot.reply_to(
    #                 message,
    #                 offer
                    
    #             )
    #             return

    #         if step == "wait_contact":
    #             if (
    #                 re.search(phone_pattern, message.text)
    #                 or re.search(email_pattern, message.text)
    #                 or "@" in message.text
    #             ):
                    
            
        
    #                 supabase.table("leads").update({
    #                     "name": message.from_user.first_name or "Без имени",
    #                     "username": f"@{message.from_user.username}" if message.from_user.username else "нет",
    #                     "phone": message.text,
    #                     "chat_id": str(chat_id),
    #                     "niche": lead_data[chat_id].get("niche", ""),
    #                     "pain": lead_data[chat_id].get("pain", ""),
    #                     "goal": lead_data[chat_id].get("goal", ""),
    #                     "score": lead_data[chat_id].get("score", 0),
    #                     "status": "new",
    #                     "segment": lead_data[chat_id].get("segment", "other"),
    #                     "priority": lead_data[chat_id].get("priority", "Normal"),
    #                     "offer_type": lead_data[chat_id].get("offer_type", "standard"),
    #                 }).eq("chat_id", str(chat_id)).execute()

    #                 bot.send_message(
    #                     1908342578,
    #                   f"🔥 Новый лид\n\n"
    #                   f"Приоритет: {lead_data[chat_id]['priority']}\n"
    #                   f"Сегмент: {lead_data[chat_id]['offer_type']}\n"
    #                   f"Score: {lead_data[chat_id]['score']}\n\n"
    #                   f"Имя: {message.from_user.first_name}\n"
    #                   f"Username: @{message.from_user.username}\n"
    #                   f"Ниша: {lead_data[chat_id]['niche']}\n"
    #                   f"Боль: {lead_data[chat_id]['pain']}\n"
    #                   f"Цель: {lead_data[chat_id]['goal']}\n"
    #                   f"Контакт: {message.text}"  
    #                 )

    #                 # del lead_state[chat_id]
    #                 # del lead_data[chat_id]
                    

    #                 bot.reply_to(
    #                     message,
    #                     "Принял 👌\n\n"
    #                     "Подготовлю конкретное предложение и свяжусь с вами 🚀"
    #                 )
    #                 return
    
            # else:
            
            if chat_id not in user_memory:

                restored_history = None

                if lead.data:
                    db_lead = lead.data[0]
                    restored_history = db_lead.get("ai_history")

                if restored_history:
                    try:
                        user_memory[chat_id] = eval(restored_history)
                    except:
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

            user_memory[chat_id].append({
                "role": "user",
                "content": message.text
            })

            if len(user_memory[chat_id]) > 80:
                user_memory[chat_id] = (
                    [user_memory[chat_id][0]]
                    + user_memory[chat_id][-11:]
                )

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=user_memory[chat_id],
                temperature=0.5,
                max_tokens=500,
            )

            answer = response.choices[0].message.content
            
            brief_prompt = f"""
            Сделай краткую CRM-сводку клиента.

            Сообщения:
            {message.text}

            Ответ AI:
            {answer}

            Нужен ответ строго в формате:

            STAGE:
            BRIEF:
            NEXT:

            Где:

            STAGE = cold / warm / hot

            BRIEF = кратко о клиенте

            NEXT = следующий шаг продажи
            """

            try:
                brief_response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": "Ты CRM AI аналитик."
                        },
                        {
                            "role": "user",
                            "content": brief_prompt
                        }
                    ],
                    temperature=0.2,
                    max_tokens=150
                )

                brief_text = brief_response.choices[0].message.content

                ai_stage = "cold"
                ai_brief = ""
                ai_next_step = ""

                for line in brief_text.split("\n"):

                    if line.startswith("STAGE:"):
                        ai_stage = line.replace("STAGE:", "").strip()

                    elif line.startswith("BRIEF:"):
                        ai_brief = line.replace("BRIEF:", "").strip()

                    elif line.startswith("NEXT:"):
                        ai_next_step = line.replace("NEXT:", "").strip()

                supabase.table("leads").update({
                    "ai_stage": ai_stage,
                    "ai_brief": ai_brief,
                    "ai_next_step": ai_next_step
                }).eq("chat_id", str(chat_id)).execute()

            except Exception as brief_error:
                print("Brief error:", brief_error)
            
            score = 0

            text_all = (
                lead_info.lower()
                + " "
                + message.text.lower()
                + " "
                + answer.lower()
            )

            # бюджет
            if any(word in text_all for word in [
                "бюджет",
                "250",
                "500",
                "миллион",
                "тысяч"
            ]):
                score += 25

            # срочность
            if any(word in text_all for word in [
                "сегодня",
                "срочно",
                "быстро",
                "сейчас",
                "готов"
            ]):
                score += 25

            # внедрение
            if any(word in text_all for word in [
                "внедрение",
                "crm",
                "ai",
                "автоматизация"
            ]):
                score += 20

            # объем
            if any(word in text_all for word in [
                "заявок",
                "сотрудников",
                "лидов"
            ]):
                score += 15

            # контакт
            if (
                re.search(phone_pattern, message.text)
                or "@" in message.text
            ):
                score += 30

            lead_temp = "cold"

            if score >= 70:
                lead_temp = "hot"

                bot.send_message(
                    1908342578,
                    f"🔥 ГОРЯЧИЙ ЛИД\n\n"
                    f"Клиент: {message.from_user.first_name}\n"
                    f"Score: {score}\n"
                    f"Сообщение: {message.text}"
                )

            elif score >= 40:
                lead_temp = "warm"

                contact_request = ""

            if (
                score >= 70
                and not re.search(phone_pattern, message.text)
                and "@" not in message.text
            ):

                contact_request = (
                    "\n\n"
                    "Если хотите — могу подготовить "
                    "конкретный план внедрения под ваш бизнес 👌\n\n"
                    "Оставьте телефон, Telegram или email для связи."
                )    


            supabase.table("leads").update({
                "lead_score": score,
                "lead_temp": lead_temp
            }).eq("chat_id", str(chat_id)).execute()  



            if len(answer) > 2000:
                answer = answer[:2000]

            user_memory[chat_id].append({
                "role": "assistant",
                "content": answer
            })
            try:
                history_text = str(user_memory[chat_id])

                supabase.table("leads").update({
                    "ai_history": history_text,
                    "last_message_at": datetime.utcnow().isoformat()
                }).eq("chat_id", str(chat_id)).execute()

            except Exception as save_error:
                print("History save error:", save_error)
           
            bot.reply_to(message, answer + contact_request)
            return
        
               

        # запуск воронки
        if (
            text == "да"
            and chat_id not in lead_state
            and chat_id not in user_memory
        ):
            lead_state[chat_id] = "wait_niche"
            lead_data[chat_id] = {}

            bot.reply_to(
                message,
                "Отлично 👌\n\n"
                "Чем вы занимаетесь?\n"
                "Коротко: ниша / бизнес / направление."
            )
            return
        

        # # если проявил интерес
        # if (any(word in text for word in lead_words)):
        #     bot.reply_to(
        #         message,
        #         "Готовы начать диагностику?\n\nНапишите: да"
        #     )
        #     return
        
        business_words = [
            "как",
            "каким образом",
            "что конкретно",
            "подробно",
            "какие системы",
            "как работает",
            "что будет",
            "реализовано"
        ]

        if any(word in text for word in business_words):
            bot.reply_to(
                message,
                "Реализация обычно такая:\n\n"
                "1) сайт / лендинг / форма заявки\n"
                "2) CRM фиксирует все обращения\n"
                "3) AI-консультант отвечает 24/7\n"
                "4) автоворонка возвращает потерянных клиентов\n"
                "5) аналитика показывает стоимость заявки\n\n"
                "Что интересно разобрать подробнее?"
            )
            return

        # обычный AI чат

        lead_exists = (
            supabase.table("leads")
            .select("id")
            .eq("chat_id", str(chat_id))
            .execute()
        )

        if not lead_exists.data:
            supabase.table("leads").insert({
                "chat_id": str(chat_id),
                "name": message.from_user.first_name or "Без имени",
                "username": (
                    f"@{message.from_user.username}"
                    if message.from_user.username
                    else "нет"
                ),
                "stage": "dialog",
                "lead_temp": "cold",
                "lead_score": 0,
                "last_message_at": datetime.utcnow().isoformat()
            }).execute()

        if chat_id not in user_memory:
            user_memory[chat_id] = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT + "\n\n" + lead_info
                }
            ]

        user_memory[chat_id].append({
            "role": "user",
            "content": message.text
        })

        try:
            history_text = str(user_memory[chat_id])

            supabase.table("leads").update({
                "ai_history": history_text,
                "last_message_at": datetime.utcnow().isoformat()
            }).eq("chat_id", str(chat_id)).execute()

        except Exception as save_error:
            print("History save error:", save_error)

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=user_memory[chat_id],
            temperature=0.3,
            max_tokens=250,
        )

        answer = response.choices[0].message.content
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

        Диалог:
        Клиент: {message.text}

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

        summary = summary_response.choices[0].message.content

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
            Клиент: {message.text}

            AI:
            {answer}

            Ответь только одним словом:
            hot / warm / cold
            """

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

        supabase.table("leads").update({
                "summary": summary,
                "stage": "dialog",
                "lead_temp": ai_temp,
                "last_message_at": datetime.utcnow().isoformat()
            }).eq("chat_id", str(chat_id)).execute() 

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

def send_followups():
    from datetime import timezone

    now = datetime.now(timezone.utc)

    rows = (
        supabase.table("leads")
        .select("*")
        .execute()
    )

    for lead in rows.data:

        if not lead.get("last_message_at"):
            continue

        last = datetime.fromisoformat(
            lead["last_message_at"].replace("Z", "+00:00")
        )

        diff = now - last
        step = lead.get("followup_step", 0)

        text = None
        next_step = step

        # 2 часа
        if step == 0 and diff >= timedelta(hours=2):

            text = (
                "Посмотрел вашу задачу 👌\n\n"
                "Уже вижу несколько вариантов, "
                "как сократить ручную работу "
                "и ускорить обработку заявок.\n\n"
                "Если актуально — напишите."
            )

            next_step = 1

        # 24 часа
        elif step == 1 and diff >= timedelta(hours=24):

            text = (
                "Подготовил еще идеи по автоматизации "
                "под ваш бизнес.\n\n"
                "Можно внедрить CRM, AI-ассистента "
                "и автоматический сбор заявок "
                "в одну систему.\n\n"
                "Если интересно — могу показать пример."
            )

            next_step = 2

        # 3 дня
        elif step == 2 and diff >= timedelta(days=3):

            text = (
                "Часто компании теряют заявки "
                "из-за ручной обработки.\n\n"
                "Автоматизация обычно окупается "
                "довольно быстро за счет скорости "
                "обработки клиентов.\n\n"
                "Если хотите — подготовлю пример "
                "под вашу нишу 👌"
            )

            next_step = 3

        if text:

            try:

                bot.send_message(
                    int(lead["chat_id"]),
                    text
                )

                supabase.table("leads").update({
                    "followup_step": next_step
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
