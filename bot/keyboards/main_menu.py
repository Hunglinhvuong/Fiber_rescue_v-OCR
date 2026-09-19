REPORT_ROLES = {"ADMIN", "MANAGER", "FIELD"}


def main_menu_text(role: str) -> str:
    lines = ["📋 <b>Chức năng chính:</b>"]
    if role in REPORT_ROLES:
        lines.append("• /bc — Báo cáo sự cố mới")
    else:
        lines.append("• (Chỉ xem) Chưa có quyền báo cáo sự cố")
    lines.append("• /kt — Tra cứu sự cố đã báo cáo")
    if role == "ADMIN":
        lines.append("• /setrole &lt;telegram_id&gt; &lt;role&gt; — Cấp quyền người dùng")
    return "\n".join(lines)
