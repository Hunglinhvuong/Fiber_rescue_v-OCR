#!/usr/bin/env bash
# ============================================================
# Sau khi code đã được cập nhật tại chỗ (git pull / copy đè lên thư
# mục gốc dự án), chạy script này để cài lại dependencies (venv
# dùng chung cho bot + dashboard) và restart service.
# KHÔNG đụng tới file .env.
#
# Dùng:
#   sudo ./deploy/update.sh
# ============================================================
set -euo pipefail

SERVICE_NAMES=("fiber_rescue" "fiber_rescue_ocr_worker")
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "❌ Cần chạy bằng sudo/root."
    exit 1
fi

if [[ ! -x "$INSTALL_DIR/venv/bin/pip" ]]; then
    echo "❌ Chưa thấy venv tại $INSTALL_DIR/venv. Chạy sudo ./deploy/install.sh trước."
    exit 1
fi

SERVICE_USER="$(stat -c '%U' "$INSTALL_DIR/venv")"
echo "▶ Cài lại dependencies (bot + dashboard + OCR worker, user: $SERVICE_USER) ..."
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install \
    -r "$INSTALL_DIR/requirements.txt" \
    -r "$INSTALL_DIR/requirements-dashboard.txt" -q

chmod +x "$INSTALL_DIR/deploy/run.sh" "$INSTALL_DIR/deploy/run_ocr_worker.sh"

echo "▶ Restart services ..."
systemctl restart "${SERVICE_NAMES[@]}"

echo "✅ Đã cập nhật & restart ${SERVICE_NAMES[*]}."
echo "   Xem log: sudo journalctl -u fiber_rescue -u fiber_rescue_ocr_worker -f"
