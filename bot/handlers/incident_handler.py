import logging
import uuid
from decimal import Decimal

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.keyboards.common import cancel_button_row
from bot.keyboards.edit_menu import edit_menu_keyboard
from bot.keyboards.main_menu import main_menu_text
from bot.keyboards.material_menu import additional_material_keyboard, material_selection_keyboard
from bot.keyboards.route_menu import (
    incident_cause_keyboard,
    incident_type_keyboard,
    repair_span_keyboard,
    route_list_keyboard,
)
from bot.states.incident_state import IncidentState
from utils.formatters import format_incident_summary
from utils.safety import safe_conversation_step
from utils.user_context import ensure_user_context
from utils.validators import parse_quantity, parse_search_text

logger = logging.getLogger(__name__)

ROUTE_PAGE_SIZE = 6
REPORT_ROLES = {"ADMIN", "MANAGER", "FIELD"}


def _reset_incident_data(context: ContextTypes.DEFAULT_TYPE, telegram_user_id: int) -> None:
    context.user_data["incident"] = {
        "session_id": f"{telegram_user_id}_{uuid.uuid4().hex[:8]}",
        "route_page": 0,
        "route_search": None,
        "selected": {},
        "material_options": {"config": [], "additional": []},
        "before_photos": [],
        "after_photos": [],
    }


def _qty_step(group: str) -> Decimal:
    return Decimal("100") if group == "CABLE" else Decimal("1")


def _get_incident(context: ContextTypes.DEFAULT_TYPE):
    """Lấy dict báo cáo đang nhập, hoặc None nếu session đã mất (VD: bot restart
    giữa lúc nhập, dữ liệu tạm trong RAM không còn)."""
    return context.user_data.get("incident")


async def _reply_session_lost(update: Update) -> int:
    text = "⚠️ Không tìm thấy dữ liệu báo cáo đang nhập (có thể do bot vừa khởi động lại).\nVui lòng gõ /bc để bắt đầu lại."
    if update.callback_query is not None:
        try:
            await update.callback_query.answer()
        except Exception:
            pass
        await update.callback_query.message.reply_text(text)
    elif update.effective_message is not None:
        await update.effective_message.reply_text(text)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Chọn tuyến
# ---------------------------------------------------------------------------

