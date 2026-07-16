# tg2tiktok

Telegram → TikTok bot. Download YouTube videos, split, speed up, and publish to TikTok/Instagram automatically.

## تشغيل مجاني بالكامل (Render Free + Supabase Free)

### 1. إنشاء مشروع Supabase مجاني
1. افتح [supabase.com](https://supabase.com) وأنشئ حساب مجاني.
2. أنشئ مشروع جديد وانتظر حتى يكتمل.
3. افتح **SQL Editor** ونفّذ الأوامر التالية بالترتيب:

**الجدول الأول — users (موجود مسبقاً، فقط تأكد من إنشائه):**
```sql
create table if not exists users (
    telegram_id bigint primary key,
    data jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
```

**الجدول الثاني — app_kv (تخزين key-value عام):
```sql
create table if not exists app_kv (
    key text primary key,
    value jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);
```

4. اذهب إلى **Project Settings → API** وانسخ:
   - `Project URL` → هذا هو `SUPABASE_URL`
   - `service_role key` → هذا هو `SUPABASE_SERVICE_KEY`

### 2. ضبط متغيرات البيئة في Render
أضف هذين المتغيرين في Render Dashboard (أو عبر `render.yaml`):
- `SUPABASE_URL` — رابط مشروع Supabase
- `SUPABASE_SERVICE_KEY` — مفتاح service_role

### 3. إعداد UptimeRobot (أو cron-job.org) مجاناً
لأن خطة Render المجانية تطفئ الخدمة بعد 15 دقيقة بدون استخدام:
1. افتح [uptimerobot.com](https://uptimerobot.com) وسجل مجاناً.
2. أضف **Monitor** جديد من النوع **HTTP(s)**.
3. ضع الرابط: `https://tg2tiktok.onrender.com/`
4. اختر **Interval = 10 minutes**.
5. احفظ — الـ pinger سيحافظ على الخدمة شغالة.

### 4. تحذيرات مهمة
- **هذا الإعداد يعتمد على نشاط UptimeRobot باستمرار** — إذا توقف الـ pinger لأي سبب، البوت سيتوقف عن الاستجابة الفورية (يحتاج طلب واحد "يوقظه" خلال دقيقة تقريباً).
- **لا يوجد نسخ احتياطي تلقائي لقاعدة Supabase على الخطة المجانية** — يُنصح بتصدير جداول `users` و `app_kv` يدوياً بشكل دوري (مثلاً أسبوعياً) عبر Supabase dashboard.
- **عند إعادة نشر (redeploy) الخدمة** — أي بيانات مؤقتة قيد المعالجة (فيديو نصف محمّل، جزء نصف مقسّم) تُفقد. هذا مقبول لأن كل البيانات الدائمة محفوظة في Supabase والملفات المؤقتة بطبيعتها ستعاد معالجتها من الطابور عند التشغيل التالي.
