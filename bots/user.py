import logging
import re
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler,
)

from core.models import User, PLANS, FREE_PARTS_LIMIT
from core import storage as store
from core.i18n import t
from pipeline.worker import Worker

logger = logging.getLogger(__name__)

(
    ONBOARDING_LANG, ONBOARDING_SPEED, ONBOARDING_SPLIT, ONBOARDING_INTERVAL,
) = range(100, 104)

YT_PATTERN = re.compile(
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be|m\.youtube\.com)/"
)


def _build_main_keyboard(lang: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "menu_queue"), callback_data="my_queue"),
         InlineKeyboardButton(t(lang, "menu_settings"), callback_data="settings")],
        [InlineKeyboardButton(t(lang, "menu_account"), callback_data="my_account"),
         InlineKeyboardButton(t(lang, "menu_schedule"), callback_data="my_schedule")],
        [InlineKeyboardButton(t(lang, "menu_help"), callback_data="help")],
    ])


def _build_settings_keyboard(lang: str, user: User):
    speed_opts = [("1.0x", "1.0"), ("1.1x", "1.1"), ("1.2x", "1.5"), ("2.0x", "2.0")]
    split_opts = [("5", "5"), ("10", "10"), ("15", "15"), ("20", "20")]
    sched_opts = [("10", "10"), ("15", "15"), ("30", "30"), ("60", "60")]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⚡ {t(lang, 'speed_label')}: {user.speed}x",
                              callback_data="set_speed")],
        [InlineKeyboardButton(f"✂️ {t(lang, 'split_label')}: {user.split_minutes}",
                              callback_data="set_split")],
        [InlineKeyboardButton(f"⏰ {t(lang, 'schedule_label')}: {user.schedule_interval}",
                              callback_data="set_schedule")],
        [InlineKeyboardButton(t(lang, "back"), callback_data="main_menu")],
    ])


