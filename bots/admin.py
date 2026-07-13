import logging
import time
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes,
)

from core.models import User, PLANS
from core import storage as store
from core.config import SUPPORT_USERNAME
from core.cookies_store import get_cookies_b64, set_cookies_b64, get_last_update_info
from core.i18n import t

logger = logging.getLogger(__name__)

(
    ASK_TELEGRAM_ID, ASK_PLAN, ASK_DAYS, ASK_MESSAGE,
    ASK_API_KEY, ASK_PROJECT_ID, ASK_ACCOUNT_ID,
    ASK_INSTAGRAM_ACCOUNT_ID, ASK_CUSTOM_DAYS, ASK_EXTEND_DAYS,
    WAITING_COOKIES,
) = range(11)


def _is_admin(update: Update, admin_id: int) -> bool:
    return update.effective_user.id == admin_id


def _main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 المستخدمين", callback_data="admin_users"),
         InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("➕ إضافة مستخدم", callback_data="admin_add"),
         InlineKeyboardButton("📢 بث", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🍪 تحديث الكوكيز", callback_data="admin_cookies"),
         InlineKeyboardButton("📋 حالة الكوكيز", callback_data="admin_cookies_status")],
    ])


def _user_details_keyboard(uid: int, user: User = None):
    buttons = []
    if user and user.is_active():
        buttons.append([InlineKeyboardButton("🔴 إيقاف", callback_data=f"admin_stop_{uid}"),
                        InlineKeyboardButton("🗑 حذف", callback_data=f"admin_delete_{uid}")])
        buttons.append([InlineKeyboardButton("⛔ إنهاء الخطة", callback_data=f"admin_expire_{uid}")])
    else:
        buttons.append([InlineKeyboardButton("🟢 تفعيل", callback_data=f"admin_activate_{uid}"),
                        InlineKeyboardButton("🗑 حذف", callback_data=f"admin_delete_{uid}")])
    buttons.append([InlineKeyboardButton("📋 تغيير الخطة", callback_data=f"admin_plan_{uid}")])
    buttons.append([InlineKeyboardButton("🌐 تغيير اللغة", callback_data=f"admin_lang_{uid}")])
    if user and user.instagram_account_id:
        buttons.append([InlineKeyboardButton("📸 تغيير انستغرام", callback_data=f"admin_ig_{uid}")])
    else:
        buttons.append([InlineKeyboardButton("📸 ربط انستغرام", callback_data=f"admin_ig_{uid}")])
    if user and user.is_active():
        buttons.append([InlineKeyboardButton("⏳ تمديد الاشتراك", callback_data=f"admin_extend_{uid}")])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_users")])
    return InlineKeyboardMarkup(buttons)


def _plan_selector(prefix: str = "admin_newplan:"):
    buttons = []
    for key, pp in PLANS.items():
        buttons.append([InlineKeyboardButton(
            pp.name, callback_data=f"{prefix}{key}"
        )])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_users")])
    return InlineKeyboardMarkup(buttons)


def _lang_selector(uid: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇸🇦 العربية", callback_data=f"admin_lang_{uid}_ar"),
         InlineKeyboardButton("🇬🇧 English", callback_data=f"admin_lang_{uid}_en")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"admin_user_{uid}")],
    ])


