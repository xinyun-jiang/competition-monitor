# -*- coding: utf-8 -*-
"""比赛去重归一化工具。"""
import re

_PUNCT = str.maketrans({
    "—": "-", "–": "-", "－": "-", "_": "-", " ": "", "\u3000": "",
    "（": "(", "）": ")", "【": "[", "】": "]", "：": ":", "；": ";",
})

_NOISE_PATTERNS = [
    r"报名(已)?(开启|启动|开始|啦)?",
    r"完整介绍及线上报名流程指南",
    r"报名通知",
    r"参赛通知",
    r"征集通知",
    r"通知",
    r"指南",
    r"详情",
]


def normalize_competition_name(name: str | None) -> str:
    if not name:
        return ""
    text = str(name).strip().lower().translate(_PUNCT)
    text = re.sub(r"\s+", "", text)
    for pat in _NOISE_PATTERNS:
        text = re.sub(pat, "", text)
    # 公众号标题里的标点、破折号、分隔符不参与比赛实体判断。
    text = re.sub(r"[-|丨:：;；,，。.!！?？·•]+", "", text)
    return text


def competition_dedupe_key(name: str | None, deadline: str | None = None) -> str:
    normalized = normalize_competition_name(name)
    # 截止日期加入 key，避免同名年度/届次不同但名称近似时误合并。
    return f"{normalized}|{(deadline or '')[:10]}"