@safe_conversation_step
async def start_incident(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    app_user = await ensure_user_context(update, context)
    if app_user is None:
        await update.message.reply_text("Vui lòng gõ /start trước để đăng ký.")
        return ConversationHandler.END

    if app_user["status"] != "ACTIVE":
        await update.message.reply_text(
            "⛔ Tài khoản của bạn đã bị vô hiệu hóa. Vui lòng liên hệ quản trị viên."
        )
        return ConversationHandler.END

    if context.user_data.get("role") not in REPORT_ROLES:
        await update.message.reply_text(
            "⛔ Bạn không có quyền báo cáo sự cố (chỉ được xem). "
            "Liên hệ quản trị viên để được cấp quyền."
        )
        return ConversationHandler.END

    _reset_incident_data(context, update.effective_user.id)

    route_repo = context.bot_data["route_repo"]
    routes = await route_repo.list_active(limit=ROUTE_PAGE_SIZE, offset=0)
    total = await route_repo.count_active()

    await update.message.reply_text(
        "🛣 Chọn tuyến cáp bị sự cố:",
        reply_markup=route_list_keyboard(routes, 0, total, ROUTE_PAGE_SIZE),
    )
    return IncidentState.SELECT_ROUTE


async def _show_route_list(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    inc = _get_incident(context)
    route_repo = context.bot_data["route_repo"]
    search = inc.get("route_search")
    page = inc.get("route_page", 0)
    routes = await route_repo.list_active(limit=ROUTE_PAGE_SIZE, offset=page * ROUTE_PAGE_SIZE, search=search)
    total = await route_repo.count_active(search=search)
    try:
        await query.edit_message_text(
            "🛣 Chọn tuyến cáp bị sự cố:",
            reply_markup=route_list_keyboard(routes, page, total, ROUTE_PAGE_SIZE),
        )
    except BadRequest:
        pass


@safe_conversation_step
async def route_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    inc["route_page"] = int(query.data.split(":")[1])
    await _show_route_list(query, context)
    return IncidentState.SELECT_ROUTE


@safe_conversation_step
async def route_search_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔍 Nhập tên tuyến cần tìm:")
    return IncidentState.SEARCH_ROUTE


@safe_conversation_step
async def route_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    search = parse_search_text(update.message.text)
    inc["route_search"] = search

    route_repo = context.bot_data["route_repo"]
    routes = await route_repo.list_active(limit=ROUTE_PAGE_SIZE, offset=0, search=search)
    total = await route_repo.count_active(search=search)

    if total == 0:
        await update.message.reply_text(
            f"Không tìm thấy tuyến nào khớp '{search}'. Nhập lại tên khác:"
        )
        return IncidentState.SEARCH_ROUTE

    inc["route_page"] = 0
    await update.message.reply_text(
        f"Kết quả cho '{search}':",
        reply_markup=route_list_keyboard(routes, 0, total, ROUTE_PAGE_SIZE),
    )
    return IncidentState.SELECT_ROUTE


@safe_conversation_step
async def select_route(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    route_id = int(query.data.split(":")[1])
    route_repo = context.bot_data["route_repo"]
    route = await route_repo.get_by_id(route_id)
    if route is None:
        await query.edit_message_text("Tuyến không tồn tại, vui lòng thử lại.")
        return ConversationHandler.END

    inc.update({
        "route_id": route["route_id"],
        "route_name": route["route_name"],
        "cable_type": route["cable_type"],
        "fiber_count": route["fiber_count"],
    })

    if inc.pop("edit_return", False):
        # Tuyến đổi -> cable_type/fiber_count đổi -> làm mới vật tư (giữ nguyên đoạn khắc phục cũ)
        await _recompute_materials(context, warn=True)
        return await _render_confirm(update, context)

    lookup_repo = context.bot_data["lookup_repo"]
    types = await lookup_repo.list_incident_types()

    await query.edit_message_text(
        f"✅ Tuyến: {route['route_name']} ({route['cable_type']}-{route['fiber_count']}FO)\n\n"
        "⚠️ Chọn loại sự cố:",
        reply_markup=incident_type_keyboard(types),
    )
    return IncidentState.SELECT_INCIDENT_TYPE


# ---------------------------------------------------------------------------
# Loại sự cố / nguyên nhân / đoạn khắc phục
# ---------------------------------------------------------------------------

@safe_conversation_step
async def select_incident_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    type_id = int(query.data.split(":")[1])
    lookup_repo = context.bot_data["lookup_repo"]
    types = await lookup_repo.list_incident_types()
    type_row = next((t for t in types if t["incident_type_id"] == type_id), None)

    inc["incident_type_id"] = type_id
    inc["incident_type_name"] = type_row["type_name"] if type_row else ""

    if inc.pop("edit_return", False):
        return await _render_confirm(update, context)

    causes = await lookup_repo.list_incident_causes()
    await query.edit_message_text(
        "🔎 Chọn nguyên nhân (nếu biết):",
        reply_markup=incident_cause_keyboard(causes),
    )
    return IncidentState.SELECT_CAUSE


@safe_conversation_step
async def select_cause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    raw = query.data.split(":")[1]
    lookup_repo = context.bot_data["lookup_repo"]

    if raw == "skip":
        inc["cause_id"] = None
        inc["cause_name"] = None
    else:
        cause_id = int(raw)
        causes = await lookup_repo.list_incident_causes()
        cause_row = next((c for c in causes if c["cause_id"] == cause_id), None)
        inc["cause_id"] = cause_id
        inc["cause_name"] = cause_row["cause_name"] if cause_row else None

    if inc.pop("edit_return", False):
        return await _render_confirm(update, context)

    spans = await lookup_repo.list_repair_span_types()
    await query.edit_message_text(
        "📏 Chọn kiểu đoạn khắc phục:",
        reply_markup=repair_span_keyboard(spans),
    )
    return IncidentState.SELECT_SPAN


async def _recompute_materials(context: ContextTypes.DEFAULT_TYPE, warn: bool) -> None:
    """Tính lại danh sách vật tư theo cable_type/fiber_count/repair_span_type_id hiện tại,
    giữ lại số lượng cho vật tư nào vẫn còn hợp lệ."""
    inc = context.user_data["incident"]
    material_service = context.bot_data["material_service"]
    options = await material_service.get_material_options(
        inc["cable_type"], inc["fiber_count"], inc["repair_span_type_id"]
    )
    inc["material_options"] = options

    old_selected = inc.get("selected", {})
    new_selected = {}
    for m in options["config"]:
        mid = m["material_id"]
        old_qty = old_selected.get(mid, {}).get("qty", Decimal("0"))
        new_selected[mid] = {
            "name": m["material_name"],
            "unit": m["unit"],
            "group": m["material_group"],
            "qty": old_qty,
        }

    additional_ids = {m["material_id"] for m in options["additional"]}
    for mid, item in old_selected.items():
        if mid not in new_selected and mid in additional_ids:
            new_selected[mid] = item

    inc["selected"] = new_selected
    if warn:
        inc["materials_refreshed_warning"] = (
            "⚠️ Danh sách vật tư đã được làm mới do đổi tuyến/đoạn khắc phục. "
            "Vui lòng kiểm tra lại số lượng."
        )


@safe_conversation_step
async def select_span(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    span_id = int(query.data.split(":")[1])
    lookup_repo = context.bot_data["lookup_repo"]
    spans = await lookup_repo.list_repair_span_types()
    span_row = next((s for s in spans if s["repair_span_type_id"] == span_id), None)

    inc["repair_span_type_id"] = span_id
    inc["span_name"] = span_row["span_name"] if span_row else ""

    is_edit = inc.pop("edit_return", False)
    await _recompute_materials(context, warn=is_edit)

    if is_edit:
        return await _render_confirm(update, context)

    await query.edit_message_text(
        "🧰 Chọn số lượng vật tư sử dụng:",
        reply_markup=material_selection_keyboard(inc["selected"]),
    )
    return IncidentState.SELECT_MATERIALS


# ---------------------------------------------------------------------------
# Chọn vật tư & số lượng
# ---------------------------------------------------------------------------

@safe_conversation_step
async def material_qty_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    action, mid_str = query.data.split(":")
    mid = int(mid_str)

    selected = inc["selected"]
    item = selected.get(mid)
    if item is None:
        return IncidentState.SELECT_MATERIALS

    step = _qty_step(item["group"])
    if action == "qty_inc":
        item["qty"] += step
    else:
        item["qty"] = max(Decimal("0"), item["qty"] - step)

    try:
        await query.edit_message_reply_markup(reply_markup=material_selection_keyboard(selected))
    except BadRequest:
        pass
    return IncidentState.SELECT_MATERIALS


@safe_conversation_step
async def material_qty_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    mid = int(query.data.split(":")[1])
    item = inc["selected"].get(mid)
    if item is None:
        return IncidentState.SELECT_MATERIALS

    inc["awaiting_qty_material_id"] = mid
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Nhập số lượng ({item['unit']}) cho '{item['name']}':",
        reply_markup=InlineKeyboardMarkup([cancel_button_row()]),
    )
    return IncidentState.ADD_MATERIAL_QTY


@safe_conversation_step
async def material_qty_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    mid = inc.get("awaiting_qty_material_id")
    qty = parse_quantity(update.message.text)

    if qty is None:
        await update.message.reply_text("Số lượng không hợp lệ. Nhập lại (VD: 150 hoặc 12.5):")
        return IncidentState.ADD_MATERIAL_QTY

    selected = inc["selected"]
    if mid in selected:
        selected[mid]["qty"] = qty
    inc.pop("awaiting_qty_material_id", None)

    await update.message.reply_text(
        "🧰 Chọn số lượng vật tư sử dụng:",
        reply_markup=material_selection_keyboard(selected),
    )
    return IncidentState.SELECT_MATERIALS


@safe_conversation_step
async def material_add_other_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    already = set(inc["selected"].keys())
    remaining = [m for m in inc["material_options"]["additional"] if m["material_id"] not in already]

    if not remaining:
        await query.answer("Không còn vật tư bổ sung khác.", show_alert=True)
        return IncidentState.SELECT_MATERIALS

    await query.answer()
    try:
        await query.edit_message_text(
            "➕ Chọn vật tư bổ sung:",
            reply_markup=additional_material_keyboard(remaining),
        )
    except BadRequest:
        pass
    return IncidentState.SELECT_MATERIALS


@safe_conversation_step
async def material_add_other_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    mid = int(query.data.split(":")[1])
    material_row = next(
        (m for m in inc["material_options"]["additional"] if m["material_id"] == mid), None
    )
    if material_row is not None and mid not in inc["selected"]:
        inc["selected"][mid] = {
            "name": material_row["material_name"],
            "unit": material_row["unit"],
            "group": material_row["material_group"],
            "qty": Decimal("1"),
        }

    try:
        await query.edit_message_text(
            "🧰 Chọn số lượng vật tư sử dụng:",
            reply_markup=material_selection_keyboard(inc["selected"]),
        )
    except BadRequest:
        pass
    return IncidentState.SELECT_MATERIALS


@safe_conversation_step
async def material_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    try:
        await query.edit_message_text(
            "🧰 Chọn số lượng vật tư sử dụng:",
            reply_markup=material_selection_keyboard(inc["selected"]),
        )
    except BadRequest:
        pass
    return IncidentState.SELECT_MATERIALS


@safe_conversation_step
async def material_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    selected = inc["selected"]
    used = {mid: item for mid, item in selected.items() if item["qty"] >= 0}

    if not used:
        await query.answer("Cần chọn ít nhất 1 vật tư có số lượng > 0.", show_alert=True)
        return IncidentState.SELECT_MATERIALS

    await query.answer()

    if inc.pop("edit_return", False):
        return await _render_confirm(update, context)

    await query.edit_message_text(
        "✏️ Nhập mô tả sự cố (hoặc bấm Bỏ qua):",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⏭ Bỏ qua", callback_data="desc_skip")]]
        ),
    )
    return IncidentState.ENTER_DESCRIPTION


# ---------------------------------------------------------------------------
# Mô tả -> GPS
# ---------------------------------------------------------------------------

@safe_conversation_step
async def description_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    inc["description"] = None

    if inc.pop("edit_return", False):
        await query.edit_message_text("✅ Đã cập nhật mô tả (bỏ qua).")
        return await _render_confirm(update, context)

    await query.edit_message_text("✅ Đã bỏ qua mô tả.")
    return await _ask_location(update, context)


@safe_conversation_step
async def description_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    inc["description"] = update.message.text.strip()

    if inc.pop("edit_return", False):
        return await _render_confirm(update, context)

    return await _ask_location(update, context)


async def _ask_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Gửi vị trí GPS", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📍 Bấm nút bên dưới để gửi vị trí GPS hiện tại:",
        reply_markup=keyboard,
    )
    return IncidentState.SEND_LOCATION


@safe_conversation_step
async def receive_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    location = update.message.location
    inc["latitude"] = location.latitude
    inc["longitude"] = location.longitude
    inc["location_accuracy_m"] = location.horizontal_accuracy

    if inc.pop("edit_return", False):
        await update.message.reply_text("✅ Đã cập nhật vị trí.", reply_markup=ReplyKeyboardRemove())
        return await _render_confirm(update, context)

    await update.message.reply_text(
        "✅ Đã nhận vị trí.\n📷 Gửi ảnh TRƯỚC khi khắc phục (có thể gửi nhiều ảnh).",
        reply_markup=ReplyKeyboardRemove(),
    )
    return IncidentState.SEND_PHOTO_BEFORE


# ---------------------------------------------------------------------------
# Ảnh trước / sau
# ---------------------------------------------------------------------------

async def _receive_photo(
    update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, photo_type: str
) -> int:
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    photo_service = context.bot_data["photo_service"]
    tg_photo = update.message.photo[-1]
    tg_file = await tg_photo.get_file()

    try:
        upload_result = await photo_service.save_photo(tg_file, inc["session_id"], photo_type)
    except Exception:
        logger.exception("Upload ảnh lên Cloudinary thất bại")
        await update.message.reply_text(
            "❌ Không upload được ảnh (lỗi mạng/Cloudinary). Vui lòng gửi lại ảnh này."
        )
        return IncidentState.SEND_PHOTO_BEFORE if photo_type == "BEFORE" else IncidentState.SEND_PHOTO_AFTER

    inc[key].append({
        "photo_type": photo_type,
        "cloudinary_url": upload_result["secure_url"],
        "cloudinary_public_id": upload_result.get("public_id"),
        "cloudinary_asset_id": upload_result.get("asset_id"),
        "telegram_file_id": tg_photo.file_id,
        "telegram_file_unique_id": tg_photo.file_unique_id,
        "caption": update.message.caption,
    })

    label = "TRƯỚC" if photo_type == "BEFORE" else "SAU"
    done_callback = "photos_before_done" if photo_type == "BEFORE" else "photos_after_done"

    await update.message.reply_text(
        f"✅ Đã nhận ảnh {label} ({len(inc[key])}). Gửi thêm hoặc bấm Xong.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ Xong", callback_data=done_callback)]]
        ),
    )
    return IncidentState.SEND_PHOTO_BEFORE if photo_type == "BEFORE" else IncidentState.SEND_PHOTO_AFTER


