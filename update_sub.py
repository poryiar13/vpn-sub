#!/usr/bin/env python3
"""
Telegram VPN Config Subscription Updater (GitHub Actions version)
--------------------------------------------------------------------
Fetches the last N posts from a public Telegram channel (via the public
t.me/s/<channel> web preview), extracts VPN configs (vless / vmess /
trojan / ss links), TCP-tests each server, keeps only the ones that
respond, and writes:

  1. working_configs.txt   -> plain list with latency comments
  2. subscription.txt      -> base64-encoded subscription (v2ray/clash format)

Meant to be run on a schedule by .github/workflows/update.yml
"""

import re
import socket
import time
import base64
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

CHANNEL = "SOSkeyNET"
MESSAGE_COUNT = 10
TIMEOUT = 3.0
WORKERS = 40

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


def get_host_port(link: str):
    try:
        if link.startswith("vmess://"):
            payload = link[len("vmess://"):]
            payload += "=" * (-len(payload) % 4)
            data = json.loads(base64.b64decode(payload).decode("utf-8", errors="ignore"))
            return data.get("add"), int(data.get("port"))
        else:
            parsed = urlparse(link)
            if parsed.hostname and parsed.port:
                return parsed.hostname, parsed.port
    except Exception:
        pass
    return None, None


def test_latency(host: str, port: int, timeout: float):
    try:
        start = time.time()
        with socket.create_connection((host, port), timeout=timeout):
            pass
        return round((time.time() - start) * 1000, 1)
    except Exception:
        return None


def check_all(configs: list, timeout: float, workers: int):
    results = []

    def worker(link):
        host, port = get_host_port(link)
        if not host or not port:
            return None
        latency = test_latency(host, port, timeout)
        if latency is None:
            return None
        return (latency, link, host, port)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(worker, link): link for link in configs}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                results.append(res)

    results.sort(key=lambda r: r[0])
    return results


def write_outputs(results):
    working_links = [r[1] for r in results]

    with open("working_configs.txt", "w", encoding="utf-8") as f:
        for latency, link, host, port in results:
            f.write(f"# {latency} ms  {host}:{port}\n{link}\n")

    sub_content = base64.b64encode("\n".join(working_links).encode("utf-8")).decode("utf-8")
    with open("subscription.txt", "w", encoding="utf-8") as f:
        f.write(sub_content)


def main():
    print(f"[1/4] Fetching last {MESSAGE_COUNT} messages from t.me/s/{CHANNEL} ...")
    texts = fetch_last_messages(CHANNEL, MESSAGE_COUNT)
    print(f"      -> got {len(texts)} messages")

    print("[2/4] Extracting config links ...")
    configs = extract_configs(texts)
    print(f"      -> found {len(configs)} unique configs")

    print(f"[3/4] Testing connectivity ({TIMEOUT}s timeout, {WORKERS} workers) ...")
    results = check_all(configs, TIMEOUT, WORKERS)
    print(f"      -> {len(results)}/{len(configs)} servers responded")

    print("[4/4] Writing outputs ...")
    write_outputs(results)
    print("      -> working_configs.txt")
    print("      -> subscription.txt")

    if not results:
        print("WARNING: no working configs found this run.")


if __name__ == "__main__":
    main()
