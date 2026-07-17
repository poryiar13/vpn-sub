#!/usr/bin/env python3
"""
Telegram VPN Config Subscription Updater (targets an exact config COUNT)
---------------------------------------------------------------------------
Instead of reading a fixed number of messages, this walks backward through
the channel's message history (paging with Telegram's public ?before=
parameter) until it has collected TARGET_CONFIGS unique vless/vmess/trojan
links, skipping any other post content (ss:// links, plain text, etc.).

Output:
  subscription.txt  -> base64-encoded subscription (v2ray/clash format)
"""

import re
import time
import base64
import requests
from bs4 import BeautifulSoup

CHANNEL = "ConfigsHUB"
TARGET_CONFIGS = 25
MAX_PAGES = 15          # safety cap on how far back in history to look

# Only these three protocols - skipping ss:// on purpose (per project scope)
CONFIG_RE = re.compile(r'(?:vless|vmess|trojan)://[^\s<>"\']+')


def fetch_page(channel: str, before: int | None):
    url = f"https://t.me/s/{channel}"
    if before:
        url += f"?before={before}"
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def iter_message_texts(channel: str, max_pages: int = MAX_PAGES):
    """Yield message texts, walking backward through channel history."""
    before = None
    seen_ids = set()
    for _ in range(max_pages):
        soup = fetch_page(channel, before)
        wrappers = soup.find_all("div", class_="tgme_widget_message", attrs={"data-post": True})
        if not wrappers:
            break

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
            yield text_div.get_text("\n") if text_div else ""

        if not page_ids:
            break
        before = min(page_ids)  # move to the next (older) page
        time.sleep(0.3)


def gather_configs(channel: str, target: int) -> list:
    seen = set()
    unique = []
    for text in iter_message_texts(channel):
        for link in CONFIG_RE.findall(text):
            if link not in seen:
                seen.add(link)
                unique.append(link)
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
