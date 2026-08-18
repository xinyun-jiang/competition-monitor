# -*- coding: utf-8 -*-
"""LLM 结构化提取：从文章正文中抽出比赛的 7 个字段，输出固定 JSON。
OpenAI 兼容接口，DeepSeek / 智谱 / Moonshot 等改配置即可切换。
"""
import json
import logging
import re

from openai import OpenAI

import config

log = logging.getLogger(__name__)

PROMPT = """你是比赛信息抽取助手。下面是一篇微信公众号文章（可能已截断）。

当前日期：{today}

任务：判断这篇文章是否是一个仍可报名/仍可提交作品的比赛、大赛、竞赛或挑战赛。
- 只接受与以下方向至少一个相关的比赛：智能体、电池、AI、储能、寿命预测。
- 如果没有明确的报名截止日期或作品提交截止日期，仍可判定为 true，但必须让 deadline 为 null。
- 截止日期早于当前日期，必须判定为 false。
- 普通征集、论坛、会议、培训、展会、项目申报、招聘、获奖公示不属于比赛，判定为 false。
- 如果不是，只返回 JSON：{{"is_competition": false}}
- 如果是，返回如下 JSON（不要输出任何其他内容）：
{{"is_competition": true,
  "name": "比赛全称",
  "level": "国际级/国家级/省级/市级/区县级/行业级/校级/不确定，根据主办方和赛事范围推断",
  "level_basis": "级别判断依据，例如主办单位、赛区范围、官方名称；拿不准填 null",
  "register_start": "报名开始时间，YYYY-MM-DD 或 null",
  "deadline": "报名截止或作品提交截止时间，YYYY-MM-DD 或 null",
  "participant_type": "大学生/企业/科研团队/个人/混合/不确定",
  "keywords": "比赛相关关键词，3-8个，用中文逗号分隔，例如 SOH、新能源、人工智能；没有明确关键词填 null",
  "eligibility": "参赛对象与具体要求，一句话概括，例如高校学生、初创企业、团队人数、地区限制等",
  "award_type": "奖金/荣誉证书/项目资助/落地孵化/资源对接/混合/不确定",
  "award_amount": "奖金金额或资助额度，例如 一等奖10万元、总奖金100万元；没有明确金额填 null",
  "awards": "奖项设置，一句话概括",
  "summary": "100字以内的比赛内容简介"}}

要求：
1. 文中只有相对时间（如"8月15日前"）时，结合文章发布时间 {publish_time} 推算为 YYYY-MM-DD；
2. 已经结束、获奖公示、赛后报道、会议/论坛招商、纯新闻报道，返回 {{"is_competition": false}}；没有截止日期的真实比赛可以保留。
3. 级别判断优先看主办单位和赛区范围：国家部委/全国性组织一般为国家级，省级部门为省级，市级部门为市级；只有单校内部活动为校级；企业单独主办但面向全国可填行业级或不确定，并在 level_basis 说明；
4. 关键词只提取与智能体、电池、AI、储能、寿命预测相关的方向；
5. 参赛者条件要明确区分大学生、企业、科研团队、个人或混合；
6. 奖项要区分是奖金、证书、项目资助、孵化/落地支持、资源对接，尽量提取金额；
7. 拿不准的字段填 null，绝对不要编造；
8. 只返回 JSON。

文章标题：{title}
文章发布时间：{publish_time}
文章来源公众号：{account}
文章正文：
{content}"""


def extract(article: dict) -> dict | None:
    """提取比赛信息。返回解析后的 dict；调用失败返回 None。"""
    if not config.LLM_API_KEY:
        raise RuntimeError("未配置 LLM_API_KEY（环境变量）")

    client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    prompt = PROMPT.format(
        today=config.TODAY,
        publish_time=article.get("publish_time") or "未知",
        title=article.get("title", ""),
        account=article.get("account", ""),
        content=article.get("content", "")[:config.LLM_MAX_CHARS],
    )
    try:
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        text = resp.choices[0].message.content.strip()
    except Exception as e:
        log.error("LLM 调用失败: %s", e)
        return None

    # 兜底：模型偶尔会在 JSON 外包裹 ```json 代码块
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.error("LLM 输出不是合法 JSON: %s", text[:200])
        return None
