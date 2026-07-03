"""
Grants KZ Lead Bot — AI консультант по зарубежным грантам + сбор лидов в Google Sheets.
"""

import os
import json
import logging
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
import anthropic
import gspread

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("GRANTS_BOT_TOKEN")
try:
    PARTNER_SALES_ID = int(os.getenv("TELEGRAM_OWNER_ID", "0"))
except (ValueError, TypeError):
    PARTNER_SALES_ID = 0
SHEET_ID = "1VJh2uN3tw14wXBVxduDXVE7lIgJWK3MMXg34IZd3JTY"

# ─── Тексты ───────────────────────────────────────────────────────────────────

TEXTS = {
    "ru": {
        "welcome": (
            "Привет! 👋 Я помогу разобраться с зарубежными грантами и стипендиями "
            "для казахстанских студентов.\n\n"
            "Задай свой вопрос — расскажу про программы в Китае, Турции, Венгрии, "
            "Корее, Германии, Малайзии, Японии и не только."
        ),
        "ask_question": "Задай вопрос:",
        "partner_btn": "🎓 Хочу помощь с поступлением",
        "trust_screen": (
            "🎓 Наш специалист свяжется с тобой бесплатно и:\n\n"
            "✅ Оценит твои шансы на грант\n"
            "✅ Подберёт подходящие программы под твой профиль\n"
            "✅ Объяснит какие документы нужны и с чего начать\n\n"
            "━━━━━━━━━━━━━━━\n"
            "Как это работает:\n\n"
            "1️⃣ Оставляешь заявку (займёт 1 минуту)\n"
            "2️⃣ Специалист свяжется в течение 24 часов\n"
            "3️⃣ Бесплатная консультация по твоей ситуации\n"
            "4️⃣ Вместе готовим документы и подаём заявку"
        ),
        "trust_btn": "Оставить заявку →",
        "collect_intro": "Отлично! Начнём.\n\nКак тебя зовут?",
        "ask_phone": "📱 Напиши свой номер телефона (WhatsApp):",
        "ask_country": "🌍 В какую страну хочешь поступить?",
        "ask_edu": "📚 Какой у тебя уровень образования сейчас?",
        "edu_options": ["🏫 Учусь в школе (10-11 класс)", "🎓 Оканчиваю школу / колледж", "📖 Бакалавр (студент или выпускник)", "🔬 Ищу магистратуру / PhD"],
        "country_options": ["🇨🇳 Китай", "🇹🇷 Турция", "🇭🇺 Венгрия", "🇰🇷 Корея", "🇩🇪 Германия", "🇲🇾 Малайзия", "🇯🇵 Япония", "🌐 Другая страна"],
        "done": (
            "✅ Спасибо! Твои данные переданы нашим партнёрам.\n\n"
            "Они свяжутся с тобой в течение 24 часов и расскажут о дальнейших шагах. "
            "Удачи с поступлением! 🍀"
        ),
        "still_questions": "Остались вопросы? Пиши, помогу!",
    },
    "kz": {
        "welcome": (
            "Сәлем! 👋 Мен сізге шетелдік грант пен стипендиялар туралы ақпарат беремін.\n\n"
            "Сұрағыңызды қойыңыз — Қытай, Түркия, Венгрия, Корея, Германия, Малайзия, "
            "Жапония және басқа елдердегі бағдарламалар туралы айтып беремін."
        ),
        "ask_question": "Сұрағыңызды жазыңыз:",
        "partner_btn": "🎓 Түсуге көмек алғым келеді",
        "trust_screen": (
            "🎓 Біздің маман сізбен тегін байланысып:\n\n"
            "✅ Грантқа мүмкіндіктеріңізді бағалайды\n"
            "✅ Профиліңізге сай бағдарламаларды таңдайды\n"
            "✅ Қандай құжаттар керек екенін түсіндіреді\n\n"
            "━━━━━━━━━━━━━━━\n"
            "Қалай жұмыс істейді:\n\n"
            "1️⃣ Өтінім қалдырасыз (1 минут)\n"
            "2️⃣ Маман 24 сағат ішінде хабарласады\n"
            "3️⃣ Жағдайыңыз бойынша тегін кеңес\n"
            "4️⃣ Бірге құжаттарды дайындап, өтінім береміз"
        ),
        "trust_btn": "Өтінім қалдыру →",
        "collect_intro": "Тамаша! Бастайық.\n\nАтыңыз кім?",
        "ask_phone": "📱 Телефон нөміріңізді жазыңыз (WhatsApp):",
        "ask_country": "🌍 Қай елге түскіңіз келеді?",
        "ask_edu": "📚 Қазіргі білім деңгейіңіз қандай?",
        "edu_options": ["🏫 Мектепте оқимын (10-11 сынып)", "🎓 Мектепті / колледжді бітіремін", "📖 Бакалавр (студент немесе түлек)", "🔬 Магистратура / PhD іздеймін"],
        "country_options": ["🇨🇳 Қытай", "🇹🇷 Түркия", "🇭🇺 Венгрия", "🇰🇷 Корея", "🇩🇪 Германия", "🇲🇾 Малайзия", "🇯🇵 Жапония", "🌐 Басқа ел"],
        "done": (
            "✅ Рахмет! Деректеріңіз серіктестерімізге жіберілді.\n\n"
            "Олар 24 сағат ішінде сізбен байланысып, келесі қадамдар туралы айтады. "
            "Түсуде сәт болсын! 🍀"
        ),
        "still_questions": "Тағы сұрақтарыңыз бар ма? Жазыңыз!",
    },
}