def create_app(token: str, admin_id: int):
    app = Application.builder().token(token).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update, admin_id):
            await update.message.reply_text(t("ar", "not_admin"))
            return
        users_data = await store.get("users")
        total = len(users_data)
        active = sum(
            1 for u in users_data.values()
            if User(**u).is_active()
        )
        text = f"🔐 لوحة التحكم\nالإجمالي: {total}\nالنشطاء: {active}"
        await update.message.reply_text(text, reply_markup=_main_keyboard())

    async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if not _is_admin(update, admin_id):
            await query.edit_message_text(t("ar", "not_admin"))
            return

        data = query.data
        users_data = await store.get("users")

        if data == "admin_stats":
            total = len(users_data)
            active = sum(1 for u in users_data.values() if User(**u).is_active())
            by_plan = {}
            for u in users_data.values():
                p = u.get("plan", "unknown")
                by_plan[p] = by_plan.get(p, 0) + 1
            plan_lines = "\n".join(
                f"{PLANS.get(k, PLANS['trial']).name}: {v}"
                for k, v in by_plan.items()
            )
            text = f"📊 إحصائيات\nالإجمالي: {total}\nالنشطاء: {active}\n\n{plan_lines}"
            await query.edit_message_text(text, reply_markup=_main_keyboard())

        elif data == "admin_users":
            await _show_users(query, users_data, 0)

        elif data.startswith("admin_users_page_"):
            page = int(data.replace("admin_users_page_", ""))
            await _show_users(query, users_data, page)

        elif data.startswith("admin_user_"):
            uid = data.replace("admin_user_", "")
            u = users_data.get(uid)
            if not u:
                await query.edit_message_text("❌ المستخدم غير موجود.")
                return
            u_obj = User(**u)
            act = "🟢 نشط" if u_obj.is_active() else "🔴 موقوف"
            plan_name = PLANS.get(u_obj.plan, PLANS["trial"]).name
            expires = time.strftime("%Y-%m-%d", time.localtime(u_obj.expires_at))
            created = time.strftime("%Y-%m-%d", time.localtime(u_obj.created_at))
            text = (
                f"👤 **المستخدم {uid}**\n"
                f"{act}\n"
                f"📋 الخطة: {plan_name}\n"
                f"📅 أنشئ: {created}\n"
                f"⏳ ينتهي: {expires}\n"
                f"🔑 API Key: {'✅' if u_obj.woopsocial_api_key else '❌'}"
            )
            await query.edit_message_text(
                text, reply_markup=_user_details_keyboard(int(uid), u_obj)
            )

        elif data.startswith("admin_stop_"):
            uid = data.replace("admin_stop_", "")
            u = users_data.get(uid)
            if u:
                u["status"] = "inactive"
                users_data[uid] = u
                await store.save("users")
                await query.edit_message_text(f"✅ تم إيقاف المستخدم {uid}")

        elif data.startswith("admin_expire_"):
            uid = data.replace("admin_expire_", "")
            u = users_data.get(uid)
            if u:
                u["expires_at"] = time.time()
                users_data[uid] = u
                await store.save("users")
                await query.edit_message_text(f"⛔ تم إنهاء خطة المستخدم {uid} فوراً")

        elif data.startswith("admin_activate_"):
            uid = data.replace("admin_activate_", "")
            u = users_data.get(uid)
            if u:
                u["status"] = "active"
                users_data[uid] = u
                await store.save("users")
                await query.edit_message_text(f"✅ تم تفعيل المستخدم {uid}")
                try:
                    u_obj = User(**u)
                    pp = PLANS.get(u_obj.plan, PLANS["trial"])
                    lang = u_obj.language
                    await context.bot.send_message(
                        chat_id=int(uid),
                        text=(
                            f"🎉 تم تفعيل حسابك في TG2TikTok!\n\n"
                            f"📋 خطتك: {pp.name}\n"
                            f"📅 تنتهي: {time.strftime('%Y-%m-%d', time.localtime(u_obj.expires_at))}\n\n"
                            f"⚙️ إعداداتك الحالية:\n"
                            f"  ⚡ السرعة: {u_obj.speed}x\n"
                            f"  ✂️ التقسيم: {u_obj.split_minutes} دقائق\n"
                            f"  ⏰ الفاصل: {u_obj.schedule_interval} دقيقة\n\n"
                            f"كيفية الاستخدام:\n"
                            f"1️⃣ أرسل رابط يوتيوب للبوت\n"
                            f"2️⃣ اختر عدد الأجزاء\n"
                            f"3️⃣ سيتم الرفع والجدولة تلقائياً\n\n"
                            f"للاستفسارات: @{SUPPORT_USERNAME}"
                        ),
                    )
                except Exception:
                    pass

        elif data.startswith("admin_lang_"):
            parts = data.split("_")
            uid = parts[2]
            u = users_data.get(uid)
            if not u:
                await query.edit_message_text("❌ المستخدم غير موجود.")
                return
            if len(parts) >= 4:
                new_lang = parts[3]
                u["language"] = new_lang
                users_data[uid] = u
                await store.save("users")
                lang_name = "العربية" if new_lang == "ar" else "English"
                await query.edit_message_text(f"✅ تم تغيير لغة المستخدم {uid} إلى {lang_name}")
            else:
                await query.edit_message_text(
                    "🌐 اختر اللغة:", reply_markup=_lang_selector(int(uid))
                )

        elif data.startswith("admin_delete_"):
            uid = data.replace("admin_delete_", "")
            if uid in users_data:
                del users_data[uid]
                await store.save("users")
                await query.edit_message_text(f"✅ تم حذف المستخدم {uid}")

        elif data.startswith("admin_plan_"):
            uid = data.replace("admin_plan_", "")
            context.user_data["admin_plan_uid"] = uid
            await query.edit_message_text(
                "اختر الخطة الجديدة:",
                reply_markup=_plan_selector(prefix="admin_setplan:"),
            )

        elif data.startswith("admin_setplan:"):
            plan = data.replace("admin_setplan:", "")
            uid = context.user_data.get("admin_plan_uid")
            if uid and uid in users_data:
                pp = PLANS.get(plan, PLANS["trial"])
                users_data[uid]["plan"] = plan
                users_data[uid]["expires_at"] = time.time() + pp.duration_days * 86400
                await store.save("users")
                await query.edit_message_text(
                    f"✅ تم تغيير خطة المستخدم {uid} إلى {pp.name}"
                )

        elif data in ("admin_back", "admin_noop"):
            await query.edit_message_text("🔐 لوحة التحكم", reply_markup=_main_keyboard())

        elif data == "admin_add":
            await query.edit_message_text("أرسل معرف المستخدم (user_id):")
            return ASK_TELEGRAM_ID

        elif data.startswith("admin_ig_"):
            uid = data.replace("admin_ig_", "")
            context.user_data["admin_ig_uid"] = uid
            await query.edit_message_text(
                "أرسل Instagram Account ID (أو أرسل 'skip' لإلغاء):"
            )
            context.user_data["admin_expected_state"] = "admin_ig"
            return

        elif data.startswith("admin_extend_"):
            uid = data.replace("admin_extend_", "")
            context.user_data["admin_extend_uid"] = uid
            await query.edit_message_text(
                "أرسل عدد الأيام الإضافية لإضافتها إلى الاشتراك الحالي:"
            )
            return ASK_EXTEND_DAYS

        elif data == "admin_cookies":
            await query.edit_message_text(
                "🍪 أرسل ملف الكوكيز (.txt بصيغة Netscape) أو الصق محتوى الكوكيز كنص مباشر:"
            )
            return WAITING_COOKIES

        elif data == "admin_cookies_status":
            info = await get_last_update_info()
            if info:
                ts = info.get("updated_at")
                by = info.get("updated_by")
                time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "غير معروف"
                await query.edit_message_text(
                    f"🍪 حالة كوكيز YouTube:\n"
                    f"🕐 آخر تحديث: {time_str}\n"
                    f"👤 بواسطة: {by}",
                    reply_markup=_main_keyboard(),
                )
            else:
                await query.edit_message_text(
                    "⚠️ لم يتم تحديث الكوكيز من البوت بعد — يُستعمل env variable الافتراضي.",
                    reply_markup=_main_keyboard(),
                )

    async def _show_users(query, users_data, page):
        per_page = 5
        total_pages = max(1, (len(users_data) + per_page - 1) // per_page)
        start = page * per_page
        items = list(users_data.items())[start:start + per_page]
        lines = [f"👥 المستخدمين (صفحة {page + 1}/{total_pages}):"]
        for uid, u in items:
            u_obj = User(**u)
            act = "🟢" if u_obj.is_active() else "🔴"
            plan_name = PLANS.get(u_obj.plan, PLANS["trial"]).name
            expires = time.strftime("%Y-%m-%d", time.localtime(u_obj.expires_at))
            lines.append(f"{act} ID: {uid} | {plan_name} | {expires}")
        buttons = []
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"admin_users_page_{page - 1}"))
        nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="admin_noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"admin_users_page_{page + 1}"))
        if nav:
            buttons.append(nav)
        for uid, _ in items:
            buttons.append([
                InlineKeyboardButton(f"👤 {uid}", callback_data=f"admin_user_{uid}")
            ])
        buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")])
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    admin_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_callback, pattern="^admin_"
                r"(add|stats|users|users_page_\d+|stop_\d+|activate_\d+|"
                r"lang_\d+(?:_(?:ar|en))?|delete_\d+|"
                r"plan_\d+|setplan:|setplan_|back|noop|user_\d+|ig_\d+|"
                r"extend_\d+|expire_\d+|cookies|cookies_status)"),
            CommandHandler("update_cookies", _cmd_update_cookies),
        ],
        states={
            ASK_TELEGRAM_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _on_telegram_id)
            ],
            ASK_PLAN: [CallbackQueryHandler(_on_plan, pattern="^admin_newplan:")],
            ASK_API_KEY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _on_api_key)
            ],
            ASK_PROJECT_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _on_project_id)
            ],
            ASK_ACCOUNT_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _on_account_id)
            ],
            ASK_INSTAGRAM_ACCOUNT_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _on_instagram_account_id)
            ],
            ASK_CUSTOM_DAYS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _on_custom_days)
            ],
            ASK_EXTEND_DAYS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _on_admin_extend)
            ],
            WAITING_COOKIES: [
                MessageHandler(filters.Document.FileExtension("txt"), _on_cookies_document),
                MessageHandler(filters.TEXT & ~filters.COMMAND, _on_cookies_text),
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        allow_reentry=True,
    )

    broadcast_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(_start_broadcast, pattern="^admin_broadcast$")],
        states={
            ASK_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _on_broadcast)
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )

    admin_ig_handler = MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.UpdateType.CHANNEL_POST,
        _on_admin_ig_text,
    )

    async def _cmd_update_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update, admin_id):
            await update.message.reply_text(t("ar", "not_admin"))
            return ConversationHandler.END
        await update.message.reply_text(
            "🍪 أرسل ملف الكوكيز (.txt بصيغة Netscape) أو الصق محتوى الكوكيز كنص مباشر:"
        )
        return WAITING_COOKIES

    async def _on_cookies_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update, admin_id):
            return ConversationHandler.END
        doc = update.message.document
        if not doc.file_name.endswith(".txt"):
            await update.message.reply_text("❌ الملف يجب أن يكون .txt. حاول مجدداً أو أرسل /cancel.")
            return WAITING_COOKIES
        try:
            file = await context.bot.get_file(doc.file_id)
            raw = await file.download_as_bytearray()
            text = raw.decode("utf-8", errors="replace")
        except Exception as e:
            await update.message.reply_text(f"❌ فشل قراءة الملف: {e}. حاول مجدداً.")
            return WAITING_COOKIES
        if not _looks_like_cookies(text):
            await update.message.reply_text("❌ الملف لا يحتوي على كوكيز بصيغة صحيحة. حاول مجدداً.")
            return WAITING_COOKIES
        import base64
        cookies_b64 = base64.b64encode(text.encode()).decode()
        try:
            await set_cookies_b64(cookies_b64, update.effective_user.id)
            now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
            await update.message.reply_text(
                f"✅ تم تحديث كوكيز YouTube بنجاح.\n"
                f"🕐 الوقت: {now_str}\n"
                f"ستُستعمل في كل التحميلات الجديدة فوراً."
            )
        except Exception as e:
            await update.message.reply_text(f"❌ فشل التحديث: {e}. حاول مجدداً بـ /update_cookies.")
        return ConversationHandler.END

    async def _on_cookies_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update, admin_id):
            return ConversationHandler.END
        text = update.message.text.strip()
        if not _looks_like_cookies(text):
            await update.message.reply_text(
                "❌ النص لا يشبه صيغة كوكيز صالحة. أرسل ملف .txt أو الصق محتوى الكوكيز الصحيح.\n"
                "hint: يجب أن يبدأ بـ # Netscape HTTP Cookie File أو يحتوي على أسطر مفصولة بـ tab."
            )
            return WAITING_COOKIES
        import base64
        cookies_b64 = base64.b64encode(text.encode()).decode()
        try:
            await set_cookies_b64(cookies_b64, update.effective_user.id)
            now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
            await update.message.reply_text(
                f"✅ تم تحديث كوكيز YouTube بنجاح.\n"
                f"🕐 الوقت: {now_str}\n"
                f"ستُستعمل في كل التحميلات الجديدة فوراً."
            )
        except Exception as e:
            await update.message.reply_text(f"❌ فشل التحديث: {e}. حاول مجدداً بـ /update_cookies.")
        return ConversationHandler.END

    app.bot_data["admin_id"] = admin_id
    app.add_handler(CommandHandler("start", start))
    app.add_handler(admin_handler)
    app.add_handler(broadcast_handler)
    app.add_handler(admin_ig_handler)
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))

    return app


