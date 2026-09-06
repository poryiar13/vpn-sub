# Telegram Config Subscription Builder

این پروژه ۲۰ کانفیگ آخر ارسال‌شده در کانال تلگرام [@Gp_config](https://t.me/Gp_config) رو
خودکار جمع‌آوری کرده و به فرمت ساب‌اسکریپشن استاندارد (base64) تبدیل می‌کنه —
قابل استفاده در V2rayNG، NekoBox، Hiddify، v2rayN و مشابه.

## چطور کار می‌کنه؟

1. `main.py` صفحه‌ی پیش‌نمایش عمومی کانال (`https://t.me/s/Gp_config`) رو می‌خونه —
   این صفحه بدون نیاز به لاگین یا API key در دسترسه.
2. لینک‌های کانفیگ (`vmess://`, `vless://`, `trojan://`, `ss://`, `hysteria2://`, `tuic://`)
   رو با regex استخراج می‌کنه.
3. آخرین ۲۰ کانفیگ رو نگه می‌داره و در دو فایل ذخیره می‌کنه:
   - `sub/configs_raw.txt` — لینک‌های خام، هر خط یک کانفیگ
   - `sub/sub_base64.txt` — همون لینک‌ها ولی base64-شده (فرمت ساب استاندارد)
4. یک GitHub Action (`.github/workflows/update-sub.yml`) هر ۳۰ دقیقه این اسکریپت رو
   اجرا کرده و در صورت تغییر، فایل‌ها رو خودکار کامیت و پوش می‌کنه.

## راه‌اندازی روی گیت‌هاب

1. یک ریپوی جدید بساز و این فایل‌ها رو داخلش آپلود/پوش کن.
2. مطمئن شو در تنظیمات ریپو (Settings → Actions → General → Workflow permissions)
   گزینه‌ی **Read and write permissions** فعال باشه، وگرنه Action نمی‌تونه کامیت کنه.
3. برو به تب **Actions** و روی وورک‌فلو `Update Telegram Config Subscription`
   کلیک کن و دستی هم یک بار Run کن (`Run workflow`) تا اولین بار فایل‌ها ساخته بشن.
4. بعد از اولین اجرا، لینک ساب‌اسکریپشن شما این آدرس خواهد بود
   (به جای `USERNAME` و `REPO` نام کاربری و نام ریپوی خودت رو بذار):

```
https://raw.githubusercontent.com/USERNAME/REPO/main/sub/sub_base64.txt
```

این لینک رو داخل اپ V2ray خودت (مثلا V2rayNG → Import config from URL) وارد کن.

## اجرای محلی (تست)

```bash
pip install -r requirements.txt
python main.py
```

## تنظیمات قابل تغییر

با متغیرهای محیطی زیر می‌تونی رفتار اسکریپت رو عوض کنی:

| متغیر | پیش‌فرض | توضیح |
|---|---|---|
| `TELEGRAM_CHANNEL` | `Gp_config` | نام کانال (بدون @) |
| `MAX_CONFIGS` | `20` | تعداد آخرین کانفیگ‌هایی که برداشته میشه |

## نکات مهم

- این روش فقط برای کانال‌های **عمومی** تلگرام کار می‌کنه (کانال‌هایی که پیش‌نمایش وب دارن).
- اگه کانال private باشه یا محدودیت نرخ (rate limit) بخوره، باید از Telegram Bot API
  یا کتابخونه‌ی Telethon/Pyrogram با api_id/api_hash واقعی استفاده کنی — که نیاز به
  ثبت اپلیکیشن در my.telegram.org داره.
- هیچ داده‌ی شخصی یا اکانتی در این پروژه ذخیره نمیشه؛ فقط محتوای عمومیِ کانال خونده میشه.