SYSTEM_PROMPT = """Ты — консультант Grants KZ по зарубежным грантам и стипендиям для казахстанских студентов.
Давай конкретные, точные ответы. Если не знаешь точной информации — скажи честно.
Отвечай на том языке, на котором пишет пользователь.

ПРОГРАММЫ КОТОРЫЕ ТЫ ЗНАЕШЬ:

КИТАЙ — CSC (Chinese Government Scholarship):
- Полная стипендия правительства КНР: обучение + жильё + питание + стипендия
- Направления: медицина (очень популярна), инженерия, IT, гуманитарные
- Уровни: бакалавр (4-6 лет), магистр (2-3 года), PhD (3-4 года)
- Дедлайн: март-апрель каждого года (через посольство КНР или напрямую в вуз)
- Требования бакалавр: аттестат мин. 75-80%, возраст до 25 лет, медсправка
- Требования магистр: диплом бакалавра, GPA от 3.5, рекомендательные письма
- Язык обучения: китайский (нужен HSK 4-5) или английский (IELTS 6.0+)
- Популярные мед. вузы: Цзилиньский, Харбинский, Шанхайский медуниверситеты
- Срок рассмотрения: 3-6 месяцев
- Подача через: csc.edu.cn или посольство Китая в Астане

ТУРЦИЯ — Türkiye Bursları:
- Полная стипендия: обучение + жильё + карманные деньги (1000 TL/мес)
- Все специальности, включая медицину
- Уровни: бакалавр, магистр, PhD, языковые курсы
- Дедлайн: февраль (открытие январь, закрытие февраль)
- Требования бакалавр: аттестат мин. 70%, возраст до 21 года
- Требования магистр: диплом бакалавра, мин. 75%, возраст до 30 лет
- Язык: турецкий (дают 1 год на изучение бесплатно) или английские программы
- Сайт: turkiyeburslari.gov.tr
- Очень высокий конкурс (сотни тысяч заявок)

ВЕНГРИЯ — Stipendium Hungaricum:
- Полная стипендия правительства Венгрии
- Много программ на английском языке
- Медицина, инженерия, IT, гуманитарные
- Дедлайн: январь-февраль
- Требования: аттестат/диплом, IELTS 5.5+ или B2, мотивационное письмо
- Сайт: stipendiumhungaricum.hu

КОРЕЯ — KGSP (Korean Government Scholarship Program):
- Полная стипендия: обучение + жильё + питание + карманные деньги
- Уровни: бакалавр и магистр/PhD
- Дедлайн: февраль-март (через посольство) или сентябрь (через университет)
- Требования: аттестат/диплом с GPA от 80%, мотивационное письмо, рекомендации
- Язык: корейский (год обучения) или английский
- Сайт: studyinkorea.go.kr

ГЕРМАНИЯ — DAAD и другие:
- В основном магистратура и PhD
- Огромный выбор программ, много на английском
- DAAD стипендия: 850-1200 EUR/месяц + медстраховка
- Требования: диплом бакалавра с отличием, языковой сертификат (немецкий B2 или IELTS 6.5+)
- Дедлайн: зависит от программы (обычно октябрь-ноябрь)
- Сайт: daad.de

МАЛАЙЗИЯ — MIS (Malaysian International Scholarship):
- Для магистратуры и PhD
- Технические специальности в приоритете
- Требования: диплом бакалавра, IELTS 6.0+, исследовательский план
- Также есть частные университеты с грантами (Universiti Malaya, UTM)

ЯПОНИЯ — MEXT (Monbukagakusho):
- Полная стипендия правительства Японии
- Уровни: бакалавр, магистр, PhD, специалист
- Дедлайн: июнь (через посольство Японии в Астане)
- Требования: аттестат/диплом, мотивационное письмо, рекомендации
- Язык: японский (учат год бесплатно) или английский
- Очень престижная, высокий конкурс

БОЛАШАК (Казахстан):
- Президентская программа для магистратуры/PhD за рубежом
- Требования: опыт работы 3+ лет, высокий GPA, IELTS 6.5+
- Контракт: обязательство работать в Казахстане после окончания
- Очень высокий конкурс, ограниченные квоты

РОССИЯ:
- Квоты правительства РФ — бесплатное обучение в российских вузах
- Подача через Россотрудничество в Астане
- Медицина, инженерия, педагогика популярны

СОВЕТЫ ПО ПОДГОТОВКЕ:
- Начинать готовиться минимум за 1-1.5 года до желаемого поступления
- Ключевые документы: аттестат/диплом с нотариальным переводом, мотивационное письмо, рекомендательные письма (2-3), медицинская справка, фото, загранпаспорт
- Языковой сертификат: IELTS, TOEFL, HSK (Китай), TOPIK (Корея), TestDaF (Германия)
- Мотивационное письмо — самый важный документ, нужно писать индивидуально под каждый вуз"""


