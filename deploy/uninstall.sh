#!/usr/bin/env bash
# ============================================================
# Gỡ cài đặt Fiber Rescue (dừng + xoá systemd service).
# KHÔNG xoá mã nguồn, .env hay dữ liệu — chỉ gỡ service + (tuỳ chọn) venv.
#
# Dùng:
#   sudo ./deploy/uninstall.sh
# ============================================================
set -euo pipefail

SERVICE_NAMES=("fiber_rescue" "fiber_rescue_ocr_worker")
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "❌ Cần chạy bằng sudo/root."
    exit 1
fi

echo "▶ Dừng & vô hiệu hoá services ..."
for SERVICE_NAME in "${SERVICE_NAMES[@]}"; do
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
done
systemctl daemon-reload

if [[ -d "$INSTALL_DIR/venv" ]]; then
    read -rp "Xoá luôn virtualenv $INSTALL_DIR/venv? [y/N] " confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
        rm -rf "$INSTALL_DIR/venv"
        echo "✅ Đã xoá venv."
    fi
fi

echo "✅ Đã gỡ cài đặt ${SERVICE_NAMES[*]} (mã nguồn, .env và dữ liệu trong $INSTALL_DIR vẫn được giữ nguyên)."
