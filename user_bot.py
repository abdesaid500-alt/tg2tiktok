import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from database import get_user, create_user, get_plan_info, is_active
from config import PLANS
from i18n import t
from keyboards import (
    main_menu,
    settings_keyboard,
    plans_keyboard,
    cancel_keyboard,
)
from queue_manager import add_to_queue, get_queue_size, cancel_queue, process_queue

logger = logging.getLogger("user_bot")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        user = create_user(user_id)
    lang = user.get("language", "ar")
    plan_info = get_plan_info(user_id)
    plan_name = plan_info["plan_name_ar"] if plan_info else t("no_active_plan", lang)
    expires = plan_info["expires"] if plan_info else "-"
    text = t("welcome", lang, name=update.effective_user.first_name,
             plan=plan_name, expires=expires)
    await update.message.reply_text(text, reply_markup=main_menu(lang))


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        user = create_user(user_id)
    lang = user.get("language", "ar")
    plan_info = get_plan_info(user_id)
    if not plan_info:
        await update.message.reply_text(t("no_active_plan", lang))
        return
    remaining = plan_info["daily_limit"] - plan_info["daily_count"]
    text = t("menu", lang, plan=plan_info["plan_name_ar"],
             remaining=max(0, remaining), limit=plan_info["daily_limit"])
    await update.message.reply_text(text, reply_markup=main_menu(lang))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        user = create_user(user_id)
    lang = user.get("language", "ar")
    text = update.message.text.strip()
    youtube_regex = r'(https?://)?(www\.)?(youtube\.com|youtu\.be|m\.youtube\.com)/'
    if not re.search(youtube_regex, text):
        await update.message.reply_text(t("invalid_link", lang))
        return
    if not is_active(user_id):
        await update.message.reply_text(t("not_active", lang))
        return
    plan_info = get_plan_info(user_id)
    if not plan_info:
        await update.message.reply_text(t("no_active_plan", lang))
        return
    success, err = add_to_queue(user_id, text)
    if success:
        qsize = get_queue_size(user_id)
        max_q = plan_info["max_queue"]
        msg = await update.message.reply_text(
            t("add_to_queue", lang, pos=qsize, max=max_q)
        )
        await process_queue(user_id, context.application.bot)
    else:
        await update.message.reply_text(t("queue_full", lang, max=plan_info["max_queue"]))


async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user.get("language", "ar") if user else "ar"
    plan_info = get_plan_info(user_id)
    max_q = plan_info["max_queue"] if plan_info else 3
    qsize = get_queue_size(user_id)
    text = t("queue_status", lang, count=qsize, max=max_q)
    await update.message.reply_text(text, reply_markup=cancel_keyboard(lang))


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    lang = user.get("language", "ar") if user else "ar"
    if get_queue_size(user_id) == 0:
        await update.message.reply_text(t("cancel_no_tasks", lang))
        return
    cancel_queue(user_id)
    await update.message.reply_text(t("queue_cancelled", lang))


