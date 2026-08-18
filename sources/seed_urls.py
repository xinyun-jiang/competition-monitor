# -*- coding: utf-8 -*-
"""手动维护的单篇文章/公告 URL 来源。"""
from pathlib import Path

import config


def discover():
    path = Path(config.SEED_URLS_FILE)
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("\t")]
        url = parts[0]
        title = parts[1] if len(parts) > 1 else url
        items.append({
            "url": url,
            "real_url": url,
            "title": title,
            "account": "手动来源",
            "snippet": "",
            "source": "seed_urls",
            "keyword": "manual",
        })
    return items
