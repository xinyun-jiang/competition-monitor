# -*- coding: utf-8 -*-
"""SQLite 存储层。
articles 表记录每篇抓过的文章及其处理状态（一切状态入库，程序可随时中断重跑）；
competitions 表记录 LLM 提取出的比赛信息。
"""
import os
import sqlite3

import config
import normalize

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE,            -- 真实的 mp.weixin.qq.com 链接
    title TEXT,
    account TEXT,               -- 公众号名称
    publish_time TEXT,
    snapshot_path TEXT,         -- 本地 HTML 快照路径
    status TEXT DEFAULT 'fetched',
    -- fetched / skipped(初筛被砍) / not_competition / competition / error / old_article / expired_competition
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS competitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE,
    dedupe_key TEXT UNIQUE,     -- 归一化去重键：比赛名 + 截止日期
    name TEXT,                  -- 比赛名称
    level TEXT,                 -- 级别：国际级/国家级/省级/行业级/校级/不确定
    register_start TEXT,        -- 报名开始时间
    deadline TEXT,              -- 报名/提交截止时间
    deadline_status TEXT DEFAULT 'unknown', -- confirmed / unknown
    eligibility TEXT,           -- 参赛对象与要求
    participant_type TEXT,      -- 参赛者类型：大学生/企业/科研团队/个人/混合/不确定
    keywords TEXT,              -- 技术/产业/赛题关键词，逗号分隔
    awards TEXT,                -- 奖项设置
    award_type TEXT,            -- 奖项类型：奖金/荣誉证书/项目资助/落地孵化/资源对接/混合/不确定
    award_amount TEXT,          -- 奖金金额或资助额度
    level_basis TEXT,           -- 级别判断依据
    summary TEXT,               -- 简介
    account TEXT,               -- 来源公众号
    title TEXT,                 -- 文章标题
    pushed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);


CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sogou_url TEXT UNIQUE NOT NULL,
    keyword TEXT,
    title TEXT,
    account TEXT,
    snippet TEXT,
    status TEXT DEFAULT 'pending',
    -- pending / resolved / processed / resolve_error / captcha / expired_link
    attempts INTEGER DEFAULT 0,
    real_url TEXT,
    source TEXT,
    last_error TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS user_favorites (
    user_id INTEGER NOT NULL,
    competition_id INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (user_id, competition_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (competition_id) REFERENCES competitions(id)
);
"""


def get_conn():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _ensure_column(conn, "competitions", "deadline_status", "TEXT DEFAULT 'unknown'")
        _ensure_column(conn, "competitions", "participant_type", "TEXT")
        _ensure_column(conn, "competitions", "keywords", "TEXT")
        _ensure_column(conn, "competitions", "award_type", "TEXT")
        _ensure_column(conn, "competitions", "award_amount", "TEXT")
        _ensure_column(conn, "competitions", "level_basis", "TEXT")
        _ensure_column(conn, "competitions", "dedupe_key", "TEXT")
        _ensure_column(conn, "candidates", "source", "TEXT")
        _backfill_dedupe_keys(conn)


def _ensure_column(conn, table, column, col_type):
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def _backfill_dedupe_keys(conn):
    rows = conn.execute(
        "SELECT id, name, deadline FROM competitions WHERE dedupe_key IS NULL OR dedupe_key = '' ORDER BY id"
    ).fetchall()
    for row in rows:
        key = normalize.competition_dedupe_key(row["name"], row["deadline"])
        if not key or key == "|":
            key = f"legacy:{row['id']}"
        exists = conn.execute(
            "SELECT id FROM competitions WHERE dedupe_key = ? AND id != ?", (key, row["id"])
        ).fetchone()
        if exists:
            # 旧数据出现重复时，后续清理脚本会合并；这里避免 UNIQUE 冲突。
            key = f"duplicate:{row['id']}:{key}"
        conn.execute("UPDATE competitions SET dedupe_key = ? WHERE id = ?", (key, row["id"]))


def url_seen(url: str) -> bool:
    """该文章是否已经处理过（含初筛被砍、判定非比赛等所有状态）。"""
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone()
    return row is not None


def save_article(url, title, account, publish_time, snapshot_path, status="fetched"):
    """保存文章但不覆盖历史记录；同一 URL 后续只补充空字段。"""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO articles (url, title, account, publish_time, snapshot_path, status)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = COALESCE(NULLIF(articles.title, ''), excluded.title),
                account = COALESCE(NULLIF(articles.account, ''), excluded.account),
                publish_time = COALESCE(NULLIF(articles.publish_time, ''), excluded.publish_time),
                snapshot_path = COALESCE(NULLIF(articles.snapshot_path, ''), excluded.snapshot_path)
            """,
            (url, title, account, publish_time, snapshot_path, status),
        )


