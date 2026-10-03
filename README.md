# Twitter Auto

一个面向 AI x Crypto 自媒体账号的自动运营 Agent。

它会优先从 Reddit RSS 抓取 AI x Crypto 社区内容，筛掉低价值内容，按「AI x Crypto 交叉度、讨论热度、新鲜度、可二创程度」评分，生成中文 X/Twitter 草稿，并通过 Telegram 请求你审批。只有你批准后，系统才会调用 X API 发布。

## 当前 MVP 做什么

- 默认抓取 Reddit RSS；也可以切换到 Google News、AI/Crypto 新闻 RSS、Hacker News 和技术博客。
- 过滤 stickied、NSFW 和明显低质量关键词。
- 给帖子打分并说明入选原因。
- 生成三种内容素材：
  - 中文短推草稿
  - thread 大纲
  - 评论区互动问题
- 如果配置了 DeepSeek，会先按账号风格做中文二创。
- 发布前用本地 humanizer 去掉明显 AI 写作痕迹。
- 把草稿写入 SQLite 内容队列。
- 通过 Telegram 发送审批按钮。
- 只发布 approved 状态的内容。
- 记录每次 X 发布调用，控制每日调用上限。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

运行默认抓取：

```bash
twitter-auto
```

还没配置 Reddit 凭证时，可以先用内置样例验证完整流程：

```bash
twitter-auto --sample
```

或者直接用 Python 模块运行：

```bash
python -m twitter_auto.cli
```

生成结果会写入：

```text
reports/latest.md
```

## 自动化命令

采集内容并写入审批队列，默认使用 Reddit RSS：

```bash
twitter-auto collect --limit 20 --top 10
```

只使用 Reddit RSS：

```bash
twitter-auto collect --source reddit-rss --limit 20 --top 10
```

使用非 Reddit 的 RSS 多源：

```bash
twitter-auto collect --source rss --limit 20 --top 10
```

RSS 加上 Reddit RSS 备用源：

```bash
twitter-auto collect --source rss --include-reddit-rss --limit 20 --top 10
```

以后 Reddit API key 准备好后，可以只使用 Reddit：

```bash
twitter-auto collect --source reddit --sort rising --limit 20 --top 10
```

也可以 RSS 和 Reddit API 一起用：

```bash
twitter-auto collect --source both --limit 20 --top 10
```

发送 Telegram 审批提醒：

```bash
twitter-auto notify --limit 5
```

没有配置 Telegram 时，可以先 dry-run：

```bash
twitter-auto notify --limit 5 --dry-run
```

处理 Telegram 按钮回调：

```bash
twitter-auto poll-telegram
```

Telegram 审批时也支持文本命令：

```text
/edit 文章ID 新文案
/approve 文章ID
/reject 文章ID
```

例如：

```text
/edit 12 这条我改成自己的观察……
```

本地手动批准待审批内容，适合测试：

```bash
twitter-auto approve --all-pending
```

发布已批准内容。默认是 dry-run，不调用 X API：

```bash
twitter-auto publish-approved --limit 3
```

真实发布到 X，需要显式加 `--live`：

```bash
twitter-auto publish-approved --limit 3 --live
```

查看今天 X 发布调用额度：

```bash
twitter-auto budget
```

## 常用命令

抓取 Reddit RSS 内容：

```bash
twitter-auto --source reddit-rss --limit 20 --top 10
```

降低筛选门槛，看到更多候选：

```bash
twitter-auto --min-score 2.5 --top 20
```

输出到指定文件：

```bash
twitter-auto --source rss --output reports/ai-crypto-today.md
```

## 配置监控范围

编辑 `config/feeds.json`：

- `google_news_queries`: Google News 搜索词
- `feeds`: AI/Crypto/Hacker News 等 RSS 源
- `reddit_rss`: 可选 Reddit RSS 备用源

编辑 `config/subreddits.json`：

- `subreddits`: Reddit API 模式下要监控的社区
- `keywords`: 你关心的 AI x Crypto 关键词
- `blocked_terms`: 明显低质量或不想要的内容

## 内容源说明

当前默认使用 `config/feeds.json` 里的 `reddit_rss` 配置。

也可以切换到非 Reddit RSS 多源，包括：

- Google News queries
- Crypto 新闻 RSS
- AI 技术博客
- Hacker News
- Reddit RSS：默认来源，也可以编辑 `reddit_rss` 增删 subreddit

你可以直接编辑 `config/feeds.json` 增删来源。

## Reddit API 说明

Reddit API 现在是备选方案，不再阻塞主流程。

- 默认 `--source reddit-rss` 不需要 Reddit API key。
- `--source rss` 使用非 Reddit RSS 多源。
- `--source reddit` 使用 Reddit API / JSON。
- `--source both` 同时使用 RSS 和 Reddit。

如果后续拿到 Reddit API key，再把凭证写入 `.env` 即可。

## X/Twitter API 说明

X API 只用于发布你批准的内容，不用于读取数据、统计表现、搜索趋势或轮询。

需要在 `.env` 里配置：

```env
X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
X_DAILY_CALL_LIMIT=10
```

安全策略：

- 未加 `--live` 时不会调用真实 X API。
- 只有 `approved` 状态会被发布。
- 发布前会再次执行 humanizer，旧草稿也会被处理。
- 每次真实发布前会检查每日调用上限。
- 每次真实发布调用都会写入本地日志。

## DeepSeek 二创

DeepSeek 是可选层。配置后，流程会变成：

```text
RSS 抓取
→ 模板初稿
→ DeepSeek 按账号风格二创
→ 本地 humanizer 兜底
→ Telegram 审批
→ X 发布
```

`.env` 配置：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

没有配置 `DEEPSEEK_API_KEY` 时，系统会自动回退到本地 humanizer。

调试时可以禁用 DeepSeek：

```bash
twitter-auto collect --source rss --no-llm
```

## Telegram Bot 设置

1. 在 Telegram 找 `@BotFather`。
2. 发送 `/newbot` 创建 bot，拿到 `TELEGRAM_BOT_TOKEN`。
3. 给 bot 发一条消息。
4. 获取你的 chat id 后填入 `.env`：

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

可以用下面命令查看 updates，里面会包含 chat id：

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates"
```

## VPS 部署

在海外 VPS 上安装并运行：

```bash
git clone <your-repo-url> twitter-auto
cd twitter-auto
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

编辑 `.env` 后，先跑 dry-run：

```bash
twitter-auto collect --sample --top 3
twitter-auto notify --dry-run
twitter-auto approve --all-pending
twitter-auto publish-approved
```

cron 示例：

```cron
0 9 * * * cd /opt/twitter-auto && . .venv/bin/activate && twitter-auto collect --sort rising --limit 20 --top 10
5 9 * * * cd /opt/twitter-auto && . .venv/bin/activate && twitter-auto notify --limit 5
*/2 * * * * cd /opt/twitter-auto && . .venv/bin/activate && twitter-auto poll-telegram
*/5 * * * * cd /opt/twitter-auto && . .venv/bin/activate && twitter-auto publish-approved --limit 1 --live
```

建议先把最后一行的 `--live` 去掉，确认 Telegram 审批流程跑通后再开启真实发布。

## 建议的日常流程

1. VPS 每天自动运行 `collect --source reddit-rss`。
2. Telegram 收到候选草稿。
3. 你点击 Approve / Reject / Edit Later。
4. 系统只发布 Approved 内容。
5. X 后台表现由你人工查看，再手动调整关键词和策略。
