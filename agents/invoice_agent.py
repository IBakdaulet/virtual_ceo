"""
Invoice Agent — генерация счётов на оплату в PDF.
"""

import json
from datetime import date
from io import BytesIO
from pathlib import Path

INVOICE_FILE = Path(__file__).parent.parent / "data" / "invoices.json"
FONT_DIR = Path(__file__).parent.parent / "assets"

SUPPLIER = {
    "name": "ТОО «Соз Медиа»",
    "bin": "200640002683",
    "address": "РК, г. Астана, район Есиль, ул. Д.Кунаева 35, кв. 154",
    "iik": "KZ18722S000014068883",
    "kbe": "17",
    "bank": 'АО "KASPI BANK"',
    "bik": "CASPKZKA",
    "kno": "859",
    "executor": "Исаев Бакдаулет Асанович",
}

SERVICES = {
    "grants_kz": {"name": "Реклама в Grants.kz", "code": "00000000150"},
    "tanda_bilim": {"name": "Реклама в Tanda Bilim", "code": "00000000151"},
    "ekonomist_media": {"name": "Реклама в Ekonomist Media", "code": "00000000152"},
}

MONTHS_GENITIVE = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}

# ─── Конвертация суммы в слова ────────────────────────────────────────────────

_ONES = ['', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять',
         'десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать', 'пятнадцать',
         'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать']
_ONES_F = ['', 'одна', 'две', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять',
           'десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать', 'пятнадцать',
           'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать']
_TENS = ['', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят',
         'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто']
_HUNDREDS = ['', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот',
             'шестьсот', 'семьсот', 'восемьсот', 'девятьсот']


def _three_digits(n: int, feminine: bool = False) -> str:
    parts = []
    h, rest = divmod(n, 100)
    t, o = divmod(rest, 10)
    if h:
        parts.append(_HUNDREDS[h])
    if t == 1:
        parts.append((_ONES_F if feminine else _ONES)[10 + o])
    else:
        if t:
            parts.append(_TENS[t])
        if o:
            parts.append((_ONES_F if feminine else _ONES)[o])
    return ' '.join(parts)


def _declension(n: int, one: str, two: str, five: str) -> str:
    last2, last1 = n % 100, n % 10
    if 11 <= last2 <= 19:
        return five
    if last1 == 1:
        return one
    if 2 <= last1 <= 4:
        return two
    return five


def amount_to_words(amount: float) -> str:
    tenge = int(amount)
    tiyn = round((amount - tenge) * 100)
    billions = tenge // 1_000_000_000
    millions = (tenge % 1_000_000_000) // 1_000_000
    thousands = (tenge % 1_000_000) // 1_000
    ones = tenge % 1_000
    parts = []
    if billions:
        parts.append(f"{_three_digits(billions)} {_declension(billions, 'миллиард', 'миллиарда', 'миллиардов')}")
    if millions:
        parts.append(f"{_three_digits(millions)} {_declension(millions, 'миллион', 'миллиона', 'миллионов')}")
    if thousands:
        parts.append(f"{_three_digits(thousands, feminine=True)} {_declension(thousands, 'тысяча', 'тысячи', 'тысяч')}")
    if ones:
        parts.append(_three_digits(ones))
    elif not parts:
        parts.append('ноль')
    result = ' '.join(parts)
    result = result[0].upper() + result[1:]
    return f"{result} тенге {tiyn:02d} тиын"


# ─── Счётчик номеров счетов ───────────────────────────────────────────────────

def _load_invoices() -> dict:
    if INVOICE_FILE.exists():
        with open(INVOICE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_number": 31, "invoices": []}


def _save_invoices(data: dict):
    with open(INVOICE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_next_invoice_number() -> int:
    data = _load_invoices()
    data["last_number"] += 1
    _save_invoices(data)
    return data["last_number"]


def save_invoice_record(record: dict):
    data = _load_invoices()
    data["invoices"].append(record)
    _save_invoices(data)


# ─── Шрифты (кириллица) ───────────────────────────────────────────────────────

def _ensure_fonts():
    """Скачивает DejaVu шрифты при первом запуске и регистрирует в reportlab."""
    FONT_DIR.mkdir(exist_ok=True)
    files = {
        "DejaVuSans.ttf": "https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf": "https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/DejaVuSans-Bold.ttf",
    }
    for fname, url in files.items():
        fpath = FONT_DIR / fname
        if not fpath.exists():
            import httpx
            r = httpx.get(url, follow_redirects=True, timeout=30)
            fpath.write_bytes(r.content)

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    try:
        pdfmetrics.getFont("DejaVu")
    except Exception:
        pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))


# ─── Генерация PDF ────────────────────────────────────────────────────────────

