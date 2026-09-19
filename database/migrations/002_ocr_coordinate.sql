-- ============================================================
-- Migration 002: OCR toạ độ từ ảnh sự cố
--
-- Giữ nguyên incident.latitude/longitude (đã dùng khắp dashboard/report)
-- làm cột "toạ độ cuối cùng". Bổ sung cột audit GPS gốc + OCR gốc, và bảng
-- coordinate_extraction lưu từng lần OCR (1 dòng / ảnh BEFORE hoặc AFTER).
-- ============================================================

BEGIN;

ALTER TABLE incident
    ADD COLUMN IF NOT EXISTS gps_latitude          NUMERIC(10,7),
    ADD COLUMN IF NOT EXISTS gps_longitude         NUMERIC(10,7),
    ADD COLUMN IF NOT EXISTS ocr_latitude           NUMERIC(10,7),
    ADD COLUMN IF NOT EXISTS ocr_longitude          NUMERIC(10,7),
    ADD COLUMN IF NOT EXISTS coordinate_source      VARCHAR(20) NOT NULL DEFAULT 'GPS',
    ADD COLUMN IF NOT EXISTS coordinate_status      VARCHAR(20) NOT NULL DEFAULT 'GPS_ONLY',
    ADD COLUMN IF NOT EXISTS coordinate_distance_m  NUMERIC(10,2);

-- Backfill dữ liệu cũ: coi toạ độ hiện có là GPS gốc, đã "chốt".
UPDATE incident
SET gps_latitude = latitude,
    gps_longitude = longitude,
    coordinate_source = 'GPS',
    coordinate_status = 'GPS_ONLY'
WHERE gps_latitude IS NULL;

ALTER TABLE incident
    ADD CONSTRAINT chk_incident_coordinate_source
        CHECK (coordinate_source IN ('GPS', 'OCR_BEFORE', 'OCR_AFTER')),
    ADD CONSTRAINT chk_incident_coordinate_status
        CHECK (coordinate_status IN ('PENDING', 'CONFIRMED', 'CONFLICT', 'GPS_ONLY', 'FAILED')),
    ADD CONSTRAINT chk_incident_gps_latitude
        CHECK (gps_latitude IS NULL OR (gps_latitude >= -90 AND gps_latitude <= 90)),
    ADD CONSTRAINT chk_incident_gps_longitude
        CHECK (gps_longitude IS NULL OR (gps_longitude >= -180 AND gps_longitude <= 180)),
    ADD CONSTRAINT chk_incident_ocr_latitude
        CHECK (ocr_latitude IS NULL OR (ocr_latitude >= -90 AND ocr_latitude <= 90)),
    ADD CONSTRAINT chk_incident_ocr_longitude
        CHECK (ocr_longitude IS NULL OR (ocr_longitude >= -180 AND ocr_longitude <= 180));

CREATE TABLE IF NOT EXISTS coordinate_extraction (
    coordinate_extraction_id BIGSERIAL PRIMARY KEY,

    incident_id              BIGINT NOT NULL,
    photo_id                 BIGINT NOT NULL,

    source                   VARCHAR(20) NOT NULL,

    status                   VARCHAR(20) NOT NULL DEFAULT 'PENDING',

    raw_text                 TEXT,
    latitude                 NUMERIC(10,7),
    longitude                NUMERIC(10,7),
    confidence                NUMERIC(5,4),

    error_message             TEXT,

    created_at                TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_coordinate_extraction_incident
        FOREIGN KEY (incident_id) REFERENCES incident(incident_id) ON DELETE CASCADE,

    CONSTRAINT fk_coordinate_extraction_photo
        FOREIGN KEY (photo_id) REFERENCES incident_photo(incident_photo_id) ON DELETE CASCADE,

    CONSTRAINT uq_coordinate_extraction_photo UNIQUE (photo_id),

    CONSTRAINT chk_coordinate_extraction_source
        CHECK (source IN ('BEFORE', 'AFTER')),

    CONSTRAINT chk_coordinate_extraction_status
        CHECK (status IN ('PENDING', 'PROCESSING', 'SUCCESS', 'INVALID', 'FAILED')),

    CONSTRAINT chk_coordinate_extraction_latitude
        CHECK (latitude IS NULL OR (latitude >= -90 AND latitude <= 90)),

    CONSTRAINT chk_coordinate_extraction_longitude
        CHECK (longitude IS NULL OR (longitude >= -180 AND longitude <= 180))
);

CREATE INDEX IF NOT EXISTS idx_coordinate_extraction_status
    ON coordinate_extraction(status, created_at);

CREATE INDEX IF NOT EXISTS idx_coordinate_extraction_incident
    ON coordinate_extraction(incident_id);

CREATE TRIGGER trg_coordinate_extraction_updated_at
BEFORE UPDATE ON coordinate_extraction
FOR EACH ROW
EXECUTE FUNCTION fn_set_updated_at();

COMMIT;
