import asyncio
import logging
import uuid
from typing import Dict

from telegram import File

from config.settings import settings
from utils.cloudinary_client import upload_image_from_url

logger = logging.getLogger(__name__)


class PhotoService:
    """Điều phối lưu ảnh: KHÔNG tải bytes ảnh về máy chủ, chỉ gọi API.

    Luồng: Telegram (file_id) -> getFile -> Telegram file URL -> Cloudinary
    (tự fetch qua URL đó) -> trả về secure_url/public_id/asset_id.
    Máy chủ chỉ chuyển tiếp 2 lệnh API nhỏ, không xử lý dữ liệu ảnh.
    """

    async def save_photo(self, tg_file: File, session_id: str, photo_type: str) -> Dict[str, str]:
        public_id = f"{photo_type.lower()}_{uuid.uuid4().hex}"
        folder = f"{settings.cloudinary_folder}/{session_id}"

        # tg_file.file_path (do PTB trả về từ getFile) là URL đầy đủ trên
        # server Telegram -> đưa thẳng cho Cloudinary tự tải, không qua RAM bot.
        # upload_image_from_url dùng requests (đồng bộ/blocking) -> chạy trong
        # thread riêng để không chặn event loop của bot.
        return await asyncio.to_thread(
            upload_image_from_url, tg_file.file_path, public_id, folder
        )
