# -*- coding: utf-8 -*-
"""主流程：关键词搜索 → 正文抓取 → 去重 → 初筛 → LLM 提取 → 入库 → 推送。
每天由 cron 定时触发（默认 12:30 和 21:30），也可手动 python main.py 跑一轮。
"""
import calendar
import logging
import os
import re
import sys
from datetime import datetime, timedelta

import article as art
import config
import db
import extract
import notify
from sources import qianfan_search, seed_pages, seed_urls

os.makedirs(config.DATA_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(config.DATA_DIR, "run.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger("main")


def _default_year():
    m = re.match(r"(20\d{2})", str(config.TODAY or ""))
    return int(m.group(1)) if m else datetime.now().year


def _parse_date(value: str | None, default_year: int | None = None):
    if not value:
        return None
    value = str(value).strip()
    parsed = []
    for candidate in (value, value[:19], value[:10]):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
            try:
                parsed.append(datetime.strptime(candidate, fmt).date())
            except ValueError:
                pass
    for year, month, day in re.findall(r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?", value):
        try:
            parsed.append(datetime(int(year), int(month), int(day)).date())
        except ValueError:
            pass
    current_year = default_year or _default_year()
    for month in re.findall(r"(?<!\d)(\d{1,2})\s*月\s*(?:底|末)", value):
        try:
            last_day = calendar.monthrange(current_year, int(month))[1]
            parsed.append(datetime(current_year, int(month), last_day).date())
        except ValueError:
            pass
    for month, day in re.findall(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日?", value):
        try:
            parsed.append(datetime(current_year, int(month), int(day)).date())
        except ValueError:
            pass
    return max(parsed) if parsed else None


def _format_date(value: str | None, default_year: int | None = None):
    parsed = _parse_date(value, default_year=default_year)
    return parsed.isoformat() if parsed else value


def _normalize_info_dates(info: dict, article: dict | None = None):
    publish_date = _parse_date((article or {}).get("publish_time"))
    default_year = publish_date.year if publish_date else _default_year()
    for field in ("register_start", "deadline"):
        if info.get(field):
            info[field] = _format_date(info.get(field), default_year=default_year)


def _today():
    parsed = _parse_date(config.TODAY)
    return parsed or datetime.now().date()


def result_is_candidate(item: dict) -> bool:
    """搜索结果层面硬筛：只让目标方向的比赛报名信息进入候选队列。"""
    text = f"{item.get('title', '')}\n{item.get('snippet', '')}"
    lowered = text.lower()
    if any(w in text for w in config.EXCLUDE_WORDS):
        return False
    has_domain = any(w.lower() in lowered for w in config.FILTER_DOMAIN)
    has_event = any(w in text for w in config.FILTER_EVENT)
    has_signup = any(w in text for w in config.FILTER_INTENT)
    return has_domain and has_event and has_signup


def article_is_recent(article: dict) -> bool:
    publish_date = _parse_date(article.get("publish_time"))
    if not publish_date:
        return True
    cutoff = _today() - timedelta(days=config.MAX_ARTICLE_AGE_DAYS)
    return publish_date >= cutoff


def competition_is_effective(info: dict) -> bool:
    """允许缺少截止日期；如果有截止日期，则不能早于今天。"""
    deadline = _parse_date(info.get("deadline"))
    if not deadline:
        # 允许没有明确截止日期，但入库时会明确标记为 unknown，提醒人工核实。
        return True
    cutoff = _today() - timedelta(days=config.DEADLINE_GRACE_DAYS)
    return deadline >= cutoff


def search_all(session) -> list:
    """从多个来源发现候选并入队。搜狗只是其中一个来源，验证码不会导致整轮失败。"""
    enqueued = 0

    if "seed_urls" in config.ENABLED_SOURCES:
        items = seed_urls.discover()
        log.info("seed_urls 来源发现 %d 条", len(items))
        for item in items:
            db.enqueue_candidate(item, item.get("keyword", "manual"))
            enqueued += 1

    if "seed_pages" in config.ENABLED_SOURCES:
        items = seed_pages.discover()
        log.info("seed_pages 来源发现 %d 条", len(items))
        for item in items:
            db.enqueue_candidate(item, item.get("keyword", "seed_page"))
            enqueued += 1

    if "qianfan_search" in config.ENABLED_SOURCES and enqueued < config.MAX_RESULTS_PER_RUN:
        items = qianfan_search.discover(
            result_filter=result_is_candidate,
            limit=config.MAX_RESULTS_PER_RUN - enqueued,
            log=log,
        )
        log.info("qianfan_search 来源发现 %d 条", len(items))
        for item in items:
            db.enqueue_candidate(item, item.get("keyword", "qianfan"))
            enqueued += 1

    log.info("多来源发现完成，本轮入队/刷新 %d 条；队列状态: %s", enqueued, db.candidate_queue_stats())
    return db.get_pending_candidates(config.MAX_RESOLVE_PER_RUN, config.CANDIDATE_TTL_HOURS)


def process_results(session, results):
    """从候选队列小批量解析真实链接 → 抓正文 → LLM → 入库。

    触发验证码后立即停止本轮，保留剩余候选下轮继续。这样比原来的等待重试更适合长期无人值守。
    """
    processed = 0
    for item in results[:config.MAX_RESOLVE_PER_RUN]:
        candidate_id = item.get("id")
        real_url = item.get("real_url")
        if not real_url:
            # 当前自动来源均直接返回真实 URL；保留失败状态，下一轮可重试。
            if candidate_id:
                db.mark_candidate_error(candidate_id, "resolve_error", "候选没有真实 URL")
            continue
        if not real_url:
            if candidate_id:
                db.mark_candidate_error(candidate_id, "resolve_error", "未能解析真实链接")
            continue
        if candidate_id:
            db.mark_candidate_resolved(candidate_id, real_url)
        processed += 1

        status = db.article_status(real_url)
        if status and status not in ("fetched", "error"):
            if candidate_id:
                db.mark_candidate_processed(candidate_id)
            continue

        article = art.fetch_any_article(real_url)
        if article is None:
            db.save_article(real_url, item["title"], item["account"], "", "", status="error")
            if candidate_id:
                db.mark_candidate_processed(candidate_id)
            continue

        db.save_article(real_url, article["title"], article["account"] or item["account"],
                        article["publish_time"], article["snapshot_path"])

        if not article_is_recent(article):
            db.set_article_status(real_url, "old_article")
            log.info("文章过旧，跳过: %s (%s)", article["title"], article["publish_time"])
            if candidate_id:
                db.mark_candidate_processed(candidate_id)
            continue

        if not art.is_relevant(article["content"]):
            db.set_article_status(real_url, "skipped")
            log.info("初筛未通过: %s", article["title"])
            if candidate_id:
                db.mark_candidate_processed(candidate_id)
            continue

        info = extract.extract(article)
        if info is None:
            db.set_article_status(real_url, "error")
            if candidate_id:
                db.mark_candidate_processed(candidate_id)
            continue
        if not info.get("is_competition"):
            db.set_article_status(real_url, "not_competition")
            log.info("LLM 判定非比赛: %s", article["title"])
            if candidate_id:
                db.mark_candidate_processed(candidate_id)
            continue
        _normalize_info_dates(info, article)
        if not competition_is_effective(info):
            db.set_article_status(real_url, "expired_competition")
            log.info("比赛已过期或缺少有效截止日期: %s deadline=%s",
                     info.get("name") or article["title"], info.get("deadline"))
            if candidate_id:
                db.mark_candidate_processed(candidate_id)
            continue

        db.insert_competition(
            url=real_url,
            name=info.get("name") or article["title"],
            level=info.get("level"),
            register_start=info.get("register_start"),
            deadline=info.get("deadline"),
            eligibility=info.get("eligibility"),
            awards=info.get("awards"),
            summary=info.get("summary"),
            account=article["account"] or item["account"],
            title=article["title"],
            participant_type=info.get("participant_type"),
            keywords=info.get("keywords"),
            award_type=info.get("award_type"),
            award_amount=info.get("award_amount"),
            level_basis=info.get("level_basis"),
            deadline_status="confirmed" if info.get("deadline") else "unknown",
        )
        db.set_article_status(real_url, "competition")
        if candidate_id:
            db.mark_candidate_processed(candidate_id)
        log.info("发现比赛: %s", info.get("name") or article["title"])

    log.info("解析处理完成，本轮解析 %d 条；队列状态: %s", processed, db.candidate_queue_stats())

def run():
    log.info("========== 本轮开始 ==========")
    if not config.LLM_API_KEY:
        raise SystemExit("未配置 LLM_API_KEY，请检查 .env 或环境变量")
    db.init_db()
    session = None
    results = search_all(session)
    process_results(session, results)

    new_comps = [c for c in db.get_unpushed_competitions() if competition_is_effective(c)]
    if new_comps:
        ok = notify.send(f"发现 {len(new_comps)} 个新比赛", notify.format_competitions(new_comps))
        if ok:
            db.mark_pushed([c["id"] for c in new_comps])
            log.info("已推送 %d 个新比赛", len(new_comps))
    else:
        log.info("本轮没有新比赛，不推送")
    log.info("========== 本轮结束 ==========")


if __name__ == "__main__":
    run()
