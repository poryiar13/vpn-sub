#!/usr/bin/env python3
"""
Telegram Config Subscription Builder
-------------------------------------
این اسکریپت پیام‌های یک کانال عمومی تلگرام رو (بدون نیاز به لاگین یا API key،
با استفاده از پیش‌نمایش وب t.me/s/<channel> و صفحه‌بندی به عقب) می‌خونه،
کانفیگ‌ها (vmess/vless/trojan/ss/hysteria2/tuic) رو استخراج می‌کنه، کشور سرور
هر کدوم رو با GeoIP تشخیص می‌ده و فقط کانفیگ‌های کشورهای مجاز رو نگه می‌داره:
    - تعداد مشخصی با آدرس دامنه‌ای/حروفی (DOMAIN_QUOTA)
    - تعداد مشخصی با آدرس IP عددی (IP_QUOTA)
اسم (remark) هر کانفیگ رو به پرچم + اسم کشور تغییر می‌ده و یک فایل ساب‌اسکریپشن
استاندارد (base64) می‌سازه.
"""

import base64
import ipaddress
import json
import os
import re
import socket
import sys
import time
from urllib.parse import urlsplit, quote

import requests
from bs4 import BeautifulSoup

# -------------------- تنظیمات --------------------
CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "SOSkeyNET")

# فقط این کشورها نگه داشته میشن (کد دو حرفی ISO)
ALLOWED_COUNTRY_CODES = {
    c.strip().upper()
    for c in os.environ.get("ALLOWED_COUNTRIES", "FR,IT,RU,NL,FI,PL").split(",")
    if c.strip()
}

# سهمیه‌ها
DOMAIN_QUOTA = int(os.environ.get("DOMAIN_QUOTA", "20"))  # آدرس حروفی/دامنه‌ای
IP_QUOTA = int(os.environ.get("IP_QUOTA", "10"))          # آدرس IP عددی

# حداکثر تعداد صفحه‌ای که به عقب برمی‌گرده (برای جلوگیری از حلقه بی‌نهایت)
MAX_PAGES = int(os.environ.get("MAX_PAGES", "30"))

# نحوه نام‌گذاری: flag | name | flag_name
LABEL_STYLE = os.environ.get("LABEL_STYLE", "flag_name")

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "sub")
RAW_FILE = os.path.join(OUTPUT_DIR, "configs_raw.txt")
SUB_FILE = os.path.join(OUTPUT_DIR, "sub_base64.txt")
DEBUG_FILE = os.path.join(OUTPUT_DIR, "debug_last_run.txt")

