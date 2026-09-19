-- ============================================================
-- FIBER RESCUE MANAGEMENT SYSTEM
-- PostgreSQL Schema V1.1
--
-- Business model:
--   F8   : UNDERGROUND / KV100
--   ADSS : UNDERGROUND / KV100 / KV200 / KV300 / KV400 / KV500
--
-- Material groups:
--   CABLE
--   HANGER
--   ANCHOR
--   SPLICE_CLOSURE
--   CLAMP
--   PIPE
--   POLE_BAND
--   OTHERS
-- ============================================================

BEGIN;


-- ============================================================
-- 1. COMMON FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 2. APP USER
-- ============================================================

CREATE TABLE app_user (
    user_id              BIGSERIAL PRIMARY KEY,

    telegram_user_id     BIGINT NOT NULL UNIQUE,
    telegram_username    VARCHAR(100),

    full_name            VARCHAR(150) NOT NULL,
    team_name            VARCHAR(150),

    role                 VARCHAR(30) NOT NULL DEFAULT 'FIELD',

    status               VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',

    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_app_user_role
        CHECK (
            role IN (
                'ADMIN',
                'MANAGER',
                'FIELD',
                'VIEWER'
            )
        ),

    CONSTRAINT chk_app_user_status
        CHECK (
            status IN (
                'ACTIVE',
                'INACTIVE'
            )
        )
);


CREATE INDEX idx_app_user_status
ON app_user(status);


CREATE TRIGGER trg_app_user_updated_at
BEFORE UPDATE ON app_user
FOR EACH ROW
EXECUTE FUNCTION fn_set_updated_at();


-- ============================================================
-- 3. FIBER ROUTE
-- ============================================================

CREATE TABLE fiber_route (
    route_id             BIGSERIAL PRIMARY KEY,

    route_code           VARCHAR(100) NOT NULL UNIQUE,
    route_name           VARCHAR(255) NOT NULL,

    route_type           VARCHAR(50),

    length_km            NUMERIC(12,3),

    cable_type           VARCHAR(20) NOT NULL,
    fiber_count          INTEGER NOT NULL,

    province             VARCHAR(100),

    status               VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',

    description          TEXT,

    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_fiber_route_cable_type
        CHECK (
            cable_type IN (
                'F8',
                'ADSS'
            )
        ),

    CONSTRAINT chk_fiber_route_fiber_count
        CHECK (
            fiber_count IN (
                6,
                12,
                24
            )
        ),

    CONSTRAINT chk_fiber_route_length
        CHECK (
            length_km IS NULL
            OR length_km >= 0
        ),

    CONSTRAINT chk_fiber_route_status
        CHECK (
            status IN (
                'ACTIVE',
                'INACTIVE'
            )
        )
);


CREATE INDEX idx_fiber_route_name
ON fiber_route(route_name);

CREATE INDEX idx_fiber_route_province
ON fiber_route(province);

CREATE INDEX idx_fiber_route_cable
ON fiber_route(cable_type, fiber_count);

CREATE INDEX idx_fiber_route_status
ON fiber_route(status);


CREATE TRIGGER trg_fiber_route_updated_at
BEFORE UPDATE ON fiber_route
FOR EACH ROW
EXECUTE FUNCTION fn_set_updated_at();


-- ============================================================
-- 4. REPAIR SPAN TYPE
-- ============================================================

CREATE TABLE repair_span_type (
    repair_span_type_id  SMALLSERIAL PRIMARY KEY,

    span_code            VARCHAR(30) NOT NULL UNIQUE,

    span_name            VARCHAR(100) NOT NULL,

    span_length_m        INTEGER,

    sort_order           INTEGER NOT NULL DEFAULT 0,

    is_active            BOOLEAN NOT NULL DEFAULT TRUE,

    description          TEXT,

    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_repair_span_length
        CHECK (
            span_length_m IS NULL
            OR span_length_m > 0
        )
);


CREATE INDEX idx_repair_span_active
ON repair_span_type(is_active);


-- ============================================================
-- 5. INCIDENT TYPE
-- ============================================================

