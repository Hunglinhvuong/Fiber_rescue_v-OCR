import re
from typing import Optional

from ocr.models import ParsedCoordinate

# ---- Pattern 1: "LAT: 18.678456" + "LONG: 105.681567" (nhãn riêng từng dòng) ----
_RE_LABELED_LAT = re.compile(r"(?:LAT|LATITUDE|VI\s*DO|VĨ\s*ĐỘ)\s*[:=]?\s*([-+]?\d{1,3}[.,]\d{3,8})", re.IGNORECASE)
_RE_LABELED_LON = re.compile(
    r"(?:LONG?|LONGITUDE|KINH\s*DO|KINH\s*ĐỘ)\s*[:=]?\s*([-+]?\d{1,3}[.,]\d{3,8})", re.IGNORECASE
)

# ---- Pattern 2: cặp thập phân "18.678456, 105.681567" ----
_RE_DECIMAL_PAIR = re.compile(
    r"([-+]?\d{1,2}[.,]\d{3,8})\s*[,;]\s*([-+]?\d{1,3}[.,]\d{3,8})"
)

# ---- Pattern 3: DMS "18°40'42.4\"N 105°40'53.6\"E" ----
_RE_DMS = re.compile(
    r"(\d{1,3})\D+(\d{1,2})\D+(\d{1,2}(?:\.\d+)?)\D*([NSEW])",
    re.IGNORECASE,
)


def _to_float(raw: str) -> float:
    return float(raw.replace(",", "."))


def _dms_to_decimal(deg: str, minutes: str, seconds: str, hemisphere: str) -> float:
    value = float(deg) + float(minutes) / 60 + float(seconds) / 3600
    if hemisphere.upper() in ("S", "W"):
        value = -value
    return value


def _try_labeled(text: str) -> Optional[ParsedCoordinate]:
    lat_match = _RE_LABELED_LAT.search(text)
    lon_match = _RE_LABELED_LON.search(text)
    if not lat_match or not lon_match:
        return None
    return ParsedCoordinate(
        latitude=_to_float(lat_match.group(1)),
        longitude=_to_float(lon_match.group(1)),
        raw_match=f"{lat_match.group(0)} | {lon_match.group(0)}",
        pattern_name="LABELED",
    )


def _try_decimal_pair(text: str) -> Optional[ParsedCoordinate]:
    match = _RE_DECIMAL_PAIR.search(text)
    if not match:
        return None
    return ParsedCoordinate(
        latitude=_to_float(match.group(1)),
        longitude=_to_float(match.group(2)),
        raw_match=match.group(0),
        pattern_name="DECIMAL_PAIR",
    )


def _try_dms(text: str) -> Optional[ParsedCoordinate]:
    matches = _RE_DMS.findall(text)
    if len(matches) < 2:
        return None

    lat_val = lon_val = None
    raw_parts = []
    for deg, minutes, seconds, hemi in matches[:2]:
        val = _dms_to_decimal(deg, minutes, seconds, hemi)
        raw_parts.append(f"{deg}°{minutes}'{seconds}\"{hemi}")
        if hemi.upper() in ("N", "S"):
            lat_val = val
        elif hemi.upper() in ("E", "W"):
            lon_val = val

    if lat_val is None or lon_val is None:
        return None

    return ParsedCoordinate(
        latitude=lat_val,
        longitude=lon_val,
        raw_match=" ".join(raw_parts),
        pattern_name="DMS",
    )


def parse_coordinates(text: str) -> Optional[ParsedCoordinate]:
    """Thử lần lượt các pattern, trả về match đầu tiên có ĐỦ lat+long từ
    cùng 1 nguồn. Không bao giờ ghép lat từ pattern này với long từ pattern
    khác. Trả None nếu không tìm thấy gì hợp lệ."""
    if not text:
        return None

    for parser_fn in (_try_labeled, _try_decimal_pair, _try_dms):
        result = parser_fn(text)
        if result is not None:
            return result
    return None
