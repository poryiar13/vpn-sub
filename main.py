#!/usr/bin/env python3
"""
Telegram Config Subscription Builder
-------------------------------------
این اسکریپت آخرین پیام‌های یک کانال عمومی تلگرام رو (بدون نیاز به لاگین یا API key،
با استفاده از پیش‌نمایش وب t.me/s/<channel>) می‌خونه، لینک‌های کانفیگ
(vmess / vless / trojan / ss / hysteria2 / tuic) رو استخراج می‌کنه، کشور سرور هر
کانفیگ رو با GeoIP تشخیص می‌ده، اسم (remark) کانفیگ رو به پرچم/اسم‌کشور تغییر می‌ده
و یک فایل ساب‌اسکریپشن استاندارد (base64) برای V2rayNG / NekoBox / Hiddify و ... می‌سازه.
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
MAX_CONFIGS = int(os.environ.get("MAX_CONFIGS", "30"))

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


# -------------------- گرفتن و پارس صفحه تلگرام --------------------

def fetch_channel_html(channel: str) -> str:
    """صفحه‌ی پیش‌نمایش عمومی کانال تلگرام رو می‌گیره (بدون نیاز به لاگین)."""
    url = f"https://t.me/s/{channel}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def extract_configs(html: str) -> tuple[list[str], dict]:
    """
    لینک‌های کانفیگ رو استخراج می‌کنه. به‌جای regex روی کل HTML خام (که با
    تگ‌های تودرتوی تلگرام مثل <code>/<tg-spoiler>/<a> ممکنه لینک‌ها رو بشکنه)،
    اول با BeautifulSoup متن خالص هر پیام رو درمیاریم.
    """
    soup = BeautifulSoup(html, "html.parser")
    message_blocks = soup.select(".tgme_widget_message_text")

    debug = {
        "html_length": len(html),
        "message_blocks_found": len(message_blocks),
        "title": soup.title.get_text(strip=True) if soup.title else None,
    }

    full_matches: list[str] = []
    if message_blocks:
        for block in message_blocks:
            text = block.get_text(separator="\n")
            full_matches.extend(m.group(0) for m in CONFIG_PATTERN.finditer(text))
    else:
        full_text = soup.get_text(separator="\n")
        full_matches = [m.group(0) for m in CONFIG_PATTERN.finditer(full_text)]

    seen = set()
    unique = []
    for cfg in full_matches:
        cfg = cfg.rstrip(".,؛،")
        if cfg not in seen:
            seen.add(cfg)
            unique.append(cfg)

    debug["raw_matches"] = len(full_matches)
    debug["unique_matches"] = len(unique)
    return unique, debug


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
            b64 += "=" * (-len(b64) % 4)  # تصحیح padding
            data = json.loads(base64.b64decode(b64).decode("utf-8", errors="ignore"))
            return data.get("add")

        # سایر پروتکل‌ها: vless / trojan / ss / hysteria2 / hy2 / tuic
        parts = urlsplit(uri)
        host = parts.hostname
        if host:
            return host

        # فرمت قدیمی ss:// که کل userinfo@host:port به‌صورت base64 هست
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
    """کشور یک IP رو با یک سرویس رایگان GeoIP تشخیص میده (با کش)."""
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
    time.sleep(0.4)  # رعایت نرخ درخواست سرویس رایگان
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

    # سایر پروتکل‌ها: قسمت #remark در انتهای لینک
    base = uri.split("#", 1)[0]
    return f"{base}#{quote(label)}"


def rename_all(configs: list[str]) -> list[str]:
    renamed = []
    country_counts: dict[str, int] = {}
    for cfg in configs:
        address = extract_address(cfg)
        geo = {"country": "Unknown", "code": None}
        if address:
            ip = resolve_ip(address)
            if ip:
                geo = geolocate(ip)

        label = make_label(geo)
        country_counts[label] = country_counts.get(label, 0) + 1
        if country_counts[label] > 1:
            label = f"{label} {country_counts[label]}"

        renamed.append(rename_config(cfg, label))
    return renamed


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
    print(f"[*] در حال گرفتن پیام‌های کانال @{CHANNEL} ...")
    try:
        html = fetch_channel_html(CHANNEL)
    except requests.RequestException as e:
        print(f"[!] خطا در گرفتن صفحه تلگرام: {e}", file=sys.stderr)
        write_debug({"error": str(e)})
        sys.exit(1)

    configs, debug = extract_configs(html)
    print(f"[*] دیباگ: {debug}")

    if not configs:
        print("[!] هیچ کانفیگی در صفحه پیدا نشد.", file=sys.stderr)
        note = (
            "هیچ لینک کانفیگی پیدا نشد. اگه message_blocks_found برابر صفر بود یعنی "
            "ساختار صفحه فرق داره یا تلگرام صفحه‌ی دیگه‌ای برگردونده. اگه "
            "message_blocks_found > 0 ولی raw_matches صفر بود، یعنی پیام‌های اخیر "
            "این کانال لینک متنی کانفیگ ندارن."
        )
        write_debug(debug, note)
        sys.exit(1)

    last_configs = configs[-MAX_CONFIGS:]
    print(f"[*] {len(configs)} کانفیگ پیدا شد، {len(last_configs)} تای آخر انتخاب شد.")

    print("[*] در حال تشخیص کشور سرورها (GeoIP) ...")
    renamed_configs = rename_all(last_configs)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(RAW_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(renamed_configs) + "\n")

    sub_content = build_subscription(renamed_configs)
    with open(SUB_FILE, "w", encoding="utf-8") as f:
        f.write(sub_content)

    write_debug(debug, "اجرای موفق.")

    print(f"[+] فایل خام: {RAW_FILE}")
    print(f"[+] فایل ساب (base64): {SUB_FILE}")


if __name__ == "__main__":
    main()
