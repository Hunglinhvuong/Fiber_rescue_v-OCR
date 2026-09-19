import os
from dataclasses import dataclass, field
from typing import Tuple

from dotenv import load_dotenv

load_dotenv()


def _parse_admin_ids(raw: str) -> Tuple[int, ...]:
    return tuple(int(x) for x in raw.split(",") if x.strip())


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_name: str = os.getenv("DB_NAME", "fiber_rescue")
    db_user: str = os.getenv("DB_USER", "postgres")
    db_password: str = os.getenv("DB_PASSWORD", "")
    db_min_pool: int = int(os.getenv("DB_MIN_POOL", "2"))
    db_max_pool: int = int(os.getenv("DB_MAX_POOL", "10"))

    persistence_file: str = os.getenv("PERSISTENCE_FILE", "storage/bot_persistence.pickle")
    timezone: str = os.getenv("APP_TIMEZONE", "Asia/Ho_Chi_Minh")

    # Thư mục chứa file .kml của từng tuyến cáp (tên file = route_code hoặc
    # route_name, ví dụ data/kml/RT-001.kml hoặc data/kml/Tuyến Hà Đông.kml)
    route_kml_dir: str = os.getenv("ROUTE_KML_DIR", "data/kml")

    cloudinary_cloud_name: str = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    cloudinary_api_key: str = os.getenv("CLOUDINARY_API_KEY", "")
    cloudinary_api_secret: str = os.getenv("CLOUDINARY_API_SECRET", "")
    cloudinary_folder: str = os.getenv("CLOUDINARY_FOLDER", "fiber_rescue/photos")
    # Cloudinary SDK dùng urllib3 trực tiếp, KHÔNG tự đọc HTTP_PROXY/HTTPS_PROXY
    # như httpx (Telegram) -> phải khai báo rõ nếu máy chỉ ra internet qua proxy.
    cloudinary_proxy: str = os.getenv(
        "CLOUDINARY_PROXY",
        os.getenv("HTTPS_PROXY", os.getenv("https_proxy", os.getenv("HTTP_PROXY", os.getenv("http_proxy", "")))),
    )

    admin_telegram_ids: Tuple[int, ...] = field(
        default_factory=lambda: _parse_admin_ids(os.getenv("ADMIN_TELEGRAM_IDS", ""))
    )

    # ---- OCR / coordinate extraction ----
    # Provider OCR cloud, KHÔNG hard-code trong code — đổi thứ tự/thêm bớt
    # provider chỉ cần sửa biến này (tên phải khớp key trong
    # ocr/service.py::_PROVIDER_REGISTRY). Mặc định: OCR.space (free) trước,
    # Google Cloud Vision sau làm fallback khi OCR.space không đọc được toạ độ.
    ocr_provider_order: Tuple[str, ...] = field(
        default_factory=lambda: tuple(
            p.strip() for p in os.getenv("OCR_PROVIDER_ORDER", "ocr_space,google_vision").split(",") if p.strip()
        )
    )
    ocr_space_api_key: str = os.getenv("OCR_SPACE_API_KEY", "")
    google_vision_api_key: str = os.getenv("GOOGLE_VISION_API_KEY", "")
    ocr_request_timeout_seconds: float = float(os.getenv("OCR_REQUEST_TIMEOUT_SECONDS", "20"))
    ocr_min_confidence: float = float(os.getenv("OCR_MIN_CONFIDENCE", "0.3"))

    # Worker polling DB-backed queue (bảng coordinate_extraction) — V1 chưa cần Redis/Celery.
    ocr_worker_poll_interval_seconds: float = float(os.getenv("OCR_WORKER_POLL_INTERVAL_SECONDS", "5"))
    ocr_worker_batch_size: int = int(os.getenv("OCR_WORKER_BATCH_SIZE", "5"))
    # Lỗi TẠM THỜI (mạng/timeout/OCR server chưa sẵn sàng) được tự requeue tối đa
    # số lần này trước khi chuyển hẳn sang FAILED (lỗi OCR đọc sai/không match
    # thì KHÔNG retry vì có retry cũng vẫn vậy - xem workers/ocr_worker.py).
    ocr_worker_max_retries: int = int(os.getenv("OCR_WORKER_MAX_RETRIES", "3"))

    # Sai khác giữa toạ độ OCR và GPS Telegram (mét) vượt ngưỡng này -> coordinate_status = CONFLICT.
    coordinate_conflict_threshold_m: float = float(os.getenv("COORDINATE_CONFLICT_THRESHOLD_M", "500"))

    # Lọc kết quả OCR sai lệch bằng bounding-box Việt Nam (bật mặc định).
    coordinate_validate_vn_bounds: bool = os.getenv("COORDINATE_VALIDATE_VN_BOUNDS", "true").lower() == "true"
    vn_lat_min: float = float(os.getenv("VN_LAT_MIN", "8.0"))
    vn_lat_max: float = float(os.getenv("VN_LAT_MAX", "23.5"))
    vn_lon_min: float = float(os.getenv("VN_LON_MIN", "102.0"))
    vn_lon_max: float = float(os.getenv("VN_LON_MAX", "110.0"))

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