def generate_invoice_pdf(
    invoice_number: int,
    invoice_date: date,
    client_name: str,
    client_bin: str,
    client_address: str,
    service_name: str,
    service_code: str,
    amount: float,
) -> bytes:
    _ensure_fonts()

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    def draw_border(canvas, doc):
        from reportlab.lib import colors as _c
        from reportlab.lib.units import mm as _mm
        from reportlab.lib.pagesizes import A4 as _A4
        w, h = _A4
        canvas.setStrokeColor(_c.black)
        canvas.setLineWidth(0.5)
        canvas.rect(10*_mm, 10*_mm, w - 20*_mm, h - 20*_mm)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm,
        onFirstPage=draw_border, onLaterPages=draw_border,
    )

    def p(text, font="DejaVu", size=7, align=TA_LEFT, bold=False):
        fn = "DejaVu-Bold" if bold else "DejaVu"
        return Paragraph(text, ParagraphStyle("s", fontName=fn, fontSize=size,
                                              leading=size + 2, alignment=align))

    C = TA_CENTER
    L = TA_LEFT
    story = []

    # Уведомление
    notice = ("Внимание! Оплата данного счета означает согласие с условиями поставки товара. "
              "Уведомление об оплате обязательно, в противном случае не гарантируется наличие товара на складе. "
              "Товар отпускается по факту прихода денег на р/с Поставщика, самовывозом, "
              "при наличии доверенности и документов удостоверяющих личность.")
    story.append(p(notice, size=6, align=C))
    story.append(Spacer(1, 4*mm))

    # Реквизиты
    W = 180*mm
    req = [
        [p("Образец платежного поручения", bold=True, size=8), '', '', '', '', ''],
        [p("Бенефициар:", bold=True), p(SUPPLIER["name"], bold=True),
         p("ИИК", align=C), p(SUPPLIER["iik"]),
         p("Кбе", align=C), p(SUPPLIER["kbe"], align=C)],
        [p(""), p(f'БИН: {SUPPLIER["bin"]}'),
         p("БИК", align=C), p(SUPPLIER["bik"]),
         p("Код назначения платежа", align=C, size=6), p(SUPPLIER["kno"], align=C)],
        [p("Банк бенефициара:", bold=True), p(SUPPLIER["bank"]), '', '', '', ''],
    ]
    cw = [28*mm, 52*mm, 12*mm, 46*mm, 28*mm, 14*mm]
    rt = Table(req, colWidths=cw)
    rt.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('SPAN', (0, 0), (-1, 0)),
        ('SPAN', (1, 3), (-1, 3)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(rt)
    story.append(Spacer(1, 5*mm))

    # Заголовок
    d = invoice_date
    title = f"Счет на оплату № {invoice_number} от {d.day} {MONTHS_GENITIVE[d.month]} {d.year} г."
    story.append(p(title, bold=True, size=13))
    story.append(Spacer(1, 4*mm))

    # Поставщик / Покупатель
    sup_str = f'БИН / ИИН {SUPPLIER["bin"]},{SUPPLIER["name"]},{SUPPLIER["address"]}'
    cli_str = f'БИН / ИИН {client_bin},{client_name},{client_address}'
    info = [
        [p("Поставщик:", bold=True), p(sup_str)],
        [p("Покупатель:", bold=True), p(cli_str)],
        [p("Договор:", bold=True), p("Без договора")],
    ]
    it = Table(info, colWidths=[28*mm, 152*mm])
    it.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(it)

    # Таблица услуг
    fmt = f'{amount:,.2f}'.replace(',', ' ').replace('.', ',')
    items = [
        [p("№", align=C, bold=True), p("Код", align=C, bold=True),
         p("Наименование", align=C, bold=True), p("Кол-во", align=C, bold=True),
         p("Ед.", align=C, bold=True), p("Цена", align=C, bold=True),
         p("Сумма", align=C, bold=True)],
        [p("1", align=C), p(service_code, align=C), p(service_name),
         p("1,000", align=C), p("Одна\nуслуга", align=C),
         p(fmt, align=C), p(fmt, align=C)],
        ['', '', '', '', '',
         p("Итого:", bold=True, align=C), p(fmt, bold=True, align=C)],
    ]
    cw2 = [8*mm, 28*mm, 62*mm, 16*mm, 18*mm, 24*mm, 24*mm]
    tbl = Table(items, colWidths=cw2)
    tbl.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('SPAN', (0, 2), (4, 2)),
        ('NOSPLIT', (0, 0), (-1, -1)),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 3*mm))

    # Итого текстом
    story.append(p(f"Всего наименований 1, на сумму {fmt} KZT"))
    words = amount_to_words(amount)
    story.append(p(f"Всего к оплате: {words}", bold=True))
    story.append(Spacer(1, 10*mm))

    # Исполнитель + печать
    stamp_path = FONT_DIR / "stamp_transparent.png"
    if stamp_path.exists():
        from reportlab.platypus import Image as RLImage
        stamp = RLImage(str(stamp_path), width=30*mm, height=30*mm)
    else:
        stamp = p("")

    ex = [
        [p("Исполнитель", bold=True), stamp, p(f"/{SUPPLIER['executor']}/")],
    ]
    et = Table(ex, colWidths=[28*mm, 100*mm, 52*mm])
    et.setStyle(TableStyle([
        ('LINEBELOW', (1, 0), (1, 0), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
    ]))
    story.append(et)

    doc.build(story)
    return buffer.getvalue()
