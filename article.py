# -*- coding: utf-8 -*-
"""公众号正文抓取与快照。
mp.weixin.qq.com 文章页不需要登录，requests 直接抓。
正文拿到后立即存 HTML 快照——搜狗链接会过期，快照是以后重跑提取的保障。
"""
import hashlib
import logging
import os
import re
import time

import requests
from bs4 import BeautifulSoup

import config

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def fetch_article(url: str) -> dict | None:
    """抓取文章，返回 {url,title,account,publish_time,content,snapshot_path}，失败返回 None。"""
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        resp.encoding = "utf-8"
    except requests.RequestException as e:
        log.warning("抓取文章失败 %s: %s", url, e)
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    content_tag = soup.select_one("#js_content")
    if content_tag is None:
        # 链接失效/被删除/需要验证
        log.warning("正文为空（链接可能已失效）: %s", url)
        return None

    title_tag = soup.select_one("#activity-name")
    account_tag = soup.select_one("#js_name")

    # 发布时间藏在 JS 变量 var ct = "1720000000" 里
    publish_time = ""
    m = re.search(r'var ct = ["\']?(\d{9,10})["\']?', resp.text)
    if m:
        publish_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(m.group(1))))

    # 存 HTML 快照
    os.makedirs(config.SNAPSHOT_DIR, exist_ok=True)
    fname = hashlib.md5(url.encode()).hexdigest() + ".html"
    snapshot_path = os.path.join(config.SNAPSHOT_DIR, fname)
    with open(snapshot_path, "w", encoding="utf-8") as f:
        f.write(resp.text)

    return {
        "url": url,
        "title": title_tag.get_text(strip=True) if title_tag else "",
        "account": account_tag.get_text(strip=True) if account_tag else "",
        "publish_time": publish_time,
        "content": content_tag.get_text("\n", strip=True),
        "snapshot_path": snapshot_path,
    }


def is_relevant(content: str) -> bool:
    """正文初筛：必须是目标方向，并且明确属于比赛类活动。"""
    text = str(content or "")
    lowered = text.lower()
    has_domain = any(w.lower() in lowered for w in config.FILTER_DOMAIN)
    has_event = any(w in text for w in config.FILTER_EVENT)
    has_signup = any(w in text for w in config.FILTER_INTENT)
    return has_domain and has_event and has_signup



def fetch_generic_article(url: str) -> dict | None:
    """抓取普通网页公告，返回与公众号文章相同结构。"""
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        resp.encoding = resp.apparent_encoding or "utf-8"
    except requests.RequestException as e:
        log.warning("抓取网页失败 %s: %s", url, e)
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup.select("script, style, noscript, header, footer, nav"):
        tag.decompose()

    title_tag = soup.select_one("h1") or soup.select_one("title")
    content_tag = (
        soup.select_one("article")
        or soup.select_one(".article")
        or soup.select_one(".content")
        or soup.select_one(".main")
        or soup.select_one("#content")
        or soup.body
    )
    if content_tag is None:
        log.warning("网页正文为空: %s", url)
        return None

    content = content_tag.get_text("\n", strip=True)
    if len(content) < 100:
        log.warning("网页正文过短: %s", url)
        return None

    publish_time = ""
    text = soup.get_text("\n", strip=True)
    m = re.search(r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})", text)
    if m:
        publish_time = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d} 00:00:00"

    os.makedirs(config.SNAPSHOT_DIR, exist_ok=True)
    fname = hashlib.md5(url.encode()).hexdigest() + ".html"
    snapshot_path = os.path.join(config.SNAPSHOT_DIR, fname)
    with open(snapshot_path, "w", encoding="utf-8") as f:
        f.write(resp.text)

    return {
        "url": url,
        "title": title_tag.get_text(strip=True) if title_tag else "",
        "account": "网页公告",
        "publish_time": publish_time,
        "content": content,
        "snapshot_path": snapshot_path,
    }


def fetch_any_article(url: str) -> dict | None:
    if "mp.weixin.qq.com" in url:
        return fetch_article(url)
    return fetch_generic_article(url)
