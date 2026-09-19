from abc import ABC, abstractmethod

from ocr.models import OCRResult


class OCRProvider(ABC):
    """Interface chung cho mọi OCR provider. Chỉ chịu trách nhiệm giao tiếp
    với API OCR và trả về OCRResult thống nhất — không parse toạ độ, không
    validate range, không biết gì về incident/coordinate_extraction.

    Thêm provider mới: tạo file mới trong ocr/providers/ implement class
    này, rồi đăng ký vào _PROVIDER_REGISTRY trong ocr/service.py. Không cần
    sửa OCRService hay bất kỳ business logic nào khác.
    """

    name: str = "base"

    @abstractmethod
    async def extract_text(self, image_url: str) -> OCRResult:
        """Gửi image_url tới OCR API, trả OCRResult(success, text, confidence,
        error, provider). Không bao giờ raise ra ngoài — mọi lỗi (mạng,
        timeout, HTTP, API-level error, thiếu API key) phải được gói lại
        thành OCRResult(success=False, error=...)."""
        raise NotImplementedError
