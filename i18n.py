TEXTS = {
    "welcome": {
        "ar": "مرحباً {name}! 👋\nاشتراكك: {plan} | ينتهي: {expires}",
        "en": "Welcome {name}! 👋\nPlan: {plan} | Expires: {expires}",
    },
    "send_link": {
        "ar": "أرسل رابط يوتيوب للبدء ⬇️",
        "en": "Send a YouTube link to start ⬇️",
    },
    "add_to_queue": {
        "ar": "✅ تمت إضافة الرابط إلى الطابور\nالموقع: {pos}/{max}",
        "en": "✅ Link added to queue\nPosition: {pos}/{max}",
    },
    "queue_full": {
        "ar": "⚠️ الطابور ممتلئ ({max}). انتظر حتى اكتمال المهام الحالية.",
        "en": "⚠️ Queue is full ({max}). Wait for current tasks to finish.",
    },
    "queue_empty": {
        "ar": "📭 الطابور فارغ. أرسل رابط يوتيوب للبدء.",
        "en": "📭 Queue is empty. Send a YouTube link to start.",
    },
    "queue_status": {
        "ar": "📋 طابورك: {count} مهمة\nالحد الأقصى: {max}",
        "en": "📋 Your queue: {count} tasks\nMax limit: {max}",
    },
    "queue_cancelled": {
        "ar": "❌ تم إلغاء جميع المهام.",
        "en": "❌ All tasks cancelled.",
    },
    "downloading": {
        "ar": "⬇️ جاري التحميل من يوتيوب...",
        "en": "⬇️ Downloading from YouTube...",
    },
    "splitting": {
        "ar": "✂️ جاري تقطيع الفيديو ({part}/{total})...",
        "en": "✂️ Splitting video ({part}/{total})...",
    },
    "uploading": {
        "ar": "☁️ جاري رفع الجزء {part}/{total} على Drive...",
        "en": "☁️ Uploading part {part}/{total} to Drive...",
    },
    "scheduling": {
        "ar": "📤 تم رفع الجزء {part}/{total}\nسيُنشر بعد {minutes} دقيقة",
        "en": "📤 Part {part}/{total} uploaded\nWill be posted in {minutes} minutes",
    },
    "done": {
        "ar": "✅ تمت معالجة جميع الأجزاء بنجاح!\n{parts} جزء → TikTok",
        "en": "✅ All parts processed successfully!\n{parts} parts → TikTok",
    },
    "error": {
        "ar": "❌ خطأ: {msg}",
        "en": "❌ Error: {msg}",
    },
    "not_active": {
        "ar": "⚠️ اشتراكك منتهٍ أو غير نشط.\nاستخدم /menu للتجديد.",
        "en": "⚠️ Your subscription is expired or inactive.\nUse /menu to renew.",
    },
    "daily_limit_reached": {
        "ar": "⚠️ وصلت للحد اليومي ({limit}). سيتم التجديد غداً.",
        "en": "⚠️ Daily limit reached ({limit}). Will reset tomorrow.",
    },
    "menu": {
        "ar": "⚙️ القائمة الرئيسية\nالحالة: {plan} | {remaining}/{limit} اليوم",
        "en": "⚙️ Main Menu\nStatus: {plan} | {remaining}/{limit} today",
    },
    "schedule_settings": {
        "ar": "⏱ إعدادات الجدولة\nالسرعة: {speed}x\nالتقطيع: {split} دقيقة\nالفاصل: {schedule} دقيقة",
        "en": "⏱ Schedule Settings\nSpeed: {speed}x\nSplit: {split} min\nInterval: {schedule} min",
    },
    "not_admin": {
        "ar": "⚠️ هذا الأمر خاص بالمشرف فقط.",
        "en": "⚠️ This command is for admins only.",
    },
    "admin_panel": {
        "ar": "🛠 لوحة التحكم\nالمستخدمين: {total}\nالنشطين: {active}",
        "en": "🛠 Admin Panel\nUsers: {total}\nActive: {active}",
    },
    "processing": {
        "ar": "🔄 جاري معالجة فيديو آخر... انتظر من فضلك.",
        "en": "🔄 Another video is being processed... Please wait.",
    },
    "no_active_plan": {
        "ar": "⚠️ ليس لديك خطة نشطة.\nتواصل مع المشرف: @admen_factory_bot",
        "en": "⚠️ No active plan.\nContact admin: @admen_factory_bot",
    },
    "user_details": {
        "ar": "👤 المستخدم: {id}\nالخطة: {plan}\nينتهي: {expires}\nالحالة: {status}\nاللغة: {lang}",
        "en": "👤 User: {id}\nPlan: {plan}\nExpires: {expires}\nStatus: {status}\nLanguage: {lang}",
    },
    "broadcast_prompt": {
        "ar": "📢 أرسل الرسالة التي تريد بثها لجميع المستخدمين:",
        "en": "📢 Send the message to broadcast to all users:",
    },
    "broadcast_done": {
        "ar": "✅ تم البث لـ {count} مستخدم.",
        "en": "✅ Broadcast sent to {count} users.",
    },
    "add_user_ask_id": {
        "ar": "أرسل user_id للمستخدم الجديد:",
        "en": "Send the user_id for the new user:",
    },
    "add_user_ask_api": {
        "ar": "أرسل WoopSocial API Key:",
        "en": "Send the WoopSocial API Key:",
    },
    "add_user_ask_project": {
        "ar": "أرسل Project ID:",
        "en": "Send the Project ID:",
    },
    "add_user_ask_account": {
        "ar": "أرسل Social Account ID:",
        "en": "Send the Social Account ID:",
    },
    "add_user_ask_plan": {
        "ar": "اختر الخطة:",
        "en": "Choose a plan:",
    },
    "add_user_done": {
        "ar": "✅ تم إضافة المستخدم {id}\nالخطة: {plan}",
        "en": "✅ User {id} added successfully\nPlan: {plan}",
    },
    "extend_days_prompt": {
        "ar": "أرسل user_id متبوعاً بعدد الأيام:\nمثال: 123456 30",
        "en": "Send user_id followed by days:\nExample: 123456 30",
    },
    "extend_done": {
        "ar": "✅ تم تمديد اشتراك المستخدم {id} بـ {days} يوم.",
        "en": "✅ User {id} subscription extended by {days} days.",
    },
    "user_not_found": {
        "ar": "❌ المستخدم غير موجود.",
        "en": "❌ User not found.",
    },
    "search_prompt": {
        "ar": "أرسل user_id للبحث:",
        "en": "Send user_id to search:",
    },
    "choose_plan": {
        "ar": "اختر الخطة المناسبة:",
        "en": "Choose your plan:",
    },
    "plan_selected": {
        "ar": "✅ اخترت خطة {plan}\nتواصل مع المشرف للتفعيل: @admen_factory_bot",
        "en": "✅ You selected {plan} plan\nContact admin to activate: @admen_factory_bot",
    },
    "expired": {
        "ar": "🚫 اشتراكك انتهى في {date}",
        "en": "🚫 Your subscription expired on {date}",
    },
    "cancel_confirm": {
        "ar": "هل تريد إلغاء جميع المهام؟",
        "en": "Do you want to cancel all tasks?",
    },
    "cancel_no_tasks": {
        "ar": "لا توجد مهام نشطة للإلغاء.",
        "en": "No active tasks to cancel.",
    },
    "invalid_link": {
        "ar": "❌ رابط غير صالح. أرسل رابط يوتيوب صحيح.",
        "en": "❌ Invalid link. Send a valid YouTube URL.",
    },
    "plan_selector": {
        "ar": "🗂 خططي المتاحة",
        "en": "🗂 Available Plans",
    },
}


def t(key, lang="ar", **kwargs):
    text = TEXTS.get(key, {}).get(lang, key)
    return text.format(**kwargs) if kwargs else text
