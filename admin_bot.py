import logging
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from database import (
    get_user, get_all_users, update_user, create_user, is_active
)
from config import PLANS, ADMIN_ID
from i18n import t
from keyboards import (
    admin_main_menu,
    admin_users_pagination,
    admin_user_actions,
    admin_plan_selector,
)

logger = logging.getLogger("admin_bot")

# Conversation states
ADD_USER_ID, ADD_API_KEY, ADD_PLAN = range(3)
SEARCH_USER, EXTEND_DAYS, BROADCAST_MSG = range(3, 6)


def _is_admin(update: Update):
    return update.effective_user.id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        lang = "ar"
        user = get_user(update.effective_user.id)
        lang = user.get("language", "ar") if user else "ar"
        await update.message.reply_text(t("not_admin", lang))
        return
    users = get_all_users()
    active = sum(1 for u in users if is_active(u["user_id"]))
    text = t("admin_panel", "ar", total=len(users), active=active)
    await update.message.reply_text(text, reply_markup=admin_main_menu("ar"))


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(update):
        await query.edit_message_text("⚠️ هذا الأمر خاص بالمشرف فقط.")
        return
    data = query.data
    if data == "admin_back":
        users = get_all_users()
        active = sum(1 for u in users if is_active(u["user_id"]))
        text = t("admin_panel", "ar", total=len(users), active=active)
        await query.edit_message_text(text, reply_markup=admin_main_menu("ar"))
    elif data == "admin_stats":
        users = get_all_users()
        total = len(users)
        active = sum(1 for u in users if is_active(u["user_id"]))
        by_plan = {}
        for u in users:
            p = u.get("plan", "unknown")
            by_plan[p] = by_plan.get(p, 0) + 1
        plan_stats = "\n".join([f"{PLANS.get(k, {}).get('name_ar', k)}: {v}" for k, v in by_plan.items()])
        text = f"📊 إحصائيات\nالإجمالي: {total}\nالنشطين: {active}\n\n{plan_stats}"
        await query.edit_message_text(text, reply_markup=admin_main_menu("ar"))
    elif data == "admin_users":
        users = get_all_users()
        context.user_data["admin_users_list"] = users
        context.user_data["admin_users_page"] = 0
        await _show_users_page(query, context, users, 0)
    elif data.startswith("admin_users_page_"):
        page = int(data.replace("admin_users_page_", ""))
        users = context.user_data.get("admin_users_list", get_all_users())
        await _show_users_page(query, context, users, page)
    elif data == "admin_noop":
        pass
    elif data.startswith("admin_toggle_"):
        uid = int(data.replace("admin_toggle_", ""))
        user = get_user(uid)
        if user:
            new_status = not user.get("active", True)
            update_user(uid, active=new_status)
            status = "مفعل" if new_status else "موقوف"
            await query.edit_message_text(f"✅ تم تغيير حالة المستخدم {uid} إلى {status}")
    elif data.startswith("admin_delete_"):
        uid = int(data.replace("admin_delete_", ""))
        from database import _read, _write
        all_users = _read()
        if str(uid) in all_users:
            del all_users[str(uid)]
            _write(all_users)
            await query.edit_message_text(f"✅ تم حذف المستخدم {uid}")
        else:
            await query.edit_message_text("❌ المستخدم غير موجود")
    elif data.startswith("admin_plan_"):
        uid = int(data.replace("admin_plan_", ""))
        context.user_data["admin_change_plan_uid"] = uid
        await query.edit_message_text(
            "اختر الخطة الجديدة:",
            reply_markup=admin_plan_selector("ar"),
        )
    elif data.startswith("admin_setplan_"):
        plan = data.replace("admin_setplan_", "")
        uid = context.user_data.get("admin_change_plan_uid")
        if uid:
            plan_days = PLANS.get(plan, PLANS["trial"])["days"]
            expires = (datetime.now() + timedelta(days=plan_days)).strftime("%Y-%m-%d")
            update_user(uid, plan=plan, plan_expires=expires, active=True)
            await query.edit_message_text(
                f"✅ تم تغيير خطة المستخدم {uid} إلى {PLANS[plan]['name_ar']}"
            )
    elif data == "admin_add_user":
        await query.edit_message_text("أرسل user_id للمستخدم الجديد:")
        return ADD_USER_ID
    elif data == "admin_broadcast":
        await query.edit_message_text("📢 أرسل الرسالة التي تريد بثها لجميع المستخدمين:")
        return BROADCAST_MSG
    return


