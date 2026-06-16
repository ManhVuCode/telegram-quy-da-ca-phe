#!/usr/bin/env python3
"""Quỹ Đá và Cà Phê — Telegram bot"""

import logging
import urllib.parse
from datetime import datetime

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

import config
from database import init_db, save_transaction, get_user_history, clear_user_history
from sheets import save_to_sheet

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Conversation states ────────────────────────────────────────────────────────
WAITING_AMOUNT = 1

# ── Menu labels ───────────────────────────────────────────────────────────────
BTN_START         = "🏠 Start"
BTN_CONTRIBUTE    = "💰 Đóng góp"
BTN_HISTORY       = "📋 Lịch sử"
BTN_SHEET         = "📊 Link Sheet"
BTN_CLEAR         = "🗑️ Xóa chat"
BTN_CLEAR_HISTORY = "❌ Xóa lịch sử"

MAIN_MENU = ReplyKeyboardMarkup(
    [
        [BTN_START,      BTN_CONTRIBUTE],
        [BTN_HISTORY,    BTN_SHEET],
        [BTN_CLEAR,      BTN_CLEAR_HISTORY],
    ],
    resize_keyboard=True,
)

# Filter that matches any menu button — used to guard WAITING_AMOUNT state
MENU_FILTER = filters.Regex(
    f"^({BTN_START}|{BTN_CONTRIBUTE}|{BTN_HISTORY}|{BTN_SHEET}|{BTN_CLEAR}|{BTN_CLEAR_HISTORY})$"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + " đ"


def vietqr_url(amount: int) -> str:
    info = urllib.parse.quote("Dong gop quy Da va Ca Phe")
    name = urllib.parse.quote(config.ACCOUNT_NAME)
    return (
        f"https://img.vietqr.io/image/{config.BANK_ID}-{config.ACCOUNT_NUMBER}-compact2.png"
        f"?amount={amount}&addInfo={info}&accountName={name}"
    )


def user_fullname(user) -> str:
    return f"{user.first_name} {user.last_name or ''}".strip()


async def send(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    """Send a plain (non-reply) message to keep chat clean."""
    return await context.bot.send_message(
        chat_id=update.effective_chat.id, text=text, **kwargs
    )


# ── Handlers ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await send(
        update, context,
        "☕ Chào mừng bạn đến với quỹ <b>Đá và Cà Phê</b>!\n\n"
        "Vui lòng chọn chức năng từ menu bên dưới.",
        parse_mode="HTML",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


async def handle_contribute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await send(
        update, context,
        "☕ <b>Quỹ Đá và Cà Phê</b>\n\n"
        "Nhập số tiền bạn muốn đóng góp cho quỹ:\n"
        f"<i>(Tối thiểu {fmt(config.MIN_AMOUNT)})</i>",
        parse_mode="HTML",
    )
    return WAITING_AMOUNT


async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    clean = raw.replace(".", "").replace(",", "").replace(" ", "").rstrip("đdĐD")

    if not clean.lstrip("-").isdigit():
        await send(
            update, context,
            "❌ Số tiền không hợp lệ. Vui lòng nhập một số nguyên.\n"
            "Ví dụ: <b>50000</b>",
            parse_mode="HTML",
        )
        return WAITING_AMOUNT

    amount = int(clean)
    if amount < config.MIN_AMOUNT:
        await send(
            update, context,
            f"❌ Số tiền tối thiểu là <b>{fmt(config.MIN_AMOUNT)}</b>. Vui lòng nhập lại.",
            parse_mode="HTML",
        )
        return WAITING_AMOUNT

    context.user_data["pending_amount"] = amount

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tôi đã chuyển khoản thành công", callback_data=f"confirm:{amount}")]
    ])

    msg = await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=vietqr_url(amount),
        caption=(
            "💳 <b>Thông tin chuyển khoản</b>\n\n"
            f"🏦 Ngân hàng: MB Bank\n"
            f"👤 Tên TK: Quỹ Đá và Cà Phê\n"
            f"📱 Số TK: <code>{config.ACCOUNT_NUMBER}</code>\n"
            f"💰 Số tiền: <b>{fmt(amount)}</b>\n"
            f"📝 Nội dung: <code>Dong gop quy Da va Ca Phe</code>\n\n"
            "<i>Quét mã QR để chuyển khoản, sau đó nhấn xác nhận bên dưới.</i>"
        ),
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    context.user_data.setdefault("bot_messages", []).append(msg.message_id)
    return ConversationHandler.END


