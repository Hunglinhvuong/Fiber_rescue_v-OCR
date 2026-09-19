import logging
from typing import Optional

import httpx

from config.settings import settings
from ocr.models import OCRResult
from ocr.providers.base import OCRProvider

logger = logging.getLogger(__name__)

_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
_DEFAULT_CONFIDENCE = 0.8


def _extract_page_confidence(full_text_annotation: dict) -> float:
    pages = full_text_annotation.get("pages") or []
    confidences = [p["confidence"] for p in pages if isinstance(p.get("confidence"), (int, float))]
    return (sum(confidences) / len(confidences)) if confidences else _DEFAULT_CONFIDENCE


class GoogleVisionProvider(OCRProvider):
    """Provider fallback khi OCR.space không đọc được toạ độ. Dùng
    DOCUMENT_TEXT_DETECTION (thay vì TEXT_DETECTION thường) vì trả kèm
    confidence theo trang, giúp lọc kết quả rác. Gửi image_url qua
    image.source.imageUri — Google tự tải ảnh (Cloudinary URL public)."""

    name = "google_vision"

    def __init__(self, api_key: Optional[str] = None, timeout: Optional[float] = None):
        self.api_key = api_key if api_key is not None else settings.google_vision_api_key
        self.timeout = timeout or settings.ocr_request_timeout_seconds

    async def extract_text(self, image_url: str) -> OCRResult:
        if not self.api_key:
            return OCRResult(success=False, error="Thiếu GOOGLE_VISION_API_KEY", provider=self.name)

        payload = {
            "requests": [
                {
                    "image": {"source": {"imageUri": image_url}},
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(_ENDPOINT, params={"key": self.api_key}, json=payload)
                resp.raise_for_status()
                data = resp.json()

            result = (data.get("responses") or [{}])[0]
            if "error" in result:
                return OCRResult(
                    success=False,
                    error=result["error"].get("message", "Google Vision trả lỗi"),
                    provider=self.name,
                )

            full_text_annotation = result.get("fullTextAnnotation")
            if not full_text_annotation or not full_text_annotation.get("text"):
                return OCRResult(success=False, error="Google Vision không đọc được text nào", provider=self.name)

            text = full_text_annotation["text"].strip()
            confidence = _extract_page_confidence(full_text_annotation)
            return OCRResult(success=True, text=text, confidence=confidence, provider=self.name)

        except httpx.TimeoutException as exc:
            logger.warning("Google Vision timeout cho %s: %s", image_url, exc)
            return OCRResult(success=False, error=f"Timeout gọi Google Vision: {exc}", provider=self.name)
        except httpx.HTTPStatusError as exc:
            logger.warning("Google Vision HTTP lỗi cho %s: %s", image_url, exc)
            return OCRResult(
                success=False, error=f"Google Vision trả lỗi HTTP {exc.response.status_code}", provider=self.name
            )
        except Exception as exc:  # noqa: BLE001 - caller cần result, không được raise
            logger.exception("Google Vision lỗi không xác định cho %s", image_url)
            return OCRResult(success=False, error=f"Lỗi không xác định Google Vision: {exc}", provider=self.name)
