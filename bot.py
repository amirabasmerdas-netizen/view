import json
import os
from flask import Flask, request
from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ========= CONFIG =========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # https://xxx.onrender.com
PORT = int(os.environ.get("PORT", 10000))

DB_FILE = "db.json"
# ==========================

# ========= DB =========
DEFAULT_DB = {
    "users": {},            # uid: approved
    "user_channels": {},    # uid: @channel
    "groups": [],           # @groups
    "joins": [],            # @channels
    "forward": False
}

def load_db():
    if not os.path.exists(DB_FILE):
        save_db(DEFAULT_DB)
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
# =======================

# ========= KEYBOARDS =========
def owner_kb():
    return ReplyKeyboardMarkup(
        [
            ["➕ افزودن گروه", "➖ حذف گروه"],
            ["➕ افزودن جوین اجباری", "➖ حذف جوین اجباری"],
            ["▶️ شروع فوروارد", "⏹ توقف فوروارد"],
        ],
        resize_keyboard=True
    )

def user_kb():
    return ReplyKeyboardMarkup(
        [
            ["➕ افزودن کانال"],
            ["📩 ارتباط با مالک", "ℹ️ راهنما"],
        ],
        resize_keyboard=True
    )
# =============================

def reset_state(ctx):
    ctx.user_data.clear()

def is_owner(uid):
    return uid == OWNER_ID

# ========= START =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    uid = str(update.effective_user.id)

    # join check
    if db["joins"]:
        btns = [[InlineKeyboardButton(ch, url=f"https://t.me/{ch[1:]}")] for ch in db["joins"]]
        btns.append([InlineKeyboardButton("✅ تأیید عضویت", callback_data="check_join")])
        await update.message.reply_text(
            "🔒 ابتدا عضو کانال‌ها شوید:",
            reply_markup=InlineKeyboardMarkup(btns)
        )
        return

    if uid not in db["users"]:
        await send_request(update, context)
        await update.message.reply_text("⏳ درخواست شما ارسال شد")
        return

    if not db["users"][uid]:
        await update.message.reply_text("❌ درخواست شما رد شده")
        return

    await update.message.reply_text(
        "👑 پنل مالک" if is_owner(update.effective_user.id) else "👤 پنل کاربر",
        reply_markup=owner_kb() if is_owner(update.effective_user.id) else user_kb()
    )
# ===========================

# ========= JOIN CHECK =========
async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    db = load_db()
    uid = q.from_user.id

    for ch in db["joins"]:
        try:
            m = await context.bot.get_chat_member(ch, uid)
            if m.status not in ["member", "administrator", "creator"]:
                await q.message.reply_text("❌ هنوز عضو نیستید")
                return
        except:
            await q.message.reply_text("❌ خطا در بررسی")
            return

    await send_request(update, context)
    await q.message.reply_text("✅ تأیید شد، درخواست ارسال شد")
# ==============================

# ========= REQUEST =========
async def send_request(update: Update, context):
    u = update.effective_user
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ پذیرش", callback_data=f"approve:{u.id}"),
            InlineKeyboardButton("❌ رد", callback_data=f"reject:{u.id}")
        ]
    ])
    txt = f"📥 درخواست جدید\n👤 {u.full_name}\n🔗 @{u.username}\n🆔 {u.id}"
    await context.bot.send_message(OWNER_ID, txt, reply_markup=kb)
# ============================

# ========= APPROVE / REJECT =========
async def approve_reject(update: Update, context):
    q = update.callback_query
    await q.answer()
    action, uid = q.data.split(":")
    db = load_db()

    if action == "approve":
        db["users"][uid] = True
        save_db(db)
        await context.bot.send_message(uid, "✅ پذیرفته شدید")
    else:
        db["users"][uid] = False
        save_db(db)
        await context.bot.send_message(uid, "❌ رد شدید")

    await q.edit_message_reply_markup(None)
# ===================================

# ========= TEXT =========
async def text_handler(update: Update, context):
    db = load_db()
    text = update.message.text.strip()
    uid = str(update.effective_user.id)

    if is_owner(update.effective_user.id):
        if text in ["➕ افزودن گروه", "➖ حذف گروه", "➕ افزودن جوین اجباری", "➖ حذف جوین اجباری"]:
            context.user_data["mode"] = text
            await update.message.reply_text("یوزرنیم با @ ارسال شود")
            return

        if text == "▶️ شروع فوروارد":
            db["forward"] = True
            save_db(db)
            await update.message.reply_text("▶️ فعال شد")
            return

        if text == "⏹ توقف فوروارد":
            db["forward"] = False
            save_db(db)
            await update.message.reply_text("⏹ متوقف شد")
            return

    if text == "➕ افزودن کانال":
        context.user_data["mode"] = "add_channel"
        await update.message.reply_text("کانال با @ ارسال شود (ربات باید ادمین باشد)")
        return

    if "mode" in context.user_data:
        if not text.startswith("@"):
            await update.message.reply_text("❌ یوزرنیم معتبر نیست")
            reset_state(context)
            return

        try:
            member = await context.bot.get_chat_member(text, context.bot.id)
            if member.status not in ["administrator", "creator"]:
                await update.message.reply_text("❌ ربات ادمین کانال نیست")
                reset_state(context)
                return
        except:
            await update.message.reply_text("❌ کانال یافت نشد")
            reset_state(context)
            return

        mode = context.user_data["mode"]

        if mode == "add_channel":
            db["user_channels"][uid] = text
            save_db(db)
            await update.message.reply_text("✅ کانال ثبت شد")

        elif mode == "➕ افزودن گروه":
            db["groups"].append(text)
            save_db(db)
            await update.message.reply_text("✅ گروه اضافه شد")

        elif mode == "➖ حذف گروه":
            if text in db["groups"]:
                db["groups"].remove(text)
                save_db(db)
                await update.message.reply_text("❌ گروه حذف شد")
            else:
                await update.message.reply_text("یافت نشد")

        elif mode == "➕ افزودن جوین اجباری":
            db["joins"].append(text)
            save_db(db)
            await update.message.reply_text("✅ جوین اضافه شد")

        elif mode == "➖ حذف جوین اجباری":
            if text in db["joins"]:
                db["joins"].remove(text)
                save_db(db)
                await update.message.reply_text("❌ حذف شد")
            else:
                await update.message.reply_text("یافت نشد")

        reset_state(context)
# ===============================

# ========= FORWARD =========
async def channel_post(update: Update, context):
    db = load_db()
    if not db["forward"]:
        return

    ch = update.channel_post.chat.username
    if not ch:
        return

    for uid, user_ch in db["user_channels"].items():
        if user_ch.lstrip("@") == ch:
            for g in db["groups"]:
                try:
                    await update.channel_post.forward(g)
                except:
                    pass
# ==============================

# ========= APP =========
app = Flask(__name__)
application = Application.builder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(check_join, pattern="check_join"))
application.add_handler(CallbackQueryHandler(approve_reject, pattern="approve|reject"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
application.add_handler(MessageHandler(filters.ChatType.CHANNEL, channel_post))

@app.route("/", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "ok"

@app.route("/", methods=["GET"])
def health():
    return "bot alive"

async def main():
    await application.bot.set_webhook(f"{WEBHOOK_URL}/")

if __name__ == "__main__":
    import asyncio
    asyncio.get_event_loop().run_until_complete(main())
    app.run(host="0.0.0.0", port=PORT)