CONFIG_PATTERN = re.compile(
    r"(?:vmess|vless|trojan|ss|hysteria2?|hy2|tuic)://\S+",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

_geo_cache: dict[str, dict] = {}


# -------------------- گرفتن و پارس صفحات تلگرام (با صفحه‌بندی) --------------------

def fetch_page(channel: str, before: int | None) -> str:
    url = f"https://t.me/s/{channel}"
    if before:
        url += f"?before={before}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_page(html: str) -> tuple[list[str], int | None]:
    """
    متن پیام‌های یک صفحه رو برمی‌گردونه (به ترتیب قدیم -> جدید، همونطور که
    تلگرام نمایش میده) به‌همراه کوچیک‌ترین شناسه‌ی پیام صفحه (برای صفحه‌بندی بعدی).
    """
    soup = BeautifulSoup(html, "html.parser")
    message_els = soup.select(".tgme_widget_message[data-post]")

    texts = []
    min_id = None
    for el in message_els:
        data_post = el.get("data-post", "")
        msg_id = None
        if "/" in data_post:
            try:
                msg_id = int(data_post.rsplit("/", 1)[-1])
            except ValueError:
                msg_id = None
        if msg_id is not None:
            min_id = msg_id if min_id is None else min(min_id, msg_id)

        text_block = el.select_one(".tgme_widget_message_text")
        if text_block:
            texts.append(text_block.get_text(separator="\n"))

    return texts, min_id


def collect_all_matching_configs() -> tuple[list[str], dict]:
    """
    از جدیدترین پیام‌ها شروع کرده و به عقب صفحه‌بندی می‌کنه تا سهمیه‌ی
    DOMAIN_QUOTA (آدرس حروفی) و IP_QUOTA (آدرس عددی) از کشورهای مجاز پر بشه.
    """
    domain_results: list[str] = []
    ip_results: list[str] = []

    before = None
    pages_fetched = 0
    messages_scanned = 0
    configs_scanned = 0
    country_hits: dict[str, int] = {}

    while pages_fetched < MAX_PAGES:
        pages_fetched += 1
        try:
            html = fetch_page(CHANNEL, before)
        except requests.RequestException as e:
            print(f"[!] خطا در گرفتن صفحه {pages_fetched}: {e}", file=sys.stderr)
            break

        message_texts, min_id = parse_page(html)
        if not message_texts:
            print(f"[*] صفحه {pages_fetched}: پیامی پیدا نشد، توقف صفحه‌بندی.")
            break

        messages_scanned += len(message_texts)

        # جدیدترین پیام‌های این صفحه اول پردازش بشن
        for text in reversed(message_texts):
            for m in CONFIG_PATTERN.finditer(text):
                cfg = m.group(0).rstrip(".,؛،")
                configs_scanned += 1

                address = extract_address(cfg)
                if not address:
                    continue
                ip = resolve_ip(address)
                if not ip:
                    continue
                geo = geolocate(ip)
                code = (geo.get("code") or "").upper()
                if code not in ALLOWED_COUNTRY_CODES:
                    continue

                country_hits[code] = country_hits.get(code, 0) + 1
                label = make_label(geo)

                if is_ip(address):
                    if len(ip_results) < IP_QUOTA:
                        ip_results.append((cfg, label))
                else:
                    if len(domain_results) < DOMAIN_QUOTA:
                        domain_results.append((cfg, label))

                if len(domain_results) >= DOMAIN_QUOTA and len(ip_results) >= IP_QUOTA:
                    break
            if len(domain_results) >= DOMAIN_QUOTA and len(ip_results) >= IP_QUOTA:
                break

        if len(domain_results) >= DOMAIN_QUOTA and len(ip_results) >= IP_QUOTA:
            break

        if min_id is None:
            print("[*] شناسه‌ی صفحه‌بندی پیدا نشد، توقف.")
            break
        before = min_id
        time.sleep(0.3)

    debug = {
        "pages_fetched": pages_fetched,
        "messages_scanned": messages_scanned,
        "configs_scanned": configs_scanned,
        "country_hits": country_hits,
        "domain_found": len(domain_results),
        "ip_found": len(ip_results),
    }

    # شماره‌گذاری برچسب‌های تکراری (مثلا دو تا کانفیگ فرانسه)
    label_counts: dict[str, int] = {}
    final = []
    for cfg, label in domain_results + ip_results:
        label_counts[label] = label_counts.get(label, 0) + 1
        final_label = label if label_counts[label] == 1 else f"{label} {label_counts[label]}"
        final.append(rename_config(cfg, final_label))

    return final, debug


# -------------------- استخراج آدرس سرور از هر پروتکل --------------------

def is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def extract_address(uri: str) -> str | None:
    """آدرس (IP یا دامنه) که کانفیگ واقعاً بهش وصل میشه رو برمی‌گردونه."""
    try:
        if uri.lower().startswith("vmess://"):
            b64 = uri[len("vmess://"):]
            b64 += "=" * (-len(b64) % 4)
            data = json.loads(base64.b64decode(b64).decode("utf-8", errors="ignore"))
            return data.get("add")

        parts = urlsplit(uri)
        host = parts.hostname
        if host:
            return host

        if uri.lower().startswith("ss://"):
            body = uri[len("ss://"):].split("#", 1)[0]
            body += "=" * (-len(body) % 4)
            decoded = base64.b64decode(body).decode("utf-8", errors="ignore")
            if "@" in decoded:
                return decoded.split("@", 1)[1].split(":", 1)[0]
    except Exception:
        return None
    return None


def resolve_ip(address: str) -> str | None:
    if is_ip(address):
        return address
    try:
        return socket.gethostbyname(address)
    except socket.gaierror:
        return None


def flag_emoji(country_code: str) -> str:
    country_code = country_code.upper()
    if len(country_code) != 2 or not country_code.isalpha():
        return "🏳️"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in country_code)