def _looks_like_cookies(text: str) -> bool:
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
    tab_lines = [l for l in lines if "\t" in l]
    if tab_lines:
        return True
    if any(l.startswith("# Netscape") or l.startswith("# HTTP") for l in text.splitlines()):
        return True
    return False


async def _on_telegram_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update, context.application.bot_data.get("admin_id", 0)):
        return ConversationHandler.END
    text = update.message.text.strip()
    try:
        uid = int(text)
    except ValueError:
        await update.message.reply_text("❌ يجب أن يكون المعرف رقماً.")
        return ConversationHandler.END

    users_data = await store.get("users")
    if str(uid) in users_data:
        await update.message.reply_text("❌ المستخدم موجود مسبقاً.")
        return ConversationHandler.END

    context.user_data["new_uid"] = uid
    await update.message.reply_text("اختر الخطة:", reply_markup=_plan_selector())
    return ASK_PLAN


async def _on_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(update, context.application.bot_data.get("admin_id", 0)):
        return ConversationHandler.END

    plan = query.data.replace("admin_newplan:", "")
    context.user_data["new_plan"] = plan
    context.user_data["new_username"] = str(context.user_data["new_uid"])
    await query.edit_message_text(
        "عدد أيام الاشتراك (أرسل رقماً، أو 'skip' لاستخدام المدة الافتراضية):"
    )
    return ASK_CUSTOM_DAYS