# ─── Google Sheets ────────────────────────────────────────────────────────────

def _get_sheets_client():
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        return None
    try:
        return gspread.service_account_from_dict(json.loads(creds_json))
    except Exception as e:
        logger.error(f"[Grants Sheets] auth error: {e}")
        return None


def save_lead(name: str, phone: str, country: str, education: str,
              language: str, first_question: str) -> None:
    gc = _get_sheets_client()
    if not gc:
        raise RuntimeError("нет GOOGLE_CREDENTIALS")
    sh = gc.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet("Лиды")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet("Лиды", rows=1000, cols=10)

    if ws.row_values(1) != ["Дата", "Имя", "Телефон", "Страна", "Образование", "Язык", "Первый вопрос"]:
        ws.update("A1", [["Дата", "Имя", "Телефон", "Страна", "Образование", "Язык", "Первый вопрос"]])

    ws.append_row([
        datetime.now().strftime("%d.%m.%Y %H:%M"),
        name, phone, country, education, language, first_question,
    ], value_input_option="USER_ENTERED")


# ─── Claude консультация ──────────────────────────────────────────────────────

def ask_claude(history: list, language: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    lang_note = "Отвечай на русском языке." if language == "ru" else "Қазақ тілінде жауап бер."
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        system=SYSTEM_PROMPT + f"\n\n{lang_note}",
        messages=history,
    )
    return response.content[0].text


# ─── Хэндлеры ────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru"),
            InlineKeyboardButton("🇰🇿 Қазақша", callback_data="lang:kz"),
        ]
    ])
    await update.message.reply_text(
        "Выберите язык / Тілді таңдаңыз:",
        reply_markup=keyboard
    )


async def handle_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":")[1]
    context.user_data["lang"] = lang
    context.user_data["history"] = []
    context.user_data["step"] = "consulting"
    t = TEXTS[lang]
    await query.edit_message_text(t["welcome"])


async def handle_partner_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang", "ru")
    t = TEXTS[lang]
    await query.edit_message_reply_markup(reply_markup=None)
    trust_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t["trust_btn"], callback_data="action:start_lead")]
    ])
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=t["trust_screen"],
        reply_markup=trust_keyboard
    )


