# Fiber Rescue Bot

Bot Telegram báo cáo ứng cứu sự cố cáp quang từ hiện trường, lưu PostgreSQL.

## Cài đặt

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Cấu hình

```bash
cp .env.example .env
# điền TELEGRAM_BOT_TOKEN và thông tin kết nối PostgreSQL
```

## Tạo database

```bash
createdb fiber_rescue
psql -d fiber_rescue -f database/schema.sql
```

Sau khi chạy schema, cần thêm dữ liệu vào các bảng `fiber_route`, `material`,
`material_rule` (vật tư theo cấu hình cable_type/fiber_count/repair_span_type)
để bot có dữ liệu để chọn.

## Chạy bot

```bash
python app.py
```

## Lệnh sử dụng

- `/start` — đăng ký (lần đầu, mặc định quyền **VIEWER**/chỉ xem) hoặc đăng nhập lại.
  Admin (trong `ADMIN_TELEGRAM_IDS`) sẽ nhận thông báo khi có người dùng mới.
- `/setrole <telegram_id> <ADMIN|MANAGER|FIELD|VIEWER>` — chỉ admin dùng để cấp quyền.
- `/bc` — bắt đầu báo cáo sự cố (yêu cầu quyền ADMIN/MANAGER/FIELD): chọn tuyến →
  chọn loại sự cố → chọn nguyên nhân → chọn đoạn khắc phục (UNDERGROUND/KV100...KV500) →
  chọn vật tư + số lượng → nhập mô tả → gửi GPS → gửi ảnh trước → gửi ảnh sau →
  xác nhận → lưu CSDL (tạo `incident`, `incident_material`, `incident_photo`,
  `incident_status_history` trong 1 transaction).
- `/kt` — tra cứu sự cố: chọn ngày → chọn mã sự cố → xem chi tiết + ảnh đã gửi
  (FIELD chỉ xem sự cố của chính mình; ADMIN/MANAGER/VIEWER xem toàn bộ).

## Triển khai trên máy Linux khác (systemd)

Copy nguyên thư mục project (hoặc git clone) sang máy đích, rồi chạy ngay tại
thư mục gốc dự án đó (không copy sang thư mục khác):

```bash
sudo ./deploy/install.sh
```

Script tự động: kiểm tra Python >= 3.10, tạo 1 virtualenv `venv/` dùng chung
cho cả bot lẫn dashboard, cài `requirements.txt` + `requirements-dashboard.txt`
vào venv đó, tạo `.env` từ mẫu (nếu chưa có), tạo + enable systemd service
**`fiber_rescue`** (chạy `deploy/run.sh` — khởi động song song bot Telegram và
`streamlit run dashboard/app.py`; nếu 1 trong 2 tiến trình chết, service tự
restart lại cả hai).

Sau khi cài (đường dẫn ví dụ, thay bằng thư mục dự án thực tế trên máy đích):
```bash
sudo nano /đường/dẫn/dự/án/.env                    # điền TELEGRAM_BOT_TOKEN, DB...
psql -d fiber_rescue -f /đường/dẫn/dự/án/database/schema.sql   # nếu DB chưa có
sudo systemctl start fiber_rescue
sudo systemctl status fiber_rescue
sudo journalctl -u fiber_rescue -f                  # xem log realtime (cả bot + dashboard)
```

Dashboard mặc định chạy ở cổng `8501` (`http://<ip_máy>:8501`) — đổi bằng biến
`DASHBOARD_PORT` trong `.env` nếu cần.

**Cập nhật code** (sau khi đã cài): `git pull` hoặc copy code mới đè lên đúng
thư mục dự án đó, rồi chạy
```bash
sudo ./deploy/update.sh
```
(không đụng tới `.env`, chỉ cài lại dependencies vào venv chung + restart service).

**Gỡ cài đặt:**
```bash
sudo ./deploy/uninstall.sh
```

## Dashboard Streamlit

Dashboard đọc trực tiếp từ cùng PostgreSQL (kết nối đồng bộ riêng, không đụng
tới pool async của bot) và hiển thị ảnh trực tiếp từ URL Cloudinary. Khi triển
khai bằng `deploy/install.sh`, dashboard chạy chung service `fiber_rescue` với
bot (xem mục deploy ở trên). Chạy thủ công (dev/test):

```bash
source venv/bin/activate             # venv chung với bot
pip install -r requirements-dashboard.txt
streamlit run dashboard/app.py
```

