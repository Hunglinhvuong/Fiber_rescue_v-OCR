import re
from itertools import permutations
from typing import Dict, List, Optional

from ocr.models import ParsedCoordinate

# Khoảng toạ độ lãnh thổ Việt Nam (nới rộng nhẹ để không loại nhầm khu vực
# biên giới/hải đảo). Dùng cho 2 việc:
#  1) suy luận thứ tự lat/long khi text không có nhãn/ký hiệu bán cầu rõ ràng
#  2) lọc "đúng 1 cặp" trong pattern BBOX_SCAN (quét mọi số thực trong ảnh).
# Đây KHÔNG phải bước validate cuối — validate -90..90/-180..180 và biên VN
# chính thức vẫn do CoordinateService đảm nhiệm.
_VN_LAT_RANGE = (7.5, 23.5)
_VN_LON_RANGE = (101.5, 110.0)

_HEMI = r"[NSEWnsew]"
# KHÔNG cho phép khoảng trắng quanh dấu thập phân nữa (từng cho phép để
# chịu lỗi OCR kiểu "18. 678456", nhưng chính điều này khiến cụm ngày/năm
# dạng "9, 2026" (có dấu cách sau dấu phẩy — cách viết ngày tháng rất phổ
# biến) bị bắt nhầm thành số thập phân 9.2026 -> sai vĩ độ. 3-9 chữ số thập
# phân: ảnh checkin chỉ có toạ độ là số nhiều chữ số thập phân như vậy, còn
# giờ/pin/dung lượng thường 0-2 chữ số.
_NUM = r"[-+]?\d{1,3}[.,]\d{3,9}"
_NUM_RE = re.compile(_NUM)

_DEG = r"\d{1,3}"
_MIN_SEC = r"\d{1,2}(?:\s*[.,]\s*\d+)?"

# ---- Khử nhiễu ngày/giờ trước khi parse toạ độ — các cụm số kiểu ngày
# tháng/giờ rất dễ bị BBOX_SCAN hoặc DECIMAL_PAIR bắt nhầm thành toạ độ
# (vd "18 thg 9, 2026 14:56:19 GMT+07:00" từ ảnh check-in). Thay bằng 1
# khoảng trắng (không xoá hẳn) để tránh 2 cụm số ở 2 bên vô tình dính lại
# thành 1 số mới. ----
_RE_NOISE = re.compile(
    r"\b\d{1,2}\s*(?:thg|tháng)\s*\d{1,2}\b"        # "18 thg 9" / "18 tháng 9"
    r"|\b\d{1,2}\s*,\s*(?:19|20)\d{2}\b"            # "9, 2026" (ngày, năm)
    r"|\b\d{1,2}:\d{2}:\d{2}\b"                     # "14:56:19"
    r"|\bGMT\s*[+-]\d{1,2}:\d{2}\b"                 # "GMT+07:00"
    r"|\b\d{1,2}/\d{1,2}/\d{4}\b",                  # "18/09/2026"
    re.IGNORECASE,
)


def _strip_noise(text: str) -> str:
    return _RE_NOISE.sub(" ", text)


# ---- Pattern LABELED: nhãn riêng "LAT: 18.678456" / "Vĩ độ: 18.678456" ----
_RE_LABELED_LAT = re.compile(
    r"(?:LAT|LATITUDE|VI\s*DO|VĨ\s*ĐỘ)\s*[:=]?\s*(" + _NUM + r")", re.IGNORECASE
)
_RE_LABELED_LON = re.compile(
    r"(?:LONG?|LONGITUDE|KINH\s*DO|KINH\s*ĐỘ)\s*[:=]?\s*(" + _NUM + r")", re.IGNORECASE
)

# ---- Pattern DMS/DDM có ký hiệu °/'/" — hemisphere tuỳ chọn vì chính ký
# hiệu độ/phút/giây đã đủ để xác định đây là toạ độ, không cần disambiguate
# thêm ----
_RE_DMS_SYMBOL = re.compile(
    r"(?:(?P<hpre>" + _HEMI + r")\s*)?"
    r"(?P<deg>" + _DEG + r")\s*[°ºo]\s*"
    r"(?P<min>" + _MIN_SEC + r")\s*['’′]\s*"
    r"(?:(?P<sec>" + _MIN_SEC + r")\s*[\"″”]\s*)?"
    r"(?P<hpost>" + _HEMI + r")?"
)

# ---- Pattern DMS/DDM KHÔNG ký hiệu, cách nhau bằng khoảng trắng, ví dụ
# "18 40 42.4 N" hoặc "N 18 40.706". Không có ký hiệu ° ' " nên bắt buộc
# phải có chữ bán cầu N/S/E/W để phân biệt với dãy số bất kỳ (thời gian,
# ID, độ cao...) — nếu không có hemisphere thì bỏ qua, để BBOX_SCAN xử lý ----
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

# ---- LƯU Ý: KHÔNG hỗ trợ DMS dính liền không dấu cách/ký hiệu (vd
# "192542N"). Dạng này quá mơ hồ (không phân biệt được là DMS 19°25'42"
# hay thập phân 19.2542 thiếu dấu chấm, hay số ngẫu nhiên khác) nên chủ
# động KHÔNG parse — thà bỏ qua còn hơn suy đoán sai toạ độ. DMS chỉ được
# chấp nhận khi có ký hiệu °/'/" (_RE_DMS_SYMBOL) hoặc có dấu cách phân
# tách rõ giữa độ/phút/giây (_RE_DMS_SPACED_PREFIX/SUFFIX) ở trên. ----

