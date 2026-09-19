import logging
from typing import Optional

import httpx

from config.settings import settings
from ocr.models import OCRResult
from ocr.providers.base import OCRProvider

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.ocr.space/parse/image"

# OCR.space (free tier) không trả confidence dạng số cho từng lần đọc ->
# dùng 1 mức cố định khi đọc thành công, việc "đủ tin cậy hay không" thực
# chất được quyết định bởi bước parse toạ độ ở OCRService/worker, không
# phải bởi con số confidence này.
_DEFAULT_CONFIDENCE = 0.85


class OCRSpaceProvider(OCRProvider):
    """Provider chính, ưu tiên vì có gói miễn phí. Gửi thẳng image_url cho
    OCR.space tự tải ảnh — bot/worker không cần tải bytes về."""

    name = "ocr_space"

    def __init__(self, api_key: Optional[str] = None, timeout: Optional[float] = None):
        self.api_key = api_key if api_key is not None else settings.ocr_space_api_key
        self.timeout = timeout or settings.ocr_request_timeout_seconds

    async def extract_text(self, image_url: str) -> OCRResult:
        if not self.api_key:
            return OCRResult(success=False, error="Thiếu OCR_SPACE_API_KEY", provider=self.name)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    _ENDPOINT,
                    data={
                        "apikey": self.api_key,
                        "url": image_url,
                        "OCREngine": 2,
                        "scale": "true",
                        "isOverlayRequired": "false",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            if data.get("IsErroredOnProcessing"):
                raw_error = data.get("ErrorMessage") or ["OCR.space lỗi xử lý ảnh"]
                error_msg = "; ".join(raw_error) if isinstance(raw_error, list) else str(raw_error)
                return OCRResult(success=False, error=error_msg, provider=self.name)

            results = data.get("ParsedResults") or []
            if not results:
                return OCRResult(success=False, error="OCR.space không trả ParsedResults", provider=self.name)

            text = "\n".join((r.get("ParsedText") or "") for r in results).strip()
            if not text:
                return OCRResult(success=False, error="OCR.space không đọc được text nào", provider=self.name)

            return OCRResult(success=True, text=text, confidence=_DEFAULT_CONFIDENCE, provider=self.name)

        except httpx.TimeoutException as exc:
            logger.warning("OCR.space timeout cho %s: %s", image_url, exc)
            return OCRResult(success=False, error=f"Timeout gọi OCR.space: {exc}", provider=self.name)
        except httpx.HTTPStatusError as exc:
            logger.warning("OCR.space HTTP lỗi cho %s: %s", image_url, exc)
            return OCRResult(
                success=False, error=f"OCR.space trả lỗi HTTP {exc.response.status_code}", provider=self.name
            )
        except Exception as exc:  # noqa: BLE001 - caller cần result, không được raise
            logger.exception("OCR.space lỗi không xác định cho %s", image_url)
            return OCRResult(success=False, error=f"Lỗi không xác định OCR.space: {exc}", provider=self.name)
