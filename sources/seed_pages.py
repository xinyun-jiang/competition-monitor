# -*- coding: utf-8 -*-
"""手动维护的列表页/公告页来源：从页面中提取疑似比赛链接。"""
from urllib.parse import urljoin
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import config

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"


def _looks_relevant(text):
    return any(w in text for w in config.FILTER_EVENT + config.FILTER_INTENT) and any(w in text for w in config.FILTER_DOMAIN)


def discover():
    path = Path(config.SEED_PAGES_FILE)
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        page_url = line.strip()
        if not page_url or page_url.startswith("#"):
            continue
        try:
            resp = requests.get(page_url, headers={"User-Agent": UA}, timeout=20)
            resp.encoding = resp.apparent_encoding or "utf-8"
        except requests.RequestException:
            continue
        soup = BeautifulSoup(resp.text, "lxml")
        for a in soup.select("a[href]"):
            title = a.get_text(" ", strip=True)
            if not title or not _looks_relevant(title):
                continue
            url = urljoin(page_url, a["href"])
            items.append({
                "url": url,
                "real_url": url,
                "title": title,
                "account": page_url,
                "snippet": "",
                "source": "seed_pages",
                "keyword": "seed_page",
            })
    return items
