"""
Google Sheets интеграция для Virtual CEO.
Пишет данные в 4 листа: Продажи, KPI, История 2025, История 2026.
"""

import json
import os
from datetime import date

import gspread

SHEET_ID = "1aGY0-SIbVjFF4uqI8v6SaEmTp5WT2r9hnsjhaAlS9Qw"
BALANCE_SHEET_ID = "1cbPpZLnPRrtlhKTdQSkzjsuzmkdbY3KUng7yN2uoZU8"

PROJECTS_RU = {
    "grants_kz": "Grants KZ",
    "tanda_bilim": "Tanda Bilim",
    "ekonomist_media": "Ekonomist Media",
}

MONTH_NAMES = {
    "01": "Январь", "02": "Февраль", "03": "Март", "04": "Апрель",
    "05": "Май", "06": "Июнь", "07": "Июль", "08": "Август",
    "09": "Сентябрь", "10": "Октябрь", "11": "Ноябрь", "12": "Декабрь"
}


def _get_client():
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        return None
    try:
        creds_dict = json.loads(creds_json)
        return gspread.service_account_from_dict(creds_dict)
    except Exception as e:
        print(f"[Sheets] Auth error: {e}")
        return None


def _get_or_create_sheet(spreadsheet: gspread.Spreadsheet, title: str) -> gspread.Worksheet:
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=500, cols=20)
        return ws


def _ensure_header(ws: gspread.Worksheet, header: list):
    first_row = ws.row_values(1)
    if first_row != header:
        ws.update("A1", [header])


def append_sales_row(today_grants: float, today_tanda: float,
                     month_grants: float, month_tanda: float):
    """Добавляет строку в лист «Продажи»."""
    gc = _get_client()
    if not gc:
        return
    try:
        sh = gc.open_by_key(SHEET_ID)
        ws = _get_or_create_sheet(sh, "Продажи")
        header = ["Дата", "Grants KZ (день)", "Tanda Bilim (день)", "Итого день",
                  "Grants KZ (месяц)", "Tanda Bilim (месяц)", "Итого месяц"]
        _ensure_header(ws, header)
        today = date.today().strftime("%d.%m.%Y")
        row = [today, today_grants, today_tanda, today_grants + today_tanda,
               month_grants, month_tanda, month_grants + month_tanda]
        ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"[Sheets] append_sales_row error: {e}")


def upsert_kpi_row(year_month: str, grants_rev: float, tanda_rev: float,
                   grants_bonus: float, tanda_bonus: float,
                   total_fixed: float, total_bonus: float):
    """Обновляет строку KPI если период уже есть, иначе добавляет новую."""
    gc = _get_client()
    if not gc:
        return
    try:
        sh = gc.open_by_key(SHEET_ID)
        ws = _get_or_create_sheet(sh, "KPI")
        header = ["Период", "Grants KZ выручка", "Tanda Bilim выручка",
                  "Grants KZ бонус", "Tanda Bilim бонус",
                  "Фикс итого", "Бонус итого", "К выплате"]
        _ensure_header(ws, header)
        row = [year_month, grants_rev, tanda_rev,
               grants_bonus, tanda_bonus,
               total_fixed, total_bonus, total_fixed + total_bonus]
        # Ищем существующую строку с таким периодом
        col_values = ws.col_values(1)  # колонка "Период"
        if year_month in col_values:
            row_idx = col_values.index(year_month) + 1
            ws.update(f"A{row_idx}", [row])
        else:
            ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"[Sheets] upsert_kpi_row error: {e}")


def populate_historical(year: int, months_data: dict):
    """
    Полностью перезаписывает лист «История {year}» из historical_sales.json.
    months_data: {"01": {"grants_kz": X, "tanda_bilim": Y, "ekonomist_media": Z}, ...}
    """
    gc = _get_client()
    if not gc:
        return
    sh = gc.open_by_key(SHEET_ID)
    ws = _get_or_create_sheet(sh, f"История {year}")
    header = ["Месяц", "Grants KZ", "Tanda Bilim", "Ekonomist Media", "Итого"]
    rows = [header]
    totals = [0.0, 0.0, 0.0]
    for month_num in sorted(months_data.keys()):
        m = months_data[month_num]
        gkz = m.get("grants_kz", 0)
        tb = m.get("tanda_bilim", 0)
        em = m.get("ekonomist_media", 0)
        totals[0] += gkz
        totals[1] += tb
        totals[2] += em
        rows.append([MONTH_NAMES.get(month_num, month_num), gkz, tb, em, gkz + tb + em])
    rows.append(["ИТОГО", totals[0], totals[1], totals[2], sum(totals)])
    ws.clear()
    ws.update("A1", rows)


