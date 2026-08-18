# -*- coding: utf-8 -*-
"""本地比赛信息查看页面。启动：streamlit run streamlit_app.py"""
import csv
import io
import sqlite3
from pathlib import Path

import streamlit as st

import config

st.set_page_config(page_title="比赛信息监控", page_icon="🏆", layout="wide")


def load_competitions(active_only: bool, keyword: str):
    db_path = Path(config.DB_PATH)
    if not db_path.exists():
        return []
    clauses = []
    params = []
    if active_only:
        clauses.append("(deadline IS NULL OR deadline = '' OR date(deadline) >= date('now', 'localtime'))")
    if keyword:
        like = f"%{keyword}%"
        clauses.append("(name LIKE ? OR title LIKE ? OR summary LIKE ? OR keywords LIKE ? OR account LIKE ?)")
        params.extend([like] * 5)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql = (
        "SELECT * FROM competitions" + where
        + " ORDER BY CASE WHEN deadline IS NULL OR deadline = '' THEN 1 ELSE 0 END, "
          "date(deadline), id DESC"
    )
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def export_csv(items):
    fields = [
        "name", "level", "register_start", "deadline", "deadline_status",
        "participant_type", "keywords", "eligibility", "award_type",
        "award_amount", "awards", "summary", "account", "title", "url",
        "created_at",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(items)
    return output.getvalue().encode("utf-8-sig")


st.title("🏆 比赛信息监控")
st.caption("数据来自本地 SQLite；爬虫由 main.py 定时运行，本页面只负责查看和导出。")

with st.sidebar:
    st.header("筛选")
    keyword = st.text_input("搜索", placeholder="例如：电池、储能、智能体")
    active_only = st.checkbox("只看未过期比赛", value=True)
    if st.button("刷新数据", use_container_width=True):
        st.rerun()

items = load_competitions(active_only, keyword.strip())
confirmed = sum(1 for item in items if item.get("deadline_status") == "confirmed")
unknown = sum(1 for item in items if item.get("deadline_status") != "confirmed")

col1, col2, col3 = st.columns(3)
col1.metric("比赛数量", len(items))
col2.metric("截止日期已确认", confirmed)
col3.metric("截止日期需核实", unknown)

if not items:
    st.info("没有找到符合条件的比赛。请先运行 main.py。")
else:
    st.download_button(
        "下载 CSV", data=export_csv(items), file_name="competition-monitor.csv", mime="text/csv"
    )
    for item in items:
        name = item.get("name") or item.get("title") or "未命名比赛"
        deadline = item.get("deadline") or "未明确，需人工核实"
        with st.expander(f"{name} | 截止：{deadline}"):
            left, right = st.columns(2)
            with left:
                st.write(f"**级别：** {item.get('level') or '不确定'}")
                st.write(f"**报名时间：** {item.get('register_start') or '?'} ~ {deadline}")
                st.write(f"**参赛对象：** {item.get('participant_type') or '不确定'}")
                st.write(f"**关键词：** {item.get('keywords') or '-'}")
                st.write(f"**来源：** {item.get('account') or '-'}")
            with right:
                st.write(f"**参赛要求：** {item.get('eligibility') or '-'}")
                st.write(f"**奖项：** {item.get('awards') or '-'}")
                st.write(f"**奖金/资助：** {item.get('award_amount') or '-'}")
                st.write(f"**简介：** {item.get('summary') or '-'}")
            if item.get("url"):
                st.link_button("打开原文", item["url"])