def geolocate(ip: str) -> dict:
    if ip in _geo_cache:
        return _geo_cache[ip]
    result = {"country": "Unknown", "code": None}
    try:
        resp = requests.get(f"https://ipwho.is/{ip}", timeout=8)
        data = resp.json()
        if data.get("success", True):
            result = {
                "country": data.get("country") or "Unknown",
                "code": data.get("country_code"),
            }
    except requests.RequestException:
        pass
    _geo_cache[ip] = result
    time.sleep(0.3)
    return result


def make_label(geo: dict) -> str:
    country = geo.get("country") or "Unknown"
    code = geo.get("code")
    flag = flag_emoji(code) if code else "🏳️"
    if LABEL_STYLE == "flag":
        return flag
    if LABEL_STYLE == "name":
        return country
    return f"{flag} {country}"


# -------------------- جایگزینی نام (remark) کانفیگ --------------------

def rename_config(uri: str, label: str) -> str:
    if uri.lower().startswith("vmess://"):
        try:
            b64 = uri[len("vmess://"):]
            b64 += "=" * (-len(b64) % 4)
            data = json.loads(base64.b64decode(b64).decode("utf-8", errors="ignore"))
            data["ps"] = label
            new_b64 = base64.b64encode(
                json.dumps(data, ensure_ascii=False).encode("utf-8")
            ).decode("utf-8")
            return f"vmess://{new_b64}"
        except Exception:
            return uri

    base = uri.split("#", 1)[0]
    return f"{base}#{quote(label)}"


# -------------------- ساخت خروجی --------------------

def build_subscription(configs: list[str]) -> str:
    joined = "\n".join(configs)
    return base64.b64encode(joined.encode("utf-8")).decode("utf-8")


def write_debug(debug: dict, extra_note: str = "") -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    lines = [f"{k}: {v}" for k, v in debug.items()]
    if extra_note:
        lines.append("")
        lines.append(extra_note)
    with open(DEBUG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    print(f"[*] در حال گرفتن و فیلتر کردن کانفیگ‌های کانال @{CHANNEL} ...")
    print(f"[*] کشورهای مجاز: {sorted(ALLOWED_COUNTRY_CODES)}")
    print(f"[*] سهمیه: {DOMAIN_QUOTA} دامنه‌ای + {IP_QUOTA} آی‌پی عددی")

    final_configs, debug = collect_all_matching_configs()
    print(f"[*] دیباگ: {debug}")

    if not final_configs:
        print("[!] هیچ کانفیگی مطابق فیلترها پیدا نشد.", file=sys.stderr)
        write_debug(debug, "هیچ کانفیگی مطابق کشورها/سهمیه‌های تعیین‌شده پیدا نشد.")
        sys.exit(1)

    if debug["domain_found"] < DOMAIN_QUOTA or debug["ip_found"] < IP_QUOTA:
        print(
            f"[!] هشدار: به سهمیه کامل نرسیدیم "
            f"(دامنه‌ای: {debug['domain_found']}/{DOMAIN_QUOTA}, "
            f"عددی: {debug['ip_found']}/{IP_QUOTA}). "
            f"شاید نیاز به افزایش MAX_PAGES باشه."
        )

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(RAW_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(final_configs) + "\n")

    sub_content = build_subscription(final_configs)
    with open(SUB_FILE, "w", encoding="utf-8") as f:
        f.write(sub_content)

    write_debug(debug, "اجرای موفق.")

    print(f"[+] {len(final_configs)} کانفیگ نهایی ذخیره شد.")
    print(f"[+] فایل خام: {RAW_FILE}")
    print(f"[+] فایل ساب (base64): {SUB_FILE}")


if __name__ == "__main__":
    main()