@safe_conversation_step
async def receive_photo_before(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _receive_photo(update, context, "before_photos", "BEFORE")


@safe_conversation_step
async def receive_photo_after(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _receive_photo(update, context, "after_photos", "AFTER")


@safe_conversation_step
async def photos_before_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    if not inc["before_photos"]:
        await query.answer("Cần ít nhất 1 ảnh trước khi khắc phục.", show_alert=True)
        return IncidentState.SEND_PHOTO_BEFORE

    await query.answer()

    if inc.pop("edit_return", False):
        await query.edit_message_text("✅ Đã cập nhật ảnh trước.")
        return await _render_confirm(update, context)

    await query.edit_message_text("✅ Đã lưu ảnh trước.\n\n📷 Gửi ảnh SAU khi khắc phục:")
    return IncidentState.SEND_PHOTO_AFTER


@safe_conversation_step
async def photos_after_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    if not inc["after_photos"]:
        await query.answer("Cần ít nhất 1 ảnh sau khi khắc phục.", show_alert=True)
        return IncidentState.SEND_PHOTO_AFTER

    await query.answer()
    inc.pop("edit_return", None)
    return await _render_confirm(update, context)


# ---------------------------------------------------------------------------
# Xác nhận (hub) & sửa thông tin
# ---------------------------------------------------------------------------

async def _render_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    inc = context.user_data["incident"]
    summary_data = {
        "route_name": inc["route_name"],
        "cable_type": inc["cable_type"],
        "fiber_count": inc["fiber_count"],
        "incident_type_name": inc["incident_type_name"],
        "cause_name": inc.get("cause_name"),
        "span_name": inc["span_name"],
        "description": inc.get("description"),
        "materials": [
            {"name": v["name"], "unit": v["unit"], "qty": v["qty"]}
            for v in inc["selected"].values()
        ],
        "latitude": inc["latitude"],
        "longitude": inc["longitude"],
        "before_count": len(inc["before_photos"]),
        "after_count": len(inc["after_photos"]),
    }
    summary_text = format_incident_summary(summary_data)

    warning = inc.pop("materials_refreshed_warning", None)
    if warning:
        summary_text = f"{warning}\n\n{summary_text}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Xác nhận & Lưu", callback_data="confirm_save")],
        [InlineKeyboardButton("✏️ Sửa thông tin", callback_data="edit_menu_open")],
        [InlineKeyboardButton("❌ Huỷ báo cáo", callback_data="confirm_cancel")],
    ])

    if update.callback_query is not None:
        try:
            await update.callback_query.edit_message_text(
                summary_text, parse_mode="HTML", reply_markup=keyboard
            )
        except BadRequest:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=summary_text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
    else:
        await update.message.reply_text(summary_text, parse_mode="HTML", reply_markup=keyboard)
    return IncidentState.CONFIRM


