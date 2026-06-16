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
from database import init_db, save_transaction, get_user_history
from sheets import save_to_sheet

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Conversation states ────────────────────────────────────────────────────────
WAITING_AMOUNT = 1

# ── Menu labels ───────────────────────────────────────────────────────────────
BTN_CONTRIBUTE = "💰 Đóng góp"
BTN_HISTORY    = "📋 Lịch sử"
BTN_SHEET      = "📊 Link Sheet"
BTN_CLEAR      = "🗑️ Xóa chat"

MAIN_MENU = ReplyKeyboardMarkup(
    [[BTN_CONTRIBUTE, BTN_HISTORY], [BTN_SHEET, BTN_CLEAR]],
    resize_keyboard=True,
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


# ── Handlers ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "☕ Chào mừng bạn đến với quỹ *Đá và Cà Phê*!\n\n"
        "Vui lòng chọn chức năng từ menu bên dưới.",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


async def handle_contribute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "☕ *Quỹ Đá và Cà Phê*\n\n"
        "Nhập số tiền bạn muốn đóng góp cho quỹ:\n"
        f"_(Tối thiểu {fmt(config.MIN_AMOUNT)})_",
        parse_mode="Markdown",
    )
    return WAITING_AMOUNT


async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    # Strip formatting characters
    clean = raw.replace(".", "").replace(",", "").replace(" ", "").rstrip("đdĐD")

    if not clean.lstrip("-").isdigit():
        await update.message.reply_text(
            "❌ Số tiền không hợp lệ. Vui lòng nhập một số nguyên.\n"
            "Ví dụ: *50000*",
            parse_mode="Markdown",
        )
        return WAITING_AMOUNT

    amount = int(clean)
    if amount < config.MIN_AMOUNT:
        await update.message.reply_text(
            f"❌ Số tiền tối thiểu là *{fmt(config.MIN_AMOUNT)}*. Vui lòng nhập lại.",
            parse_mode="Markdown",
        )
        return WAITING_AMOUNT

    context.user_data["pending_amount"] = amount

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tôi đã chuyển khoản thành công", callback_data=f"confirm:{amount}")]
    ])

    msg = await update.message.reply_photo(
        photo=vietqr_url(amount),
        caption=(
            "💳 *Thông tin chuyển khoản*\n\n"
            f"🏦 Ngân hàng: MB Bank\n"
            f"👤 Tên TK: Quỹ Đá và Cà Phê\n"
            f"📱 Số TK: `{config.ACCOUNT_NUMBER}`\n"
            f"💰 Số tiền: *{fmt(amount)}*\n"
            f"📝 Nội dung: `Dong gop quy Da va Ca Phe`\n\n"
            "_Quét mã QR để chuyển khoản, sau đó nhấn xác nhận bên dưới._"
        ),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    # track message id so Clear can remove it
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
            "🎉 *Chúc mừng bạn đóng góp quỹ thành công!*\n\n"
            f"👤 Người đóng góp: *{full_name}*\n"
            f"💰 Số tiền: *{fmt(amount)}*\n"
            f"📅 Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
            "Cảm ơn bạn đã ủng hộ quỹ Đá và Cà Phê ☕🧊"
        ),
        parse_mode="Markdown",
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

    msg = await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )
    context.user_data.setdefault("bot_messages", []).append(msg.message_id)


async def handle_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = config.GOOGLE_SHEET_LINK
    if not link:
        await update.message.reply_text(
            "📊 Link Google Sheet chưa được cập nhật. Vui lòng liên hệ quản trị viên."
        )
        return

    await update.message.reply_text(
        f"📊 *Bảng theo dõi quỹ Đá và Cà Phê:*\n\n{link}",
        parse_mode="Markdown",
        disable_web_page_preview=False,
    )


async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg_ids = context.user_data.pop("bot_messages", [])

    for mid in msg_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass  # already deleted or not accessible

    # Also delete the Clear button message itself
    try:
        await update.message.delete()
    except Exception:
        pass

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text="✅ Đã xóa nội dung chat!\n_(Lịch sử chuyển khoản vẫn được lưu)_",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )
    context.user_data["bot_messages"] = [msg.message_id]


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Đã hủy. Chọn chức năng từ menu.", reply_markup=MAIN_MENU
    )
    return ConversationHandler.END


# ── Wiring ────────────────────────────────────────────────────────────────────

def main():
    init_db()

    app = Application.builder().token(config.BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{BTN_CONTRIBUTE}$"), handle_contribute)],
        states={
            WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex(f"^{BTN_HISTORY}$"), handle_history),
            MessageHandler(filters.Regex(f"^{BTN_SHEET}$"), handle_sheet),
            MessageHandler(filters.Regex(f"^{BTN_CLEAR}$"), handle_clear),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(handle_confirm, pattern=r"^confirm:"))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_HISTORY}$"), handle_history))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_SHEET}$"), handle_sheet))
    app.add_handler(MessageHandler(filters.Regex(f"^{BTN_CLEAR}$"), handle_clear))

    logger.info("Bot đang chạy...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
