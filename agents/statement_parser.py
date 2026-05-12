"""
Парсер банковских выписок (PDF) для Kaspi, Halyk, Freedom.
Использует Claude API для нативного чтения PDF.
"""

import base64
import re
import json
import os
import anthropic
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

DATA_FILE = Path(__file__).parent.parent / "data" / "finance.json"
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

EXPENSE_CATEGORIES = {
    "еда и рестораны": ["магнум", "small", "burger", "kfc", "mcdonalds", "макдоналдс", "пицца", "pizza",
                        "кафе", "ресторан", "cafe", "food", "sushi", "суши", "glovo", "яндекс еда",
                        "choco", "чоко", "супермаркет", "продукты", "market", "маркет"],
    "транспорт": ["uber", "яндекс такси", "yandex taxi", "bolt", "каршеринг", "автобус", "метро",
                  "parkright", "parking", "парковка", "бензин", "azs", "азс", "shell", "лукойл"],
    "развлечения": ["cinema", "кино", "алматы арена", "концерт", "netflix", "spotify", "steam",
                    "казино", "бар", "bar", "club", "клуб"],
    "здоровье": ["аптека", "pharmacy", "клиника", "clinic", "больница", "hospital", "dentist",
                 "стоматолог", "спортзал", "gym", "фитнес", "fitness"],
    "одежда и шоппинг": ["gloria", "zara", "h&m", "adidas", "nike", "lamoda", "wildberries",
                         "magnum", "sulpak", "технодом", "mechta"],
    "образование": ["udemy", "coursera", "skillbox", "книги", "курс", "course"],
    "бизнес расходы": ["notion", "figma", "canva", "adobe", "google", "apple", "microsoft",
                       "реклама", "facebook ads", "instagram"],
    "переводы": ["перевод", "transfer", "p2p"],
    "коммуналка": ["казахтелеком", "beeline", "activ", "kcell", "алматы энерго", "газ", "вода"],
}


def detect_bank(text: str) -> str:
    """Определяет банк по содержимому PDF."""
    text_lower = text.lower()
    if "kaspi" in text_lower or "каспи" in text_lower:
        return "kaspi"
    if "halyk" in text_lower or "халык" in text_lower or "народный" in text_lower:
        return "halyk"
    if "freedom" in text_lower or "фридом" in text_lower:
        return "freedom"
    return "unknown"


def parse_kaspi(text: str) -> List[Dict]:
    """Парсит выписку Kaspi Bank."""
    transactions = []
    # Kaspi формат: дата, описание, сумма
    patterns = [
        r"(\d{2}\.\d{2}\.\d{4})\s+(.+?)\s+([-+]?\s*[\d\s]+[,.]?\d*)\s*₸",
        r"(\d{2}\.\d{2}\.\d{4})\s+(.+?)\s+([-+]?\s*[\d\s]+[,.]?\d*)\s*KZT",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.MULTILINE)
        for match in matches:
            date_str, description, amount_str = match
            amount_str = amount_str.replace(" ", "").replace(",", ".")
            try:
                amount = float(amount_str)
                transactions.append({
                    "date": date_str,
                    "description": description.strip(),
                    "amount": amount,
                    "bank": "kaspi"
                })
            except ValueError:
                continue
    return transactions