async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        user = create_user(user_id)
    lang = user.get("language", "ar")
    speed = user.get("speed", 1.1)
    split_min = user.get("split_minutes", 10)
    schedule_min = user.get("schedule_minutes", 15)
    text = t("schedule_settings", lang, speed=speed,
             split=split_min, schedule=schedule_min)
    await update.message.reply_text(text, reply_markup=settings_keyboard(lang))


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        user = create_user(user_id)
    lang = user.get("language", "ar")
    data = query.data
    if data == "main_menu":
        plan_info = get_plan_info(user_id)
        remaining = 0
        limit = 10
        plan_name = "-"
        if plan_info:
            remaining = plan_info["daily_limit"] - plan_info["daily_count"]
            limit = plan_info["daily_limit"]
            plan_name = plan_info["plan_name_ar"]
        text = t("menu", lang, plan=plan_name,
                 remaining=max(0, remaining), limit=limit)
        await query.edit_message_text(text, reply_markup=main_menu(lang))
    elif data == "send_link":
        await query.edit_message_text(t("send_link", lang))
    elif data == "my_queue":
        plan_info = get_plan_info(user_id)
        max_q = plan_info["max_queue"] if plan_info else 3
        qsize = get_queue_size(user_id)
        text = t("queue_status", lang, count=qsize, max=max_q)
        await query.edit_message_text(text, reply_markup=cancel_keyboard(lang))
    elif data == "settings":
        speed = user.get("speed", 1.1)
        split_min = user.get("split_minutes", 10)
        schedule_min = user.get("schedule_minutes", 15)
        text = t("schedule_settings", lang, speed=speed,
                 split=split_min, schedule=schedule_min)
        await query.edit_message_text(text, reply_markup=settings_keyboard(lang))
    elif data == "plans":
        await query.edit_message_text(
            t("plan_selector", lang),
            reply_markup=plans_keyboard(lang),
        )
    elif data == "toggle_lang":
        new_lang = "en" if lang == "ar" else "ar"
        from database import update_user
        update_user(user_id, language=new_lang)
        await query.edit_message_text(
            "✅ تم تغيير اللغة إلى العربية" if new_lang == "ar" else "✅ Language changed to English",
            reply_markup=main_menu(new_lang),
        )
    elif data == "cancel_queue":
        cancel_queue(user_id)
        await query.edit_message_text(t("queue_cancelled", lang))
    elif data.startswith("select_plan_"):
        plan_key = data.replace("select_plan_", "")
        plan_info = PLANS.get(plan_key, {})
        name = plan_info.get("name_ar", plan_key)
        await query.edit_message_text(
            t("plan_selected", lang, plan=name)
        )
    elif data == "set_speed":
        speeds = [("1.0x", "1.0"), ("1.1x", "1.1"), ("1.2x", "1.2"),
                  ("1.5x", "1.5"), ("2.0x", "2.0")]
        buttons = [
            [InlineKeyboardButton(s[0], callback_data=f"speed_{s[1]}")]
            for s in speeds
        ]
        buttons.append([InlineKeyboardButton(
            "🔙 رجوع" if lang == "ar" else "🔙 Back",
            callback_data="settings"
        )])
        await query.edit_message_text(
            "اختر السرعة:" if lang == "ar" else "Choose speed:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    elif data.startswith("speed_"):
        speed_val = float(data.replace("speed_", ""))
        from database import update_user
        update_user(user_id, speed=speed_val)
        await query.edit_message_text(
            f"✅ تم تعيين السرعة: {speed_val}x"
        )
    elif data == "set_split":
        splits = [("5 دقائق", "5"), ("10 دقائق", "10"), ("15 دقائق", "15"),
                  ("20 دقيقة", "20")]
        buttons = [
            [InlineKeyboardButton(s[0], callback_data=f"split_{s[1]}")]
            for s in splits
        ]
        buttons.append([InlineKeyboardButton(
            "🔙 رجوع" if lang == "ar" else "🔙 Back",
            callback_data="settings"
        )])
        await query.edit_message_text(
            "اختر مدة التقطيع:" if lang == "ar" else "Choose split duration:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    elif data.startswith("split_"):
        split_val = int(data.replace("split_", ""))
        from database import update_user
        update_user(user_id, split_minutes=split_val)
        await query.edit_message_text(
            f"✅ تم تعيين التقطيع: {split_val} دقائق"
        )
    elif data == "set_schedule":
        scheds = [("5 دقائق", "5"), ("10 دقائق", "10"), ("15 دقيقة", "15"),
                  ("30 دقيقة", "30"), ("60 دقيقة", "60")]
        buttons = [
            [InlineKeyboardButton(s[0], callback_data=f"sched_{s[1]}")]
            for s in scheds
        ]
        buttons.append([InlineKeyboardButton(
            "🔙 رجوع" if lang == "ar" else "🔙 Back",
            callback_data="settings"
        )])
        await query.edit_message_text(
            "اختر الفاصل الزمني:" if lang == "ar" else "Choose interval:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    elif data.startswith("sched_"):
        sched_val = int(data.replace("sched_", ""))
        from database import update_user
        update_user(user_id, schedule_minutes=sched_val)
        await query.edit_message_text(
            f"✅ تم تعيين الفاصل: {sched_val} دقائق"
        )


def build_user_app():
    from config import USER_BOT_TOKEN
    app = Application.builder().token(USER_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("queue", queue_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("schedule", schedule_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_handler))
    return app
