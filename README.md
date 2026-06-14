# auto-wechat-official

微信公众号自动化发布系统 — 从URL/文件自动生成公众号文章，支持多模型切换和关键区域截图。

## 安装

```bash
pip install -r requirements.txt
playwright install chromium
```

## 配置

首次使用前，复制模板并填写真实凭据（`config.yaml` 含密钥，已被 gitignore，请勿提交）：

```bash
cp config/config.example.yaml config/config.yaml
```

编辑 `config/config.yaml`：

### 必填配置

```yaml
wechat:
  app_id: "你的公众号AppID"
  app_secret: "你的公众号AppSecret"
  author: "作者名"
  default_thumb_media_id: "封面图素材ID"

ai:
  provider: "deepseek"          # 默认模型
  deepseek:
    api_key: "sk-xxx"
    base_url: "https://api.deepseek.com"
    model: "deepseek-chat"
```

### 可选模型配置

```yaml
ai:
  kimi:
    api_key: "sk-xxx"           # Moonshot API Key
    base_url: "https://api.moonshot.cn/v1"
    model: "moonshot-v1-8k"
  minimax:
    api_key: "xxx"              # MiniMax API Key
    base_url: "https://api.minimax.chat"
    model: "abab6.5s-chat"
    image_model: "image-01"     # 用于AI配图生成
```

### 微信公众号后台设置

在 mp.weixin.qq.com → 开发 → 基本配置：
- 将服务器公网IP加入IP白名单
- 获取 AppID 和 AppSecret

## 使用方法

### 从URL生成文章

```bash
# 从GitHub仓库生成
python cli.py from-url https://github.com/user/repo

# 从技术文章生成
python cli.py from-url https://36kr.com/p/123456

# 从任意网页生成
python cli.py from-url https://example.com/article
```

### 从本地文件生成

```bash
python cli.py from-file ./readme.md
python cli.py from-file ./doc.html
python cli.py from-file ./notes.txt
```

### 指定模型

```bash
# 使用Kimi
python cli.py from-url https://... --model kimi

# 使用MiniMax
python cli.py from-url https://... --model minimax

# 使用DeepSeek（默认）
python cli.py from-url https://... --model deepseek
```

### 截图功能

```bash
# 截取代码块
python cli.py from-url https://... --screenshot code

# 截取代码块+图表+表格
python cli.py from-url https://... --screenshot code,charts,tables

# 截取所有关键区域
python cli.py from-url https://... --screenshot all
```

截图类型：
- `code` — 自动识别页面中的代码块并截取
- `charts` — 截取图表（canvas、svg等）
- `tables` — 截取表格
- `images` — 截取文章中的图片
- `all` — 以上全部 + 全页面长截图

### 文章风格

```bash
python cli.py from-url https://... --style tech_explanation   # 科技解读（默认）
python cli.py from-url https://... --style product_review      # 产品测评
python cli.py from-url https://... --style industry_analysis   # 行业分析
python cli.py from-url https://... --style tutorial            # 教程干货
```

### 自定义提示词

```bash
python cli.py from-url https://... --prompt "写成入门教程风格，面向初学者"
python cli.py from-url https://... --prompt "重点分析性能对比，加入benchmark数据"
```

### AI配图

默认会尝试生成AI配图（仅MiniMax支持）。跳过配图：

```bash
python cli.py from-url https://... --no-images
```

### 发布到微信

```bash
# 生成后直接创建草稿
python cli.py from-url https://... --publish

# 生成后手动选择是否发布
python cli.py from-url https://...
# 然后用 main.py publish <id> 发布
```

### 其他命令

```bash
# 查看可用模型配置
python cli.py models

# 微信扫码登录（首次使用）
python cli.py login

# 查看文章列表
python cli.py list

# 采集热点话题
python cli.py topics
```

## 完整示例

```bash
# 1. 配置API Key
# 编辑 config/config.yaml 填入 deepseek/kimi/minimax 的 api_key

# 2. 首次登录微信
python cli.py login

# 3. 从GitHub仓库生成文章，使用Kimi模型，截取代码块
python cli.py from-url https://github.com/langchain-ai/langchain \
  --model kimi \
  --screenshot code \
  --style tutorial \
  --prompt "写成LangChain入门指南"

# 4. 从技术文章生成，使用MiniMax（带AI配图）
python cli.py from-url https://36kr.com/p/123456 \
  --model minimax \
  --screenshot all \
  --publish

# 5. 从本地markdown生成
python cli.py from-file ./project-readme.md \
  --style tech_explanation \
  -o output.html
```

## 模型对比

| 模型 | 文本生成 | 图片生成 | 特点 |
|------|---------|---------|------|
| DeepSeek | ✅ | ❌ | 性价比高，中文效果好 |
| Kimi | ✅ | ❌ | 长文本理解强 |
| MiniMax | ✅ | ✅ | 支持AI配图生成 |

## 项目结构

```
auto-wechat-official/
├── cli.py                  # CLI入口（新）
├── main.py                 # 原有入口（保留兼容）
├── config/
│   ├── config.yaml         # 配置文件
│   └── prompts/            # Prompt模板
├── src/
│   ├── ai/                 # AI模型抽象层（新）
│   │   ├── provider.py     # 基类+工厂
│   │   ├── deepseek.py     # DeepSeek
│   │   ├── kimi.py         # Kimi/Moonshot
│   │   └── minimax.py      # MiniMax（含图片生成）
│   ├── content/
│   │   ├── fetcher.py      # 内容抓取器（新）
│   │   ├── screenshot.py   # 关键区域截图（新）
│   │   ├── humanizer.py    # 去AI味处理
│   │   ├── generator.py    # 原有生成器（保留兼容）
│   │   ├── hot_topics.py   # 热点采集
│   │   └── template.py     # HTML模板
│   ├── pipeline.py         # 新版流水线（新）
│   ├── wechat/             # 微信API+浏览器发布
│   ├── db/                 # 数据库模型
│   └── scheduler/          # 定时调度
└── data/                   # 运行时数据
```
