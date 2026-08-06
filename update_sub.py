#!/usr/bin/env python3
"""
Telegram VPN Config Subscription Updater (targets an exact PASSING count)
----------------------------------------------------------------------------
Walks backward through the channel's message history (paging with
Telegram's public ?before= parameter), extracting vless/vmess/trojan
links only (ss:// and hysteria2:// and raw tg://proxy links are skipped
on purpose - keeps things to widely-supported client protocols).

Each candidate gets a quick TCP connect test (host:port) - only ones
that actually respond are kept, until TARGET_CONFIGS have been collected.

Output:
  subscription.txt  -> base64-encoded subscription (v2ray/clash format)
"""

import re
import time
import json
import socket
import base64
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed

CHANNEL = "Gp_config"
TARGET_CONFIGS = 30
MAX_PAGES = 25          # safety cap on how far back in history to look
TCP_TIMEOUT = 3.0
TEST_WORKERS = 20

# Only these three protocols - v2ray/most clients recognize them everywhere
CONFIG_RE = re.compile(r'(?:vless|vmess|trojan)://[^\s<>"\']+')

# Matches a real country flag (two regional-indicator symbols), but NOT
# generic single-glyph symbols (checkered flag, etc.)
FLAG_RE = re.compile(r'[\U0001F1E6-\U0001F1FF]{2}')


# ------------------------------------------------------------- fetching

def fetch_page(channel: str, before):
    url = f"https://t.me/s/{channel}"
    if before:
        url += f"?before={before}"
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def iter_pages(channel: str, max_pages: int = MAX_PAGES):
    """Yield (message_text) list per page, walking backward through history."""
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


# --------------------------------------------------------------- tagging

def flag_to_country_code(flag: str) -> str:
    return "".join(chr(ord(ch) - 0x1F1E6 + ord("A")) for ch in flag)


def build_display_tag(message_text: str) -> str:
    match = FLAG_RE.search(message_text)
    if match:
        return f"Config {match.group(0)}"
    return "Config"


# --------------------------------------------------------- quick TCP test

def quick_host_port(link: str):
    try:
        if link.startswith("vmess://"):
            payload = link[len("vmess://"):]
            payload += "=" * (-len(payload) % 4)
            data = json.loads(base64.b64decode(payload).decode("utf-8", errors="ignore"))
            return data.get("add"), int(data.get("port"))
        parsed = urlparse(link)
        if parsed.hostname and parsed.port:
            return parsed.hostname, parsed.port
    except Exception:
        pass
    return None, None


def tcp_alive(host, port, timeout=TCP_TIMEOUT):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def test_batch(raw_links, workers=TEST_WORKERS):
    def check(link):
        host, port = quick_host_port(link)
        if not host or not port:
            return link, False
        return link, tcp_alive(host, port)

    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(check, link) for link in raw_links]
        for fut in as_completed(futures):
            link, ok = fut.result()
            results[link] = ok
    return results


# ------------------------------------------------------------- gathering

def gather_configs(channel: str, target: int) -> list:
    seen_base = set()
    passed = []

    for page_texts in iter_pages(channel):
        candidates = []  # (raw_link, message_text)
        for text in page_texts:
            for raw_link in CONFIG_RE.findall(text):
                base = raw_link.split("#", 1)[0]
                if base in seen_base:
                    continue
                seen_base.add(base)
                candidates.append((raw_link, text))

        if not candidates:
            continue

        alive_map = test_batch([c[0] for c in candidates])

        for raw_link, text in candidates:
            if not alive_map.get(raw_link):
                continue
            base = raw_link.split("#", 1)[0]
            tag = build_display_tag(text)
            passed.append(f"{base}#{quote(tag, safe='')}")
            if len(passed) >= target:
                return passed

    return passed  # ran out of history before reaching target


def write_outputs(configs: list):
    sub_content = base64.b64encode("\n".join(configs).encode("utf-8")).decode("utf-8")
    with open("subscription.txt", "w", encoding="utf-8") as f:
        f.write(sub_content)


def main():
    print(f"[1/2] Collecting {TARGET_CONFIGS} live vless/vmess/trojan configs from t.me/s/{CHANNEL} ...")
    configs = gather_configs(CHANNEL, TARGET_CONFIGS)
    print(f"      -> collected {len(configs)}/{TARGET_CONFIGS} that passed the TCP test")
    if len(configs) < TARGET_CONFIGS:
        print(f"      NOTE: hit MAX_PAGES={MAX_PAGES} before reaching the target - "
              f"increase MAX_PAGES if this keeps happening.")

    print("[2/2] Writing subscription.txt ...")
    write_outputs(configs)
    print("      -> subscription.txt")


if __name__ == "__main__":
    main()
