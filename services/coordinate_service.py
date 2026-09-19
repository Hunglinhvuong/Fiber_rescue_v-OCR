import logging
import math
from typing import Optional

import asyncpg

from config.settings import settings
from database.repositories.coordinate_repository import CoordinateExtractionRepository
from database.repositories.incident_repository import IncidentRepository
from ocr.models import CoordinateCandidate

logger = logging.getLogger(__name__)


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Khoảng cách 2 điểm trên mặt cầu Trái Đất (mét)."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def is_within_valid_range(latitude: float, longitude: float) -> bool:
    return -90 <= latitude <= 90 and -180 <= longitude <= 180


def is_within_vietnam_bounds(latitude: float, longitude: float) -> bool:
    if not settings.coordinate_validate_vn_bounds:
        return True
    return (
        settings.vn_lat_min <= latitude <= settings.vn_lat_max
        and settings.vn_lon_min <= longitude <= settings.vn_lon_max
    )


class CoordinateService:
    """Chịu trách nhiệm DUY NHẤT: validate nguồn ứng viên, chọn toạ độ cuối
    cùng theo thứ tự ưu tiên OCR_AFTER > OCR_BEFORE > GPS, tính khoảng cách
    đối soát, và ghi kết quả vào incident. KHÔNG gọi OCR, KHÔNG parse text."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.incident_repo = IncidentRepository(pool)
        self.extraction_repo = CoordinateExtractionRepository(pool)

    async def recompute_final_coordinate(self, incident_id: int) -> None:
        gps_row = await self.incident_repo.get_coordinates(incident_id)
        if gps_row is None:
            logger.warning("recompute_final_coordinate: incident %s không tồn tại", incident_id)
            return

        gps_lat, gps_lon = gps_row["gps_latitude"], gps_row["gps_longitude"]

        after_row = await self.extraction_repo.get_latest_success_by_source(incident_id, "AFTER")
        before_row = await self.extraction_repo.get_latest_success_by_source(incident_id, "BEFORE")

        candidate: Optional[CoordinateCandidate] = None
        if after_row is not None:
            candidate = CoordinateCandidate("OCR_AFTER", after_row["latitude"], after_row["longitude"])
        elif before_row is not None:
            candidate = CoordinateCandidate("OCR_BEFORE", before_row["latitude"], before_row["longitude"])

        if candidate is None:
            # Chưa có OCR nào thành công (đang PENDING, hoặc cả 2 đều FAILED/INVALID) -> giữ GPS.
            await self.incident_repo.update_final_coordinate(
                incident_id,
                latitude=gps_lat,
                longitude=gps_lon,
                coordinate_source="GPS",
                coordinate_status="GPS_ONLY",
                coordinate_distance_m=None,
                ocr_latitude=None,
                ocr_longitude=None,
            )
            return

        distance_m = None
        coordinate_status = "CONFIRMED"
        if gps_lat is not None and gps_lon is not None:
            distance_m = haversine_distance_m(candidate.latitude, candidate.longitude, gps_lat, gps_lon)
            if distance_m > settings.coordinate_conflict_threshold_m:
                coordinate_status = "CONFLICT"

        await self.incident_repo.update_final_coordinate(
            incident_id,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
            coordinate_source=candidate.source,
            coordinate_status=coordinate_status,
            coordinate_distance_m=distance_m,
            ocr_latitude=candidate.latitude,
            ocr_longitude=candidate.longitude,
        )
        logger.info(
            "incident %s: toạ độ cuối = %s (%.6f, %.6f) status=%s distance=%s",
            incident_id, candidate.source, candidate.latitude, candidate.longitude,
            coordinate_status, distance_m,
        )