def _build_value_keyboard(lang: str, values: list, prefix: str):
    buttons = []
    row = []
    for label, val in values:
        row.append(InlineKeyboardButton(label, callback_data=f"{prefix}{val}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(t(lang, "back"), callback_data="settings")])
    return InlineKeyboardMarkup(buttons)


def create_app(token: str, worker: Worker):
    app = Application.builder().token(token).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        users = await store.get("users")
        u_data = users.get(str(uid))
        if not u_data:
            context.user_data["onboarding_uid"] = uid
            context.user_data["onboarding_user"] = update.effective_user.full_name or str(uid)
            await update.message.reply_text(
                f"🎬 أهلاً بك في TG2TikTok!\n\n"
                f"🚀 لك {FREE_PARTS_LIMIT} جزء مجاني لتجربة البوت!\n"
                f"سنساعدك في ضبط الإعدادات بسرعة.\nاختر اللغة أولاً:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🇸🇦 العربية", callback_data="ob_lang_ar"),
                     InlineKeyboardButton("🇬🇧 English", callback_data="ob_lang_en")],
                ]),
            )
            return ONBOARDING_LANG
        user = User(**u_data)
        lang = user.language
        text = t(lang, "start")
        if user.plan:
            pp = user.plan_params()
            expires = time.strftime("%Y-%m-%d", time.localtime(user.expires_at))
            text += f"\n\n{t(lang, 'account_plan', plan=t(lang, f'plan_{user.plan}'))}\n"
            text += t(lang, "account_expires", date=expires)
        await update.message.reply_text(text, reply_markup=_build_main_keyboard(lang))
        return ConversationHandler.END

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        text = update.message.text.strip()
        lang = "ar"

        users = await store.get("users")
        u_data = users.get(str(uid))
        if not u_data:
            await update.message.reply_text(t("ar", "not_active"))
            return
        user = User(**u_data)
        lang = user.language

        if not YT_PATTERN.search(text):
            await update.message.reply_text(
                t(lang, "invalid_url"), reply_markup=_build_main_keyboard(lang)
            )
            return

        if not user.is_active():
            await update.message.reply_text(t(lang, "not_active"))
            return

        if not user.can_process():
            pp = user.plan_params()
            await update.message.reply_text(
                t(lang, "daily_limit", limit=pp.daily_limit)
            )
            return

        ok, result, item_id = await worker.enqueue(uid, text)
        if not ok:
            if result == "not_active":
                await update.message.reply_text(t(lang, "not_active"))
            elif result == "no_api_key":
                from core.models import PLANS
                plans_text = "\n".join(
                    f"• {pp.name}: {pp.daily_limit} فيديو/يوم | {pp.duration_days} يوم"
                    for pp in PLANS.values()
                )
                await update.message.reply_text(
                    f"❌ انتهت الأجزاء المجانية!\n\n"
                    f"━━━ 📋 خطط الاشتراك ━━━\n{plans_text}\n\n"
                    f"💬 تواصل مع الدعم للاشتراك"
                )
            elif result == "queue_full":
                pp = user.plan_params()
                await update.message.reply_text(
                    t(lang, "queue_full", limit=pp.queue_limit)
                )
            return

        pp = user.plan_params()
        queue_len = len(worker.get_user_queue(uid))
        msg = t(lang, "queued",
                title=text[:40], duration="?",
                position=str(queue_len), id=item_id,
                speed=str(user.speed), split=str(user.split_minutes),
                schedule=str(user.schedule_interval))
        await update.message.reply_text(msg, reply_markup=_build_main_keyboard(lang))

    async def onboarding_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        uid = context.user_data.get("onboarding_uid", update.effective_user.id)

        if data == "ob_lang_ar":
            context.user_data["ob_lang"] = "ar"
            await query.edit_message_text(
                "⚡ اختر سرعة التشغيل:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("1.0x", callback_data="ob_speed_1.0"),
                     InlineKeyboardButton("1.1x", callback_data="ob_speed_1.1")],
                    [InlineKeyboardButton("1.5x", callback_data="ob_speed_1.5"),
                     InlineKeyboardButton("2.0x", callback_data="ob_speed_2.0")],
                ]),
            )
            return ONBOARDING_SPEED

        elif data == "ob_lang_en":
            context.user_data["ob_lang"] = "en"
            await query.edit_message_text(
                "⚡ Choose playback speed:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("1.0x", callback_data="ob_speed_1.0"),
                     InlineKeyboardButton("1.1x", callback_data="ob_speed_1.1")],
                    [InlineKeyboardButton("1.5x", callback_data="ob_speed_1.5"),
                     InlineKeyboardButton("2.0x", callback_data="ob_speed_2.0")],
                ]),
            )
            return ONBOARDING_SPEED

        elif data.startswith("ob_speed_"):
            val = float(data.replace("ob_speed_", ""))
            context.user_data["ob_speed"] = val
            lang = context.user_data.get("ob_lang", "ar")
            text = t(lang, "onboarding_split")
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("1", callback_data="ob_split_1"),
                     InlineKeyboardButton("3", callback_data="ob_split_3"),
                     InlineKeyboardButton("5", callback_data="ob_split_5"),
                     InlineKeyboardButton("10", callback_data="ob_split_10")],
                ]),
            )
            return ONBOARDING_SPLIT

        elif data.startswith("ob_split_"):
            val = int(data.replace("ob_split_", ""))
            context.user_data["ob_split"] = val
            lang = context.user_data.get("ob_lang", "ar")
            text = t(lang, "onboarding_interval")
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("30", callback_data="ob_interval_30"),
                     InlineKeyboardButton("60", callback_data="ob_interval_60"),
                     InlineKeyboardButton("120", callback_data="ob_interval_120"),
                     InlineKeyboardButton("240", callback_data="ob_interval_240")],
                ]),
            )
            return ONBOARDING_INTERVAL

        elif data.startswith("ob_interval_"):
            val = int(data.replace("ob_interval_", ""))
            context.user_data["ob_interval"] = val
            lang = context.user_data.get("ob_lang", "ar")
            speed = context.user_data["ob_speed"]
            split_min = context.user_data["ob_split"]
            interval = context.user_data["ob_interval"]

            now = time.time()
            pp = PLANS["trial"]
            user = User(
                telegram_id=uid,
                plan="trial",
                created_at=now,
                expires_at=now + pp.duration_days * 86400,
                username=context.user_data.get("onboarding_user", str(uid)),
                language=lang,
                speed=speed,
                split_minutes=split_min,
                schedule_interval=interval,
            )
            users = await store.get("users")
            users[str(uid)] = user.__dict__
            await store.save("users")

            await query.edit_message_text(
                t(lang, "onboarding_done"),
                reply_markup=_build_main_keyboard(lang),
            )
            return ConversationHandler.END

    async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        uid = update.effective_user.id
        data = query.data
        lang = "ar"

        users = await store.get("users")
        u_data = users.get(str(uid))
        if not u_data:
            await query.edit_message_text("❌ حساب غير موجود.")
            return
        user = User(**u_data)
        lang = user.language

        if data == "main_menu":
            text = t(lang, "start")
            if user.plan:
                pp = user.plan_params()
                expires = time.strftime("%Y-%m-%d", time.localtime(user.expires_at))
                text += f"\n\n{t(lang, 'account_plan', plan=t(lang, f'plan_{user.plan}'))}\n"
                text += t(lang, "account_expires", date=expires)
            await query.edit_message_text(text, reply_markup=_build_main_keyboard(lang))

        elif data == "settings":
            await query.edit_message_text(
                t(lang, "settings_title"),
                reply_markup=_build_settings_keyboard(lang, user),
            )

        elif data == "my_queue":
            items = worker.get_user_queue(uid)
            if not items:
                await query.edit_message_text(
                    t(lang, "queue_empty"),
                    reply_markup=_build_main_keyboard(lang),
                )
                return
            lines = [t(lang, "queue_header")]
            for it in items:
                st = t(lang, f"status_{it['status']}", default=it["status"])
                lines.append(f"🆔 {it['id']} — {it['title'][:30]}\n⏳ {st}")
            lines.append("")
            await query.edit_message_text(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ إلغاء الكل", callback_data="cancel_queue")],
                    [InlineKeyboardButton(t(lang, "back"), callback_data="main_menu")],
                ]),
            )

        elif data == "cancel_queue":
            count = await worker.cancel_queue(uid)
            if count:
                text = f"✅ تم إلغاء {count} مهمة"
            else:
                text = t(lang, "cancel_no_tasks")
            await query.edit_message_text(
                text, reply_markup=_build_main_keyboard(lang)
            )

        elif data == "my_account":
            pp = user.plan_params()
            expires = time.strftime("%Y-%m-%d", time.localtime(user.expires_at))
            text = (
                f"{t(lang, 'account_title')}\n\n"
                f"{t(lang, 'account_plan', plan=t(lang, f'plan_{user.plan}'))}\n"
                f"{t(lang, 'account_expires', date=expires)}\n"
                f"{t(lang, 'account_daily', used=user.today_count(), limit=pp.daily_limit)}\n"
                f"{t(lang, 'account_total', videos=user.total_videos, parts=user.total_parts)}"
            )
            await query.edit_message_text(text, reply_markup=_build_main_keyboard(lang))

        elif data == "my_schedule":
            if user.last_scheduled_at:
                last = time.strftime(
                    "%Y-%m-%d %H:%M",
                    time.localtime(user.last_scheduled_at),
                )
                text = f"📅 آخر نشر: {last}\n⏰ الفاصل: {user.schedule_interval} دقيقة"
            else:
                text = "📅 لا يوجد جدول نشر بعد."
            await query.edit_message_text(text, reply_markup=_build_main_keyboard(lang))

        elif data == "help":
            await query.edit_message_text(
                t(lang, "help"), reply_markup=_build_main_keyboard(lang)
            )

        elif data == "set_speed":
            vals = [("1.0x", "1.0"), ("1.1x", "1.1"), ("1.5x", "1.5"), ("2.0x", "2.0")]
            await query.edit_message_text(
                t(lang, "speed_label"),
                reply_markup=_build_value_keyboard(lang, vals, "speed_"),
            )

        elif data.startswith("speed_"):
            val = float(data.replace("speed_", ""))
            user.speed = val
            users[str(uid)] = user.__dict__
            await store.save("users")
            await query.edit_message_text(
                t(lang, "settings_updated",
                  setting=t(lang, "speed_label"), value=f"{val}x"),
                reply_markup=_build_settings_keyboard(lang, user),
            )

        elif data == "set_split":
            vals = [("5", "5"), ("10", "10"), ("15", "15"), ("20", "20")]
            await query.edit_message_text(
                t(lang, "split_label"),
                reply_markup=_build_value_keyboard(lang, vals, "split_"),
            )

        elif data.startswith("split_"):
            val = int(data.replace("split_", ""))
            user.split_minutes = val
            users[str(uid)] = user.__dict__
            await store.save("users")
            await query.edit_message_text(
                t(lang, "settings_updated",
                  setting=t(lang, "split_label"), value=f"{val}د"),
                reply_markup=_build_settings_keyboard(lang, user),
            )

        elif data == "set_schedule":
            vals = [("10", "10"), ("15", "15"), ("30", "30"), ("60", "60")]
            await query.edit_message_text(
                t(lang, "schedule_label"),
                reply_markup=_build_value_keyboard(lang, vals, "sched_"),
            )

        elif data.startswith("sched_"):
            val = int(data.replace("sched_", ""))
            user.schedule_interval = val
            users[str(uid)] = user.__dict__
            await store.save("users")
            await query.edit_message_text(
                t(lang, "settings_updated",
                  setting=t(lang, "schedule_label"), value=f"{val}د"),
                reply_markup=_build_settings_keyboard(lang, user),
            )

    onboarding_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ONBOARDING_LANG: [CallbackQueryHandler(onboarding_callback, pattern="^ob_lang_")],
            ONBOARDING_SPEED: [CallbackQueryHandler(onboarding_callback, pattern="^ob_speed_")],
            ONBOARDING_SPLIT: [CallbackQueryHandler(onboarding_callback, pattern="^ob_split_")],
            ONBOARDING_INTERVAL: [CallbackQueryHandler(onboarding_callback, pattern="^ob_interval_")],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )

    app.add_handler(onboarding_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_handler, pattern="^("
        "main_menu|settings|my_queue|cancel_queue|my_account|my_schedule|help|"
        "set_speed|speed_|set_split|split_|set_schedule|sched_"
        ")"))
    return app
