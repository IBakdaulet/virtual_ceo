"""
Finance Agent — личный финансовый советник Ибакдаулета.
Хранит состояние счетов, анализирует расходы, ставит цели, даёт рекомендации.
"""

import json
import os
import anthropic
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_FILE = Path(__file__).parent.parent / "data" / "finance.json"
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

ACCOUNT_ALIASES = {
    "kaspi": "kaspi_card",
    "kaspi карта": "kaspi_card",
    "каспи": "kaspi_card",
    "каспи карта": "kaspi_card",
    "kaspi депозит usd": "kaspi_deposit_usd",
    "каспи депозит доллар": "kaspi_deposit_usd",
    "каспи usd": "kaspi_deposit_usd",
    "kaspi grants": "kaspi_deposit_grants",
    "каспи грантс": "kaspi_deposit_grants",
    "грантс депозит": "kaspi_deposit_grants",
    "halyk": "halyk_card",
    "халык": "halyk_card",
    "халык карта": "halyk_card",
    "halyk usd": "halyk_deposit_usd",
    "халык доллар": "halyk_deposit_usd",
    "халык депозит доллар": "halyk_deposit_usd",
    "halyk kzt": "halyk_deposit_kzt",
    "халык тенге": "halyk_deposit_kzt",
    "халык депозит тенге": "halyk_deposit_kzt",
    "freedom": "freedom_card",
    "фридом": "freedom_card",
    "фридом карта": "freedom_card",
    "freedom invest": "freedom_invest",
    "фридом инвест": "freedom_invest",
}


def _load() -> dict:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_usd_rate() -> float:
    """Получает актуальный курс USD/KZT с open.er-api.com."""
    import urllib.request
    url = "https://open.er-api.com/v6/latest/USD"
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.loads(r.read())
    return round(data["rates"]["KZT"], 2)


def update_usd_rate() -> str:
    """Обновляет курс в finance.json и возвращает строку с результатом."""
    try:
        rate = fetch_usd_rate()
        data = _load()
        old = data.get("usd_to_kzt_rate", 0)
        data["usd_to_kzt_rate"] = rate
        _save(data)
        diff = rate - old
        sign = "+" if diff >= 0 else ""
        return f"✅ Курс обновлён: 1 USD = {rate} ₸ ({sign}{diff:.1f} ₸)"
    except Exception as e:
        return f"Не удалось получить курс: {e}"


def _save(data: dict):
    data["last_updated"] = datetime.now().isoformat()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _push_to_github(DATA_FILE, "data/finance.json")


def _push_to_github(file_path: Path, repo_path: str):
    """Пушит файл в GitHub чтобы данные не терялись при редеплое."""
    import base64, httpx
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return
    url = f"https://api.github.com/repos/IBakdaulet/virtual_ceo/contents/{repo_path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    try:
        resp = httpx.get(url, headers=headers, timeout=10)
        sha = resp.json().get("sha", "")
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        encoded = base64.b64encode(content.encode()).decode()
        httpx.put(url, headers=headers, json={
            "message": f"update: {repo_path} via bot",
            "content": encoded,
            "sha": sha,
        }, timeout=10)
    except Exception:
        pass


def get_total_in_kzt(data: dict) -> dict:
    """Считает общий капитал в KZT."""
    rate = data.get("usd_to_kzt_rate", 510)
    total_kzt = 0
    total_usd = 0
    breakdown = []

    for key, acc in data["accounts"].items():
        bal = acc["balance"]
        cur = acc["currency"]
        if cur == "USD":
            kzt_val = bal * rate
            total_usd += bal
        else:
            kzt_val = bal
        total_kzt += kzt_val
        breakdown.append({
            "name": acc["name"],
            "balance": bal,
            "currency": cur,
            "kzt_equivalent": kzt_val
        })

    return {
        "total_kzt": total_kzt,
        "total_usd_accounts": total_usd,
        "usd_rate": rate,
        "breakdown": breakdown
    }


