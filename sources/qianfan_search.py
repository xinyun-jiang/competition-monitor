# -*- coding: utf-8 -*-
"""百度千帆 AI Search 来源：调用官方 web_search API 获取普通网页候选。"""
import itertools

import requests

import config

API_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"


def _query_candidates():
    """生成单关键词和双关键词组合查询。

    每条查询都带“比赛 报名”，避免单独搜索“AI”时返回大量无关内容。
    例如：
    - 单关键词：AI 比赛 报名
    - 组合关键词：AI 电池 比赛 报名
    """
    max_queries = max(1, int(config.QIANFAN_MAX_QUERIES_PER_RUN))
    single_queries = [f"{keyword} 比赛 报名" for keyword in config.DOMAIN_WORDS]
    pair_queries = [
        f"{left} {right} 比赛 报名"
        for left, right in itertools.combinations(config.DOMAIN_WORDS, 2)
    ]
    queries = single_queries + pair_queries
    return queries[:max_queries]


def _parse_references(data):
    refs = data.get("references") or data.get("reference") or []
    if isinstance(refs, dict):
        refs = refs.get("items") or refs.get("list") or []
    if not isinstance(refs, list):
        return []
    return refs


def _search(query, log):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.QIANFAN_API_KEY}",
        "X-Appbuilder-Authorization": f"Bearer {config.QIANFAN_API_KEY}",
    }
    payload = {
        "messages": [{"role": "user", "content": query[:72]}],
        "search_source": "baidu_search_v2",
        "resource_type_filter": [{"type": "web", "top_k": config.QIANFAN_RESULTS_PER_QUERY}],
        "search_recency_filter": config.QIANFAN_RECENCY,
        "safe_search": True,
    }
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
    if resp.status_code >= 400:
        log.warning("千帆搜索失败 status=%s query=%s body=%s", resp.status_code, query, resp.text[:300])
        return []
    data = resp.json()
    if data.get("code"):
        log.warning("千帆搜索错误 code=%s message=%s query=%s", data.get("code"), data.get("message"), query)
        return []
    return _parse_references(data)


def discover(result_filter, limit, log):
    if not config.QIANFAN_API_KEY:
        log.warning("未配置 QIANFAN_API_KEY，跳过 qianfan_search 来源")
        return []

    seen = set()
    items = []
    queries = _query_candidates()
    log.info("千帆来源：本轮搜索 %d 个 query，每个最多 %d 条", len(queries), config.QIANFAN_RESULTS_PER_QUERY)

    for query in queries:
        refs = _search(query, log)
        for ref in refs:
            url = ref.get("url") or ref.get("link") or ref.get("href")
            if not url or url in seen:
                continue
            seen.add(url)
            title = ref.get("title") or ref.get("name") or url
            snippet = ref.get("summary") or ref.get("snippet") or ref.get("content") or ref.get("abstract") or ""
            item = {
                "url": url,
                "real_url": url,
                "title": title,
                "account": ref.get("site_name") or ref.get("source") or "百度千帆搜索",
                "snippet": snippet,
                "source": "qianfan_search",
                "keyword": query,
            }
            if result_filter(item):
                items.append(item)
                if len(items) >= limit:
                    return items
    return items