async def _on_custom_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update, context.application.bot_data.get("admin_id", 0)):
        return ConversationHandler.END
    text = update.message.text.strip()
    if text.lower() == "skip":
        context.user_data["custom_days"] = None
    else:
        try:
            val = int(text)
            if val < 1:
                raise ValueError
            context.user_data["custom_days"] = val
        except ValueError:
            await update.message.reply_text("❌ الرقم غير صالح. أرسل رقماً صحيحاً موجباً، أو 'skip':")
            return ASK_CUSTOM_DAYS
    await update.message.reply_text("أرسل WoopSocial API Key:")
    return ASK_API_KEY


async def _on_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update, context.application.bot_data.get("admin_id", 0)):
        return ConversationHandler.END
    context.user_data["new_api_key"] = update.message.text.strip()
    await update.message.reply_text("أرسل WoopSocial Project ID:")
    return ASK_PROJECT_ID


async def _on_project_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update, context.application.bot_data.get("admin_id", 0)):
        return ConversationHandler.END
    context.user_data["new_project_id"] = update.message.text.strip()
    await update.message.reply_text("أرسل WoopSocial Account ID:")
    return ASK_ACCOUNT_ID


async def _on_account_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update, context.application.bot_data.get("admin_id", 0)):
        return ConversationHandler.END

    context.user_data["new_account_id"] = update.message.text.strip()
    await update.message.reply_text(
        "أرسل Instagram Account ID (أو أرسل 'skip' لتخطي هذه الخطوة):"
    )
    return ASK_INSTAGRAM_ACCOUNT_ID


