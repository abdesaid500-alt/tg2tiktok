from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import PLANS


def main_menu(lang="ar"):
    buttons = [
        [InlineKeyboardButton("📥 إرسال رابط" if lang == "ar" else "📥 Send Link",
                              callback_data="send_link")],
        [InlineKeyboardButton("📋 طابوري" if lang == "ar" else "📋 My Queue",
                              callback_data="my_queue")],
        [InlineKeyboardButton("⏱ الإعدادات" if lang == "ar" else "⏱ Settings",
                              callback_data="settings")],
        [InlineKeyboardButton("🗂 خططي" if lang == "ar" else "🗂 Plans",
                              callback_data="plans")],
        [InlineKeyboardButton("🌐 اللغة" if lang == "ar" else "🌐 Language",
                              callback_data="toggle_lang")],
    ]
    return InlineKeyboardMarkup(buttons)


def settings_keyboard(lang="ar"):
    buttons = [
        [InlineKeyboardButton("🚀 السرعة" if lang == "ar" else "🚀 Speed",
                              callback_data="set_speed")],
        [InlineKeyboardButton("✂️ التقطيع" if lang == "ar" else "✂️ Split",
                              callback_data="set_split")],
        [InlineKeyboardButton("⏱ الفاصل الزمني" if lang == "ar" else "⏱ Interval",
                              callback_data="set_schedule")],
        [InlineKeyboardButton("🔙 رجوع" if lang == "ar" else "🔙 Back",
                              callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(buttons)


def plans_keyboard(lang="ar"):
    buttons = []
    for key, plan in PLANS.items():
        label = f"{plan['name_ar']} - {plan['days']} يوم" if lang == "ar" else f"{key} - {plan['days']} days"
        buttons.append([InlineKeyboardButton(label, callback_data=f"select_plan_{key}")])
    buttons.append([InlineKeyboardButton("🔙 رجوع" if lang == "ar" else "🔙 Back",
                                         callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def cancel_keyboard(lang="ar"):
    buttons = [
        [InlineKeyboardButton("❌ إلغاء الكل" if lang == "ar" else "❌ Cancel All",
                              callback_data="cancel_queue")],
        [InlineKeyboardButton("🔙 رجوع" if lang == "ar" else "🔙 Back",
                              callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(buttons)


def admin_main_menu(lang="ar"):
    buttons = [
        [InlineKeyboardButton("👥 المستخدمين" if lang == "ar" else "👥 Users",
                              callback_data="admin_users")],
        [InlineKeyboardButton("📊 إحصائيات" if lang == "ar" else "📊 Statistics",
                              callback_data="admin_stats")],
        [InlineKeyboardButton("➕ إضافة مستخدم" if lang == "ar" else "➕ Add User",
                              callback_data="admin_add_user")],
        [InlineKeyboardButton("📢 بث رسالة" if lang == "ar" else "📢 Broadcast",
                              callback_data="admin_broadcast")],
    ]
    return InlineKeyboardMarkup(buttons)


def admin_users_pagination(page, total_pages, lang="ar"):
    buttons = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"admin_users_page_{page - 1}"))
    row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="admin_noop"))
    if page < total_pages - 1:
        row.append(InlineKeyboardButton("➡️", callback_data=f"admin_users_page_{page + 1}"))
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 رجوع" if lang == "ar" else "🔙 Back",
                                         callback_data="admin_back")])
    return InlineKeyboardMarkup(buttons)


def admin_user_actions(user_id, lang="ar"):
    sid = str(user_id)
    buttons = [
        [InlineKeyboardButton("🔇 تعليق" if lang == "ar" else "🔇 Suspend",
                              callback_data=f"admin_toggle_{sid}"),
         InlineKeyboardButton("🗑 حذف" if lang == "ar" else "🗑 Delete",
                              callback_data=f"admin_delete_{sid}")],
        [InlineKeyboardButton("🔄 تغيير الخطة" if lang == "ar" else "🔄 Change Plan",
                              callback_data=f"admin_plan_{sid}")],
        [InlineKeyboardButton("🔙 رجوع" if lang == "ar" else "🔙 Back",
                              callback_data="admin_users")],
    ]
    return InlineKeyboardMarkup(buttons)


def admin_plan_selector(lang="ar"):
    buttons = []
    for key in PLANS:
        buttons.append([InlineKeyboardButton(PLANS[key]["name_ar"],
                                             callback_data=f"admin_setplan_{key}")])
    buttons.append([InlineKeyboardButton("🔙 رجوع" if lang == "ar" else "🔙 Back",
                                         callback_data="admin_users")])
    return InlineKeyboardMarkup(buttons)
