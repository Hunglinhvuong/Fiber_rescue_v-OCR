from decimal import Decimal, InvalidOperation
from typing import Optional


def validate_full_name(text: str) -> bool:
    return len(text.strip()) >= 3


def parse_quantity(text: str) -> Optional[Decimal]:
    """Parse chuỗi số lượng người dùng nhập (hỗ trợ dấu , hoặc .). Trả None nếu không hợp lệ."""
    cleaned = text.strip().replace(",", ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if value <= 0:
        return None
    return value


def parse_search_text(text: str) -> str:
    return text.strip()[:100]
