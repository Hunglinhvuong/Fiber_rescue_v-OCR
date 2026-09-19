import logging
from typing import List, Optional

from config.settings import settings
from ocr.models import OCRResult
from ocr.parser import parse_coordinates
from ocr.providers.base import OCRProvider
from ocr.providers.google_vision import GoogleVisionProvider
from ocr.providers.ocr_space import OCRSpaceProvider

logger = logging.getLogger(__name__)

# Đăng ký provider tại đây khi thêm mới — OCRService không hard-code tên
# provider nào, chỉ đọc thứ tự từ settings.ocr_provider_order.
_PROVIDER_REGISTRY = {
    "ocr_space": OCRSpaceProvider,
    "google_vision": GoogleVisionProvider,
}


def _is_valid_range(latitude: float, longitude: float) -> bool:
    return -90 <= latitude <= 90 and -180 <= longitude <= 180


def _build_provider_chain() -> List[OCRProvider]:
    chain: List[OCRProvider] = []
    for name in settings.ocr_provider_order:
        provider_cls = _PROVIDER_REGISTRY.get(name)
        if provider_cls is None:
            logger.warning("Bỏ qua provider không xác định trong OCR_PROVIDER_ORDER: %s", name)
            continue
        chain.append(provider_cls())
    if not chain:
        raise RuntimeError(
            "OCR_PROVIDER_ORDER rỗng hoặc không hợp lệ — không có OCR provider nào để chạy"
        )
    return chain


class OCRService:
    """Điều phối fallback qua nhiều OCR provider theo thứ tự cấu hình
    (mặc định OCR.space -> Google Cloud Vision). KHÔNG phụ thuộc trực tiếp
    vào provider cụ thể nào — chỉ biết interface OCRProvider.

    Quy tắc chuyển provider: chỉ gọi provider kế tiếp khi provider hiện tại
    THẤT BẠI HOÀN TOÀN (lỗi mạng/API) HOẶC đọc được text nhưng KHÔNG parse
    ra toạ độ hợp lệ. Dừng ngay khi có provider cho toạ độ hợp lệ — không
    gọi thêm provider phía sau (tránh tốn quota/tiền không cần thiết).
    """

    def __init__(self, providers: Optional[List[OCRProvider]] = None):
        self.providers = providers or _build_provider_chain()

    async def extract_text(self, image_url: str) -> OCRResult:
        last_result: Optional[OCRResult] = None

        for provider in self.providers:
            result = await provider.extract_text(image_url)
            last_result = result

            if not result.success:
                logger.info("Provider %s thất bại cho %s: %s", provider.name, image_url, result.error)
                continue

            parsed = parse_coordinates(result.text)
            if parsed is not None and _is_valid_range(parsed.latitude, parsed.longitude):
                logger.info("Provider %s đọc được toạ độ hợp lệ cho %s", provider.name, image_url)
                return result

            logger.info(
                "Provider %s có text nhưng không có toạ độ hợp lệ cho %s -> thử provider kế tiếp",
                provider.name, image_url,
            )

        # Không provider nào cho toạ độ hợp lệ. Trả kết quả cuối cùng để
        # worker lưu raw_text/error phục vụ audit (mark_invalid/mark_failed).
        if last_result is None:
            return OCRResult(success=False, error="Không có OCR provider nào được cấu hình")
        return last_result