async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, amount_str = query.data.split(":", 1)
    amount = int(amount_str)

    user = update.effective_user
    full_name = user_fullname(user)
    username = user.username or "N/A"

    save_transaction(user.id, username, full_name, amount)
    save_to_sheet(full_name, amount, username)

    await query.edit_message_caption(
        caption=(
            "🎉 <b>Chúc mừng bạn đóng góp quỹ thành công!</b>\n\n"
            f"👤 Người đóng góp: <b>{full_name}</b>\n"
            f"💰 Số tiền: <b>{fmt(amount)}</b>\n"
            f"📅 Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
            "Cảm ơn bạn đã ủng hộ quỹ Đá và Cà Phê ☕🧊"
        ),
        parse_mode="HTML",
    )
    context.user_data.pop("pending_amount", None)


async def handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rows, total = get_user_history(user.id)
    month = datetime.now().strftime("%m/%Y")

    lines = [
        "📋 <b>Lịch sử đóng góp quỹ</b>",
        "<i>Đây là lịch sử đóng góp quỹ của bạn trong tháng này, tháng sau sẽ làm mới.</i>",
        "",
    ]

    if not rows:
        lines.append("Bạn chưa có giao dịch nào trong tháng này.")
    else:
        for i, (name, amount, date) in enumerate(rows, 1):
            lines.append(f"{i}. 💰 {fmt(amount)} — {date}")
        lines.append(f"\n💎 <b>Tổng tháng {month}: {fmt(total)}</b>")

    await send(update, context, "\n".join(lines), parse_mode="HTML")


async def handle_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = config.GOOGLE_SHEET_LINK
    if not link:
        await send(update, context, "📊 Link Google Sheet chưa được cập nhật.")
        return

    await send(
        update, context,
        f"📊 <b>Bảng theo dõi quỹ Đá và Cà Phê:</b>\n\n{link}",
        parse_mode="HTML",
    )


async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg_ids = context.user_data.pop("bot_messages", [])

    for mid in msg_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass

    try:
        await update.message.delete()
    except Exception:
        pass

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text="✅ Đã xóa nội dung chat!\n<i>(Lịch sử chuyển khoản vẫn được lưu)</i>",
        parse_mode="HTML",
        reply_markup=MAIN_MENU,
    )
    context.user_data["bot_messages"] = [msg.message_id]


async def handle_clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    month = datetime.now().strftime("%m/%Y")
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Xác nhận xóa", callback_data="clrhist:yes"),
            InlineKeyboardButton("❌ Hủy", callback_data="clrhist:no"),
        ]
    ])
    await send(
        update, context,
        f"⚠️ Bạn có chắc muốn xóa toàn bộ lịch sử đóng góp tháng <b>{month}</b> không?\n"
        "<i>(Dữ liệu trên Google Sheet sẽ không bị ảnh hưởng)</i>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def handle_confirm_clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "clrhist:no":
        await query.edit_message_text("↩️ Đã hủy. Lịch sử của bạn vẫn được giữ nguyên.")
        return

    deleted = clear_user_history(update.effective_user.id)
    month = datetime.now().strftime("%m/%Y")
    await query.edit_message_text(
        f"✅ Đã xóa <b>{deleted}</b> giao dịch tháng <b>{month}</b> khỏi lịch sử.",
        parse_mode="HTML",
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await send(update, context, "Đã hủy. Chọn chức năng từ menu.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


# ── Wiring ────────────────────────────────────────────────────────────────────

def main():
    init_db()

    app = Application.builder().token(config.BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            MessageHandler(filters.Regex(f"^{BTN_START}$"), cmd_start),
            MessageHandler(filters.Regex(f"^{BTN_CONTRIBUTE}$"), handle_contribute),
        ],
        states={
            # Exclude menu buttons so they fall through to fallbacks
            WAITING_AMOUNT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~MENU_FILTER,
                    handle_amount,
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex(f"^{BTN_START}$"), cmd_start),
            MessageHandler(filters.Regex(f"^{BTN_CONTRIBUTE}$"), handle_contribute),
            MessageHandler(filters.Regex(f"^{BTN_HISTORY}$"), handle_history),
            MessageHandler(filters.Regex(f"^{BTN_SHEET}$"), handle_sheet),
            MessageHandler(filters.Regex(f"^{BTN_CLEAR}$"), handle_clear),
            MessageHandler(filters.Regex(f"^{BTN_CLEAR_HISTORY}$"), handle_clear_history),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)

    # Standalone handlers — active at ALL times (even when not in a conversation)
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_START}$"), cmd_start))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_HISTORY}$"), handle_history))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_SHEET}$"), handle_sheet))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_CLEAR}$"), handle_clear))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_CLEAR_HISTORY}$"), handle_clear_history))

    app.add_handler(CallbackQueryHandler(handle_confirm, pattern=r"^confirm:"))
    app.add_handler(CallbackQueryHandler(handle_confirm_clear_history, pattern=r"^clrhist:"))

    logger.info("Bot đang chạy...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