def set_article_status(url, status):
    with get_conn() as conn:
        conn.execute("UPDATE articles SET status = ? WHERE url = ?", (status, url))


def article_status(url):
    with get_conn() as conn:
        row = conn.execute("SELECT status FROM articles WHERE url = ?", (url,)).fetchone()
    return row["status"] if row else None


def insert_competition(url, name, level, register_start, deadline,
                       eligibility, awards, summary, account, title,
                       participant_type=None, keywords=None, award_type=None, award_amount=None, level_basis=None,
                       deadline_status=None):
    dedupe_key = normalize.competition_dedupe_key(name, deadline)
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM competitions WHERE dedupe_key = ? OR url = ?", (dedupe_key, url)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE competitions
                SET url = COALESCE(url, ?),
                    name = COALESCE(NULLIF(name, ''), ?),
                    level = COALESCE(NULLIF(level, ''), ?),
                    register_start = COALESCE(NULLIF(register_start, ''), ?),
                    deadline = COALESCE(NULLIF(deadline, ''), ?),
                    deadline_status = CASE WHEN deadline IS NOT NULL AND deadline != '' THEN 'confirmed' ELSE ? END,
                    eligibility = COALESCE(NULLIF(eligibility, ''), ?),
                    participant_type = COALESCE(NULLIF(participant_type, ''), ?),
                    keywords = COALESCE(NULLIF(keywords, ''), ?),
                    awards = COALESCE(NULLIF(awards, ''), ?),
                    award_type = COALESCE(NULLIF(award_type, ''), ?),
                    award_amount = COALESCE(NULLIF(award_amount, ''), ?),
                    level_basis = COALESCE(NULLIF(level_basis, ''), ?),
                    summary = COALESCE(NULLIF(summary, ''), ?),
                    account = COALESCE(NULLIF(account, ''), ?),
                    title = COALESCE(NULLIF(title, ''), ?)
                WHERE id = ?
                """,
                (url, name, level, register_start, deadline, deadline_status or ("confirmed" if deadline else "unknown"),
                 eligibility, participant_type, keywords, awards, award_type, award_amount, level_basis, summary, account, title, existing["id"]),
            )
            return existing["id"]

        conn.execute(
            "INSERT OR IGNORE INTO competitions"
            " (url, dedupe_key, name, level, register_start, deadline, deadline_status, eligibility, participant_type, keywords,"
            " awards, award_type, award_amount, level_basis, summary, account, title)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (url, dedupe_key, name, level, register_start, deadline, deadline_status or ("confirmed" if deadline else "unknown"),
             eligibility, participant_type, keywords,
             awards, award_type, award_amount, level_basis, summary, account, title),
        )
        row = conn.execute("SELECT id FROM competitions WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
        return row["id"] if row else None


def get_unpushed_competitions():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM competitions WHERE pushed = 0 ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def mark_pushed(ids):
    if not ids:
        return
    with get_conn() as conn:
        conn.executemany("UPDATE competitions SET pushed = 1 WHERE id = ?",
                         [(i,) for i in ids])

# ---------------- 多用户系统查询 ----------------

def create_user(email, password_hash, is_admin=False):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, ?)",
            (email.lower().strip(), password_hash, 1 if is_admin else 0),
        )


def get_user_by_email(email):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_competitions(q=None, active_only=True, limit=50, offset=0):
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    clauses = []
    params = []
    if active_only:
        clauses.append("(competitions.deadline IS NULL OR competitions.deadline = '' OR date(competitions.deadline) >= date('now', 'localtime'))")
    if q:
        like = f"%{q}%"
        clauses.append("(competitions.name LIKE ? OR competitions.title LIKE ? OR competitions.summary LIKE ? OR competitions.account LIKE ? OR competitions.keywords LIKE ?)")
        params.extend([like, like, like, like, like])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql = (
        """
        SELECT competitions.*,
               articles.status AS article_status,
               articles.snapshot_path AS snapshot_path
        FROM competitions
        LEFT JOIN articles ON articles.url = competitions.url
        """ + where +
        " ORDER BY CASE WHEN competitions.deadline IS NULL OR competitions.deadline = '' THEN 1 ELSE 0 END, date(competitions.deadline), competitions.id DESC"
        " LIMIT ? OFFSET ?"
    )
    with get_conn() as conn:
        rows = conn.execute(sql, (*params, limit, offset)).fetchall()
    return [dict(r) for r in rows]


def get_competition(competition_id):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT competitions.*,
                   articles.status AS article_status,
                   articles.snapshot_path AS snapshot_path
            FROM competitions
            LEFT JOIN articles ON articles.url = competitions.url
            WHERE competitions.id = ?
            """,
            (competition_id,),
        ).fetchone()
    return dict(row) if row else None


