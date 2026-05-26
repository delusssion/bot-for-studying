import random
import string
from datetime import datetime
from typing import Optional


def kopecks_to_rubles(kopecks: int) -> str:
    rubles = kopecks // 100
    cents = kopecks % 100
    if cents == 0:
        return f"{rubles} ₽"
    return f"{rubles}.{cents:02d} ₽"


def generate_referral_code(prefix: str = "UCH") -> str:
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}-{''.join(random.choices(chars, k=4))}"


def format_datetime(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


ORDER_TYPE_LABELS = {
    "lab_docx": "Лабораторная работа (DOCX)",
    "presentation_pptx": "Презентация (PPTX)",
    "text_answer": "Текстовый ответ",
    "lab_plus_pres": "Лаба + Презентация",
}

ORDER_STATUS_LABELS = {
    "pending": "⏳ Ожидает",
    "processing": "⚙️ Обрабатывается",
    "done": "✅ Готово",
    "error": "❌ Ошибка",
    "refunded": "↩️ Возврат",
}


def order_type_label(order_type: str) -> str:
    return ORDER_TYPE_LABELS.get(order_type, order_type)


def order_status_label(status: str) -> str:
    return ORDER_STATUS_LABELS.get(status, status)
