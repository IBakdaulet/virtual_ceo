"""
Telegram-бот — главный интерфейс Virtual CEO.
Планировщик: запрос балансов в 23:00, повтор в 12:00 если нет ответа.
Поддержка голосовых сообщений через OpenAI Whisper.
"""

import os
import json
import logging
import tempfile
from datetime import datetime, time
from pathlib import Path

import pytz
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

load_dotenv()

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

OWNER_ID = int(os.getenv("TELEGRAM_OWNER_ID", "0"))
SALESPERSON_ID = int(os.getenv("SALESPERSON_ID", "0"))
ALMATY_TZ = pytz.FixedOffset(6 * 60)  # UTC+6 (фактический часовой пояс системы)
STATE_FILE = Path(__file__).parent.parent / "data" / "daily_state.json"

conversation_history: list = []
statement_analyses: list = []
adddata_state: dict = {"active": False, "year": None}  # in-memory, не файл
YEARPLAN_FILE = Path(__file__).parent.parent / "data" / "yearplan_state.json"

def _load_yearplan() -> dict:
    if YEARPLAN_FILE.exists():
        with open(YEARPLAN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"active": False, "data": [], "year": None, "waiting_year": False}

def _save_yearplan(state: dict):
    with open(YEARPLAN_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ─── Утилиты ────────────────────────────────────────────────────────────────

def is_owner(update: Update) -> bool:
    return update.effective_user.id == OWNER_ID


def is_salesperson(update: Update) -> bool:
    return SALESPERSON_ID != 0 and update.effective_user.id == SALESPERSON_ID


async def send_long(update: Update, text: str):
    MAX_LEN = 4000
    for chunk in [text[i:i+MAX_LEN] for i in range(0, len(text), MAX_LEN)]:
        await update.message.reply_text(chunk)


def load_state() -> dict:
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def mark_responded():
    state = load_state()
    state["pending_update"] = False
    state["last_update"] = datetime.now(ALMATY_TZ).isoformat()
    save_state(state)


# ─── Продажи: запрос, напоминания, отчёт ────────────────────────────────────

async def request_sales_report(context):
    """17:00 — запускаем пошаговый диалог с продажником."""
    if SALESPERSON_ID == 0:
        return
    from agents.sales_agent import SalesConversation, reset_daily_state
    reset_daily_state()
    conv = SalesConversation()
    conv.reset()
    msg = conv.start()
    await context.bot.send_message(chat_id=SALESPERSON_ID, text=msg)


async def check_stale_conversation(context):
    """Каждые 30 мин: если диалог завис — сброс и напоминание продажнику."""
    if SALESPERSON_ID == 0:
        return
    from agents.sales_agent import SalesConversation, reset_daily_state
    conv = SalesConversation()
    if conv.is_stale(max_minutes=60):
        reset_daily_state()
        conv.reset()
        msg = conv.start()
        await context.bot.send_message(
            chat_id=SALESPERSON_ID,
            text="⚠️ Отчёт не был заполнен до конца. Начинаем заново — нужно заполнить все 3 проекта.\n\n" + msg
        )
        logger.info("Зависший диалог сброшен и перезапущен")


async def check_sales_19(context):
    """19:00 — если отчёт получен, шлём владельцу. Если нет — напоминание."""
    from agents.sales_agent import is_submitted_today, daily_report, get_reminder_message
    if is_submitted_today():
        report = daily_report()
        await context.bot.send_message(chat_id=OWNER_ID, text=report)
    else:
        if SALESPERSON_ID != 0:
            await context.bot.send_message(
                chat_id=SALESPERSON_ID,
                text=get_reminder_message(attempt=1)
            )
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text="⏳ Дневной отчёт по продажам ещё не получен. Напомнил продажнику."
        )


async def remind_sales_2030(context):
    """20:30 — второе напоминание если всё ещё нет данных."""
    from agents.sales_agent import is_submitted_today, get_reminder_message
    if is_submitted_today():
        return
    if SALESPERSON_ID != 0:
        await context.bot.send_message(
            chat_id=SALESPERSON_ID,
            text=get_reminder_message(attempt=2)
        )
    await context.bot.send_message(
        chat_id=OWNER_ID,
        text="🔔 Продажник до сих пор не прислал отчёт."
    )