async def handle_start_lead_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang", "ru")
    t = TEXTS[lang]
    context.user_data["step"] = "collect_name"
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat_id, text=t["collect_intro"])


async def handle_country_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang", "ru")
    t = TEXTS[lang]
    idx = int(query.data.replace("country:", ""))
    context.user_data["country"] = t["country_options"][idx]
    context.user_data["step"] = "collect_edu"
    buttons = [
        [InlineKeyboardButton(opt, callback_data=f"edu:{i}")]
        for i, opt in enumerate(t["edu_options"])
    ]
    await query.edit_message_text(t["ask_edu"], reply_markup=InlineKeyboardMarkup(buttons))


async def handle_edu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang", "ru")
    t = TEXTS[lang]
    idx = int(query.data.replace("edu:", ""))
    context.user_data["education"] = t["edu_options"][idx]
    context.user_data["step"] = "done"

    name = context.user_data.get("name", "")
    phone = context.user_data.get("phone", "")
    country = context.user_data.get("country", "")
    education = context.user_data.get("education", "")
    first_q = context.user_data.get("first_question", "")

    import asyncio
    try:
        await asyncio.to_thread(save_lead, name, phone, country, education, lang, first_q)
    except Exception as e:
        logger.error(f"[Grants] save_lead error: {e}")

    await query.edit_message_text(t["done"])

    if PARTNER_SALES_ID:
        notification = (
            f"🎓 Новая заявка — Grants KZ\n\n"
            f"👤 Имя: {name}\n"
            f"📱 Телефон: {phone}\n"
            f"🌍 Страна: {country}\n"
            f"📚 Образование: {education}\n"
            f"❓ Вопрос: {first_q or '—'}\n\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        try:
            await context.bot.send_message(chat_id=PARTNER_SALES_ID, text=notification)
        except Exception as e:
            logger.error(f"[Grants] partner notify error: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = context.user_data.get("lang", "ru")
    t = TEXTS[lang]
    step = context.user_data.get("step", "no_lang")
    text = update.message.text.strip()

    if step == "no_lang":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru"),
                InlineKeyboardButton("🇰🇿 Қазақша", callback_data="lang:kz"),
            ]
        ])
        await update.message.reply_text("Выберите язык / Тілді таңдаңыз:", reply_markup=keyboard)
        return

    if step == "consulting":
        history = context.user_data.get("history", [])
        if not history:
            context.user_data["first_question"] = text
        history.append({"role": "user", "content": text})

        await update.message.reply_chat_action("typing")
        try:
            import asyncio
            reply = await asyncio.to_thread(ask_claude, history, lang)
        except Exception as e:
            logger.error(f"[Grants] claude error: {e}")
            reply = "Произошла ошибка. Попробуйте ещё раз." if lang == "ru" else "Қате орын алды. Қайталап көріңіз."

        history.append({"role": "assistant", "content": reply})
        context.user_data["history"] = history[-10:]  # последние 10 сообщений

        partner_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton(t["partner_btn"], callback_data="action:partner")]
        ])
        await update.message.reply_text(reply, reply_markup=partner_btn)
        return

    if step == "collect_name":
        context.user_data["name"] = text
        context.user_data["step"] = "collect_phone"
        await update.message.reply_text(t["ask_phone"])
        return

    if step == "collect_phone":
        context.user_data["phone"] = text
        context.user_data["step"] = "collect_country"
        buttons = [
            [InlineKeyboardButton(opt, callback_data=f"country:{i}")]
            for i, opt in enumerate(t["country_options"])
        ]
        await update.message.reply_text(t["ask_country"], reply_markup=InlineKeyboardMarkup(buttons))
        return

    if step == "done":
        await update.message.reply_text(t["still_questions"])
        context.user_data["step"] = "consulting"
        await handle_message(update, context)
        return


# ─── Запуск ───────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_lang_callback, pattern="^lang:"))
    app.add_handler(CallbackQueryHandler(handle_partner_callback, pattern="^action:partner"))
    app.add_handler(CallbackQueryHandler(handle_start_lead_callback, pattern="^action:start_lead"))
    app.add_handler(CallbackQueryHandler(handle_country_callback, pattern="^country:"))
    app.add_handler(CallbackQueryHandler(handle_edu_callback, pattern="^edu:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Grants KZ Bot запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