async def _on_instagram_account_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update, context.application.bot_data.get("admin_id", 0)):
        return ConversationHandler.END

    uid = context.user_data["new_uid"]
    plan = context.user_data["new_plan"]
    api_key = context.user_data["new_api_key"]
    project_id = context.user_data["new_project_id"]
    account_id = context.user_data["new_account_id"]
    username = context.user_data.get("new_username", str(uid))

    ig_text = update.message.text.strip()
    ig_account_id = "" if ig_text.lower() == "skip" else ig_text

    pp = PLANS.get(plan, PLANS["trial"])
    custom_days = context.user_data.pop("custom_days", None)
    duration_days = custom_days if custom_days else pp.duration_days
    now = time.time()
    user = User(
        telegram_id=uid,
        plan=plan,
        created_at=now,
        expires_at=now + duration_days * 86400,
        username=username,
        status="active",
        woopsocial_api_key=api_key,
        woopsocial_project_id=project_id,
        woopsocial_account_id=account_id,
        instagram_account_id=ig_account_id,
        publish_instagram=bool(ig_account_id),
    )

    users_data = await store.get("users")
    users_data[str(uid)] = user.__dict__
    await store.save("users")

    try:
        await context.bot.send_message(
            chat_id=uid,
            text=f"🎉 تم تفعيل حسابك!\nالخطة: {pp.name}\nتاريخ الانتهاء: {time.strftime('%Y-%m-%d', time.localtime(user.expires_at))}",
        )
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ تم إنشاء المستخدم!\n👤 {username}\n📋 {pp.name}",
        reply_markup=_main_keyboard(),
    )
    return ConversationHandler.END