CREATE TABLE incident_type (
    incident_type_id     SMALLSERIAL PRIMARY KEY,

    type_code            VARCHAR(50) NOT NULL UNIQUE,

    type_name            VARCHAR(150) NOT NULL,

    description          TEXT,

    is_active            BOOLEAN NOT NULL DEFAULT TRUE,

    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- 6. INCIDENT CAUSE
-- ============================================================

CREATE TABLE incident_cause (
    cause_id             SMALLSERIAL PRIMARY KEY,

    cause_code           VARCHAR(50) NOT NULL UNIQUE,

    cause_name           VARCHAR(150) NOT NULL,

    description          TEXT,

    is_active            BOOLEAN NOT NULL DEFAULT TRUE,

    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- 7. MATERIAL MASTER
--
-- Danh mục vật tư thực tế.
--
-- Không phải tất cả vật tư đều có quy tắc tự động.
--
-- CABLE / HANGER / ANCHOR / SPLICE_CLOSURE:
--     có thể được hệ thống phân loại tự động.
--
-- CLAMP / PIPE / POLE_BAND / OTHERS:
--     không tự phân loại.
-- ============================================================

CREATE TABLE material (
    material_id          BIGSERIAL PRIMARY KEY,

    material_code        VARCHAR(100) NOT NULL UNIQUE,

    material_name        VARCHAR(255) NOT NULL,

    material_group       VARCHAR(30) NOT NULL,

    unit                 VARCHAR(30) NOT NULL,

    description          TEXT,

    is_active            BOOLEAN NOT NULL DEFAULT TRUE,

    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_material_group
        CHECK (
            material_group IN (
                'CABLE',
                'HANGER',
                'ANCHOR',
                'SPLICE_CLOSURE',
                'CLAMP',
                'PIPE',
                'POLE_BAND',
                'OTHERS'
            )
        )
);


CREATE INDEX idx_material_group
ON material(material_group);

CREATE INDEX idx_material_active
ON material(is_active);


CREATE TRIGGER trg_material_updated_at
BEFORE UPDATE ON material
FOR EACH ROW
EXECUTE FUNCTION fn_set_updated_at();


-- ============================================================
-- 8. MATERIAL CLASSIFICATION RULE
--
-- Chỉ dùng cho các vật tư có quy tắc phân loại:
--
-- CABLE
-- SPLICE_CLOSURE
-- HANGER
-- ANCHOR
--
-- Các vật tư:
-- CLAMP / PIPE / POLE_BAND / OTHERS
-- không bắt buộc phải có rule.
-- ============================================================

CREATE TABLE material_rule (
    material_rule_id     BIGSERIAL PRIMARY KEY,

    material_id          BIGINT NOT NULL,

    cable_type           VARCHAR(20),

    fiber_count          INTEGER,

    repair_span_type_id  SMALLINT,

    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_material_rule_material
        FOREIGN KEY (material_id)
        REFERENCES material(material_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_material_rule_span
        FOREIGN KEY (repair_span_type_id)
        REFERENCES repair_span_type(repair_span_type_id),

    CONSTRAINT chk_material_rule_cable
        CHECK (
            cable_type IS NULL
            OR cable_type IN (
                'F8',
                'ADSS'
            )
        ),

    CONSTRAINT chk_material_rule_fiber
        CHECK (
            fiber_count IS NULL
            OR fiber_count IN (
                6,
                12,
                24
            )
        )
);


CREATE INDEX idx_material_rule_lookup
ON material_rule(
    cable_type,
    fiber_count,
    repair_span_type_id
);


-- ============================================================
-- 9. INCIDENT
-- ============================================================

CREATE TABLE incident (
    incident_id          BIGSERIAL PRIMARY KEY,

    incident_code        VARCHAR(50) NOT NULL UNIQUE,

    route_id             BIGINT NOT NULL,

    reported_by          BIGINT NOT NULL,

    incident_type_id     SMALLINT NOT NULL,

    cause_id             SMALLINT,

    repair_span_type_id  SMALLINT NOT NULL,

    latitude             NUMERIC(10,7) NOT NULL,

    longitude            NUMERIC(10,7) NOT NULL,

    location_accuracy_m  NUMERIC(10,2),

    description          TEXT,

    status               VARCHAR(20) NOT NULL DEFAULT 'DRAFT',

    reported_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    completed_at         TIMESTAMP,

    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_incident_route
        FOREIGN KEY (route_id)
        REFERENCES fiber_route(route_id),

    CONSTRAINT fk_incident_reported_by
        FOREIGN KEY (reported_by)
        REFERENCES app_user(user_id),

    CONSTRAINT fk_incident_type
        FOREIGN KEY (incident_type_id)
        REFERENCES incident_type(incident_type_id),

    CONSTRAINT fk_incident_cause
        FOREIGN KEY (cause_id)
        REFERENCES incident_cause(cause_id),

    CONSTRAINT fk_incident_repair_span
        FOREIGN KEY (repair_span_type_id)
        REFERENCES repair_span_type(repair_span_type_id),

    CONSTRAINT chk_incident_latitude
        CHECK (
            latitude >= -90
            AND latitude <= 90
        ),

    CONSTRAINT chk_incident_longitude
        CHECK (
            longitude >= -180
            AND longitude <= 180
        ),

    CONSTRAINT chk_incident_accuracy
        CHECK (
            location_accuracy_m IS NULL
            OR location_accuracy_m >= 0
        ),

    CONSTRAINT chk_incident_status
        CHECK (
            status IN (
                'DRAFT',
                'COMPLETED',
                'CANCELLED'
            )
        )
);


CREATE INDEX idx_incident_route
ON incident(route_id);

CREATE INDEX idx_incident_reported_by
ON incident(reported_by);

CREATE INDEX idx_incident_reported_at
ON incident(reported_at);

CREATE INDEX idx_incident_status
ON incident(status);

CREATE INDEX idx_incident_repair_span
ON incident(repair_span_type_id);


CREATE TRIGGER trg_incident_updated_at
BEFORE UPDATE ON incident
FOR EACH ROW
EXECUTE FUNCTION fn_set_updated_at();


-- ============================================================
-- 10. INCIDENT MATERIAL
--
-- Vật tư thực tế sử dụng cho sự cố.
--
-- quantity:
--   CABLE       -> mét
--   HANGER      -> bộ
--   ANCHOR      -> bộ
--   SPLICE      -> bộ
--   ...
--
-- Không lưu material_name ở đây.
-- Chỉ lưu material_id để tránh trùng dữ liệu.
-- ============================================================

CREATE TABLE incident_material (
    incident_material_id BIGSERIAL PRIMARY KEY,

    incident_id          BIGINT NOT NULL,

    material_id          BIGINT NOT NULL,

    quantity             NUMERIC(14,3) NOT NULL,

    note                 TEXT,

    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_incident_material_incident
        FOREIGN KEY (incident_id)
        REFERENCES incident(incident_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_incident_material_material
        FOREIGN KEY (material_id)
        REFERENCES material(material_id),

    CONSTRAINT chk_incident_material_quantity
        CHECK (
            quantity > 0
        ),

    CONSTRAINT uq_incident_material
        UNIQUE (
            incident_id,
            material_id
        )
);


CREATE INDEX idx_incident_material_incident
ON incident_material(incident_id);

CREATE INDEX idx_incident_material_material
ON incident_material(material_id);


-- ============================================================
-- 11. INCIDENT PHOTO
-- ============================================================

CREATE TABLE incident_photo (
    incident_photo_id       BIGSERIAL PRIMARY KEY,

    incident_id             BIGINT NOT NULL,

    photo_type              VARCHAR(20) NOT NULL,

    telegram_file_id        TEXT,

    telegram_file_unique_id TEXT,

    cloudinary_public_id    TEXT,

    cloudinary_asset_id     TEXT,

    cloudinary_url          TEXT NOT NULL,

    caption                 TEXT,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_incident_photo_incident
        FOREIGN KEY (incident_id)
        REFERENCES incident(incident_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_incident_photo_type
        CHECK (
            photo_type IN (
                'BEFORE',
                'AFTER',
                'OTHER'
            )
        ),

    CONSTRAINT uq_incident_photo_cloudinary_public_id UNIQUE (cloudinary_public_id)
);


CREATE INDEX idx_incident_photo_incident
ON incident_photo(incident_id);


-- ============================================================
-- 12. INCIDENT STATUS HISTORY
-- ============================================================

CREATE TABLE incident_status_history (
    history_id           BIGSERIAL PRIMARY KEY,

    incident_id          BIGINT NOT NULL,

    old_status           VARCHAR(20),

    new_status           VARCHAR(20) NOT NULL,

    changed_by           BIGINT,

    changed_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    note                 TEXT,

    CONSTRAINT fk_status_history_incident
        FOREIGN KEY (incident_id)
        REFERENCES incident(incident_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_status_history_user
        FOREIGN KEY (changed_by)
        REFERENCES app_user(user_id),

    CONSTRAINT chk_status_history_old
        CHECK (
            old_status IS NULL
            OR old_status IN (
                'DRAFT',
                'COMPLETED',
                'CANCELLED'
            )
        ),

    CONSTRAINT chk_status_history_new
        CHECK (
            new_status IN (
                'DRAFT',
                'COMPLETED',
                'CANCELLED'
            )
        )
);


CREATE INDEX idx_status_history_incident
ON incident_status_history(incident_id);


-- ============================================================
-- 13. INCIDENT CODE SEQUENCE
-- ============================================================

CREATE SEQUENCE incident_code_seq
START WITH 1
INCREMENT BY 1;


CREATE OR REPLACE FUNCTION generate_incident_code()
RETURNS VARCHAR AS $$
BEGIN

    RETURN
        'SC' ||
        TO_CHAR(CURRENT_DATE, 'YYYYMMDD') ||
        '-' ||
        LPAD(
            NEXTVAL('incident_code_seq')::TEXT,
            4,
            '0'
        );

END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION fn_set_incident_code()
RETURNS TRIGGER AS $$
BEGIN

    IF NEW.incident_code IS NULL
       OR NEW.incident_code = '' THEN

        NEW.incident_code :=
            generate_incident_code();

    END IF;

    RETURN NEW;

END;
$$ LANGUAGE plpgsql;


CREATE TRIGGER trg_incident_code
BEFORE INSERT ON incident
FOR EACH ROW
EXECUTE FUNCTION fn_set_incident_code();


-- ============================================================
-- 14. SEED REPAIR SPAN
-- ============================================================

INSERT INTO repair_span_type
(
    span_code,
    span_name,
    span_length_m,
    sort_order,
    description
)
VALUES
(
    'UNDERGROUND',
    'Cáp ngầm',
    NULL,
    10,
    'Đoạn cáp triển khai ngầm'
),
(
    'KV100',
    'Khoảng vượt 100m',
    100,
    20,
    'Khoảng vượt tối đa 100m'
),
(
    'KV200',
    'Khoảng vượt 200m',
    200,
    30,
    'Khoảng vượt tối đa 200m'
),
(
    'KV300',
    'Khoảng vượt 300m',
    300,
    40,
    'Khoảng vượt tối đa 300m'
),
(
    'KV400',
    'Khoảng vượt 400m',
    400,
    50,
    'Khoảng vượt tối đa 400m'
),
(
    'KV500',
    'Khoảng vượt 500m',
    500,
    60,
    'Khoảng vượt tối đa 500m'
);


-- ============================================================
-- 15. SEED INCIDENT TYPE
-- ============================================================

INSERT INTO incident_type
(
    type_code,
    type_name,
    description
)
VALUES
(
    'CABLE_BREAK',
    'Đứt cáp',
    'Cáp quang bị đứt'
),
(
    'CABLE_DAMAGE',
    'Hỏng cáp',
    'Cáp bị hư hỏng'
),
(
    'CABLE_SAG',
    'Cáp võng',
    'Cáp bị võng hoặc không đảm bảo độ cao'
),
(
    'HARDWARE_DAMAGE',
    'Hỏng phụ kiện',
    'Hỏng phụ kiện treo, néo, kẹp...'
),
(
    'OTHER',
    'Khác',
    'Loại sự cố khác'
);


-- ============================================================
-- 16. SEED INCIDENT CAUSE
-- ============================================================

INSERT INTO incident_cause
(
    cause_code,
    cause_name,
    description
)
VALUES
(
    'VEHICLE',
    'Xe va quệt',
    'Phương tiện giao thông gây sự cố'
),
(
    'CONSTRUCTION',
    'Thi công',
    'Hoạt động thi công gây sự cố'
),
(
    'TREE',
    'Cây đổ',
    'Cây/cành cây gây sự cố'
),
(
    'STORM',
    'Mưa bão',
    'Thời tiết, thiên tai'
),
(
    'FIRE',
    'Cháy',
    'Sự cố do cháy'
),
(
    'HUMAN',
    'Con người',
    'Tác động của con người'
),
(
    'ANIMAL',
    'Động vật',
    'Động vật gây sự cố'
),
(
    'UNKNOWN',
    'Chưa xác định',
    'Chưa xác định được nguyên nhân'
),
(
    'OTHER',
    'Khác',
    'Nguyên nhân khác'
);


-- ============================================================
-- 17. MATERIAL GROUP COMMENTS
-- ============================================================

COMMENT ON COLUMN material.material_group IS
'Nhóm vật tư: CABLE, HANGER, ANCHOR, SPLICE_CLOSURE, CLAMP, PIPE, POLE_BAND, OTHERS';


-- ============================================================
-- 18. FINAL COMMENTS
-- ============================================================

COMMENT ON TABLE fiber_route IS
'Danh mục tuyến cáp. Một tuyến có thể có nhiều khoảng vượt khác nhau nên không lưu repair_span_type tại đây.';

COMMENT ON TABLE incident IS
'Thông tin một lần ứng cứu sự cố. repair_span_type được xác định tại hiện trường.';

COMMENT ON TABLE material IS
'Danh mục vật tư sử dụng trong công tác ứng cứu.';

COMMENT ON TABLE material_rule IS
'Quy tắc phân loại vật tư tự động theo loại cáp, số FO và kiểu đoạn ứng cứu.';

COMMENT ON TABLE incident_material IS
'Vật tư thực tế sử dụng cho từng sự cố.';

COMMENT ON COLUMN incident_material.quantity IS
'Số lượng thực tế sử dụng, không phải chiều dài/khoảng vượt của đoạn cáp.';


COMMIT;