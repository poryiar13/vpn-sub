#!/usr/bin/env python3
"""
Telegram VPN Config Subscription Updater (simple version, no testing)
------------------------------------------------------------------------
Walks backward through the channel's message history (paging with
Telegram's public ?before= parameter) until it has collected
TARGET_CONFIGS unique vless/vmess/trojan links - no connectivity
testing (GitHub Actions' IP range gets blocked by many of these
servers, so a "positive" test from there isn't meaningful anyway).

Output:
  subscription.txt  -> base64-encoded subscription (v2ray/clash format)
"""

import re
import time
import base64
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

CHANNEL = "Gp_config"
TARGET_CONFIGS = 30
MAX_PAGES = 25          # safety cap on how far back in history to look

# Only these three protocols - v2ray/most clients recognize them everywhere
CONFIG_RE = re.compile(r'(?:vless|vmess|trojan)://[^\s<>"\']+')

# Matches a real country flag (two regional-indicator symbols), but NOT
# generic single-glyph symbols (checkered flag, etc.)
FLAG_RE = re.compile(r'[\U0001F1E6-\U0001F1FF]{2}')


def build_display_tag(message_text: str) -> str:
    match = FLAG_RE.search(message_text)
    if match:
        return f"Config {match.group(0)}"
    return "Config"


def fetch_page(channel: str, before):
    url = f"https://t.me/s/{channel}"
    if before:
        url += f"?before={before}"
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def iter_pages(channel: str, max_pages: int = MAX_PAGES):
    """Yield a list of message texts per page, walking backward through history."""
    before = None
    seen_ids = set()
    for _ in range(max_pages):
        soup = fetch_page(channel, before)
        wrappers = soup.find_all("div", class_="tgme_widget_message", attrs={"data-post": True})
        if not wrappers:
            return

        page_texts = []
        page_ids = []
        for w in wrappers:
            post = w.get("data-post", "")
            try:
                mid = int(post.split("/")[-1])
            except Exception:
                continue
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            page_ids.append(mid)
            text_div = w.find("div", class_="tgme_widget_message_text")
            page_texts.append(text_div.get_text("\n") if text_div else "")

        if not page_ids:
            return
        yield page_texts
        before = min(page_ids)
        time.sleep(0.3)


def gather_configs(channel: str, target: int) -> list:
    seen_base = set()
    unique = []
    for page_texts in iter_pages(channel):
        for text in page_texts:
            for raw_link in CONFIG_RE.findall(text):
                base = raw_link.split("#", 1)[0]
                if base in seen_base:
                    continue
                seen_base.add(base)
                tag = build_display_tag(text)
                unique.append(f"{base}#{quote(tag, safe='')}")
                if len(unique) >= target:
                    return unique
    return unique  # ran out of history before reaching target


def write_outputs(configs: list):
    sub_content = base64.b64encode("\n".join(configs).encode("utf-8")).decode("utf-8")
    with open("subscription.txt", "w", encoding="utf-8") as f:
        f.write(sub_content)


def main():
    print(f"[1/2] Collecting {TARGET_CONFIGS} vless/vmess/trojan configs from t.me/s/{CHANNEL} ...")
    configs = gather_configs(CHANNEL, TARGET_CONFIGS)
    print(f"      -> collected {len(configs)}/{TARGET_CONFIGS}")
    if len(configs) < TARGET_CONFIGS:
        print(f"      NOTE: hit MAX_PAGES={MAX_PAGES} before reaching the target - "
              f"increase MAX_PAGES if this keeps happening.")

    print("[2/2] Writing subscription.txt ...")
    write_outputs(configs)
    print("      -> subscription.txt")


if __name__ == "__main__":
    main()
