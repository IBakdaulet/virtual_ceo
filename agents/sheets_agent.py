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
    """Добавляет строку с балансами всех счетов в отдельную таблицу."""
    gc = _get_client()
    if not gc:
        return
    try:
        sh = gc.open_by_key(BALANCE_SHEET_ID)
        ws = _get_or_create_sheet(sh, "Балансы")

        # Собираем данные
        from datetime import datetime
        row_data = {"Дата": datetime.now().strftime("%d.%m.%Y %H:%M")}
        total_kzt = 0.0
        for acc in accounts.values():
            name = acc.get("name", "")
            balance = acc.get("balance", 0)
            currency = acc.get("currency", "KZT")
            row_data[f"{name} ({currency})"] = balance
            total_kzt += balance * usd_rate if currency == "USD" else balance
        row_data["Итого KZT"] = round(total_kzt)

        header = list(row_data.keys())
        _ensure_header(ws, header)
        ws.append_row(list(row_data.values()), value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"[Sheets] append_balance_row error: {e}")


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
