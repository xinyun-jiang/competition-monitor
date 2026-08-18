# 比赛信息监控

自动抓取并展示 **智能体、电池、AI、储能、寿命预测** 相关比赛信息的在线网站。

数据每日自动更新，无需手动运行代码，打开网页即可查看最新比赛信息。

---

## 在线访问

🔗 **网站地址**：`https://competitionmonitor.streamlit.app`

> 部署在 [Streamlit Cloud](https://streamlit.io/cloud) 上

---

## 功能特点

- **自动抓取**：每日自动从百度千帆搜索、指定公告页、指定 URL 抓取比赛信息
- **智能筛选**：通过 LLM 判断是否为真实比赛，自动过滤获奖名单、论坛、培训等无关内容
- **截止日期识别**：自动提取报名截止日期，已过期的自动丢弃，未明确的标注提醒
- **历史累积**：数据不会每日覆盖，新发现的比赛自动追加到已有数据库
- **零成本部署**：GitHub Actions 定时任务 + Streamlit Cloud 免费托管，无需服务器

---

## 关注方向

当前监控以下 5 个关键词的比赛信息：

- 智能体
- 电池
- AI
- 储能
- 寿命预测

系统只保留包含**比赛/大赛/竞赛/挑战赛**字样，且带有**报名/参赛/作品提交**等语义的真实赛事。

---

## 数据来源

| 来源 | 说明 |
|------|------|
| `qianfan_search` | 百度千帆 AI 搜索，自动生成关键词组合查询 |
| `seed_pages` | 读取 `sources_seed_pages.txt` 中的公告列表页 |
| `seed_urls` | 读取 `sources_seed_urls.txt` 中的单篇 URL |

搜索策略：每轮执行单关键词和双关键词组合搜索，覆盖 5 个单关键词 + 10 个双关键词组合，共 15 个查询。

---

## 自动更新机制

项目使用 **GitHub Actions** 每天自动运行两次：

| 时间（北京时间） | 说明 |
|----------------|------|
| 08:00 | 早间自动抓取 |
| 20:00 | 晚间自动抓取 |

运行流程：

```
GitHub Actions 触发
  ↓
安装 Python 依赖
  ↓
从 GitHub Secrets 读取 API 密钥，生成 .env
  ↓
运行 main.py 抓取数据
  ↓
将更新后的数据提交回仓库
  ↓
Streamlit Cloud 自动同步最新数据
  ↓
网站展示最新比赛信息
```

---

## 项目结构

```
.
├── .github/workflows/daily.yml   # GitHub Actions 定时任务配置
├── data/
│   ├── monitor.db                # SQLite 数据库（比赛信息）
│   ├── articles/                 # 网页正文快照
│   └── run.log                   # 运行日志
├── sources/                      # 源文件处理模块
├── article.py                    # 文章抓取与解析
├── config.py                     # 关键词和配置
├── db.py                         # 数据库操作
├── extract.py                    # 信息提取
├── main.py                       # 主程序入口
├── normalize.py                  # 数据标准化
├── notify.py                     # 消息推送
├── streamlit.py                  # 网站前端（Streamlit）
├── requirements.txt              # Python 依赖
├── sources_seed_pages.txt        # 公告列表页种子
├── sources_seed_urls.txt         # 单篇 URL 种子
└── README.md                     # 本文件
```

---

## 输出字段

每条比赛记录包含：

- 比赛名称
- 报名开始时间
- 报名截止时间（`confirmed` / `unknown`）
- 参赛对象和要求
- 比赛方向关键词
- 奖项和奖金
- 比赛简介
- 来源和原文链接
- 本地 HTML 快照

---

## 本地开发（可选）

如需本地调试：

```bash
# 1. 克隆仓库
git clone https://github.com/xinyunj933-hash/competition-monitor.git
cd competition-monitor

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
# 在项目根目录创建 .env 文件，填入你的 API 密钥
# 参考 .env.example（如需）

# 4. 手动运行抓取
python main.py

# 5. 本地预览网站
streamlit run streamlit.py
```

---

## 技术栈

- **爬虫与数据处理**：Python + SQLite
- **搜索接口**：百度千帆 AI Search
- **信息提取**：智谱 GLM-4-Flash
- **定时任务**：GitHub Actions
- **前端展示**：Streamlit
- **托管平台**：Streamlit Cloud（免费）

---

## 数据备份

数据库和快照文件位于 `data/` 目录：

```
data/monitor.db      # 比赛数据库
data/articles/      # 网页快照
data/run.log        # 运行日志
```

GitHub Actions 每次运行后会自动将更新提交回仓库，因此数据天然有 Git 版本记录。如需额外备份，直接下载 `data/` 文件夹即可。

---

## 部署说明

本项目采用 **零成本自动化部署** 架构：

1. **代码托管**：GitHub（免费）
2. **定时运行**：GitHub Actions（免费额度足够每日两次运行）
3. **敏感信息**：存储在 GitHub Secrets（API Key 不上传代码）
4. **网站托管**：Streamlit Cloud（免费，自动同步 GitHub 仓库）

如需重新部署：

1. Fork 本仓库
2. 在仓库 Settings → Secrets 中配置你的 API 密钥
3. 在 [Streamlit Cloud](https://streamlit.io/cloud) 导入仓库，主文件路径填 `streamlit.py`
4. 网站自动上线，数据每日自动更新

---

## 许可证

本项目仅供学习交流使用。