def append_balance_row(accounts: dict, usd_rate: float):
    """
    Добавляет новый столбец с датой — счета в строках, даты в столбцах.
    Структура:
      Строка 1: [Счёт, Валюта, дата1, дата2, ...]
      Строка 2: [Kaspi карта, KZT, 201600, ...]
      ...
      Последняя: [Итого KZT, KZT, 24500000, ...]
    """
    gc = _get_client()
    if not gc:
        return
    try:
        from datetime import datetime
        sh = gc.open_by_key(BALANCE_SHEET_ID)
        ws = _get_or_create_sheet(sh, "Балансы")

        date_str = datetime.now().strftime("%d.%m.%Y")

        # Считаем итог
        total_kzt = 0.0
        for acc in accounts.values():
            balance = acc.get("balance", 0)
            currency = acc.get("currency", "KZT")
            total_kzt += balance * usd_rate if currency == "USD" else balance

        # Строим список строк: [название, валюта, баланс]
        acc_rows = []
        for acc in accounts.values():
            acc_rows.append([acc.get("name", ""), acc.get("currency", "KZT"), acc.get("balance", 0)])
        acc_rows.append(["Итого KZT", "KZT", round(total_kzt)])

        all_data = ws.get_all_values()

        # Всегда обновляем A и B (названия и валюты)
        name_col = [["Счёт", "Валюта"]] + [[name, currency] for name, currency, _ in acc_rows]
        ws.update("A1", name_col)

        # Ищем колонку с сегодняшней датой — если есть, перезаписываем
        header_row = all_data[0] if all_data else []
        if date_str in header_row:
            target_col = header_row.index(date_str) + 1
        else:
            target_col = max(len(header_row) + 1, 3)

        ws.update_cell(1, target_col, date_str)
        for i, (_, _, balance) in enumerate(acc_rows):
            ws.update_cell(i + 2, target_col, balance)
    except Exception as e:
        print(f"[Sheets] append_balance_row error: {e}")


EXPENSE_ROWS = [
    "Еда и рестораны", "Транспорт", "Развлечения", "Здоровье",
    "Одежда и шоппинг", "Образование", "Бизнес расходы",
    "Коммуналка", "Переводы", "Другое", "ИТОГО расходы", "ИТОГО доходы"
]

CATEGORY_MAP = {
    "еда и рестораны": "Еда и рестораны",
    "транспорт": "Транспорт",
    "развлечения": "Развлечения",
    "здоровье": "Здоровье",
    "одежда и шоппинг": "Одежда и шоппинг",
    "образование": "Образование",
    "бизнес расходы": "Бизнес расходы",
    "коммуналка": "Коммуналка",
    "переводы": "Переводы",
    "другое": "Другое",
}


def append_expense_month(month_label: str, categories: dict, total_expenses: float, total_income: float):
    """
    Добавляет столбец с расходами за месяц в лист «Расходы».
    categories: {"еда и рестораны": 150000, "транспорт": 50000, ...}
    """
    gc = _get_client()
    if not gc:
        return
    try:
        sh = gc.open_by_key(BALANCE_SHEET_ID)
        ws = _get_or_create_sheet(sh, "Расходы")
        all_data = ws.get_all_values()

        # Нормализуем категории
        normalized = {}
        for k, v in categories.items():
            mapped = CATEGORY_MAP.get(k.lower().strip(), "Другое")
            normalized[mapped] = normalized.get(mapped, 0) + v
        normalized["ИТОГО расходы"] = total_expenses
        normalized["ИТОГО доходы"] = total_income

        if not all_data:
            # Первая запись — создаём структуру
            rows = [["Категория", month_label]]
            for row_name in EXPENSE_ROWS:
                rows.append([row_name, normalized.get(row_name, 0)])
            ws.update("A1", rows)
        else:
            # Всегда обновляем колонку A с названиями
            name_col = [["Категория"]] + [[r] for r in EXPENSE_ROWS]
            ws.update("A1", name_col)
            # Добавляем новый столбец
            next_col = max(len(all_data[0]) + 1, 2)
            ws.update_cell(1, next_col, month_label)
            for i, row_name in enumerate(EXPENSE_ROWS):
                ws.update_cell(i + 2, next_col, normalized.get(row_name, 0))
    except Exception as e:
        print(f"[Sheets] append_expense_month error: {e}")


def sync_historical_to_sheets():
    """Синхронизирует весь historical_sales.json в Google Sheets."""
    from pathlib import Path
    hist_file = Path(__file__).parent.parent / "data" / "historical_sales.json"
    if not hist_file.exists():
        return
    with open(hist_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    for year_str, year_data in data.get("years", {}).items():
        months = year_data.get("months", {})
        if months:
            populate_historical(int(year_str), months)