async def weekly_sales_job(context):
    """Понедельник 9:00 — недельный отчёт владельцу."""
    from agents.sales_agent import weekly_report
    report = weekly_report()
    await context.bot.send_message(chat_id=OWNER_ID, text=report)


async def monthly_sales_job(context):
    """1-е число 9:00 — месячный отчёт владельцу."""
    from agents.sales_agent import monthly_report
    from datetime import date
    last_month = date.today().replace(day=1) - __import__('datetime').timedelta(days=1)
    report = monthly_report(last_month.strftime("%Y-%m"))
    await context.bot.send_message(chat_id=OWNER_ID, text=report)


def _make_keyboard(buttons: list) -> InlineKeyboardMarkup:
    """Строит InlineKeyboardMarkup из списка [(текст, data), ...]."""
    keyboard = [
        [InlineKeyboardButton(text, callback_data=data) for text, data in row]
        for row in buttons
    ]
    return InlineKeyboardMarkup(keyboard)


async def handle_salesperson_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пошаговый диалог с продажником по всем проектам."""
    from agents.sales_agent import SalesConversation, daily_report, is_submitted_today

    conv = SalesConversation()
    text = update.message.text.strip()

    if not conv.is_active():
        msg = conv.start()
        await update.message.reply_text(msg)
        return

    await update.message.reply_chat_action("typing")
    next_q, _, is_done = conv.process_answer(text)
    await update.message.reply_text(next_q)

    if is_done:
        report = daily_report()
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"📊 Дневной отчёт по продажам:\n\n{report}"
        )


# ─── Курс доллара ────────────────────────────────────────────────────────────

async def auto_update_rate(context):
    """Ежедневно обновляет курс USD/KZT автоматически."""
    from agents.finance_agent import update_usd_rate
    result = update_usd_rate()
    logger.info(f"Курс: {result}")


# ─── Планировщик ────────────────────────────────────────────────────────────

async def request_balances(context):
    """Отправляет запрос балансов владельцу."""
    from agents.finance_agent import format_summary, _load
    data = _load()
    summary = format_summary(data)

    state = load_state()
    state["pending_update"] = True
    state["last_request"] = datetime.now(ALMATY_TZ).isoformat()
    save_state(state)

    text = (
        f"🌙 Добрый вечер! Время обновить балансы.\n\n"
        f"Текущее состояние:\n{summary}\n\n"
        f"Отправьте новые балансы текстом или голосовым.\n"
        f"Пример: каспи 150000, халык 800000, халык депозит 24500000"
    )
    await context.bot.send_message(chat_id=OWNER_ID, text=text)


async def reminder_balances(context):
    """Повторный запрос в 12:00 если не ответил."""
    state = load_state()
    if not state.get("pending_update"):
        return  # Уже обновил — не беспокоим

    await context.bot.send_message(
        chat_id=OWNER_ID,
        text=(
            "☀️ Напоминание: вчера вечером не обновили балансы счетов.\n"
            "Отправьте текстом или голосовым когда будет время."
        )
    )


# ─── Голосовые сообщения ─────────────────────────────────────────────────────

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        return

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        await update.message.reply_text(
            "Голосовые сообщения требуют OPENAI_API_KEY в .env файле."
        )
        return

    await update.message.reply_text("🎙 Слушаю...")

    tmp_ogg = tmp_mp3 = None
    try:
        from openai import OpenAI
        oai = OpenAI(api_key=openai_key)

        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            tmp_ogg = f.name
        await file.download_to_drive(tmp_ogg)

        # Транскрибируем через Whisper
        with open(tmp_ogg, "rb") as audio:
            transcript = oai.audio.transcriptions.create(
                model="whisper-1",
                file=audio,
                language="ru"
            )

        text = transcript.text
        await update.message.reply_text(f"🎙 Распознал: {text}\n\nОбновляю...")
        await _process_balance_text(update, text)

    except Exception as e:
        logger.error(f"Ошибка голосового: {e}")
        await update.message.reply_text(f"Не смог распознать: {e}")
    finally:
        for p in [tmp_ogg, tmp_mp3]:
            if p:
                try:
                    os.unlink(p)
                except Exception:
                    pass


async def _process_balance_text(update: Update, text: str):
    """Обновляет балансы из текста или голосовой транскрипции через Claude."""
    import anthropic as ant
    import json as _json
    from agents.finance_agent import update_balance, _load, format_summary

    data = _load()

    # Claude извлекает балансы — понимает и цифры и слова ("сто пятьдесят тысяч")
    client = ant.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    accounts_list = "\n".join(
        f'  "{k}": "{v["name"]} ({v["currency"]})"'
        for k, v in data["accounts"].items()
    )

    prompt = f"""Из этого текста извлеки балансы счетов. Текст может быть голосовым (числа словами).

