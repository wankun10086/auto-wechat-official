# auto-wechat-official

微信公众号自动化创作与草稿箱系统。支持从议题、URL、GitHub 仓库或本地文件生成公众号文章，经过多轮“去模板化/去 AI 腔”处理后保存到 SQLite，并可通过微信公众号官方 API 创建草稿，由你在后台决定何时发布。

## 安装

```bash
pip install -r requirements.txt
playwright install chromium
cd web/frontend && npm install && npm run build
```

## 配置

复制配置模板并填写真实凭据：

```bash
cp config/config.example.yaml config/config.yaml
```

`config/config.yaml` 包含 API Key 和公众号密钥，已被 gitignore，不能提交。

关键配置：

```yaml
wechat:
  app_id: "your-app-id"
  app_secret: "your-app-secret"
  author: "Your Name"
  default_thumb_media_id: "your-thumb-media-id"

ai:
  provider: deepseek            # deepseek | kimi | minimax | glm
  deepseek:
    api_key: "sk-your-deepseek-key"
    base_url: https://api.deepseek.com
    model: deepseek-chat
  kimi:
    api_key: ""
    base_url: https://api.moonshot.cn/v1
    model: moonshot-v1-8k
  minimax:
    api_key: "sk-your-minimax-key"
    base_url: https://api.minimaxi.com/anthropic
    model: MiniMax-M3
    image_base_url: https://api.minimax.io
    image_model: image-01
  glm:
    api_key: "your-zhipu-api-key"
    base_url: https://open.bigmodel.cn/api/paas/v4
    model: glm-4-flash
    image_model: glm-image
    image_size: 1280x1280

research:
  search_provider: duckduckgo   # duckduckgo | bing | serper
  serper_api_key: ""
  query_suffix: "最新 解读 分析"
  material_count: 5
  image_count: 4
  download_images: true
```

`research` 配置用于议题模式：系统会按议题生成搜索 query，抓取网页素材，提取候选图片，并下载可用图片。`serper` 需要 API Key；`duckduckgo` 和 `bing` 走 HTML 搜索，稳定性取决于网络环境。

## CLI

从议题自动搜索素材并生成：

```bash
python cli.py from-topic "AI Agent 产品趋势" --model glm --style industry_analysis
python cli.py from-topic "MiniMax 新模型解读" --model minimax --publish
```

从 URL 或本地文件生成：

```bash
python cli.py from-url https://github.com/user/repo --model kimi --screenshot code,charts
python cli.py from-file ./readme.md --style tutorial
```

常用参数：

```bash
--model deepseek|kimi|minimax|glm
--style tech_explanation|tutorial|industry_analysis|product_review
--prompt "额外写作要求"
--no-images
--publish
-o out.html
```

`--publish` 的含义是创建微信公众号草稿，不会群发。草稿创建成功后，你仍然在公众号后台决定何时发布。

其他命令：

```bash
python cli.py login
python cli.py list
python cli.py topics
python cli.py models
```

## Web UI

FastAPI 会服务 React 构建产物：

```bash
python -m web.server 8000
```

Web UI 支持三种来源：议题、链接、本地文件。生成任务在后台线程中运行，日志通过 SSE 推送到页面。

## 调度器

定时任务使用 `src.scheduler.job_runner.ArticlePipeline`，现在也复用新的 `ArticleGenerationPipeline`，因此热点话题会进入同一条“议题检索 -> 生成 -> humanize -> 草稿箱”的主链路。

```bash
python -m src.scheduler.job_runner run hot_tech
python -m src.scheduler.job_runner start
```

## 图片与草稿箱

- MiniMax 和 GLM 支持 AI 配图；DeepSeek 和 Kimi 只负责文本。
- 议题模式会从检索素材中提取图片候选，并可下载后嵌入文章。
- 创建微信草稿前，本地 `<img src="...">` 会通过 `media/uploadimg` 上传并替换为微信图片 URL。
- 如果 `default_thumb_media_id` 为空，系统会尝试上传本次生成/检索到的第一张本地图片作为封面素材。
- 已经是 `http://`、`https://` 或 `data:` 的图片 URL 不会被本地上传逻辑改写。

## 架构

- `src/pipeline.py`：推荐主流水线，支持 `url | file | topic`。
- `src/content/researcher.py`：议题搜索、素材抓取、图片候选下载。
- `src/content/fetcher.py`：URL/GitHub/本地文件抓取。
- `src/content/humanizer.py`：多轮去模板化、口语化、情绪注入和 AI 腔评分。
- `src/ai/provider.py`：模型工厂，支持 DeepSeek、Kimi、MiniMax、GLM、Mock。
- `src/wechat/api_client.py`：微信公众号官方 API，负责素材图上传和草稿创建。
- `web/api.py`：Web API 与后台任务状态。
- `src/scheduler/job_runner.py`：热点/定时任务入口，复用主流水线。

## 验证

```bash
python -m pytest -q
cd web/frontend && npm run build
python cli.py from-topic --help
```

当前测试使用 mock provider，可在没有真实 LLM/微信凭据时验证主流程、议题模式、图片改写和调度器复用。
