import glob
import os
import unicodedata
from typing import List, Optional, Tuple
from xml.etree import ElementTree as ET

from config.settings import settings

Coordinate = Tuple[float, float]  # (lat, lon)


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def _normalize(text: str) -> str:
    return _strip_accents(text).lower().strip()


def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _find_kml_file(route_code: str, route_name: str) -> Optional[str]:
    """Tìm file KML khớp với tuyến theo route_code hoặc route_name.
    Thứ tự ưu tiên: khớp tên file chính xác -> khớp tên đã chuẩn hoá (bỏ dấu,
    thường hoá) -> tên file chứa route_name/route_code."""
    kml_dir = settings.route_kml_dir
    if not os.path.isdir(kml_dir):
        return None

    for candidate in (f"{route_code}.kml", f"{route_name}.kml"):
        path = os.path.join(kml_dir, candidate)
        if os.path.isfile(path):
            return path

    target_code = _normalize(route_code)
    target_name = _normalize(route_name)
    all_kml = sorted(glob.glob(os.path.join(kml_dir, "*.kml")))

    for path in all_kml:
        stem = _normalize(os.path.splitext(os.path.basename(path))[0])
        if stem == target_code or stem == target_name:
            return path

    for path in all_kml:
        stem = _normalize(os.path.splitext(os.path.basename(path))[0])
        if (target_name and target_name in stem) or (target_code and target_code in stem):
            return path

    return None


def _parse_coordinates(text: str) -> List[Coordinate]:
    points: List[Coordinate] = []
    for token in text.split():
        parts = token.strip().split(",")
        if len(parts) < 2:
            continue
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        points.append((lat, lon))
    return points


def _extract_linestrings(root: ET.Element) -> List[List[Coordinate]]:
    lines: List[List[Coordinate]] = []
    for elem in root.iter():
        if _local_tag(elem.tag) != "LineString":
            continue
        for child in elem:
            if _local_tag(child.tag) == "coordinates" and child.text:
                coords = _parse_coordinates(child.text)
                if len(coords) >= 2:
                    lines.append(coords)
    return lines


def load_route_path(route_code: str, route_name: str) -> Optional[List[List[Coordinate]]]:
    """Đọc file KML tương ứng với tuyến (theo route_code hoặc route_name),
    trả về danh sách các đoạn polyline [[(lat, lon), ...], ...] để vẽ trên
    folium.PolyLine. Trả None nếu không tìm thấy file hoặc file không có
    LineString hợp lệ."""
    path = _find_kml_file(route_code, route_name)
    if path is None:
        return None
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return None
    lines = _extract_linestrings(tree.getroot())
    return lines or None


def list_available_kml_routes() -> List[str]:
    """Danh sách tên (không đuôi) các file .kml hiện có trong thư mục cấu hình
    — hữu ích để kiểm tra tuyến nào chưa có file KML tương ứng."""
    kml_dir = settings.route_kml_dir
    if not os.path.isdir(kml_dir):
        return []
    return sorted(
        os.path.splitext(os.path.basename(p))[0]
        for p in glob.glob(os.path.join(kml_dir, "*.kml"))
    )