Текст: "{text}"

Доступные счета:
{accounts_list}

Верни JSON массив только тех счетов которые упомянуты:
[{{"account_key": "kaspi_card", "balance": 150000}}, ...]

Правила:
- "сто пятьдесят тысяч" = 150000
- "миллион пятьсот" = 1500000
- Если счёт не упомянут — не включай
- Только JSON, без текста"""

    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = resp.content[0].text.strip()

    # Извлекаем JSON из ответа
    import re
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        from core.orchestrator import run
        response = run(text, conversation_history)
        await send_long(update, response)
        return

    try:
        balances = _json.loads(match.group())
    except Exception:
        await update.message.reply_text("Не смог распознать балансы. Попробуйте ещё раз.")
        return

    if not balances:
        from core.orchestrator import run
        response = run(text, conversation_history)
        await send_long(update, response)
        return

    updated = []
    for item in balances:
        key = item.get("account_key")
        bal = item.get("balance")
        if key and bal is not None:
            result = update_balance(key, float(bal), data)
            updated.append(result)

    if updated:
        mark_responded()
        summary = format_summary(data)
        await update.message.reply_text(
            "✅ Балансы обновлены:\n" + "\n".join(updated) + f"\n\n{summary}"
        )
    else:
        await update.message.reply_text("Не нашёл балансов в сообщении. Попробуйте ещё раз.")


# ─── Команды ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        return
    await update.message.reply_text(
        "Виртуальный СЕО запущен.\n\n"
        "Каждый день в 23:00 буду запрашивать балансы.\n"
        "Если не ответите — напомню в 12:00.\n\n"
        "Команды:\n"
        "/clear — очистить диалог\n"
        "/reset — сбросить загруженные выписки\n"
        "/balances — запросить балансы сейчас"
    )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        return
    conversation_history.clear()
    await update.message.reply_text("История диалога очищена.")


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        return
    statement_analyses.clear()
    await update.message.reply_text("Выписки сброшены.")


async def cmd_balances(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ручной запрос обновления балансов."""
    if not is_owner(update):
        return
    await request_balances(context)


def _load_adddata() -> dict:
    return adddata_state

def _save_adddata(state: dict):
    global adddata_state
    adddata_state.update(state)