# ---- Pattern DECIMAL_PAIR: cặp thập phân ĐỨNG CẠNH NHAU, mọi biến thể:
# "18.678456, 105.681567", "18.678456°N 105.681567°E",
# "N 18.678456 E 105.681567" ----
_RE_DECIMAL_PAIR = re.compile(
    r"(?:(?P<h1pre>" + _HEMI + r")\s*)?(?P<v1>" + _NUM + r")\s*°?\s*(?P<h1post>" + _HEMI + r")?"
    r"\s*[,;/\s]\s*"
    r"(?:(?P<h2pre>" + _HEMI + r")\s*)?(?P<v2>" + _NUM + r")\s*°?\s*(?P<h2post>" + _HEMI + r")?"
)

# ---- 1 số thập phân đứng lẻ + hemisphere (không cần số thứ 2 đứng cạnh) —
# dùng cho pattern MIXED: 1 bên là DMS, bên kia là thập phân độ thường ----
_RE_DECIMAL_HEMI = re.compile(r"(?P<v>" + _NUM + r")\s*°?\s*(?P<hemi>" + _HEMI + r")")


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
    """Quyết định giá trị nào là latitude, giá trị nào là longitude + dấu.
    Ưu tiên ký hiệu bán cầu (N/S/E/W) nếu có; nếu không, suy luận theo
    khoảng toạ độ Việt Nam. Không bao giờ ghép lat của cặp này với long của
    cặp khác — cả hai giá trị luôn đến từ CÙNG một match."""
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
    """Quét pattern có ký hiệu °/'/" và pattern cách khoảng trắng — gộp lại
    theo vị trí xuất hiện, loại các match chồng lấp (ưu tiên pattern có ký
    hiệu vì rõ ràng/ít nhầm hơn)."""
    candidates: List[Dict] = []
    for m in _RE_DMS_SYMBOL.finditer(text):
        candidates.append(_token_from_match(m, "symbol"))
    for m in _RE_DMS_SPACED_PREFIX.finditer(text):
        candidates.append(_token_from_match(m, "spaced"))
    for m in _RE_DMS_SPACED_SUFFIX.finditer(text):
        candidates.append(_token_from_match(m, "spaced"))

    _priority = {"symbol": 0, "spaced": 1}
    candidates.sort(key=lambda c: (c["start"], _priority[c["source"]]))

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


def _try_mixed(text: str) -> Optional[ParsedCoordinate]:
    """Trường hợp lai: 1 bên là DMS/DDM (ký hiệu hoặc cách khoảng trắng),
    bên còn lại là số thập phân độ đứng cùng hemisphere như '105.7174E' —
    không đứng cạnh nhau theo kiểu DECIMAL_PAIR (không có dấu phẩy/gạch/
    khoảng trắng nối trực tiếp giữa 2 giá trị). OCR đôi khi đọc lệch định
    dạng giữa lat và long trong cùng 1 ảnh. Chỉ áp dụng khi có ĐÚNG 1 token
    DMS và ĐÚNG 1 số thập phân+hemisphere còn lại trong text — nếu nhiều
    hơn thì quá mơ hồ, bỏ qua."""
    dms_tokens = _extract_dms_tokens(text)
    if len(dms_tokens) != 1:
        return None
    dms_token = dms_tokens[0]

    decimal_candidates = [
        m
        for m in _RE_DECIMAL_HEMI.finditer(text)
        if not (m.start() < dms_token["end"] and m.end() > dms_token["start"])
    ]
    if len(decimal_candidates) != 1:
        return None
    dec = decimal_candidates[0]

    lat, lon = _resolve_pair(
        dms_token["magnitude"], dms_token["hemi"], _to_float(dec.group("v")), dec.group("hemi").upper()
    )
    return ParsedCoordinate(
        latitude=lat,
        longitude=lon,
        raw_match=f"{dms_token['raw']} {dec.group(0).strip()}",
        pattern_name="MIXED",
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
    """Fallback cuối: quét TẤT CẢ số thực có 3-9 chữ số thập phân trong text
    (không cần liền nhau, không cần nhãn/ký hiệu), rồi chọn ra đúng 1 cặp
    (lat, long) là cặp mà 1 số rơi vào khoảng vĩ độ VN và số khác rơi vào
    khoảng kinh độ VN. Dành cho ảnh checkin chỉ có toạ độ + ngày giờ, không
    có nhãn 'Lat/Long' hay dấu phân tách rõ ràng.
    Nếu có nhiều cặp thoả bounding box, chọn cặp gần nhau nhất trong text
    (nhiều khả năng là 1 cặp toạ độ thật hơn 2 số không liên quan)."""
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
    """Khử nhiễu ngày/giờ trước, rồi thử lần lượt các pattern theo độ tin
    cậy giảm dần: LABELED -> DMS/DDM (ký hiệu hoặc cách khoảng trắng, KHÔNG
    chấp nhận số viết liền không dấu cách/ký hiệu) -> MIXED (1 bên DMS, 1
    bên thập phân) -> DECIMAL_PAIR (2 số thập phân liền nhau, không dấu
    cách) -> BBOX_SCAN (quét mọi số + bounding box VN). Trả về match đầu
    tiên có ĐỦ lat+long từ CÙNG một nguồn — không bao giờ ghép lat từ
    pattern/nguồn này với long từ pattern/nguồn khác. Trả None nếu không
    tìm thấy gì hợp lệ."""
    if not text:
        return None

    text = _strip_noise(text)

    for parser_fn in (_try_labeled, _try_dms, _try_mixed, _try_decimal_pair, _try_bbox_scan):
        result = parser_fn(text)
        if result is not None:
            return result
    return None
