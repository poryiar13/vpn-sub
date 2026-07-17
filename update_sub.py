#!/usr/bin/env python3
"""
Telegram VPN Config Subscription Updater (simple version, no testing)
------------------------------------------------------------------------
Fetches the last N posts from a public Telegram channel, extracts VPN
configs (vless / vmess / trojan / ss links), and writes them straight
into a subscription file - no ping/connectivity testing at all.

Outputs:
  subscription.txt  -> base64-encoded subscription (v2ray/clash format)
"""

import re
import base64
import requests
from bs4 import BeautifulSoup

CHANNEL = "SOSkeyNET"
MESSAGE_COUNT = 10

CONFIG_RE = re.compile(r'(?:vless|vmess|trojan|ss)://[^\s<>"\']+')


def fetch_last_messages(channel: str, count: int) -> list:
    url = f"https://t.me/s/{channel}"
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    message_divs = soup.find_all("div", class_="tgme_widget_message_text")
    texts = [m.get_text("\n") for m in message_divs]
    return texts[-count:] if len(texts) > count else texts


def extract_configs(texts: list) -> list:
    configs = []
    for t in texts:
        configs.extend(CONFIG_RE.findall(t))
    seen = set()
    unique = []
    for c in configs:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def write_outputs(configs):
    sub_content = base64.b64encode("\n".join(configs).encode("utf-8")).decode("utf-8")
    with open("subscription.txt", "w", encoding="utf-8") as f:
        f.write(sub_content)


def main():
    print(f"[1/3] Fetching last {MESSAGE_COUNT} messages from t.me/s/{CHANNEL} ...")
    texts = fetch_last_messages(CHANNEL, MESSAGE_COUNT)
    print(f"      -> got {len(texts)} messages")

    print("[2/3] Extracting config links ...")
    configs = extract_configs(texts)
    print(f"      -> found {len(configs)} unique configs")

    print("[3/3] Writing subscription.txt ...")
    write_outputs(configs)
    print("      -> subscription.txt")


if __name__ == "__main__":
    main()
