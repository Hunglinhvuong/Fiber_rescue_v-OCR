import re
from itertools import permutations
from typing import Dict, List, Optional

from ocr.models import ParsedCoordinate

# Khoảng toạ độ lãnh thổ Việt Nam (nới rộng nhẹ để không loại nhầm khu vực
# biên giới/hải đảo).
_VN_LAT_RANGE = (8.5, 23.0)
_VN_LON_RANGE = (101.5, 110.0)

# Dùng \b để bắt độc lập các chữ cái bán cầu, tránh nuốt chữ N trong "Network"
_HEMI = r"\b[NSEWnsew]\b"

# Không cho phép khoảng trắng giữa dấu phân cách thập phân để tránh gộp "9, 2026" -> "9.2026"
_NUM = r"[-+]?\d{1,3}(?:[.,]\d{3,9})"
_NUM_RE = re.compile(_NUM)

_DEG = r"\d{1,3}"
_MIN_SEC = r"\d{1,2}(?:[.,]\d+)?"

# Pattern gạt bỏ nhiễu Ngày/Tháng/Năm & Giờ GMT trước khi parse
_RE_NOISE_DATE_TIME = re.compile(
    r"(?:thg|tháng)\s*\d{1,2}\s*,\s*\d{4}|GMT\s*[-+]\s*\d{1,2}(?::\d{2})?|\d{1,2}:\d{2}(?::\d{2})?",
    re.IGNORECASE,
)

# ---- Pattern LABELED: nhãn riêng "LAT: 18.678456" / "Vĩ độ: 18.678456" ----
_RE_LABELED_LAT = re.compile(
    r"(?:LAT|LATITUDE|VI\s*DO|VĨ\s*ĐỘ)\s*[:=]?\s*(" + _NUM + r")", re.IGNORECASE
)
_RE_LABELED_LON = re.compile(
    r"(?:LONG?|LONGITUDE|KINH\s*DO|KINH\s*ĐỘ)\s*[:=]?\s*(" + _NUM + r")", re.IGNORECASE
)

# ---- Pattern Compact DMS (Dạng liền 192542N hoặc 192542.5N -> 19°25'42.5"N) ----
_RE_COMPACT_DMS = re.compile(
    r"\b(?P<deg>\d{2,3})(?P<min>\d{2})(?P<sec>\d{2}(?:[.,]\d+)?)\s*(?P<hemi>[NSEWnsew])\b"
)

# ---- Pattern DMS/DDM có ký hiệu °/'/" ----
_RE_DMS_SYMBOL = re.compile(
    r"(?:(?P<hpre>" + _HEMI + r")\s*)?"
    r"(?P<deg>" + _DEG + r")\s*[°ºo]\s*"
    r"(?P<min>" + _MIN_SEC + r")\s*['’′]\s*"
    r"(?:(?P<sec>" + _MIN_SEC + r")\s*[\"″”]\s*)?"
    r"(?P<hpost>" + _HEMI + r")?"
)

# ---- Pattern DMS/DDM KHÔNG ký hiệu, cách nhau bằng khoảng trắng ----
_RE_DMS_SPACED_PREFIX = re.compile(
    r"(?P<hpre>" + _HEMI + r")\s+"
    r"(?P<deg>" + _DEG + r")\s+"
    r"(?P<min>" + _MIN_SEC + r")"
    r"(?:\s+(?P<sec>" + _MIN_SEC + r"))?"
)
_RE_DMS_SPACED_SUFFIX = re.compile(
    r"(?P<deg>" + _DEG + r")\s+"
    r"(?P<min>" + _MIN_SEC + r")"
    r"(?:\s+(?P<sec>" + _MIN_SEC + r"))?"
    r"\s*(?P<hpost>" + _HEMI + r")"
)

# ---- Pattern DECIMAL_PAIR: cặp thập phân ĐỨNG CẠNH NHAU ----
_RE_DECIMAL_PAIR = re.compile(
    r"(?:(?P<h1pre>" + _HEMI + r")\s*)?(?P<v1>" + _NUM + r")\s*°?\s*(?P<h1post>" + _HEMI + r")?"
    r"\s*[,;/\s]\s*"
    r"(?:(?P<h2pre>" + _HEMI + r")\s*)?(?P<v2>" + _NUM + r")\s*°?\s*(?P<h2post>" + _HEMI + r")?"
)


def _sanitize_text(text: str) -> str:
    """Loại bỏ chuỗi ngày tháng, giờ GMT gây nhiễu trước khi parse coordinate."""
    return _RE_NOISE_DATE_TIME.sub(" ", text)


def _to_float(raw: str) -> float:
    return float(raw.replace(" ", "").replace(",", "."))


def _in_range(value: float, rng: tuple) -> bool:
    lo, hi = rng
    return lo <= abs(value) <= hi


def _apply_hemisphere(value: float, hemi: str) -> float:
    hemi = hemi.upper()
    if hemi in ("S", "W"):
        return -abs(value)
    if hemi in ("N", "E"):
        return abs(value)
    return value


def _resolve_pair(v1: float, h1: str, v2: float, h2: str) -> tuple:
    v1 = _apply_hemisphere(v1, h1)
    v2 = _apply_hemisphere(v2, h2)

    if h1 in ("N", "S") and h2 in ("E", "W"):
        return v1, v2
    if h1 in ("E", "W") and h2 in ("N", "S"):
        return v2, v1

    if _in_range(v1, _VN_LAT_RANGE) and _in_range(v2, _VN_LON_RANGE):
        return v1, v2
    if _in_range(v1, _VN_LON_RANGE) and _in_range(v2, _VN_LAT_RANGE):
        return v2, v1

    return v1, v2


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