Mặc định chạy ở `http://localhost:8501`. Cấu hình DB lấy chung từ file `.env`
(`DB_HOST`, `DB_NAME`...) — đảm bảo `.env` đã có sẵn ở thư mục gốc trước khi chạy.

**Các trang đã triển khai:**
- 📊 **Tổng quan** — KPI (tổng số, đang xử lý, hoàn tất, hôm nay, 7 ngày), biểu đồ
  sự cố theo ngày, nguyên nhân, top tuyến nhiều sự cố.
- 🗺️ **Bản đồ sự cố** — marker theo toạ độ GPS (màu theo trạng thái), click marker
  xem thông tin nhanh rồi mở chi tiết đầy đủ.
- 🚨 **Sự cố** — bảng lọc theo ngày/trạng thái/tuyến/loại/nguyên nhân/từ khoá,
  xuất Excel, click 1 dòng để xem chi tiết + ảnh trước/sau (dạng popup).
- 📈 **Phân tích** — tổng quan sự cố theo thời gian/nguyên nhân/route type, phân
  tích nguyên nhân (tỷ trọng, xu hướng, drill-down Nguyên nhân→Tuyến→Địa
  điểm→Sự cố), phát hiện bất thường (tuyến/nguyên nhân/vật tư tăng đột biến).
- 🧰 **Vật tư** — danh mục vật tư, phân tích tiêu hao (vật tư/sự cố, cáp/sự cố,
  so sánh giữa các tuyến), thống kê sử dụng theo khoảng thời gian + xuất Excel.
- 🛣️ **Tuyến cáp** — danh sách tuyến, chi tiết tuyến (lịch sử sự cố, nguyên
  nhân, vật tư đã dùng), bản đồ tuyến vẽ từ file `.kml` (đặt trong thư mục cấu
  hình bởi `ROUTE_KML_DIR` trong `.env`, tên file = `route_code.kml` hoặc
  `route_name.kml`) + marker vị trí sự cố trên tuyến.

⚠️ Dashboard hiện **chưa có xác thực đăng nhập** — hiển thị ảnh hiện trường và
thông tin sự cố cho bất kỳ ai truy cập được URL. Nếu deploy ra ngoài mạng nội bộ,
cần đặt sau reverse proxy có auth (VD: Nginx + Basic Auth, hoặc Streamlit
`st.login` nếu dùng bản có hỗ trợ) trước khi public.

## Ghi chú

- **Ảnh trước/sau khắc phục**: máy chủ bot KHÔNG tải/lưu bytes ảnh. Luồng:
  Telegram (`file_id`) → `getFile` → URL file Telegram → gửi URL đó cho
  Cloudinary tự fetch (upload REST API, `file=<url>`) → nhận về
  `secure_url`/`public_id`/`asset_id`, lưu vào `incident_photo.cloudinary_url` /
  `cloudinary_public_id` / `cloudinary_asset_id`. Cần cấu hình
  `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` trong
  `.env` (và `CLOUDINARY_PROXY` nếu máy chủ ra internet qua proxy).
  `/kt` (Telegram) gửi lại ảnh qua `telegram_file_id` (không qua Cloudinary);
  Streamlit nhúng thẳng `cloudinary_url` — trình duyệt người xem tự tải ảnh từ
  Cloudinary, dashboard không xử lý ảnh.
- Nếu nâng cấp từ bản cũ (còn ảnh lưu local hoặc cột `file_path`), chạy lần lượt:
  ```bash
  python scripts/migrate_photos_to_cloudinary.py --dry-run   # rồi bỏ --dry-run
  python scripts/migrate_incident_photo_schema.py --dry-run  # rồi bỏ --dry-run
  ```
  (script 2 cần chạy sau script 1, đổi cấu trúc bảng sang cột Cloudinary riêng
  + đổi tên `photo_id`→`incident_photo_id`, `uploaded_at`→`created_at`.)
- Repository `material_repository` khớp vật tư theo `material_rule`
  (NULL trong rule = wildcard khớp mọi giá trị của cột đó).
- `/bc` tự huỷ báo cáo đang nhập dở nếu không thao tác gì trong 3 phút
  (`conversation_timeout` trong `incident_handler.py`). Cần cài lại
  `pip install -r requirements.txt` (đã thêm extra `job-queue`) trên các máy
  đã triển khai trước đó để tính năng này hoạt động.
- Chưa gồm `dashboard/` (Streamlit) trong phạm vi này — báo nếu cần bổ sung.
