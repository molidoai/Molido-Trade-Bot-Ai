# کارهای باقی‌مانده برای شما (User Action Items)

کد فازهای اصلی در مخزن آماده است. موارد زیر **فقط توسط شما** قابل انجام است:

## ۱. زیر (ضروری برای اجرا)

1. **خرید VPS** (ترجیحاً مطابق پرامپت: اوبونتو، منابع کافی؛ فرانسه اختیاری)
2. **دامنه** (گفتید دارید) → DNS به IP سرور + SSL (Certbot)
3. کلون مخزن:
   ```bash
   git clone https://github.com/molidoai/Molido-Trade-Bot-Ai.git
   cd Molido-Trade-Bot-Ai
   cp .env.example .env
   # SECRET_KEY و POSTGRES_PASSWORD را قوی بگذارید
   ```
4. نصب Docker + Docker Compose روی سرور
5. `docker compose up -d postgres redis`
6. Migration و اجرای API / Paper

## ۲. بروکر و MT5

7. **حساب Demo** نزد بروکر MT5 (Login, Password, Server)
8. ترمینال MT5 روی سرور (Wine) یا ویندوز جدا + مسیر `terminal64.exe`
9. پر کردن `MT5_DEMO_*` در `.env`
10. فقط بعد از تست Demo: در صورت نیاز `MT5_PROP_*` برای پراپ

## ۳. تلگرام

11. ساخت ربات در @BotFather → `TELEGRAM_BOT_TOKEN`
12. `TELEGRAM_ADMIN_CHAT_ID` (و در صورت نیاز لیست مجاز)

## ۴. تقویم اقتصادی (اختیاری ولی توصیه‌شده)

13. کلید API منبع تقویم برای News Blackout واقعی  
    (بدون آن حالت غیرسخت‌گیرانه فعال است)

## ۵. تصمیم‌های انسانی (اجباری طبق پرامپت)

14. **هیچ‌گاه** REAL یا Master را پیش‌فرض روشن نکنید
15. قبل از Micro-Live: مبلغ سرمایه، سقف ریسک، و تأیید کتبی خودتان
16. یک‌بار تمرین Backup/Restore دیتابیس
17. توکن GitHub که در چت بود را **Revoke** کنید و توکن جدید بسازید

## ۶. آنچه عمداً خودکار نشده

- فعال‌سازی Live / Micro-Live
- دور زدن Risk Engine
- تضمین سود (وجود ندارد و اضافه نخواهد شد)

پس از آماده‌شدن سرور، بگویید تا راهنمای deploy دقیق همان VPS را مرحله‌به‌مرحله بنویسیم.