async def _show_users_page(query, context, users, page):
    from keyboards import admin_user_actions
    per_page = 5
    total_pages = max(1, (len(users) + per_page - 1) // per_page)
    start = page * per_page
    end = start + per_page
    page_users = users[start:end]
    lines = [f"👥 المستخدمين (صفحة {page + 1}/{total_pages}):"]
    for u in page_users:
        uid = u.get("user_id", "?")
        plan = PLANS.get(u.get("plan", ""), {}).get("name_ar", u.get("plan", "?"))
        act = "🟢" if is_active(uid) else "🔴"
        lines.append(f"{act} ID: {uid} | {plan} | ينتهي: {u.get('plan_expires', '-')}")
    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"admin_users_page_{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="admin_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"admin_users_page_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")])
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def add_user_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return ConversationHandler.END
    text = update.message.text.strip()
    state = context.user_data.get("add_user_state", ADD_USER_ID)
    if state == ADD_USER_ID:
        try:
            uid = int(text)
            if get_user(uid):
                await update.message.reply_text("❌ المستخدم موجود مسبقاً.")
                return ConversationHandler.END
            context.user_data["add_uid"] = uid
            context.user_data["add_user_state"] = ADD_API_KEY
            await update.message.reply_text("أرسل WoopSocial API Key:")
            return ADD_API_KEY
        except ValueError:
            await update.message.reply_text("❌ user_id يجب أن يكون رقماً.")
            return ConversationHandler.END
    elif state == ADD_API_KEY:
        context.user_data["add_api_key"] = text
        context.user_data["add_user_state"] = ADD_PLAN
        context.user_data["add_account_id"] = text
        context.user_data["add_user_state"] = ADD_PLAN
        buttons = []
        for key in PLANS:
            buttons.append([InlineKeyboardButton(
                PLANS[key]["name_ar"],
                callback_data=f"admin_confirm_plan_{key}"
            )])
        await update.message.reply_text(
            "اختر الخطة:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return ADD_PLAN
    return ConversationHandler.END


async def add_user_plan_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(update):
        return ConversationHandler.END
    plan = query.data.replace("admin_confirm_plan_", "")
    uid = context.user_data.get("add_uid")
    api_key = context.user_data.get("add_api_key", "")
    user = create_user(uid, plan=plan)
    if api_key:
        update_user(uid, woopsocial_api_key=api_key)
    await query.edit_message_text(
        f"✅ تم إضافة المستخدم {uid}\nالخطة: {PLANS[plan]['name_ar']}"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def add_user_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text("❌ تم إلغاء الإضافة.")
    return ConversationHandler.END


async def search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return ConversationHandler.END
    text = update.message.text.strip()
    try:
        uid = int(text)
        user = get_user(uid)
        if not user:
            await update.message.reply_text("❌ المستخدم غير موجود.")
            return ConversationHandler.END
        status = "🟢 نشط" if is_active(uid) else "🔴 غير نشط"
        msg = (
            f"👤 المستخدم: {uid}\n"
            f"الخطة: {PLANS.get(user['plan'], {}).get('name_ar', user['plan'])}\n"
            f"ينتهي: {user.get('plan_expires', '-')}\n"
            f"الحالة: {status}\n"
            f"اللغة: {user.get('language', 'ar')}\n"
            f"API Key: {'✅' if user.get('woopsocial_api_key') else '❌'}\n"
            f"Daily: {user.get('daily_count', 0)}"
        )
        await update.message.reply_text(msg, reply_markup=admin_user_actions(uid))
    except ValueError:
        await update.message.reply_text("❌ user_id يجب أن يكون رقماً.")
    return ConversationHandler.END


async def extend_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return ConversationHandler.END
    text = update.message.text.strip()
    match = re.match(r"(\d+)\s+(\d+)", text)
    if not match:
        await update.message.reply_text(
            "❌ الصيغة: user_id عدد_الأيام\nمثال: 123456 30"
        )
        return ConversationHandler.END
    uid = int(match.group(1))
    days = int(match.group(2))
    user = get_user(uid)
    if not user:
        await update.message.reply_text("❌ المستخدم غير موجود.")
        return ConversationHandler.END
    try:
        current = datetime.strptime(user["plan_expires"], "%Y-%m-%d")
        new_expires = (current + timedelta(days=days)).strftime("%Y-%m-%d")
    except:
        new_expires = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    update_user(uid, plan_expires=new_expires, active=True)
    await update.message.reply_text(
        f"✅ تم تمديد اشتراك {uid} بـ {days} يوم حتى {new_expires}"
    )
    return ConversationHandler.END


async def broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return ConversationHandler.END
    msg_text = update.message.text.strip()
    users = get_all_users()
    sent = 0
    for u in users:
        try:
            await context.application.bot.send_message(
                chat_id=u["user_id"],
                text=msg_text,
            )
            sent += 1
        except Exception as e:
            logger.warning(f"فشل إرسال البث للمستخدم {u['user_id']}: {e}")
    await update.message.reply_text(f"✅ تم البث لـ {sent} من أصل {len(users)} مستخدم.")
    return ConversationHandler.END


async def admin_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ أرسل: /search user_id")
        return
    try:
        uid = int(args[0])
        user = get_user(uid)
        if not user:
            await update.message.reply_text("❌ المستخدم غير موجود.")
            return
        status = "🟢 نشط" if is_active(uid) else "🔴 غير نشط"
        msg = (
            f"👤 المستخدم: {uid}\n"
            f"الخطة: {PLANS.get(user['plan'], {}).get('name_ar', user['plan'])}\n"
            f"ينتهي: {user.get('plan_expires', '-')}\n"
            f"الحالة: {status}\n"
            f"اللغة: {user.get('language', 'ar')}\n"
            f"API Key: {'✅' if user.get('woopsocial_api_key') else '❌'}\n"
            f"Daily: {user.get('daily_count', 0)}"
        )
        await update.message.reply_text(msg, reply_markup=admin_user_actions(uid))
    except ValueError:
        await update.message.reply_text("❌ user_id يجب أن يكون رقماً.")


async def admin_extend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text("❌ أرسل: /extend user_id days")
        return
    try:
        uid = int(args[0])
        days = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ user_id و days يجب أن يكونا رقمين.")
        return
    user = get_user(uid)
    if not user:
        await update.message.reply_text("❌ المستخدم غير موجود.")
        return
    try:
        current = datetime.strptime(user["plan_expires"], "%Y-%m-%d")
        new_expires = (current + timedelta(days=days)).strftime("%Y-%m-%d")
    except:
        new_expires = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    update_user(uid, plan_expires=new_expires, active=True)
    await update.message.reply_text(
        f"✅ تم تمديد اشتراك {uid} بـ {days} يوم حتى {new_expires}"
    )


async def broadcast_conv_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return ConversationHandler.END
    await update.message.reply_text("📢 أرسل الرسالة التي تريد بثها لجميع المستخدمين:")
    return BROADCAST_MSG


async def broadcast_conv_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return ConversationHandler.END
    msg_text = update.message.text.strip()
    users = get_all_users()
    sent = 0
    for u in users:
        try:
            await context.application.bot.send_message(
                chat_id=u["user_id"], text=msg_text
            )
            sent += 1
        except Exception as e:
            logger.warning(f"فشل إرسال البث للمستخدم {u['user_id']}: {e}")
    await update.message.reply_text(
        f"✅ تم البث لـ {sent} من أصل {len(users)} مستخدم."
    )
    return ConversationHandler.END


def build_admin_app():
    from config import ADMIN_BOT_TOKEN
    app = Application.builder().token(ADMIN_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", admin_search))
    app.add_handler(CommandHandler("extend", admin_extend))
    add_user_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_user_callback, pattern="^admin_add_user$")],
        states={
            ADD_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_conversation)],
            ADD_API_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_conversation)],
            ADD_PLAN: [CallbackQueryHandler(add_user_plan_confirm, pattern="^admin_confirm_plan_")],
        },
        fallbacks=[MessageHandler(filters.COMMAND, add_user_cancel)],
    )
    app.add_handler(add_user_conv)
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^admin_broadcast$")],
        states={
            BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_conv_handle)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )
    app.add_handler(broadcast_conv)
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    return app
