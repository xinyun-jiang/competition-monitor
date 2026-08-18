# -*- coding: utf-8 -*-
"""微信推送：新比赛汇总。
Server酱 / PushPlus 二选一——config 里配了哪个 key 就用哪个，都配时优先 Server酱。
"""
import logging

import requests

import config

log = logging.getLogger(__name__)

PUSHPLUS_URL = "http://www.pushplus.plus/send"


def _send_serverchan(title: str, content: str) -> bool:
    """Server酱 Turbo，desp 字段原生支持 Markdown。"""
    url = f"https://sctapi.ftqq.com/{config.SERVERCHAN_KEY}.send"
    resp = requests.post(url, data={"title": title, "desp": content}, timeout=15)
    ok = resp.json().get("code") == 0
    if not ok:
        log.error("Server酱 推送失败: %s", resp.text)
    return ok


def _send_pushplus(title: str, content: str) -> bool:
    resp = requests.post(PUSHPLUS_URL, json={
        "token": config.PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "markdown",
    }, timeout=15)
    ok = resp.json().get("code") == 200
    if not ok:
        log.error("PushPlus 推送失败: %s", resp.text)
    return ok


def send(title: str, content: str) -> bool:
    """发送 Markdown 消息到微信。返回是否成功。"""
    try:
        if config.SERVERCHAN_KEY:
            return _send_serverchan(title, content)
        if config.PUSHPLUS_TOKEN:
            return _send_pushplus(title, content)
        log.warning("未配置推送密钥（SERVERCHAN_KEY / PUSHPLUS_TOKEN），跳过推送。标题: %s", title)
        return False
    except requests.RequestException as e:
        log.error("推送请求异常: %s", e)
        return False

def format_competitions(comps: list) -> str:
    """把新入库的比赛列表排成 Markdown。"""
    lines = [f"本轮新发现 **{len(comps)}** 个相关比赛：\n"]
    for i, c in enumerate(comps, 1):
        lines.append(f"### {i}. {c['name'] or c['title']}")
        lines.append(f"- 级别：{c['level'] or '不确定'}")
        if c.get('level_basis'):
            lines.append(f"- 级别依据：{c['level_basis']}")
        deadline_text = c["deadline"] or "未明确（需人工核实）"
        lines.append(f"- 报名：{c['register_start'] or '?'} ~ {deadline_text}")
        lines.append(f"- 参赛者类型：{c.get('participant_type') or '不确定'}")
        lines.append(f"- 对象：{c['eligibility'] or '-'}")
        lines.append(f"- 奖项类型：{c.get('award_type') or '不确定'}")
        if c.get('award_amount'):
            lines.append(f"- 奖金/资助：{c['award_amount']}")
        lines.append(f"- 奖项：{c['awards'] or '-'}")
        lines.append(f"- 简介：{c['summary'] or '-'}")
        lines.append(f"- 来源：{c['account'] or '-'}　[原文链接]({c['url']})")
        lines.append("")
    return "\n".join(lines)