def competition_stats():
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN deadline IS NOT NULL AND deadline != '' AND date(deadline) >= date('now', 'localtime') THEN 1 ELSE 0 END) AS active_with_deadline,
              SUM(CASE WHEN pushed = 0 THEN 1 ELSE 0 END) AS unpushed
            FROM competitions
            """
        ).fetchone()
    return dict(row)

# ---------------- 搜狗候选队列 ----------------

def enqueue_candidate(item, keyword):
    real_url = item.get("real_url")
    status = "resolved" if real_url else "pending"
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO candidates (sogou_url, keyword, title, account, snippet, status, real_url, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sogou_url) DO UPDATE SET
              keyword = excluded.keyword,
              title = excluded.title,
              account = excluded.account,
              snippet = excluded.snippet,
              real_url = COALESCE(candidates.real_url, excluded.real_url),
              source = excluded.source,
              status = CASE
                WHEN candidates.status IN ('resolve_error', 'captcha', 'expired_link') THEN 'pending'
                ELSE candidates.status
              END,
              updated_at = datetime('now', 'localtime')
            """,
            (item.get("url"), keyword, item.get("title", ""), item.get("account", ""), item.get("snippet", ""),
             status, real_url, item.get("source", "")),
        )


def count_pending_candidates():
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM candidates WHERE status IN ('pending', 'captcha', 'resolved')").fetchone()
    return int(row["n"])


def get_pending_candidates(limit, ttl_hours):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, sogou_url AS url, real_url, title, account, snippet, keyword, attempts, source
            FROM candidates
            WHERE status IN ('pending', 'captcha', 'resolved')
              AND datetime(created_at) >= datetime('now', 'localtime', ?)
              AND attempts < 3
            ORDER BY attempts, id
            LIMIT ?
            """,
            (f"-{int(ttl_hours)} hours", int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_candidate_resolved(candidate_id, real_url):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE candidates
            SET status = 'resolved', real_url = ?, updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (real_url, candidate_id),
        )


def mark_candidate_processed(candidate_id):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE candidates
            SET status = 'processed', updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (candidate_id,),
        )


def mark_candidate_error(candidate_id, status, error):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE candidates
            SET status = ?, attempts = attempts + 1, last_error = ?, updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (status, str(error)[:500], candidate_id),
        )


def candidate_queue_stats():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM candidates GROUP BY status ORDER BY status"
        ).fetchall()
    return {r["status"]: r["n"] for r in rows}



# ---------------- 管理员比赛维护 ----------------

def upsert_competition_admin(data, competition_id=None):
    name = data.get("name") or data.get("title") or "未命名比赛"
    deadline = data.get("deadline")
    dedupe_key = normalize.competition_dedupe_key(name, deadline)
    fields = {
        "url": data.get("url") or "",
        "dedupe_key": dedupe_key,
        "name": name,
        "level": data.get("level"),
        "register_start": data.get("register_start"),
        "deadline": deadline,
        "deadline_status": data.get("deadline_status") or ("confirmed" if deadline else "unknown"),
        "eligibility": data.get("eligibility"),
        "participant_type": data.get("participant_type"),
        "keywords": data.get("keywords"),
        "awards": data.get("awards"),
        "award_type": data.get("award_type"),
        "award_amount": data.get("award_amount"),
        "level_basis": data.get("level_basis"),
        "summary": data.get("summary"),
        "account": data.get("account") or "管理员手动维护",
        "title": data.get("title") or name,
    }
    cols = list(fields.keys())
    vals = [fields[c] for c in cols]
    with get_conn() as conn:
        if competition_id:
            assignments = ", ".join([f"{c} = ?" for c in cols])
            conn.execute(f"UPDATE competitions SET {assignments} WHERE id = ?", (*vals, competition_id))
            return competition_id
        conn.execute(
            "INSERT INTO competitions (" + ", ".join(cols) + ") VALUES (" + ", ".join(["?"] * len(cols)) + ")"
            " ON CONFLICT(dedupe_key) DO UPDATE SET " + ", ".join([f"{c}=excluded.{c}" for c in cols if c != "dedupe_key"]),
            vals,
        )
        row = conn.execute("SELECT id FROM competitions WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
        return row["id"] if row else None


def hide_competition(competition_id):
    with get_conn() as conn:
        row = conn.execute("SELECT url FROM competitions WHERE id = ?", (competition_id,)).fetchone()
        if not row:
            return False
        conn.execute("UPDATE articles SET status = 'hidden_competition' WHERE url = ?", (row["url"],))
        conn.execute("DELETE FROM competitions WHERE id = ?", (competition_id,))
        return True