def parse_halyk(text: str) -> List[Dict]:
    """Парсит выписку Halyk Bank."""
    transactions = []
    patterns = [
        r"(\d{2}\.\d{2}\.\d{4})\s+(.+?)\s+([-+]?\s*[\d\s]+[,.]?\d*)\s*(?:KZT|₸|тенге)",
        r"(\d{2}/\d{2}/\d{4})\s+(.+?)\s+([-+]?\s*[\d\s]+[,.]?\d*)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.MULTILINE)
        for match in matches:
            date_str, description, amount_str = match
            amount_str = amount_str.replace(" ", "").replace(",", ".")
            try:
                amount = float(amount_str)
                transactions.append({
                    "date": date_str,
                    "description": description.strip(),
                    "amount": amount,
                    "bank": "halyk"
                })
            except ValueError:
                continue
    return transactions


def parse_freedom(text: str) -> List[Dict]:
    """Парсит выписку Freedom Bank."""
    transactions = []
    patterns = [
        r"(\d{2}\.\d{2}\.\d{4})\s+(.+?)\s+([-+]?\s*[\d\s]+[,.]?\d*)\s*(?:KZT|₸|USD|\$)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.MULTILINE)
        for match in matches:
            date_str, description, amount_str = match
            amount_str = amount_str.replace(" ", "").replace(",", ".")
            try:
                amount = float(amount_str)
                transactions.append({
                    "date": date_str,
                    "description": description.strip(),
                    "amount": amount,
                    "bank": "freedom"
                })
            except ValueError:
                continue
    return transactions


def categorize(description: str) -> str:
    """Определяет категорию транзакции."""
    desc_lower = description.lower()
    for category, keywords in EXPENSE_CATEGORIES.items():
        if any(kw in desc_lower for kw in keywords):
            return category
    return "другое"


def parse_pdf(file_path: str) -> Dict:
    """Читает PDF как base64 и отдаёт Claude для нативного анализа."""
    with open(file_path, "rb") as f:
        pdf_bytes = f.read()

    pdf_base64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    bank = "unknown"

    # Быстро определяем банк по имени файла или первым байтам текста
    filename = Path(file_path).name.lower()
    if "kaspi" in filename or "каспи" in filename:
        bank = "kaspi"
    elif "halyk" in filename or "халык" in filename:
        bank = "halyk"
    elif "freedom" in filename or "фридом" in filename:
        bank = "freedom"

    return {
        "bank": bank,
        "pdf_base64": pdf_base64,
        "raw_text": "",
        "pages_text": [],
        "total_pages": "?",
        "transactions": [],
        "count": 0
    }

    parsers = {
        "kaspi": parse_kaspi,
        "halyk": parse_halyk,
        "freedom": parse_freedom,
    }

    if bank in parsers:
        transactions = parsers[bank](all_text)
    else:
        transactions = (parse_kaspi(all_text) or
                        parse_halyk(all_text) or
                        parse_freedom(all_text))

    for t in transactions:
        t["category"] = categorize(t["description"])

    return {
        "bank": bank,
        "raw_text": all_text,
        "pages_text": pages_text,
        "total_pages": total_pages,
        "transactions": transactions,
        "count": len(transactions)
    }


def _group_by_month(transactions: List[Dict]) -> Dict:
    """Группирует транзакции по месяцам."""
    months = {}
    for t in transactions:
        date_str = t.get("date", "")
        # Поддерживаем форматы DD.MM.YYYY и DD/MM/YYYY
        try:
            if "." in date_str:
                dt = datetime.strptime(date_str, "%d.%m.%Y")
            elif "/" in date_str:
                dt = datetime.strptime(date_str, "%d/%m/%Y")
            else:
                continue
            key = dt.strftime("%Y-%m")
            label = dt.strftime("%B %Y").capitalize()
        except ValueError:
            continue

        if key not in months:
            months[key] = {"label": label, "income": 0, "expenses": 0, "categories": {}, "transactions": []}

        amt = t["amount"]
        cat = t.get("category", "другое")
        if amt > 0:
            months[key]["income"] += amt
        else:
            months[key]["expenses"] += abs(amt)
            months[key]["categories"][cat] = months[key]["categories"].get(cat, 0) + abs(amt)
        months[key]["transactions"].append(t)

    return dict(sorted(months.items()))


def _get_limits_context() -> str:
    """Получает лимиты для добавления в промпт."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        monthly = data.get("limits", {}).get("monthly", {})
        if not monthly:
            return ""
        lines = ["МЕСЯЧНЫЕ ЛИМИТЫ ПОЛЬЗОВАТЕЛЯ:"]
        for cat, amt in monthly.items():
            lines.append(f"  {cat}: {amt:,.0f} ₸")
        return "\n".join(lines)
    except Exception:
        return ""


def analyze_with_claude(parsed: Dict, period: Optional[str] = None) -> str:
    """Отправляет PDF напрямую Claude для нативного анализа."""

    bank_name = parsed["bank"].upper() if parsed["bank"] != "unknown" else "банк"
    period_str = f" за {period}" if period else ""
    limits_ctx = _get_limits_context()

    prompt = f"""Это банковская выписка {bank_name}{period_str}.
{limits_ctx}

ШАГ 1: Найди ВСЕ месяцы в документе от первой до последней страницы. Не пропускай ни один.

ШАГ 2: Для КАЖДОГО найденного месяца выведи:

📅 [МЕСЯЦ ГОД]
  Доходы: +X ₸
  Расходы: -Y ₸
  Баланс: Z ₸
  Категории расходов:
    • Еда и рестораны: X ₸
    • Транспорт: X ₸
    • Переводы: X ₸
    • Шоппинг: X ₸
    • (другие категории)

ШАГ 3: После всех месяцев выведи итог:

📊 ИТОГО ЗА ВЕСЬ ПЕРИОД
  Доходы: +X ₸
  Расходы: -Y ₸
  Баланс: Z ₸
  Топ расходов: Категория X ₸, Категория X ₸, Категория X ₸

💡 ВЫВОДЫ: 2-3 коротких совета

СТРОГИЕ ПРАВИЛА:
- Показывай ВСЕ месяцы без исключения
- В категориях ТОЛЬКО итоговая сумма, без перечисления отдельных транзакций
- Категоризируй сам: переводы, еда, транспорт, коммуналка, шоппинг, развлечения, другое
- Только цифры из документа, русский язык"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system="Ты — личный финансовый советник казахстанского предпринимателя Ибакдаулета. Читай PDF внимательно, анализируй каждый месяц отдельно. Только факты из документа.",
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": parsed["pdf_base64"]
                    }
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        }]
    )
    return response.content[0].text


