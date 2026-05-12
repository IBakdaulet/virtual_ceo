"""
Sales Agent — сбор данных от продажника, отчёты, контроль плана.
Проекты: Grants KZ, Tanda Bilim, Ekonomist Media.
"""

import json
import os
import re
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import anthropic

DATA_FILE = Path(__file__).parent.parent / "data" / "sales.json"
STATE_FILE = Path(__file__).parent.parent / "data" / "salesperson_state.json"
HISTORICAL_FILE = Path(__file__).parent.parent / "data" / "historical_sales.json"
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PROJECTS = {
    "grants_kz": "Grants KZ",
    "tanda_bilim": "Tanda Bilim",
    "ekonomist_media": "Ekonomist Media",
}

SALESPERSON_PROMPT_TEMPLATE = """📊 Дневной отчёт — {date}

Привет! Пришли данные по каждому проекту.
Можно в свободном формате — разберу сам.

Нужно по каждому:
• Grants KZ
• Tanda Bilim
• Ekonomist Media

Для каждого:
— Выручка за день (оплаченные сделки, ₸)
— Звонков / встреч
— Сделок закрыто
— Pipeline (общая сумма всех активных переговоров)
— Активные переговоры: Клиент — сумма

Пример:
Grants KZ: выручка 200к, 3 сделки, 15 звонков, pipeline 1.2М
Активные: Самрук 300к, Нурбанк 150к, ещё 2 без суммы"""


def _load() -> dict:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_request_message() -> str:
    today = date.today().strftime("%d.%m.%Y")
    return SALESPERSON_PROMPT_TEMPLATE.format(date=today)


def get_reminder_message(attempt: int = 1) -> str:
    projects = ", ".join(PROJECTS.values())
    if attempt == 1:
        return (
            f"⏰ Напоминание: жду дневной отчёт по продажам.\n"
            f"Нужно заполнить по всем проектам: {projects}.\n"
            f"Напиши мне и я спрошу по порядку."
        )
    return (
        f"🔔 Последнее напоминание: отчёт по продажам до сих пор не заполнен.\n"
        f"Проекты: {projects}.\n"
        f"Напиши мне любое сообщение — начнём прямо сейчас."
    )


def parse_sales_report(text: str) -> List[Dict]:
    """Claude извлекает структурированные данные из свободного текста продажника."""
    prompt = f"""Из этого отчёта продажника извлеки данные по каждому проекту.

Текст: "{text}"

Проекты (используй точно эти ключи):
- grants_kz (Grants KZ, Гранты)
- tanda_bilim (Tanda Bilim, Танда)
- ekonomist_media (Ekonomist Media, Экономист)

Верни JSON массив по каждому упомянутому проекту:
[
  {{
    "project": "grants_kz",
    "revenue": 200000,
    "deals_closed": 3,
    "calls_made": 15,
    "pipeline_total": 1200000,
    "active_negotiations": [
      {{"client": "Самрук", "amount": 300000}},
      {{"client": "Нурбанк", "amount": 150000}}
    ],
    "notes": ""
  }}
]

Правила:
- revenue: деньги реально закрытых/оплаченных сделок за сегодня
- pipeline_total: общая сумма ВСЕХ активных переговоров
- active_negotiations: список клиентов (amount=0 если сумма не указана)
- "200к" = 200000, "1.2М" = 1200000, "миллион" = 1000000
- Если проект не упомянут — не включай
- Только JSON без текста"""

    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = resp.content[0].text.strip()
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group())
    except Exception:
        return []


def save_entries(entries: List[Dict]) -> int:
    data = _load()
    today = date.today().isoformat()

    for entry in entries:
        entry["date"] = today
        data["entries"] = [
            e for e in data["entries"]
            if not (e["date"] == today and e["project"] == entry["project"])
        ]
        data["entries"].append(entry)

    data["daily_state"]["submitted_today"] = True
    data["daily_state"]["submitted_date"] = today
    _save(data)
    return len(entries)


def is_submitted_today() -> bool:
    data = _load()
    today = date.today().isoformat()
    state = data.get("daily_state", {})
    return state.get("submitted_today") and state.get("submitted_date") == today


def reset_daily_state():
    data = _load()
    data["daily_state"]["submitted_today"] = False
    data["daily_state"]["submitted_date"] = None
    _save(data)