@safe_conversation_step
async def edit_menu_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    await query.edit_message_text("✏️ Chọn mục cần sửa:", reply_markup=edit_menu_keyboard(inc))
    return IncidentState.EDIT_MENU


@safe_conversation_step
async def open_edit_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lệnh /sua — dùng được ở bất kỳ bước nào trong lúc đang nhập báo cáo."""
    inc = _get_incident(context)
    if inc is None:
        await update.message.reply_text("Bạn chưa bắt đầu báo cáo nào. Gõ /bc để bắt đầu.")
        return ConversationHandler.END

    await update.message.reply_text("✏️ Chọn mục cần sửa:", reply_markup=edit_menu_keyboard(inc))
    return IncidentState.EDIT_MENU


async def _ask_route_edit(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_route_list(query, context)


async def _ask_incident_type_edit(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    lookup_repo = context.bot_data["lookup_repo"]
    types = await lookup_repo.list_incident_types()
    await query.edit_message_text("⚠️ Chọn loại sự cố:", reply_markup=incident_type_keyboard(types))


async def _ask_cause_edit(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    lookup_repo = context.bot_data["lookup_repo"]
    causes = await lookup_repo.list_incident_causes()
    await query.edit_message_text(
        "🔎 Chọn nguyên nhân (nếu biết):", reply_markup=incident_cause_keyboard(causes)
    )


async def _ask_span_edit(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    lookup_repo = context.bot_data["lookup_repo"]
    spans = await lookup_repo.list_repair_span_types()
    await query.edit_message_text("📏 Chọn kiểu đoạn khắc phục:", reply_markup=repair_span_keyboard(spans))


async def _ask_materials_edit(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    inc = _get_incident(context)
    await query.edit_message_text(
        "🧰 Chọn số lượng vật tư sử dụng:",
        reply_markup=material_selection_keyboard(inc["selected"]),
    )


async def _ask_description_edit(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    await query.edit_message_text(
        "✏️ Nhập mô tả sự cố (hoặc bấm Bỏ qua):",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⏭ Bỏ qua", callback_data="desc_skip")]]
        ),
    )


async def _ask_location_edit(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    await query.edit_message_text("📍 Gửi vị trí GPS mới bằng bàn phím bên dưới:")
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Gửi vị trí GPS", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="📍 Bấm nút bên dưới để gửi vị trí GPS mới:",
        reply_markup=keyboard,
    )


_EDIT_FIELD_HANDLERS = {
    "route": (_ask_route_edit, IncidentState.SELECT_ROUTE),
    "itype": (_ask_incident_type_edit, IncidentState.SELECT_INCIDENT_TYPE),
    "cause": (_ask_cause_edit, IncidentState.SELECT_CAUSE),
    "span": (_ask_span_edit, IncidentState.SELECT_SPAN),
    "materials": (_ask_materials_edit, IncidentState.SELECT_MATERIALS),
    "description": (_ask_description_edit, IncidentState.ENTER_DESCRIPTION),
    "location": (_ask_location_edit, IncidentState.SEND_LOCATION),
}


async def _ask_photo_edit_choice(query, context: ContextTypes.DEFAULT_TYPE, key: str) -> int:
    label = "TRƯỚC" if key == "photo_before" else "SAU"
    await query.edit_message_text(
        f"📷 Sửa ảnh {label}:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Gửi thêm ảnh", callback_data=f"photo_edit_add:{key}")],
            [InlineKeyboardButton("🗑 Xoá hết & gửi lại", callback_data=f"photo_edit_clear:{key}")],
            [InlineKeyboardButton("⬅️ Quay lại", callback_data="edit_menu_back")],
        ]),
    )
    return IncidentState.EDIT_MENU


@safe_conversation_step
async def edit_field_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    key = query.data.split(":", 1)[1]

    if key in ("photo_before", "photo_after"):
        return await _ask_photo_edit_choice(query, context, key)

    entry = _EDIT_FIELD_HANDLERS.get(key)
    if entry is None:
        await query.edit_message_text("Không hỗ trợ sửa mục này.")
        return IncidentState.EDIT_MENU

    render_fn, next_state = entry
    inc["edit_return"] = True
    await render_fn(query, context)
    return next_state


@safe_conversation_step
async def photo_edit_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    key = query.data.split(":", 1)[1]
    inc["edit_return"] = True

    if key == "photo_before":
        await query.edit_message_text("📷 Gửi thêm ảnh TRƯỚC khi khắc phục:")
        return IncidentState.SEND_PHOTO_BEFORE

    await query.edit_message_text("📷 Gửi thêm ảnh SAU khi khắc phục:")
    return IncidentState.SEND_PHOTO_AFTER


@safe_conversation_step
async def photo_edit_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    key = query.data.split(":", 1)[1]
    inc["edit_return"] = True

    if key == "photo_before":
        inc["before_photos"] = []
        await query.edit_message_text("🗑 Đã xoá ảnh TRƯỚC cũ. Gửi ảnh TRƯỚC mới:")
        return IncidentState.SEND_PHOTO_BEFORE

    inc["after_photos"] = []
    await query.edit_message_text("🗑 Đã xoá ảnh SAU cũ. Gửi ảnh SAU mới:")
    return IncidentState.SEND_PHOTO_AFTER


@safe_conversation_step
async def edit_menu_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    return await _render_confirm(update, context)


# ---------------------------------------------------------------------------
# Xác nhận & lưu CSDL
# ---------------------------------------------------------------------------

@safe_conversation_step
async def confirm_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Đang lưu...")

    inc = _get_incident(context)
    if inc is None:
        return await _reply_session_lost(update)

    incident_service = context.bot_data["incident_service"]

    materials = [
        (mid, item["qty"], None) for mid, item in inc["selected"].items() if item["qty"] >= 0
    ]
    photos = inc["before_photos"] + inc["after_photos"]

    try:
        result = await incident_service.submit_incident(
            route_id=inc["route_id"],
            reported_by=context.user_data["user_id"],
            incident_type_id=inc["incident_type_id"],
            cause_id=inc.get("cause_id"),
            repair_span_type_id=inc["repair_span_type_id"],
            latitude=inc["latitude"],
            longitude=inc["longitude"],
            location_accuracy_m=inc.get("location_accuracy_m"),
            description=inc.get("description"),
            materials=materials,
            photos=photos,
        )
    except Exception:
        logger.exception("Failed to save incident")
        await query.edit_message_text("❌ Có lỗi khi lưu vào cơ sở dữ liệu. Vui lòng thử lại sau.")
        return ConversationHandler.END

    await query.edit_message_text(
        f"🎉 Đã lưu thành công!\nMã sự cố: <b>{result['incident_code']}</b>",
        parse_mode="HTML",
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=main_menu_text(context.user_data.get("role", "VIEWER")),
        parse_mode="HTML",
    )
    context.user_data.pop("incident", None)
    return ConversationHandler.END


@safe_conversation_step
async def confirm_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("incident", None)
    await query.edit_message_text("❌ Đã huỷ báo cáo sự cố.")
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=main_menu_text(context.user_data.get("role", "VIEWER")),
        parse_mode="HTML",
    )
    return ConversationHandler.END


@safe_conversation_step
async def cancel_incident(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("incident", None)
    await update.message.reply_text("❌ Đã huỷ báo cáo sự cố.")
    return ConversationHandler.END


INCIDENT_CONVERSATION_TIMEOUT = 240  # 4 phút không thao tác -> tự huỷ


@safe_conversation_step
async def on_incident_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("incident", None)
    text = (
        "⏱ Đã hết thời gian chờ (4 phút không thao tác).\n"
        "Báo cáo đang nhập dở đã bị huỷ. Gõ /bc để bắt đầu lại."
    )

    if update.callback_query is not None:
        try:
            await update.callback_query.answer()
        except BadRequest:
            pass
        try:
            await update.callback_query.edit_message_text(text)
            return ConversationHandler.END
        except BadRequest:
            pass

    if update.effective_chat is not None:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# ConversationHandler
# ---------------------------------------------------------------------------

def get_incident_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("bc", start_incident),
        ],
        states={
            IncidentState.SELECT_ROUTE: [
                CallbackQueryHandler(select_route, pattern=r"^route:\d+$"),
                CallbackQueryHandler(route_page, pattern=r"^route_page:\d+$"),
                CallbackQueryHandler(route_search_prompt, pattern=r"^route_search$"),
            ],
            IncidentState.SEARCH_ROUTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, route_search_text),
            ],
            IncidentState.SELECT_INCIDENT_TYPE: [
                CallbackQueryHandler(select_incident_type, pattern=r"^itype:\d+$"),
            ],
            IncidentState.SELECT_CAUSE: [
                CallbackQueryHandler(select_cause, pattern=r"^cause:"),
            ],
            IncidentState.SELECT_SPAN: [
                CallbackQueryHandler(select_span, pattern=r"^span:\d+$"),
            ],
            IncidentState.SELECT_MATERIALS: [
                CallbackQueryHandler(material_qty_change, pattern=r"^qty_(inc|dec):\d+$"),
                CallbackQueryHandler(material_qty_prompt, pattern=r"^qty_noop:\d+$"),
                CallbackQueryHandler(material_add_other_menu, pattern=r"^material_add_other$"),
                CallbackQueryHandler(material_add_other_select, pattern=r"^add_material:\d+$"),
                CallbackQueryHandler(material_back, pattern=r"^material_back$"),
                CallbackQueryHandler(material_done, pattern=r"^material_done$"),
            ],
            IncidentState.ADD_MATERIAL_QTY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, material_qty_text),
            ],
            IncidentState.ENTER_DESCRIPTION: [
                CallbackQueryHandler(description_skip, pattern=r"^desc_skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, description_text),
            ],
            IncidentState.SEND_LOCATION: [
                MessageHandler(filters.LOCATION, receive_location),
            ],
            IncidentState.SEND_PHOTO_BEFORE: [
                MessageHandler(filters.PHOTO, receive_photo_before),
                CallbackQueryHandler(photos_before_done, pattern=r"^photos_before_done$"),
            ],
            IncidentState.SEND_PHOTO_AFTER: [
                MessageHandler(filters.PHOTO, receive_photo_after),
                CallbackQueryHandler(photos_after_done, pattern=r"^photos_after_done$"),
            ],
            IncidentState.CONFIRM: [
                CallbackQueryHandler(confirm_save, pattern=r"^confirm_save$"),
                CallbackQueryHandler(edit_menu_open, pattern=r"^edit_menu_open$"),
                CallbackQueryHandler(confirm_cancel, pattern=r"^confirm_cancel$"),
            ],
            IncidentState.EDIT_MENU: [
                CallbackQueryHandler(edit_field_selected, pattern=r"^edit_field:\w+$"),
                CallbackQueryHandler(photo_edit_add, pattern=r"^photo_edit_add:(photo_before|photo_after)$"),
                CallbackQueryHandler(photo_edit_clear, pattern=r"^photo_edit_clear:(photo_before|photo_after)$"),
                CallbackQueryHandler(edit_menu_back, pattern=r"^edit_menu_back$"),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, on_incident_timeout),
                CallbackQueryHandler(on_incident_timeout),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_incident),
            CommandHandler("sua", open_edit_menu_command),
            CallbackQueryHandler(confirm_cancel, pattern=r"^cancel_incident_inline$"),
        ],
        conversation_timeout=INCIDENT_CONVERSATION_TIMEOUT,
        name="incident_conversation",
        persistent=False,
    )
