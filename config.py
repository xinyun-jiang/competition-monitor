# -*- coding: utf-8 -*-
"""全局配置：关键词、LLM、推送、存储路径。
API key 等敏感项通过环境变量注入，不要写死在代码里。
"""
import os
import time
from dotenv import load_dotenv
load_dotenv()

TODAY = os.getenv("TODAY", time.strftime("%Y-%m-%d"))

# ---------------- 搜索关键词 ----------------
# 只监控这 5 个方向，并且搜索时必须带比赛报名语义。
DOMAIN_WORDS = ["智能体", "电池", "AI", "储能", "寿命预测"]
EVENT_WORDS = ["比赛 报名", "大赛 报名", "竞赛 报名", "挑战赛 报名"]
STANDALONE_COMPETITION_QUERIES = [
    "智能体 比赛 报名", "电池 比赛 报名", "AI 比赛 报名",
    "储能 比赛 报名", "寿命预测 比赛 报名",
]

# 正文必须同时命中目标关键词、明确比赛类型和报名语义。
FILTER_DOMAIN = DOMAIN_WORDS
FILTER_EVENT = ["比赛", "大赛", "竞赛", "挑战赛"]
FILTER_INTENT = ["报名", "参赛", "作品提交", "报名时间", "报名截止", "截止时间", "报名通道"]
EXCLUDE_WORDS = ["获奖名单", "获奖结果", "结果公示", "收官", "落幕", "圆满结束", "赛事回顾", "复盘", "颁奖典礼"]

# 搜狗曾支持 tsn 时间参数，但当前带 tsn 会被重定向到首页，导致 0 结果。
# 不在搜索词中硬编码年份；近期/有效性统一按文章发布时间和 LLM 提取的截止日期过滤。
MAX_ARTICLE_AGE_DAYS = int(os.getenv("MAX_ARTICLE_AGE_DAYS", "3650"))
# 有截止日期时必须未过期；没有明确截止日期的比赛允许入库，但会标注待核实。
REQUIRE_VALID_DEADLINE = True
DEADLINE_GRACE_DAYS = int(os.getenv("DEADLINE_GRACE_DAYS", "0"))
MAX_RESULTS_PER_RUN = int(os.getenv("MAX_RESULTS_PER_RUN", "40"))
MAX_RESOLVE_PER_RUN = int(os.getenv("MAX_RESOLVE_PER_RUN", "12"))
CANDIDATE_TTL_HOURS = int(os.getenv("CANDIDATE_TTL_HOURS", "36"))


# ---------------- 多来源发现 ----------------
ENABLED_SOURCES = [s.strip() for s in os.getenv("ENABLED_SOURCES", "qianfan_search").split(",") if s.strip()]
SEED_URLS_FILE = os.getenv("SEED_URLS_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources_seed_urls.txt"))
SEED_PAGES_FILE = os.getenv("SEED_PAGES_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources_seed_pages.txt"))
QIANFAN_API_KEY = os.getenv("QIANFAN_API_KEY", "")
QIANFAN_MAX_QUERIES_PER_RUN = int(os.getenv("QIANFAN_MAX_QUERIES_PER_RUN", "15"))
QIANFAN_RESULTS_PER_QUERY = int(os.getenv("QIANFAN_RESULTS_PER_QUERY", "5"))
QIANFAN_RECENCY = os.getenv("QIANFAN_RECENCY", "month")  # week/month/semiyear/year

# ---------------- 搜狗搜索 ----------------

# ---------------- LLM（OpenAI 兼容接口） ----------------
# 默认使用智谱 GLM；搜索默认使用百度千帆
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "glm-4-flash")
LLM_MAX_CHARS = 6000       # 送给 LLM 的正文最大字符数（比赛信息一般在文章前半部分）

# ---------------- 推送（Server酱 / PushPlus） ----------------
SERVERCHAN_KEY = os.getenv("SERVERCHAN_KEY", "")
PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN", "")

# ---------------- 存储 ----------------
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "monitor.db")
SNAPSHOT_DIR = os.path.join(DATA_DIR, "articles")