def _get_month_plan(data: dict, year_month: str, project: str) -> float:
    plans = data.get("monthly_plans", {})
    if year_month in plans and project in plans[year_month]:
        return plans[year_month][project]
    return data["projects"].get(project, {}).get("monthly_plan", 0)


def _month_revenue(data: dict, project: str, year_month: str, up_to: date) -> float:
    """Сумма продаж за месяц — берём paid_clients из последней записи (кумулятивный список)."""
    month_start = date(int(year_month[:4]), int(year_month[5:7]), 1).isoformat()
    up_to_str = up_to.isoformat()
    month_entries = sorted(
        [e for e in data["entries"]
         if e.get("project") == project
         and month_start <= e.get("date", "") <= up_to_str],
        key=lambda e: e.get("date", "")
    )
    if not month_entries:
        return 0.0
    latest = month_entries[-1]
    # Если есть paid_clients — суммируем их (кумулятивный список за месяц)
    paid = latest.get("paid_clients", [])
    if paid:
        return sum(c.get("amount", 0) for c in paid)
    # Fallback: сумма дневных revenue
    return sum(e.get("revenue", 0) for e in month_entries)


def daily_report(target_date: Optional[date] = None) -> str:
    data = _load()
    target_date = target_date or date.today()
    today_str = target_date.isoformat()

    entries = [e for e in data["entries"] if e.get("date") == today_str]
    if not entries:
        return f"📊 Данных по продажам за {target_date.strftime('%d.%m.%Y')} нет."

    year_month = target_date.strftime("%Y-%m")
    day = target_date.day
    days_in_month = monthrange(target_date.year, target_date.month)[1]

    lines = [f"📊 ПРОДАЖИ — {target_date.strftime('%d.%m.%Y')}", "─" * 30]
    total_revenue = 0
    total_pipeline = 0

    for project_key, project_name in PROJECTS.items():
        proj = next((e for e in entries if e["project"] == project_key), None)
        if not proj:
            continue

        revenue = proj.get("revenue", 0)
        pipeline = proj.get("pipeline_total", 0)
        total_revenue += revenue
        total_pipeline += pipeline

        month_rev = _month_revenue(data, project_key, year_month, target_date)
        plan = _get_month_plan(data, year_month, project_key)
        expected = plan * day / days_in_month if plan else 0
        pace_pct = month_rev / expected * 100 if expected else 0
        plan_pct = month_rev / plan * 100 if plan else 0

        icon = "✅" if pace_pct >= 100 else ("⚠️" if pace_pct >= 75 else "🚨")

        lines.append(f"\n{icon} {project_name}")
        lines.append(f"  Выручка сегодня: {revenue:,.0f} ₸")
        lines.append(f"  Сделок закрыто: {proj.get('deals_closed', 0)}")
        lines.append(f"  Pipeline: {pipeline:,.0f} ₸")

        if proj.get("paid_clients"):
            lines.append("  Оплатили в этом месяце:")
            for c in proj["paid_clients"]:
                amt = c.get("amount", 0)
                amt_str = f" — {amt:,.0f} ₸" if amt else ""
                lines.append(f"    ✅ {c['client']}{amt_str}")

        if proj.get("active_negotiations"):
            lines.append("  Активные переговоры:")
            for neg in proj["active_negotiations"]:
                amt = neg.get("amount", 0)
                amt_str = f" — {amt:,.0f} ₸" if amt else ""
                lines.append(f"    • {neg['client']}{amt_str}")

        if plan:
            lines.append(f"  За месяц: {month_rev:,.0f} / {plan:,.0f} ₸ ({plan_pct:.0f}%)")
            deviation = month_rev - expected
            sign = "+" if deviation >= 0 else ""
            lines.append(f"  Темп: {pace_pct:.0f}% {icon}  (отклонение {sign}{deviation:,.0f} ₸)")

        if proj.get("notes"):
            lines.append(f"  Заметки: {proj['notes']}")

    lines.append(f"\n{'─' * 30}")
    lines.append(f"Итого за день: {total_revenue:,.0f} ₸")
    lines.append(f"Общий pipeline: {total_pipeline:,.0f} ₸")
    return "\n".join(lines)


