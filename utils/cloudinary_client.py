"""
Client Cloudinary tự viết bằng `requests`, KHÔNG dùng SDK `cloudinary` chính thức.

Lý do: bản SDK cloudinary (urllib3 nội bộ) không áp dụng đúng `api_proxy` cho
API listing (cloudinary.api.resources), khiến máy chủ chỉ ra internet qua
proxy (HTTP_PROXY/HTTPS_PROXY) không kết nối được. `requests` hỗ trợ `proxies=`
ổn định, rõ ràng, không phụ thuộc hành vi nội bộ khó đoán của SDK.
"""
import hashlib
import time
from typing import Dict, Optional

import requests

from config.settings import settings


def _get_proxies() -> Optional[Dict[str, str]]:
    if not settings.cloudinary_proxy:
        return None
    return {"http": settings.cloudinary_proxy, "https": settings.cloudinary_proxy}


def _sign_params(params: Dict[str, str], api_secret: str) -> str:
    """Thuật toán ký request của Cloudinary: nối các tham số (sắp xếp theo key)
    dạng key=value&key2=value2, cộng api_secret, rồi SHA1."""
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params.keys()))
    return hashlib.sha1((to_sign + api_secret).encode("utf-8")).hexdigest()


def upload_image_from_url(source_url: str, public_id: str, folder: str) -> Dict[str, Optional[str]]:
    """Upload 1 ảnh lên Cloudinary bằng cách đưa THẲNG URL nguồn (VD: link file
    Telegram) cho Cloudinary tự tải — máy chủ của bot KHÔNG tải ảnh về, chỉ gửi
    1 request nhỏ (JSON/form, không có bytes ảnh) rồi nhận lại metadata.
    Trả về {"secure_url", "public_id", "asset_id"}.
    """
    timestamp = str(int(time.time()))
    params_to_sign = {"folder": folder, "public_id": public_id, "timestamp": timestamp}
    signature = _sign_params(params_to_sign, settings.cloudinary_api_secret)

    url = f"https://api.cloudinary.com/v1_1/{settings.cloudinary_cloud_name}/image/upload"
    data = {
        **params_to_sign,
        "api_key": settings.cloudinary_api_key,
        "signature": signature,
        "file": source_url,  # Cloudinary tự fetch ảnh từ URL này (remote fetch upload)
    }

    resp = requests.post(url, data=data, proxies=_get_proxies(), timeout=30)
    resp.raise_for_status()
    result = resp.json()
    return {
        "secure_url": result["secure_url"],
        "public_id": result["public_id"],
        "asset_id": result.get("asset_id"),
    }


def upload_image_bytes(file_bytes: bytes, public_id: str, folder: str) -> Dict[str, Optional[str]]:
    """Upload 1 ảnh (đọc trực tiếp từ đĩa) lên Cloudinary bằng multipart form.
    Chỉ dùng cho script migrate dữ liệu cũ (đọc file local có sẵn trên server)
    — bot chính KHÔNG dùng hàm này (bot dùng upload_image_from_url, không tải
    bytes về máy chủ)."""
    timestamp = str(int(time.time()))
    params_to_sign = {"folder": folder, "public_id": public_id, "timestamp": timestamp}
    signature = _sign_params(params_to_sign, settings.cloudinary_api_secret)

    url = f"https://api.cloudinary.com/v1_1/{settings.cloudinary_cloud_name}/image/upload"
    data = {**params_to_sign, "api_key": settings.cloudinary_api_key, "signature": signature}
    files = {"file": ("photo.jpg", file_bytes, "image/jpeg")}

    resp = requests.post(url, data=data, files=files, proxies=_get_proxies(), timeout=60)
    resp.raise_for_status()
    result = resp.json()
    return {
        "secure_url": result["secure_url"],
        "public_id": result["public_id"],
        "asset_id": result.get("asset_id"),
    }


def list_all_resources(prefix: str = "") -> Dict[str, str]:
    """Liệt kê toàn bộ ảnh trên Cloudinary (Admin API, có phân trang).
    Trả về dict {basename_không_đuôi: secure_url}."""
    mapping: Dict[str, str] = {}
    next_cursor = None
    url = f"https://api.cloudinary.com/v1_1/{settings.cloudinary_cloud_name}/resources/image/upload"
    auth = (settings.cloudinary_api_key, settings.cloudinary_api_secret)

    while True:
        params = {"max_results": 500}
        if prefix:
            params["prefix"] = prefix
        if next_cursor:
            params["next_cursor"] = next_cursor

        resp = requests.get(url, auth=auth, params=params, proxies=_get_proxies(), timeout=30)
        resp.raise_for_status()
        result = resp.json()

        for res in result.get("resources", []):
            basename = res["public_id"].rsplit("/", 1)[-1]
            mapping[basename] = res["secure_url"]

        next_cursor = result.get("next_cursor")
        if not next_cursor:
            break

    return mapping