def save_transactions(transactions: List[Dict]):
    """Сохраняет транзакции в finance.json для истории."""
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    existing_descs = {(t["date"], t["description"]) for t in data.get("transactions", [])}
    new_count = 0
    for t in transactions:
        key = (t.get("date", ""), t.get("description", ""))
        if key not in existing_descs:
            data["transactions"].append(t)
            new_count += 1

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return new_count


def category_detail(category_query: str) -> str:
    """Показывает все транзакции по категории из сохранённой истории."""
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    transactions = data.get("transactions", [])
    if not transactions:
        return "Нет сохранённых транзакций. Сначала загрузите выписку."

    # Ищем совпадение категории
    query = category_query.lower().strip()
    matched_cat = None
    for cat in EXPENSE_CATEGORIES:
        if query in cat.lower() or cat.lower() in query:
            matched_cat = cat
            break

    # Фильтруем транзакции
    if matched_cat:
        filtered = [t for t in transactions if t.get("category") == matched_cat and t.get("amount", 0) < 0]
    else:
        # Поиск по ключевому слову в описании
        filtered = [t for t in transactions if query in t.get("description", "").lower() and t.get("amount", 0) < 0]
        matched_cat = f'"{category_query}"'

    if not filtered:
        return f"Транзакций по категории '{category_query}' не найдено."

    # Группируем по месяцам
    by_month: Dict[str, list] = {}
    total = 0
    for t in sorted(filtered, key=lambda x: x.get("date", ""), reverse=True):
        date_str = t.get("date", "")
        try:
            if "." in date_str:
                dt = datetime.strptime(date_str, "%d.%m.%Y")
            elif "/" in date_str:
                dt = datetime.strptime(date_str, "%d/%m/%Y")
            else:
                dt = None
            month = dt.strftime("%B %Y") if dt else "Без даты"
        except ValueError:
            month = "Без даты"

        if month not in by_month:
            by_month[month] = []
        by_month[month].append(t)
        total += abs(t["amount"])

    lines = [f"Категория: {matched_cat}\nВсего потрачено: {total:,.0f} ₸\n"]
    for month, txns in by_month.items():
        month_total = sum(abs(t["amount"]) for t in txns)
        lines.append(f"\n{month} — {month_total:,.0f} ₸")
        for t in txns:
            lines.append(f"  {t.get('date','')}  {t.get('description','')[:40]}  -{abs(t['amount']):,.0f} ₸")

    return "\n".join(lines)