def format_summary(data: dict) -> str:
    """Форматирует текущее состояние счетов."""
    totals = get_total_in_kzt(data)
    rate = totals["usd_rate"]
    lines = ["💰 *Состояние счетов*\n"]

    cards = [a for a in totals["breakdown"] if data["accounts"].get(
        next((k for k, v in data["accounts"].items() if v["name"] == a["name"]), ""), {}).get("type") in ["card", None]]

    kzt_accounts = [a for a in totals["breakdown"] if a["currency"] == "KZT"]
    usd_accounts = [a for a in totals["breakdown"] if a["currency"] == "USD"]

    lines.append("*Тенговые счета:*")
    for a in kzt_accounts:
        lines.append(f"  {a['name']}: {a['balance']:,.0f} ₸")

    lines.append("\n*Долларовые счета:*")
    for a in usd_accounts:
        lines.append(f"  {a['name']}: ${a['balance']:,.0f} ({a['kzt_equivalent']:,.0f} ₸)")

    lines.append(f"\n*Итого (по курсу {rate} ₸/$):*")
    lines.append(f"  В тенге: {totals['total_kzt']:,.0f} ₸")
    lines.append(f"  В долларах: ~${totals['total_kzt']/rate:,.0f}")

    change = get_monthly_change()
    if change:
        diff = change["diff"]
        sign = "+" if diff >= 0 else ""
        icon = "📈" if diff >= 0 else "📉"
        lines.append(f"\n{icon} За месяц: {sign}{diff:,.0f} ₸ (с {change['date']})")

    if data.get("last_updated"):
        dt = datetime.fromisoformat(data["last_updated"])
        lines.append(f"\n_Обновлено: {dt.strftime('%d.%m.%Y %H:%M')}_")

    return "\n".join(lines)


def format_business(data: dict) -> str:
    """Форматирует бизнес-доходы."""
    lines = ["📊 *Бизнес-доходы (ежемесячно)*\n"]
    total_my_share = 0
    for key, biz in data["business"].items():
        rev = biz["monthly_revenue"]
        share = biz["my_share_pct"]
        my_income = rev * share / 100
        total_my_share += my_income
        lines.append(f"*{biz['name']}* ({share}%)")
        lines.append(f"  Выручка: {rev:,.0f} ₸ → Ваша доля: {my_income:,.0f} ₸")
    lines.append(f"\n*Итого ваш доход: {total_my_share:,.0f} ₸/мес*")
    return "\n".join(lines)


SNAPSHOTS_FILE = Path(__file__).parent.parent / "data" / "balance_snapshots.json"


def save_monthly_snapshot(data: dict):
    """Сохраняет снапшот балансов с текущей датой."""
    if SNAPSHOTS_FILE.exists():
        with open(SNAPSHOTS_FILE, "r", encoding="utf-8") as f:
            snapshots = json.load(f)
    else:
        snapshots = []

    totals = get_total_in_kzt(data)
    snapshots.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_kzt": totals["total_kzt"],
        "usd_rate": totals["usd_rate"],
    })
    # Храним только последние 24 снапшота
    snapshots = snapshots[-24:]
    with open(SNAPSHOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshots, f, ensure_ascii=False, indent=2)


