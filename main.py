#!/usr/bin/env python3
"""
Telegram Config Subscription Builder
-------------------------------------
این اسکریپت ۲۰ پیام آخر یک کانال عمومی تلگرام رو (بدون نیاز به لاگین یا API key،
با استفاده از پیش‌نمایش وب t.me/s/<channel>) می‌خونه، لینک‌های کانفیگ
(vmess / vless / trojan / ss / hysteria2 / tuic) رو استخراج می‌کنه و
یک فایل ساب‌اسکریپشن استاندارد (base64) برای V2rayNG / NekoBox / Hiddify و ... می‌سازه.
"""

import base64
import os
import re
import sys
from html import unescape

import requests

# -------------------- تنظیمات --------------------
# آیدی کانال بدون @ (مثلا برای https://t.me/Gp_config مقدار "SOSkeyNET")
CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "Gp_config")

# چند تا کانفیگ آخر می‌خوایم
MAX_CONFIGS = int(os.environ.get("MAX_CONFIGS", "30)

# مسیر خروجی‌ها
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "sub")
RAW_FILE = os.path.join(OUTPUT_DIR, "configs_raw.txt")
SUB_FILE = os.path.join(OUTPUT_DIR, "sub_base64.txt")

# پروتکل‌هایی که استخراج میشن
CONFIG_PATTERN = re.compile(
    r"(vmess|vless|trojan|ss|hysteria2?|hy2|tuic)://[^\s<>\"'`]+",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def fetch_channel_html(channel: str) -> str:
    """صفحه‌ی پیش‌نمایش عمومی کانال تلگرام رو می‌گیره (بدون نیاز به لاگین)."""
    url = f"https://t.me/s/{channel}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def extract_configs(html: str) -> list[str]:
    """لینک‌های کانفیگ رو از HTML صفحه استخراج می‌کنه، به ترتیب ظهور (قدیم -> جدید)."""
    text = unescape(html)
    matches = CONFIG_PATTERN.findall(text)
    # findall با گروه، فقط پروتکل رو برمی‌گردونه؛ دوباره با finditer کل لینک رو می‌گیریم
    full_matches = [m.group(0) for m in CONFIG_PATTERN.finditer(text)]
    # حذف تکراری‌ها با حفظ ترتیب
    seen = set()
    unique = []
    for cfg in full_matches:
        cfg = cfg.rstrip(".,")  # حذف نقطه/کاما اضافه در انتهای لینک
        if cfg not in seen:
            seen.add(cfg)
            unique.append(cfg)
    return unique


def build_subscription(configs: list[str]) -> str:
    """محتوای کانفیگ‌ها رو به فرمت استاندارد ساب (base64 خط به خط) تبدیل می‌کنه."""
    joined = "\n".join(configs)
    return base64.b64encode(joined.encode("utf-8")).decode("utf-8")


def main() -> None:
    print(f"[*] در حال گرفتن پیام‌های کانال @{CHANNEL} ...")
    try:
        html = fetch_channel_html(CHANNEL)
    except requests.RequestException as e:
        print(f"[!] خطا در گرفتن صفحه تلگرام: {e}", file=sys.stderr)
        sys.exit(1)

    configs = extract_configs(html)
    if not configs:
        print("[!] هیچ کانفیگی در صفحه پیدا نشد.", file=sys.stderr)
        sys.exit(1)

    # آخرین N تا کانفیگ (جدیدترین‌ها آخر صفحه هستن)
    last_configs = configs[-MAX_CONFIGS:]
    print(f"[*] {len(configs)} کانفیگ پیدا شد، {len(last_configs)} تای آخر انتخاب شد.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(RAW_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(last_configs) + "\n")

    sub_content = build_subscription(last_configs)
    with open(SUB_FILE, "w", encoding="utf-8") as f:
        f.write(sub_content)

    print(f"[+] فایل خام: {RAW_FILE}")
    print(f"[+] فایل ساب (base64): {SUB_FILE}")


if __name__ == "__main__":
    main()
