# 比赛信息监控后端

这是一个纯后端、无人值守运行的比赛信息爬虫。它只关注以下 5 个方向：

- 智能体
- 电池
- AI
- 储能
- 寿命预测

系统只保留比赛、大赛、竞赛、挑战赛相关信息。搜索使用百度千帆，信息提取使用智谱。已过报名截止日期的信息会被过滤；没有明确截止日期的真实比赛可以保留，但会标记为“未明确（需人工核实）”。

## 当前抓取流程

```text
搜索来源
  ↓
候选结果筛选：目标关键词 + 比赛词 + 报名语义
  ↓
候选队列去重
  ↓
抓取公众号或普通网页正文，并保存本地快照
  ↓
正文筛选：目标关键词 + 比赛词 + 报名语义
  ↓
LLM 判断是否是真正的比赛并提取字段
  ↓
解析报名截止日期
  ├── 有截止日期且未过期：入库，标记 confirmed
  ├── 有截止日期但已过期：丢弃
  └── 没有明确截止日期：入库，标记 unknown，推送时提醒人工核实
  ↓
SQLite 去重保存
  ↓
PushPlus 或 Server酱推送新增比赛
```

## 数据来源

默认配置：

```env
ENABLED_SOURCES=qianfan_search,seed_pages,seed_urls
```

- `seed_urls`：读取 `sources_seed_urls.txt` 中的单篇 URL；
- `seed_pages`：读取 `sources_seed_pages.txt` 中的公告列表页；
- `qianfan_search`：调用百度千帆 AI Search 搜索普通网页，默认唯一自动搜索来源；

## 下载到本地后必须修改的内容

下载或复制项目后，先复制配置模板：

```bash
cp .env.example .env
```

然后打开本地 `.env`，至少填写：

```env
LLM_API_KEY=你的智谱API密钥
QIANFAN_API_KEY=你的百度千帆API密钥
```

如果需要自动推送，还要填写以下其中一个：

```env
PUSHPLUS_TOKEN=你的PushPlus密钥
# 或
SERVERCHAN_KEY=你的Server酱密钥
```

不要把真实密钥写入 Python 代码、README、截图或公开仓库。`.env` 只保存在本地，并建议设置为仅当前用户可读。

## 配置

复制配置模板：

```bash
cp .env.example .env
```

至少配置：

```env
LLM_API_KEY=你的智谱API密钥
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_MODEL=glm-4-flash

QIANFAN_API_KEY=你的千帆搜索密钥

PUSHPLUS_TOKEN=你的PushPlus密钥
# 或使用 SERVERCHAN_KEY=你的Server酱密钥
```

不要把 `.env` 提交到公开仓库。

## 本地运行

安装依赖：

```bash
pip install -r requirements.txt
```

手动运行一轮：

```bash
python main.py
```

如果使用项目自带依赖目录：

```bash
PYTHONPATH=.python-packages python3 main.py
```

## 本地查看页面

安装 Streamlit：

```bash
pip install streamlit
```

启动查看页面：

```bash
streamlit run streamlit_app.py
```

浏览器打开命令行显示的本地地址，通常是 `http://localhost:8501`。页面直接读取 `data/monitor.db`，支持搜索、只看未过期比赛、查看详情和下载 CSV。先运行 `main.py` 抓取数据，再打开页面查看。

日志在：

```text
data/run.log
data/cron.log
```

数据库和文章快照在：

```text
data/monitor.db
data/articles/
```

## Docker 运行

```bash
docker compose build
docker compose up -d
```

查看日志：

```bash
docker compose logs -f
```

当前 Compose 只有一个 `monitor` 容器，不再提供网站、FastAPI 接口或登录系统。

## 搜索方式

百度千帆每轮同时执行单关键词和双关键词组合搜索。当前 5 个关键词会生成：

- 单关键词：`智能体 比赛 报名`、`电池 比赛 报名` 等；
- 双关键词：`智能体 电池 比赛 报名`、`AI 储能 比赛 报名` 等。

默认每轮执行 15 个查询，正好覆盖 5 个单关键词和 10 个双关键词组合。可在 `.env` 中调整：

```env
QIANFAN_MAX_QUERIES_PER_RUN=15
```

查询结果还会经过目标关键词、比赛类型和报名语义三重筛选，因此搜索词放宽不会直接导致无关内容入库。

## 关键词和筛选规则

关键词配置在 `config.py`：

```python
DOMAIN_WORDS = ["智能体", "电池", "AI", "储能", "寿命预测"]
```

候选内容必须同时具备：

1. 至少一个目标关键词；
2. 至少一个比赛词：比赛、大赛、竞赛、挑战赛；
3. 至少一个报名语义：报名、参赛、作品提交、报名截止等。

以下内容会被过滤：

- 获奖名单和结果公示；
- 收官、落幕、颁奖和赛事回顾；
- 论坛、会议、培训和展会；
- 普通新闻或与比赛无关的活动。

## 输出字段

每条比赛至少保存：

- 比赛名称；
- 报名开始时间；
- 报名截止时间；
- 截止日期状态：`confirmed` 或 `unknown`；
- 参赛对象和要求；
- 比赛方向关键词；
- 奖项和奖金；
- 比赛简介；
- 来源和原文链接；
- 本地 HTML 快照。


## 数据不会被每日运行覆盖

程序使用固定的 `data/monitor.db`，每天运行时：

- 不删除数据库；
- 不清空历史比赛；
- 不覆盖已有比赛的完整字段；
- 同一个 URL 只处理一次；
- 同名且同截止日期的比赛只保留一条；
- 新发现的比赛追加到原有数据后面；
- 文章正文快照保存在 `data/articles/`，历史快照持续保留。

如果要换电脑，只需复制整个项目目录，尤其是 `data/` 和 `.env`，不要新建空数据库替换原数据库。

## 备份

定期备份整个 `data/` 目录，尤其是：

```text
data/monitor.db
data/articles/
data/run.log
```

最简单的备份方式是复制项目文件夹到 U 盘、团队网盘或移动硬盘。

## Windows 任务计划程序

如果在个人电脑运行：

1. 打开“任务计划程序”；
2. 创建每日任务；
3. 程序选择 Python；
4. 参数填写项目绝对路径下的 `main.py`；
5. 起始位置填写项目目录；
6. 电脑必须开机、联网且不能休眠。

## 当前项目边界

本项目现在是纯后端爬虫，不再包含：

- 前端页面；
- FastAPI 接口；
- 用户登录和注册；
- 多用户权限；
- 网站管理后台。

团队成员通过推送消息获取结果，管理员通过项目文件、日志和数据库进行维护。
