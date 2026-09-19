from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OCRResult:
    """Kết quả OCR thống nhất — mọi provider (OCR.space, Google Vision, ...)
    đều trả đúng shape này, không rò rỉ field riêng của API gốc. success=False
    khi lỗi mạng/timeout/HTTP/API hoặc không đọc được text, KHÔNG raise
    exception ra ngoài provider -> caller luôn có kết quả để lưu DB."""

    success: bool
    text: str = ""
    confidence: float = 0.0
    error: Optional[str] = None
    provider: Optional[str] = None


@dataclass(frozen=True)
class ParsedCoordinate:
    """Toạ độ trích ra từ text OCR. Chỉ được coi là hợp lệ khi có đủ
    latitude + longitude từ CÙNG một match (không ghép lat/long khác nguồn)."""

    latitude: float
    longitude: float
    raw_match: str
    pattern_name: str


@dataclass(frozen=True)
class CoordinateCandidate:
    """1 nguồn toạ độ ứng viên (OCR_AFTER / OCR_BEFORE / GPS) dùng để
    CoordinateService chọn toạ độ cuối cùng."""

    source: str  # "OCR_AFTER" | "OCR_BEFORE" | "GPS"
    latitude: float
    longitude: float