async def cmd_adddata(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавляет новые данные к историческим продажам за указанный год."""
    if not is_owner(update):
        return
    args = context.args
    if args and args[0].isdigit() and len(args[0]) == 4:
        year = int(args[0])
        _save_adddata({"active": True, "year": year})
        await update.message.reply_text(
            f"📥 Добавляем данные за {year} год.\n\n"
            f"Отправь текст с новыми данными, например:\n"
            f"Январь 1.200.000\nФевраль 1.500.000\n\n"
            f"Напиши 'отмена' чтобы выйти."
        )
    else:
        await update.message.reply_text(
            "Укажи год: /adddata 2025"
        )


async def cmd_yearplan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запускает режим составления годового плана продаж."""
    if not is_owner(update):
        return
    state = {"active": True, "data": [], "year": None, "waiting_year": True}
    _save_yearplan(state)
    await update.message.reply_text(
        "📊 Годовой план продаж.\n\nЗа какой год составляем план? (напиши год, например: 2026)"
    )


async def cmd_sales(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Внеплановый запрос дневного отчёта у продажника."""
    if not is_owner(update):
        return
    if SALESPERSON_ID == 0:
        await update.message.reply_text("SALESPERSON_ID не задан в .env")
        return
    from agents.sales_agent import SalesConversation, reset_daily_state
    reset_daily_state()
    conv = SalesConversation()
    conv.reset()
    msg = conv.start()
    await context.bot.send_message(chat_id=SALESPERSON_ID, text=msg)
    await update.message.reply_text("✅ Запрос отправлен продажнику.")


# ─── Текстовые сообщения ─────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_salesperson(update):
        await handle_salesperson_message(update, context)
        return

    if not is_owner(update):
        return

    user_text = update.message.text.strip()
    await update.message.reply_chat_action("typing")

    # Режим добавления данных
    ad = _load_adddata()
    if ad["active"]:
        if user_text.lower() in ["отмена", "стоп", "cancel"]:
            _save_adddata({"active": False, "year": None})
            await update.message.reply_text("Отменено.")
            return
        year = ad["year"]
        try:
            from agents.sales_agent import save_historical_data, get_historical_raw
            save_historical_data(year, user_text)
            _save_adddata({"active": False, "year": None})
            updated = get_historical_raw(year)
            await update.message.reply_text(f"✅ Данные за {year} год обновлены.\n\n{updated}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при сохранении: {e}")
        return

    # Запрос исторических продаж — ВСЕГДА в приоритете (даже если yearplan активен)
    import re as _re
    hist_match = _re.search(r"20\d{2}", user_text)
    if hist_match and any(w in user_text.lower() for w in ["продаж", "выручк", "отчет", "данные", "план", "статистик", "итог"]):
        year = int(hist_match.group())
        from agents.sales_agent import get_historical_raw
        result = get_historical_raw(year)
        await send_long(update, result)
        return

    # Режим годового планирования
    yp = _load_yearplan()
    if yp["active"]:
        if any(w in user_text.lower() for w in ["отмена", "стоп", "cancel"]):
            _save_yearplan({"active": False, "data": [], "year": None, "waiting_year": False})
            await update.message.reply_text("Режим планирования отменён.")
            return

        # Ждём год
        if yp["waiting_year"]:
            import re as _re
            year_match = _re.search(r"20\d{2}", user_text)
            if not year_match:
                await update.message.reply_text("Напиши год цифрами, например: 2026")
                return
            yp["year"] = int(year_match.group())
            yp["waiting_year"] = False
            _save_yearplan(yp)
            await update.message.reply_text(
                f"✅ Составляем план на {yp['year']} год.\n\n"
                f"Теперь загрузи данные прошлых лет:\n"
                f"• PDF, Excel или CSV файл с выручкой\n"
                f"• Или напиши вручную:\n\n"
                f"2024: Grants KZ янв 800к, фев 1М...\n"
                f"Tanda Bilim: янв 600к, фев 700к...\n\n"
                f"Можно несколько файлов. Когда всё готово — напиши 'анализируй'."
            )
            return

        # Ждём данные или команду анализа
        trigger_words = ["анализируй", "готово", "составь план", "сделай план", "генерируй"]
        if any(w in user_text.lower() for w in trigger_words):
            if not yp["data"]:
                await update.message.reply_text("Сначала загрузи данные — файл или текст с выручкой прошлых лет.")
                return
            target_year = yp["year"]
            await update.message.reply_text(f"⏳ Анализирую данные и тренды рынка Казахстана для плана на {target_year}... Займёт минуту.")
            from agents.sales_agent import generate_annual_plan, save_annual_plan_as_targets
            combined = "\n\n---\n\n".join(yp["data"])
            plan = generate_annual_plan(combined, target_year)
            _save_yearplan({"active": False, "data": [], "year": None, "waiting_year": False})
            await send_long(update, plan)
            save_result = save_annual_plan_as_targets(plan, target_year)
            await update.message.reply_text(save_result)
            return
        else:
            yp["data"].append(user_text)
            _save_yearplan(yp)
            # Сохраняем в исторические данные — год ищем в тексте, fallback на "raw"
            import re as _re2
            year_in_text = _re2.search(r"20\d{2}", user_text)
            hist_year = int(year_in_text.group()) if year_in_text else (yp.get("year") or 0)
            if hist_year:
                from agents.sales_agent import save_historical_data
                save_historical_data(hist_year, user_text)
            chunks = len(yp["data"])
            await update.message.reply_text(
                f"✅ Данные добавлены ({chunks} блок(ов) загружено).\n"
                f"Загрузи ещё или напиши 'анализируй'."
            )
            return

    # Итог по нескольким выпискам
    if any(w in user_text.lower() for w in ["итог", "общая картина", "сводка", "суммируй"]):
        if not statement_analyses:
            await update.message.reply_text("Нет загруженных выписок.")
            return
        await send_combined_summary(update)
        return

    # Подтверждение / отмена
    if user_text.lower() in ["да", "ок", "ok", "yes", "подтверждаю", "верно"]:
        await update.message.reply_text("✅ Принято.")
        mark_responded()
        return
    if user_text.lower() in ["нет", "no", "отмена", "неверно"]:
        await update.message.reply_text("Окей, отменено. Отправьте правильные данные.")
        return

    # Проверяем — может это обновление балансов
    state = load_state()
    balance_keywords = ["каспи", "kaspi", "халык", "halyk", "фридом", "freedom"]
    if state.get("pending_update") or any(w in user_text.lower() for w in balance_keywords):
        await _process_balance_text(update, user_text)
        return

    # Всё остальное — оркестратор
    try:
        from core.orchestrator import run
        response = run(user_text, conversation_history)
        await send_long(update, response)
    except Exception as e:
        logger.error(f"Ошибка оркестратора: {e}")
        await update.message.reply_text(f"Ошибка: {e}")


# ─── PDF выписки ─────────────────────────────────────────────────────────────

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        return

    doc = update.message.document
    fname = doc.file_name.lower()

    # Режим годового планирования — принимаем любые файлы
    yp = _load_yearplan()
    if yp["active"]:
        await update.message.reply_text(f"📎 Получил файл: {doc.file_name}\nОбрабатываю...")
        tmp_path = None
        try:
            file = await context.bot.get_file(doc.file_id)
            suffix = "." + fname.split(".")[-1] if "." in fname else ".bin"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_path = tmp.name
            await file.download_to_drive(tmp_path)

            if fname.endswith(".pdf"):
                import base64
                with open(tmp_path, "rb") as f:
                    pdf_b64 = base64.standard_b64encode(f.read()).decode()
                # Извлекаем текст через Claude
                import anthropic as ant
                cl = ant.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                resp = cl.messages.create(
                    model="claude-opus-4-6", max_tokens=4096,
                    messages=[{"role": "user", "content": [
                        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                        {"type": "text", "text": "Извлеки все данные о выручке и продажах из этого документа. Выведи в структурированном виде по месяцам и проектам."}
                    ]}]
                )
                extracted = resp.content[0].text
            elif fname.endswith((".csv", ".txt")):
                with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                    extracted = f.read()
            elif fname.endswith((".xlsx", ".xls")):
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(tmp_path, data_only=True)
                    rows = []
                    for sheet in wb.worksheets:
                        rows.append(f"[Лист: {sheet.title}]")
                        for row in sheet.iter_rows(values_only=True):
                            if any(cell is not None for cell in row):
                                rows.append("\t".join(str(c) if c is not None else "" for c in row))
                    extracted = "\n".join(rows)
                except ImportError:
                    extracted = f"Excel файл: {doc.file_name} (установи openpyxl для чтения)"
            else:
                extracted = f"Файл {doc.file_name} — не удалось прочитать автоматически."

            yp["data"].append(f"[Файл: {doc.file_name}]\n{extracted}")
            _save_yearplan(yp)
            if yp.get("year"):
                from agents.sales_agent import save_historical_data
                save_historical_data(yp["year"], f"[Файл: {doc.file_name}]\n{extracted}")
            await update.message.reply_text(
                f"✅ Файл обработан ({len(yp['data'])} блок(ов) загружено).\n"
                f"Загрузи ещё файлы или напиши данные вручную.\n"
                f"Когда всё готово — напиши 'анализируй'."
            )
        except Exception as e:
            logger.error(f"Ошибка обработки файла для плана: {e}")
            await update.message.reply_text(f"Ошибка обработки файла: {e}")
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
        return

    if not fname.endswith(".pdf"):
        await update.message.reply_text("Поддерживаю только PDF выписки.")
        return

    count = len(statement_analyses) + 1
    await update.message.reply_text(f"📄 Выписка {count}: {doc.file_name}\nАнализирую...")

    tmp_path = None
    try:
        file = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

        from agents.statement_parser import parse_pdf, analyze_with_claude

        caption = update.message.caption or ""
        parsed = parse_pdf(tmp_path)
        bank = parsed["bank"].upper() if parsed["bank"] != "unknown" else "банк"
        analysis = analyze_with_claude(parsed, period=caption or None)

        statement_analyses.append({
            "bank": bank,
            "period": caption or doc.file_name,
            "analysis": analysis
        })

        header = f"📊 Выписка {count}: {bank}" + (f" ({caption})" if caption else "")
        await send_long(update, f"{header}\n{'─'*30}\n\n{analysis}\n\n💡 Загружено: {len(statement_analyses)} шт. Напишите итог для общей картины.")

    except Exception as e:
        logger.error(f"Ошибка анализа: {e}")
        await update.message.reply_text(f"Ошибка: {e}")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


async def send_combined_summary(update: Update) -> None:
    import anthropic as ant
    client = ant.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    banks = ", ".join(set(a["bank"] for a in statement_analyses))
    all_analyses = "\n\n".join(
        f"--- Выписка {i+1}: {a['bank']} {a['period']} ---\n{a['analysis']}"
        for i, a in enumerate(statement_analyses)
    )

    prompt = f"""Объедини {len(statement_analyses)} выписки ({banks}) в единый отчёт:

{all_analyses}

Формат:
📅 [МЕСЯЦ ГОД]
  Доходы: +X ₸ | Расходы: -Y ₸ | Баланс: Z ₸
  Категории: Еда X ₸, Транспорт X ₸, ...

📊 ИТОГО: Доходы +X ₸, Расходы -Y ₸, Баланс Z ₸

💡 ВЫВОДЫ: 3 совета предпринимателю"""

    await update.message.reply_text(f"Объединяю {len(statement_analyses)} выписки...")

    resp = client.messages.create(
        model="claude-opus-4-6", max_tokens=4096,
        system="Финансовый советник. Объединяй данные точно, на русском.",
        messages=[{"role": "user", "content": prompt}]
    )

    statement_analyses.clear()
    await send_long(update, f"📊 ОБЩИЙ ОТЧЁТ ({banks})\n\n{resp.content[0].text}")


# ─── Запуск ──────────────────────────────────────────────────────────────────

async def on_startup(context):
    """Через 30 сек после старта проверяем пропущенные джобы за сегодня."""
    now = datetime.now(ALMATY_TZ)

    # После 23:00 — запрос балансов если ещё не запрашивали сегодня
    if now.hour >= 23:
        state = load_state()
        last_req = state.get("last_request", "")
        today_str = now.strftime("%Y-%m-%d")
        if today_str not in last_req:
            try:
                from agents.finance_agent import format_summary, _load
                data = _load()
                summary = format_summary(data)
                state["pending_update"] = True
                state["last_request"] = now.isoformat()
                save_state(state)
                text = (
                    f"🌙 Добрый вечер! Время обновить балансы.\n\n"
                    f"Текущее состояние:\n{summary}\n\n"
                    f"Отправьте новые балансы текстом или голосовым.\n"
                    f"Пример: каспи 150000, халык 800000"
                )
                await context.bot.send_message(chat_id=OWNER_ID, text=text)
                logger.info("Запрос балансов отправлен при старте (пропущен 23:00)")
            except Exception as e:
                logger.error(f"Не удалось запросить балансы: {e}")

    # После 17:00 — запрос продажнику если ещё не отправляли
    if now.hour >= 17 and SALESPERSON_ID != 0:
        from agents.sales_agent import SalesConversation, reset_daily_state, is_submitted_today
        conv = SalesConversation()
        if not conv.is_active() and not is_submitted_today():
            reset_daily_state()
            conv.reset()
            msg = conv.start()
            try:
                await context.bot.send_message(chat_id=SALESPERSON_ID, text=msg)
                logger.info("Запрос продажнику отправлен при старте (пропущен 17:00)")
            except Exception as e:
                logger.error(f"Не удалось отправить запрос продажнику: {e}")

    # После 19:00 — отчёт продаж владельцу если данные уже есть
    if now.hour >= 19:
        from agents.sales_agent import is_submitted_today, daily_report
        if is_submitted_today():
            try:
                report = daily_report()
                await context.bot.send_message(chat_id=OWNER_ID, text=f"📊 Дневной отчёт по продажам:\n\n{report}")
                logger.info("Отчёт продаж отправлен при старте (пропущен 19:00)")
            except Exception as e:
                logger.error(f"Не удалось отправить отчёт: {e}")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")

    app = Application.builder().token(token).build()

    # Проверка пропущенных джобов через 30 сек после старта
    app.job_queue.run_once(on_startup, when=30, name="startup_check")

    # Курс USD/KZT: каждый день в 9:00
    app.job_queue.run_daily(
        auto_update_rate,
        time=time(9, 0, tzinfo=ALMATY_TZ),
        name="usd_rate_update"
    )

    # Балансы: 23:00 запрос, 12:00 повтор
    app.job_queue.run_daily(
        request_balances,
        time=time(23, 0, tzinfo=ALMATY_TZ),
        name="daily_balance_request"
    )
    app.job_queue.run_daily(
        reminder_balances,
        time=time(12, 0, tzinfo=ALMATY_TZ),
        name="balance_reminder"
    )

    # Продажи: 17:00 запрос у продажника
    app.job_queue.run_daily(
        request_sales_report,
        time=time(17, 0, tzinfo=ALMATY_TZ),
        name="sales_request"
    )
    # Каждые 30 мин: проверка зависшего диалога
    app.job_queue.run_repeating(
        check_stale_conversation,
        interval=1800,
        first=60,
        name="stale_conv_check"
    )

    # 19:00 отчёт владельцу или напоминание
    app.job_queue.run_daily(
        check_sales_19,
        time=time(19, 0, tzinfo=ALMATY_TZ),
        name="sales_check_19"
    )
    # 20:30 второе напоминание если нет данных
    app.job_queue.run_daily(
        remind_sales_2030,
        time=time(20, 30, tzinfo=ALMATY_TZ),
        name="sales_remind_2030"
    )
    # Еженедельный отчёт: понедельник 9:00
    app.job_queue.run_daily(
        weekly_sales_job,
        time=time(9, 0, tzinfo=ALMATY_TZ),
        days=(0,),
        name="weekly_sales"
    )
    # Ежемесячный отчёт: 1-е число 9:00
    app.job_queue.run_monthly(
        monthly_sales_job,
        when=time(9, 0, tzinfo=ALMATY_TZ),
        day=1,
        name="monthly_sales"
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("balances", cmd_balances))
    app.add_handler(CommandHandler("sales", cmd_sales))
    app.add_handler(CommandHandler("yearplan", cmd_yearplan))
    app.add_handler(CommandHandler("adddata", cmd_adddata))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен. Планировщик: 23:00 и 12:00 по Алматы.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