def get_monthly_change() -> Optional[dict]:
    """Возвращает изменение за ~30 дней или None если нет данных."""
    if not SNAPSHOTS_FILE.exists():
        return None
    with open(SNAPSHOTS_FILE, "r", encoding="utf-8") as f:
        snapshots = json.load(f)
    if len(snapshots) < 2:
        return None
    # Берём снапшот ~30 дней назад
    from datetime import date as _date, timedelta
    target = (_date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    old = None
    for s in snapshots:
        if s["date"] <= target:
            old = s
    if not old:
        old = snapshots[0]
    current = snapshots[-1]
    diff = current["total_kzt"] - old["total_kzt"]
    return {"old": old["total_kzt"], "current": current["total_kzt"],
            "diff": diff, "date": old["date"]}


def update_balance(account_key: str, new_balance: float, data: dict) -> str:
    """Обновляет баланс счёта."""
    if account_key not in data["accounts"]:
        return f"Счёт '{account_key}' не найден."
    old = data["accounts"][account_key]["balance"]
    data["accounts"][account_key]["balance"] = new_balance
    diff = new_balance - old
    sign = "+" if diff >= 0 else ""
    data["last_updated"] = datetime.now().isoformat()
    _save(data)
    save_monthly_snapshot(data)
    name = data["accounts"][account_key]["name"]
    return f"✅ {name}: {old:,.0f} → {new_balance:,.0f} ({sign}{diff:,.0f})"


def add_goal(goal_text: str, data: dict) -> str:
    """Добавляет финансовую цель."""
    goal = {
        "id": len(data["goals"]) + 1,
        "text": goal_text,
        "created": datetime.now().isoformat(),
        "status": "active"
    }
    data["goals"].append(goal)
    _save(data)
    return f"🎯 Цель зафиксирована: {goal_text}"


def list_goals(data: dict) -> str:
    """Показывает список целей."""
    active = [g for g in data["goals"] if g["status"] == "active"]
    if not active:
        return "Финансовые цели пока не заданы. Напишите 'Цель: ...' чтобы добавить."
    lines = ["🎯 *Ваши финансовые цели:*\n"]
    for g in active:
        lines.append(f"{g['id']}. {g['text']}")
    return "\n".join(lines)


def ai_analysis(task: str, data: dict) -> str:
    """Глубокий анализ и рекомендации через Claude."""
    totals = get_total_in_kzt(data)
    goals = [g["text"] for g in data["goals"] if g["status"] == "active"]

    context = f"""Финансовое состояние Ибакдаулета (казахстанский медиа-предприниматель):

СЧЕТА:
{json.dumps(data["accounts"], ensure_ascii=False, indent=2)}

КУРС: 1 USD = {data['usd_to_kzt_rate']} KZT
ИТОГО: ~{totals['total_kzt']:,.0f} ₸ (~${totals['total_kzt']/data['usd_to_kzt_rate']:,.0f})

БИЗНЕС-ДОХОДЫ (ежемесячно, доля владельца):
{json.dumps(data["business"], ensure_ascii=False, indent=2)}

ФИНАНСОВЫЕ ЦЕЛИ:
{chr(10).join(goals) if goals else 'Не заданы'}

ЗАДАЧА: {task}"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        system="""Ты — личный финансовый советник казахстанского предпринимателя Ибакдаулета.
Давай конкретные, персонализированные рекомендации на русском языке.
Учитывай казахстанский контекст (KZT, USD, местные банки).
Будь прямым и полезным. Без воды.""",
        messages=[{"role": "user", "content": context}]
    )
    return response.content[0].text


PERIOD_NAMES = {"день": "daily", "неделя": "weekly", "неделю": "weekly", "месяц": "monthly",
                "daily": "daily", "weekly": "weekly", "monthly": "monthly"}

CATEGORY_ALIASES = {
    "еда": "еда и рестораны", "рестораны": "еда и рестораны", "продукты": "еда и рестораны",
    "транспорт": "транспорт", "такси": "транспорт",
    "развлечения": "развлечения", "отдых": "развлечения",
    "здоровье": "здоровье", "аптека": "здоровье", "спорт": "здоровье",
    "одежда": "одежда и шоппинг", "шоппинг": "одежда и шоппинг",
    "образование": "образование", "курсы": "образование",
    "бизнес": "бизнес расходы", "реклама": "бизнес расходы",
    "переводы": "переводы",
    "коммуналка": "коммуналка", "связь": "коммуналка",
    "другое": "другое",
}


def set_limit(period: str, category: str, amount: float, data: dict) -> str:
    """Устанавливает лимит расходов по категории и периоду."""
    if "limits" not in data:
        data["limits"] = {"daily": {}, "weekly": {}, "monthly": {}}
    cat = CATEGORY_ALIASES.get(category.lower(), category.lower())
    data["limits"][period][cat] = amount
    _save(data)
    period_ru = {"daily": "день", "weekly": "неделю", "monthly": "месяц"}
    return f"✅ Лимит установлен: {cat} — {amount:,.0f} ₸ в {period_ru[period]}"


def show_limits(data: dict) -> str:
    """Показывает все установленные лимиты."""
    limits = data.get("limits", {})
    if not any(limits.get(p) for p in ["daily", "weekly", "monthly"]):
        return "Лимиты не заданы. Напишите: лимит еда месяц 150000"

    period_ru = {"daily": "📅 День", "weekly": "📆 Неделя", "monthly": "🗓 Месяц"}
    lines = ["💳 Лимиты расходов по категориям:\n"]
    for period, label in period_ru.items():
        cats = limits.get(period, {})
        if cats:
            lines.append(f"{label}:")
            for cat, amt in cats.items():
                lines.append(f"  • {cat}: {amt:,.0f} ₸")
    return "\n".join(lines)


def check_limits_against_statement(categories_spent: dict, data: dict) -> str:
    """Проверяет расходы из выписки против месячных лимитов."""
    limits = data.get("limits", {}).get("monthly", {})
    if not limits:
        return ""

    warnings = []
    for cat, spent in categories_spent.items():
        cat_lower = cat.lower()
        limit = limits.get(cat_lower)
        if limit:
            pct = spent / limit * 100
            if pct >= 100:
                warnings.append(f"🚨 {cat}: потрачено {spent:,.0f} ₸ — ПРЕВЫШЕН лимит {limit:,.0f} ₸ ({pct:.0f}%)")
            elif pct >= 80:
                warnings.append(f"⚠️ {cat}: потрачено {spent:,.0f} ₸ — {pct:.0f}% от лимита {limit:,.0f} ₸")

    if not warnings:
        return ""
    return "\n\n⚡ ПРЕДУПРЕЖДЕНИЯ ПО ЛИМИТАМ:\n" + "\n".join(warnings)


class FinanceAgent:
    def run(self, task: str) -> str:
        data = _load()
        task_lower = task.lower().strip()

        # Обновление баланса: "kaspi 150000" или "халык карта 52000"
        for alias, key in ACCOUNT_ALIASES.items():
            if task_lower.startswith(alias):
                remainder = task_lower[len(alias):].strip()
                # Извлекаем число
                import re
                numbers = re.findall(r"[\d\s]+(?:[.,]\d+)?", remainder)
                if numbers:
                    num_str = numbers[0].replace(" ", "").replace(",", ".")
                    try:
                        new_balance = float(num_str)
                        return update_balance(key, new_balance, data)
                    except ValueError:
                        pass

        # Лимиты: "лимит еда месяц 150000"
        if task_lower.startswith("лимит"):
            import re
            # Показать лимиты
            if any(w in task_lower for w in ["покажи", "список", "все", "мои"]):
                return show_limits(data)
            # Установить лимит: лимит [категория] [период] [сумма]
            nums = re.findall(r"[\d\s]+(?:[.,]\d+)?", task_lower)
            if nums:
                amount = float(nums[0].replace(" ", "").replace(",", "."))
                period = next((PERIOD_NAMES[w] for w in PERIOD_NAMES if w in task_lower), "monthly")
                category = next((CATEGORY_ALIASES[w] for w in CATEGORY_ALIASES if w in task_lower), "другое")
                return set_limit(period, category, amount, data)
            return show_limits(data)

        # Показать лимиты
        if any(w in task_lower for w in ["лимиты", "ограничения", "мои лимиты"]):
            return show_limits(data)

        # Детализация по категории расходов
        detail_triggers = ["детально", "детали", "покажи категорию", "расходы по", "траты по", "что тратил на"]
        if any(w in task_lower for w in detail_triggers):
            from agents.statement_parser import category_detail
            # Извлекаем название категории после триггера
            for trigger in detail_triggers:
                if trigger in task_lower:
                    cat_query = task_lower.split(trigger)[-1].strip()
                    return category_detail(cat_query)

        # Показать все счета
        if any(w in task_lower for w in ["счет", "счёт", "баланс", "сколько", "состояние", "итого", "summary"]):
            return format_summary(data)

        # Бизнес-доходы
        if any(w in task_lower for w in ["бизнес", "доход", "проект", "выручк"]):
            return format_business(data)

        # Цели
        if task_lower.startswith("цель:") or task_lower.startswith("цель "):
            goal_text = task[5:].strip() if ":" in task[:6] else task[5:].strip()
            return add_goal(goal_text, data)

        if any(w in task_lower for w in ["цели", "goal", "мои цели"]):
            return list_goals(data)

        # Курс доллара
        if "курс" in task_lower:
            import re
            numbers = re.findall(r"\d+", task)
            if numbers:
                rate = int(numbers[0])
                data["usd_to_kzt_rate"] = rate
                _save(data)
                return f"✅ Курс обновлён: 1 USD = {rate} ₸"

        # Всё остальное — анализ через Claude
        return ai_analysis(task, data)
