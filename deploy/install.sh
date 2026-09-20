#!/usr/bin/env bash
# ============================================================
# Cài đặt Fiber Rescue làm 3 systemd service ĐỘC LẬP, chạy NGAY TẠI
# thư mục gốc dự án hiện tại (không copy sang /opt hay nơi khác):
#   - Fiber_rescue-teleBot    (bot Telegram)
#   - Fiber_rescue-dashboard  (dashboard Streamlit)
#   - Fiber_rescue-OcrWorker  (worker OCR toạ độ)
# Cả 3 dùng chung 1 virtualenv (venv/) và 1 file .env.
#
# KHÔNG đụng tới database — tự áp schema/migration thủ công trước
# khi khởi động services (xem database/schema.sql, database/migrations/).
#
# Dùng:
#   sudo ./deploy/install.sh
# ============================================================
set -euo pipefail

SERVICE_NAMES=("Fiber_rescue-teleBot" "Fiber_rescue-dashboard" "Fiber_rescue-OcrWorker")
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-${USER:-$(id -un)}}}"

if [[ $EUID -ne 0 ]]; then
    echo "❌ Cần chạy bằng sudo/root (để tạo systemd service)."
    echo "   Ví dụ: sudo ./deploy/install.sh"
    exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    echo "❌ User '$SERVICE_USER' không tồn tại. Tạo trước hoặc chỉ định SERVICE_USER=<user_có_sẵn>."
    exit 1
fi

echo "▶ Thư mục dự án:   $INSTALL_DIR"
echo "▶ Chạy bằng user:  $SERVICE_USER"
echo "▶ Services:        ${SERVICE_NAMES[*]}"
echo ""

command -v python3 >/dev/null 2>&1 || { echo "❌ Chưa cài python3."; exit 1; }
PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
PY_MAJOR="$(python3 -c 'import sys; print(sys.version_info[0])')"
PY_MINOR="$(python3 -c 'import sys; print(sys.version_info[1])')"
echo "▶ Python version:  $PY_VERSION"
if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 10 ) ]]; then
    echo "❌ Cần Python >= 3.10 (đang có $PY_VERSION)."
    exit 1
fi

mkdir -p "$INSTALL_DIR/storage"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"

echo "▶ Tạo virtualenv dùng chung cho cả 3 service ..."
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install \
    -r "$INSTALL_DIR/requirements.txt" \
    -r "$INSTALL_DIR/requirements-dashboard.txt" -q

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    chown "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
    NEW_ENV=1
else
    NEW_ENV=0
fi

chmod +x "$INSTALL_DIR/deploy/run_telebot.sh" "$INSTALL_DIR/deploy/run_dashboard.sh" "$INSTALL_DIR/deploy/run_ocrworker.sh"

echo "▶ Tạo systemd services ..."
for SERVICE_NAME in "${SERVICE_NAMES[@]}"; do
    sed \
        -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
        -e "s|__SERVICE_USER__|$SERVICE_USER|g" \
        "$INSTALL_DIR/deploy/${SERVICE_NAME}.service.template" > "/etc/systemd/system/${SERVICE_NAME}.service"
done

systemctl daemon-reload
for SERVICE_NAME in "${SERVICE_NAMES[@]}"; do
    systemctl enable "$SERVICE_NAME" >/dev/null
done

echo ""
echo "✅ Cài đặt xong."
if [[ "$NEW_ENV" -eq 1 ]]; then
    echo "   1. Sửa cấu hình:  sudo nano $INSTALL_DIR/.env"
else
    echo "   1. (.env đã tồn tại sẵn, giữ nguyên) — kiểm tra lại nếu cần: sudo nano $INSTALL_DIR/.env"
fi
echo "   2. Đảm bảo database đã sẵn sàng (schema + mọi migration cần thiết) — tự thực hiện thủ công,"
echo "      script cài đặt này KHÔNG đụng tới database."
echo "   3. Khởi động:      sudo systemctl start ${SERVICE_NAMES[*]}"
echo "   4. Xem trạng thái: sudo systemctl status ${SERVICE_NAMES[*]}"
echo "   5. Xem log:        sudo journalctl -u ${SERVICE_NAMES[0]} -u ${SERVICE_NAMES[1]} -u ${SERVICE_NAMES[2]} -f"
echo "   6. Dashboard mặc định chạy ở cổng 8501 (đổi bằng DASHBOARD_PORT trong .env nếu cần)"