async def _on_admin_ig_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update, context.application.bot_data.get("admin_id", 0)):
        return
    expected = context.user_data.get("admin_expected_state")
    if expected != "admin_ig":
        return
    uid = context.user_data.get("admin_ig_uid")
    if not uid:
        return
    text = update.message.text.strip()
    users_data = await store.get("users")
    if uid not in users_data:
        await update.message.reply_text("❌ المستخدم غير موجود.")
        context.user_data.pop("admin_expected_state", None)
        context.user_data.pop("admin_ig_uid", None)
        return
    if text.lower() != "skip":
        users_data[uid]["instagram_account_id"] = text
        users_data[uid]["publish_instagram"] = True
        await store.save("users")
        await update.message.reply_text(f"✅ تم ربط حساب Instagram للمستخدم {uid}")
    else:
        await update.message.reply_text(f"⏭️ تم تخطي ربط Instagram للمستخدم {uid}")
    context.user_data.pop("admin_expected_state", None)
    context.user_data.pop("admin_ig_uid", None)


async def _on_admin_extend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update, context.application.bot_data.get("admin_id", 0)):
        return ConversationHandler.END
    uid = context.user_data.get("admin_extend_uid")
    if not uid:
        await update.message.reply_text("❌ خطأ: لم يتم تحديد المستخدم.")
        return ConversationHandler.END
    text = update.message.text.strip()
    try:
        extra_days = int(text)
        if extra_days < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ الرقم غير صالح. أرسل رقماً صحيحاً موجباً:")
        return ASK_EXTEND_DAYS
    users_data = await store.get("users")
    if uid not in users_data:
        await update.message.reply_text("❌ المستخدم غير موجود.")
        return ConversationHandler.END
    old_expires = users_data[uid].get("expires_at", time.time())
    new_expires = max(old_expires, time.time()) + extra_days * 86400
    users_data[uid]["expires_at"] = new_expires
    await store.save("users")
    expire_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(new_expires))
    await update.message.reply_text(f"✅ تم تمديد اشتراك المستخدم {uid} لمدة {extra_days} يوم.\n📅 ينتهي: {expire_str}")
    context.user_data.pop("admin_extend_uid", None)
    return ConversationHandler.END


async def _start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(update, context.application.bot_data.get("admin_id", 0)):
        return ConversationHandler.END
    await query.edit_message_text("📢 أرسل الرسالة التي تريد بثها لجميع المستخدمين:")
    return ASK_MESSAGE


async def _on_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update, context.application.bot_data.get("admin_id", 0)):
        return ConversationHandler.END
    text = update.message.text.strip()
    users_data = await store.get("users")
    sent = 0
    for uid in users_data:
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(
        f"✅ تم البث لـ {sent} من أصل {len(users_data)} مستخدم."
    )
    return ConversationHandler.END