def weekly_report() -> str:
    data = _load()
    today = date.today()
    week_start = today - timedelta(days=6)

    lines = [f"📅 ПРОДАЖИ ЗА НЕДЕЛЮ ({week_start.strftime('%d.%m')} — {today.strftime('%d.%m.%Y')})", "─" * 30]
    total_week = 0

    for project_key, project_name in PROJECTS.items():
        proj_entries = [
            e for e in data["entries"]
            if e["project"] == project_key
            and week_start.isoformat() <= e.get("date", "") <= today.isoformat()
        ]
        if not proj_entries:
            continue

        revenue = sum(e.get("revenue", 0) for e in proj_entries)
        deals = sum(e.get("deals_closed", 0) for e in proj_entries)
        pipeline = max((e.get("pipeline_total", 0) for e in proj_entries), default=0)
        total_week += revenue

        year_month = today.strftime("%Y-%m")
        plan = _get_month_plan(data, year_month, project_key)
        week_plan = plan / 4 if plan else 0
        pct = revenue / week_plan * 100 if week_plan else 0
        icon = "✅" if pct >= 100 else ("⚠️" if pct >= 75 else "🚨")

        lines.append(f"\n{icon} {project_name}")
        lines.append(f"  Выручка: {revenue:,.0f} ₸" + (f" / {week_plan:,.0f} ₸ ({pct:.0f}%)" if week_plan else ""))
        lines.append(f"  Сделок: {deals}")
        lines.append(f"  Pipeline: {pipeline:,.0f} ₸")

        best = max(proj_entries, key=lambda e: e.get("revenue", 0))
        if best.get("revenue", 0) > 0:
            best_day = date.fromisoformat(best["date"]).strftime("%d.%m")
            lines.append(f"  Лучший день: {best_day} — {best['revenue']:,.0f} ₸")

    lines.append(f"\n{'─' * 30}")
    lines.append(f"Итого за неделю: {total_week:,.0f} ₸")
    return "\n".join(lines)


def monthly_report(year_month: Optional[str] = None) -> str:
    data = _load()
    today = date.today()
    year_month = year_month or today.strftime("%Y-%m")
    year, month = map(int, year_month.split("-"))
    month_start = date(year, month, 1)
    days_in_month = monthrange(year, month)[1]
    month_end = date(year, month, days_in_month)
    up_to = min(month_end, today)

    month_label = month_start.strftime("%B %Y")
    lines = [f"🗓 ПРОДАЖИ — {month_label}", "─" * 30]
    total_rev = 0
    total_plan = 0

    for project_key, project_name in PROJECTS.items():
        revenue = _month_revenue(data, project_key, year_month, up_to)
        plan = _get_month_plan(data, year_month, project_key)
        total_rev += revenue
        total_plan += plan

        proj_entries = [
            e for e in data["entries"]
            if e["project"] == project_key
            and month_start.isoformat() <= e.get("date", "") <= up_to.isoformat()
        ]
        deals = sum(e.get("deals_closed", 0) for e in proj_entries)

        pct = revenue / plan * 100 if plan else 0
        icon = "✅" if pct >= 100 else ("⚠️" if pct >= 70 else "🚨")

        expected = plan * today.day / days_in_month if plan else 0
        deviation = revenue - expected
        sign = "+" if deviation >= 0 else ""

        lines.append(f"\n{icon} {project_name}")
        lines.append(f"  Выручка: {revenue:,.0f} / {plan:,.0f} ₸ ({pct:.0f}%)")
        lines.append(f"  Сделок: {deals}  |  Рабочих дней: {len(proj_entries)}")
        if plan:
            lines.append(f"  Отклонение от темпа: {sign}{deviation:,.0f} ₸")

    lines.append(f"\n{'─' * 30}")
    total_pct = total_rev / total_plan * 100 if total_plan else 0
    lines.append(f"Итого: {total_rev:,.0f} / {total_plan:,.0f} ₸ ({total_pct:.0f}%)")
    return "\n".join(lines)


def set_plan(project_key: str, amount: float, year_month: Optional[str] = None) -> str:
    data = _load()
    year_month = year_month or date.today().strftime("%Y-%m")
    if "monthly_plans" not in data:
        data["monthly_plans"] = {}
    if year_month not in data["monthly_plans"]:
        data["monthly_plans"][year_month] = {}
    data["monthly_plans"][year_month][project_key] = amount
    _save(data)
    name = PROJECTS.get(project_key, project_key)
    return f"✅ План установлен: {name} — {amount:,.0f} ₸ ({year_month})"