def _try_compact_dms(text: str) -> Optional[ParsedCoordinate]:
    """Bắt các tọa độ định dạng compact liền nhau như 192542N 1057174E"""
    matches = list(_RE_COMPACT_DMS.finditer(text))
    if len(matches) < 2:
        return None

    m1, m2 = matches[0], matches[1]
    v1 = _dms_magnitude(m1.group("deg"), m1.group("min"), m1.group("sec"))
    v2 = _dms_magnitude(m2.group("deg"), m2.group("min"), m2.group("sec"))
    h1 = m1.group("hemi").upper()
    h2 = m2.group("hemi").upper()

    lat, lon = _resolve_pair(v1, h1, v2, h2)
    return ParsedCoordinate(
        latitude=lat,
        longitude=lon,
        raw_match=f"{m1.group(0)} {m2.group(0)}",
        pattern_name="COMPACT_DMS",
    )


def _dms_magnitude(deg: str, minute: Optional[str], sec: Optional[str]) -> float:
    d = float(deg)
    m = float((minute or "0").replace(" ", "").replace(",", "."))
    s = float((sec or "0").replace(" ", "").replace(",", ".")) if sec else 0.0
    return d + m / 60 + s / 3600


def _token_from_match(m: "re.Match", source: str) -> Dict:
    groups = m.groupdict()
    return {
        "start": m.start(),
        "end": m.end(),
        "magnitude": _dms_magnitude(groups["deg"], groups.get("min"), groups.get("sec")),
        "hemi": (groups.get("hpre") or groups.get("hpost") or "").upper(),
        "raw": m.group(0).strip(),
        "source": source,
    }


def _extract_dms_tokens(text: str) -> List[Dict]:
    candidates: List[Dict] = []
    for m in _RE_DMS_SYMBOL.finditer(text):
        candidates.append(_token_from_match(m, "symbol"))
    for m in _RE_DMS_SPACED_PREFIX.finditer(text):
        candidates.append(_token_from_match(m, "spaced"))
    for m in _RE_DMS_SPACED_SUFFIX.finditer(text):
        candidates.append(_token_from_match(m, "spaced"))

    candidates.sort(key=lambda c: (c["start"], 0 if c["source"] == "symbol" else 1))

    tokens: List[Dict] = []
    used_spans: List[tuple] = []
    for c in candidates:
        if any(c["start"] < e and c["end"] > s for s, e in used_spans):
            continue
        used_spans.append((c["start"], c["end"]))
        tokens.append(c)

    tokens.sort(key=lambda c: c["start"])
    return tokens


def _try_dms(text: str) -> Optional[ParsedCoordinate]:
    tokens = _extract_dms_tokens(text)
    if len(tokens) < 2:
        return None

    t1, t2 = tokens[0], tokens[1]
    lat, lon = _resolve_pair(t1["magnitude"], t1["hemi"], t2["magnitude"], t2["hemi"])
    return ParsedCoordinate(
        latitude=lat,
        longitude=lon,
        raw_match=f"{t1['raw']} {t2['raw']}",
        pattern_name="DMS",
    )


def _try_decimal_pair(text: str) -> Optional[ParsedCoordinate]:
    match = _RE_DECIMAL_PAIR.search(text)
    if not match:
        return None

    v1 = _to_float(match.group("v1"))
    v2 = _to_float(match.group("v2"))
    h1 = (match.group("h1pre") or match.group("h1post") or "").upper()
    h2 = (match.group("h2pre") or match.group("h2post") or "").upper()

    lat, lon = _resolve_pair(v1, h1, v2, h2)
    return ParsedCoordinate(latitude=lat, longitude=lon, raw_match=match.group(0), pattern_name="DECIMAL_PAIR")


def _try_bbox_scan(text: str) -> Optional[ParsedCoordinate]:
    numbers = [
        {"value": _to_float(m.group(0)), "start": m.start(), "raw": m.group(0)}
        for m in _NUM_RE.finditer(text)
    ]
    if len(numbers) < 2:
        return None

    best = None
    for a, b in permutations(numbers, 2):
        if _in_range(a["value"], _VN_LAT_RANGE) and _in_range(b["value"], _VN_LON_RANGE):
            distance = abs(a["start"] - b["start"])
            if best is None or distance < best[2]:
                best = (a, b, distance)

    if best is None:
        return None

    a, b, _dist = best
    return ParsedCoordinate(
        latitude=abs(a["value"]),
        longitude=abs(b["value"]),
        raw_match=f"{a['raw']} .. {b['raw']}",
        pattern_name="BBOX_SCAN",
    )


def parse_coordinates(text: str) -> Optional[ParsedCoordinate]:
    if not text:
        return None

    # Tiền xử lý để loại bỏ các chuỗi ngày tháng / giờ gây nhiễu
    cleaned_text = _sanitize_text(text)

    for parser_fn in (_try_labeled, _try_compact_dms, _try_dms, _try_decimal_pair, _try_bbox_scan):
        result = parser_fn(cleaned_text)
        if result is not None:
            return result
    return None