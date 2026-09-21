# Tích hợp mô hình OCR;
## 1
Cài dependencyvenv/pip install -r requirements.txt -r requirements-dashboard.txt (httpx đã có sẵn, không cần thêm gì).
## 2
Lấy API keyOCR.space: đăng ký free tại ocr.space/ocrapi/freekey (nhận key qua email). Google Vision (tuỳ chọn, chỉ cần nếu muốn fallback): console.cloud.google.com > bật Vision API > tạo API key.
## 3
Cập nhật .envĐiền OCR_PROVIDER_ORDER=ocr_space,google_vision, OCR_SPACE_API_KEY=<key>, GOOGLE_VISION_API_KEY=<key hoặc để trống>. Nếu .env đang dùng biến cũ OCR_SERVER_URL/OCR_SERVER_API_KEY thì xoá 2 dòng đó (không còn dùng nữa).
## 4
Áp migration DB (nếu chưa chạy trước đó)python -m scripts.migrate_002_ocr_coordinate rồi python -m scripts.migrate_003_coordinate_retry. Nếu bạn đã chạy 2 lệnh này ở lần trước (khi còn dùng ocr_server) thì BỎ QUA bước này — schema DB không đổi, chỉ đổi cách gọi OCR.
## 5
Test nhanh provider (không cần bot)python -c "import asyncio; from ocr.service import OCRService; print(asyncio.run(OCRService().extract_text('<url_ảnh_có_toạ_độ>')))" — chạy trong venv, PYTHONPATH=. Kỳ vọng in ra OCRResult(success=True, text=..., provider='ocr_space').
## 6
Chạy bot (terminal 1)PYTHONPATH=. python app.py — luồng /bc không đổi gì, ảnh vẫn upload Cloudinary bình thường và enqueue job vào coordinate_extraction.
## 7
Chạy OCR worker (terminal 2, song song)PYTHONPATH=. python -m workers.ocr_worker — poll bảng coordinate_extraction mỗi 5s (OCR_WORKER_POLL_INTERVAL_SECONDS), log ra provider nào đọc được toạ độ.
## 8
Kiểm tra kết quảBáo cáo 1 sự cố có ảnh chứa toạ độ overlay qua Telegram. Xem log worker (OCR thành công... provider=ocr_space) rồi query: SELECT * FROM coordinate_extraction ORDER BY created_at DESC LIMIT 5; và SELECT latitude, longitude, coordinate_source, coordinate_status FROM incident WHERE incident_id=<id>;

# Luồng xử lý OCR:

Có 4 tầng thứ tự khác nhau trong pipeline OCR toạ độ — độc lập với nhau:

## 1. Job nào worker xử lý trước — database/repositories/coordinate_repository.py::claim_pending_batch

*sql
ORDER BY ce.created_at   -- FIFO, KHÔNG ưu tiên theo source (AFTER/BEFORE ngang nhau)*

Đổi: sửa ORDER BY ở đây (vd ORDER BY (source='AFTER') DESC, created_at để ưu tiên ảnh AFTER xử lý trước).

## 2. Provider OCR nào gọi trước (OCR.space → Google Vision) — *ocr/service.py::_build_provider_chain(), đọc từ settings.ocr_provider_order
*python
for name in settings.ocr_provider_order:   # tuple đọc từ OCR_PROVIDER_ORDER trong .env*
Chỉ dừng ở provider kế nếu provider trước thất bại hoàn toàn HOẶC không parse ra toạ độ hợp lệ.
Đổi: sửa biến OCR_PROVIDER_ORDER trong .env, không cần sửa code:

*OCR_PROVIDER_ORDER=google_vision,ocr_space*

Thêm provider mới: tạo file trong ocr/providers/, đăng ký vào _PROVIDER_REGISTRY trong ocr/service.py, rồi thêm tên vào OCR_PROVIDER_ORDER.
## 3. Pattern parser nào thử trước (trên text OCR trả về) — ocr/parser.py::parse_coordinates()

*python
for parser_fn in (_try_labeled, _try_dms, _try_mixed, _try_decimal_pair, _try_bbox_scan):*

LABELED → DMS → MIXED → DECIMAL_PAIR → BBOX_SCAN (tin cậy giảm dần, dừng ở pattern đầu tiên match).
Đổi: sửa thứ tự tuple này trực tiếp trong code (đây là logic nghiệp vụ, không config hoá qua .env).

## 4. Nguồn toạ độ nào được chọn làm cuối cùng cho incident (OCR_AFTER > OCR_BEFORE > GPS) — services/coordinate_service.py::recompute_final_coordinate()

*python
if after_row is not None:
    candidate = CoordinateCandidate("OCR_AFTER", after_row["latitude"], after_row["longitude"])
elif before_row is not None:
    candidate = CoordinateCandidate("OCR_BEFORE", before_row["latitude"], before_row["longitude"])
  None cả 2 -> giữ GPS*

Đổi: đảo 2 nhánh if/elif này để ưu tiên BEFORE trước AFTER (chỉ dùng get_latest_success_by_source(..., "AFTER"/"BEFORE") sẵn có, không cần sửa repository).