def _parse_amount(text: str) -> float:
    """Парсит сумму: 200к→200000, 1.2М→1200000, нет→0."""
    t = text.strip().lower()
    if t in ["нет", "0", "не было", "-", "без", "пусто", "ничего"]:
        return 0.0
    t = t.replace(" ", "").replace(",", ".")
    m = re.match(r"([\d.]+)м", t)
    if m:
        return float(m.group(1)) * 1_000_000
    m = re.match(r"([\d.]+)к", t)
    if m:
        return float(m.group(1)) * 1_000
    m = re.match(r"[\d.]+", t)
    if m:
        return float(m.group())
    return 0.0


def _parse_count(text: str) -> int:
    """Парсит целое число: 15, нет→0."""
    t = text.strip().lower()
    if t in ["нет", "0", "не было", "-", "без", "ничего"]:
        return 0
    m = re.search(r"\d+", t)
    return int(m.group()) if m else 0


def _parse_negotiations(text: str) -> List[Dict]:
    """Claude извлекает список клиентов с суммами."""
    if text.strip().lower() in ["нет", "-", "без", "нету", "0", "пусто", "ничего"]:
        return []
    prompt = f"""Из текста извлеки список активных переговоров (клиент + сумма).

Текст: "{text}"

Верни JSON массив:
[{{"client": "Самрук", "amount": 300000}}, {{"client": "Нурбанк", "amount": 0}}]

"300к" = 300000, "1.2М" = 1200000, если суммы нет — 0.
Только JSON."""
    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = resp.content[0].text.strip()
    m = re.search(r'\[.*\]', raw, re.DOTALL)
    if not m:
        return [{"client": text.strip(), "amount": 0}]
    try:
        return json.loads(m.group())
    except Exception:
        return []


class SalesConversation:
    """Пошаговый диалог с продажником для сбора дневного отчёта."""

    STEPS = ["revenue", "paid_clients", "deals", "pipeline", "negotiations"]

    QUESTIONS = {
        "revenue": (
            "💰 {name} — выручка за сегодня?\n"
            "Сколько денег реально поступило на счёт сегодня.\n"
            "Пример: 350к  или  1.2М  или  0"
        ),
        "paid_clients": (
            "🧾 Кто оплатил в этом месяце?\n"
            "Перечисли ВСЕХ клиентов кто заплатил за текущий месяц и суммы.\n"
            "Пример: Самрук 500к, Нурбанк 300к, ТОО Альфа 150к\n"
            "Если никто — напиши нет"
        ),
        "deals": (
            "🤝 Сделок закрыто сегодня?\n"
            "Количество договоров подписанных сегодня.\n"
            "Пример: 3  или  0"
        ),
        "pipeline": (
            "📋 Общий pipeline?\n"
            "Суммируй ВСЕ переговоры которые сейчас в работе (не только сегодняшние).\n"
            "Пример: 2.5М  или  800к  или  0"
        ),
        "negotiations": (
            "👥 Активные переговоры — назови клиентов:\n"
            "Все с кем сейчас ведёшь переговоры + примерная сумма.\n"
            "Пример: Самрук 300к, Нурбанк 150к, Казтелеком (без суммы)\n"
            "Если нет — напиши нет"
        ),
    }

    def _load_state(self) -> dict:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_state(self, state: dict):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def is_stale(self, max_minutes: int = 120) -> bool:
        """Проверяет завис ли диалог дольше max_minutes."""
        state = self._load_state()
        if not state.get("active") or not state.get("started_at"):
            return False
        from datetime import datetime as dt
        started = dt.fromisoformat(state["started_at"])
        elapsed = (dt.now() - started).total_seconds() / 60
        return elapsed > max_minutes

    def start(self) -> str:
        """Начинает диалог по всем трём проектам сразу."""
        today = date.today().strftime("%d.%m.%Y")
        from datetime import datetime as dt
        state = {
            "active": True,
            "step": self.STEPS[0],
            "project_index": 0,
            "active_projects": list(PROJECTS.keys()),
            "temp_data": {},
            "started_at": dt.now().isoformat()
        }
        self._save_state(state)
        total = len(PROJECTS)
        return (
            f"📊 Дневной отчёт — {today}\n"
            f"Заполни по всем {total} проектам. Начинаем!\n\n"
            + self._ask_current(state)
        )

    def process_answer(self, text: str) -> tuple:
        """
        Обрабатывает ответ на текущий вопрос.
        Возвращает (следующий вопрос, клавиатура или None, is_done).
        """
        state = self._load_state()
        step = state["step"]
        proj_key = state["active_projects"][state["project_index"]]

        if proj_key not in state["temp_data"]:
            state["temp_data"][proj_key] = {}

        if step == "revenue":
            state["temp_data"][proj_key]["revenue"] = _parse_amount(text)
        elif step == "paid_clients":
            state["temp_data"][proj_key]["paid_clients"] = _parse_negotiations(text)
        elif step == "calls":
            state["temp_data"][proj_key]["calls_made"] = _parse_count(text)
        elif step == "deals":
            state["temp_data"][proj_key]["deals_closed"] = _parse_count(text)
        elif step == "pipeline":
            state["temp_data"][proj_key]["pipeline_total"] = _parse_amount(text)
        elif step == "negotiations":
            state["temp_data"][proj_key]["active_negotiations"] = _parse_negotiations(text)

        # Переходим к следующему шагу
        step_idx = self.STEPS.index(step)
        if step_idx + 1 < len(self.STEPS):
            state["step"] = self.STEPS[step_idx + 1]
        else:
            # Переходим к следующему проекту
            state["project_index"] += 1
            if state["project_index"] < len(state["active_projects"]):
                state["step"] = self.STEPS[0]
            else:
                # Всё собрали
                state["active"] = False
                self._save_state(state)
                entries = self._build_entries(state)
                save_entries(entries)
                return "✅ Отлично! Всё записал. Спасибо!", None, True

        self._save_state(state)
        return self._ask_current(state), None, False

    def _ask_current(self, state: dict) -> str:
        proj_key = state["active_projects"][state["project_index"]]
        proj_name = PROJECTS[proj_key]
        step = state["step"]
        total = len(state["active_projects"])
        idx = state["project_index"] + 1
        progress = f"[{idx}/{total}] " if total > 1 else ""
        return f"{progress}{self.QUESTIONS[step].format(name=proj_name)}"

    def _build_entries(self, state: dict) -> List[Dict]:
        return [
            {"project": key, **vals}
            for key, vals in state["temp_data"].items()
        ]

    def is_active(self) -> bool:
        state = self._load_state()
        return state.get("active", False)

    def reset(self):
        self._save_state({
            "active": False, "step": None,
            "project_index": 0, "active_projects": [], "temp_data": {}
        })


def save_historical_data(year: int, raw_text: str):
    """Сохраняет сырые данные за год в historical_sales.json."""
    with open(HISTORICAL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if str(year) not in data["years"]:
        data["years"][str(year)] = []
    data["years"][str(year)].append(raw_text)
    with open(HISTORICAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def query_historical_year(year: int) -> str:
    """Возвращает анализ исторических данных за год через Claude."""
    with open(HISTORICAL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Ищем данные: сначала точно по году, потом во всех блоках
    year_data = data["years"].get(str(year))
    if not year_data:
        # Ищем упоминание года во всех блоках
        all_blocks = []
        for blocks in data["years"].values():
            all_blocks.extend(blocks)
        year_data = [b for b in all_blocks if str(year) in b]

    if not year_data:
        return f"Данных за {year} год нет. Загрузи их через /yearplan."

    combined = "\n\n---\n\n".join(year_data)

    prompt = f"""Проанализируй данные продаж за {year} год по проектам Grants KZ, Tanda Bilim, Ekonomist Media.

ДАННЫЕ:
{combined}

Выведи структурированный отчёт:

📊 ПРОДАЖИ {year} ГОДА

По каждому проекту:
— Помесячная выручка (таблица)
— Итого за год
— Лучший и худший месяц
— Средняя выручка в месяц

📈 ОБЩИЙ ИТОГ {year}:
— Все проекты суммарно
— Динамика по кварталам (Q1/Q2/Q3/Q4)
— Ключевые наблюдения

Русский язык, суммы в тенге (₸)."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def generate_annual_plan(historical_text: str, target_year: int) -> str:
    """Claude анализирует исторические данные и генерирует годовой план продаж."""
    prompt = f"""Ты — старший аналитик продаж медиа-холдинга в Казахстане.

ИСТОРИЧЕСКИЕ ДАННЫЕ КОМПАНИИ:
{historical_text}

ПРОЕКТЫ:
- Grants KZ: агрегатор зарубежных грантов и стипендий, монетизация — реклама в Instagram и Telegram. Аудитория: казахстанская молодёжь 18-30 лет.
- Tanda Bilim: образовательный видеоконтент по истории Казахстана, монетизация — реклама в Instagram.
- Ekonomist Media: деловые медиа об экономике Казахстана, молодой проект, монетизация в стадии развития.

ЗАДАЧА: Составь детальный план продаж на {target_year} год по месяцам для каждого проекта.

ОБЯЗАТЕЛЬНО учти:
1. Сезонность казахстанского рынка рекламы (Q1 — низкий сезон после Нового года, март-апрель — рост, лето — спад, сентябрь-декабрь — пик)
2. Сезонность по грантам (дедлайны грантов: январь-март и сентябрь-ноябрь — пиковый интерес)
3. Тренды рынка: рост EdTech и цифровых медиа в Казахстане, рост рынка Instagram-рекламы
4. Исторические темпы роста компании из данных выше
5. Реалистичный, но амбициозный рост

ФОРМАТ ОТВЕТА:

📊 ГОДОВОЙ ПЛАН ПРОДАЖ — {target_year}
(анализ на основе исторических данных + тренды рынка)

━━━━━━━━━━━━━━━━━━━━
🎯 GRANTS KZ
━━━━━━━━━━━━━━━━━━━━
Янв: X ₸    Фев: X ₸    Мар: X ₸
Апр: X ₸    Май: X ₸    Июн: X ₸
Июл: X ₸    Авг: X ₸    Сен: X ₸
Окт: X ₸    Ноя: X ₸    Дек: X ₸
Итого: X ₸  |  Рост: +X% к прошлому году
Обоснование: [2-3 предложения почему такие цифры]

━━━━━━━━━━━━━━━━━━━━
🎯 TANDA BILIM
━━━━━━━━━━━━━━━━━━━━
[аналогично]

━━━━━━━━━━━━━━━━━━━━
🎯 EKONOMIST MEDIA
━━━━━━━━━━━━━━━━━━━━
[аналогично]

━━━━━━━━━━━━━━━━━━━━
📈 ОБЩИЙ ИТОГ {target_year}
━━━━━━━━━━━━━━━━━━━━
Все проекты: X ₸
Рост к прошлому году: +X%
Лучший квартал: Q?
Сложный период: [месяц] — стратегия на этот период

💡 КЛЮЧЕВЫЕ РИСКИ И РЕКОМЕНДАЦИИ:
1. ...
2. ...
3. ...

Отвечай только на русском языке. Все суммы в тенге (₸)."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system="Ты — аналитик продаж медиа-компании в Казахстане. Давай конкретные, обоснованные цифры. Только факты и аналитика.",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def save_annual_plan_as_targets(plan_text: str, target_year: int) -> str:
    """Парсит план и сохраняет как месячные цели в sales.json."""
    prompt = f"""Из этого текста планa продаж извлеки месячные цифры по каждому проекту.

{plan_text}

Верни JSON:
{{
  "{target_year}-01": {{"grants_kz": 1500000, "tanda_bilim": 1200000, "ekonomist_media": 300000}},
  "{target_year}-02": {{"grants_kz": 1600000, "tanda_bilim": 1300000, "ekonomist_media": 350000}},
  ...до декабря
}}

Только JSON, без текста."""

    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = resp.content[0].text.strip()
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        return "Не удалось сохранить план автоматически."

    try:
        monthly_targets = json.loads(match.group())
        data = _load()
        if "monthly_plans" not in data:
            data["monthly_plans"] = {}
        data["monthly_plans"].update(monthly_targets)
        _save(data)
        months_saved = len(monthly_targets)
        return f"✅ План сохранён как цели на {months_saved} месяцев {target_year} года."
    except Exception as e:
        return f"Ошибка сохранения плана: {e}"


class SalesAgent:
    def run(self, task: str) -> str:
        task_lower = task.lower().strip()

        if any(w in task_lower for w in ["месяц", "monthly", "ежемесяч"]):
            return monthly_report()
        if any(w in task_lower for w in ["недел", "weekly"]):
            return weekly_report()
        if any(w in task_lower for w in ["день", "сегодня", "дневн"]):
            return daily_report()

        return daily_report()
