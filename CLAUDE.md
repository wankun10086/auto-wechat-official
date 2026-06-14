# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

微信公众号 (WeChat Official Account) automated publishing system. Ingest a source (URL, GitHub repo, or local file) → generate an article with an LLM → strip "AI flavor" → optionally screenshot key regions / generate images → wrap in styled HTML → persist to SQLite → optionally create a WeChat draft. Ships a CLI, a FastAPI + React web UI, and an APScheduler cron mode.

## Commands

```bash
# Setup
pip install -r requirements.txt
playwright install chromium                      # required for screenshots + browser publish
cd web/frontend && npm install && npm run build  # build the web UI

# CLI (primary) — src/pipeline.ArticleGenerationPipeline (source-driven)
python cli.py from-url <url> [--model deepseek|kimi|minimax] \
    [--style tech_explanation|tutorial|industry_analysis|product_review] \
    [--screenshot code,charts,tables,images,all] [--prompt "..."] [--no-images] [--publish] [-o out.html]
python cli.py from-file ./readme.md [same flags, except --screenshot is ignored]
python cli.py login | list | topics | models

# Web UI (FastAPI serves React build from web/frontend/dist)
python -m web.server 8000        # or run start.bat on Windows

# Legacy / topic-driven entry — src/scheduler/job_runner.ArticlePipeline
python main.py generate | publish [id] | full [strategy] | login | scheduler | topics | list

# Scheduler
python -m src.scheduler.job_runner start | run [strategy]
```

No test suite or linter is configured.

## Configuration

`config/config.yaml` is loaded by the `Config` singleton (`src/config.py`) and **holds secrets** (WeChat `app_secret`, LLM API keys). It is gitignored — copy `config/config.example.yaml` → `config/config.yaml` and fill in real values. `config.load()` must run once at startup (every entry point does it); `Config()` returns the same singleton, so modules read config lazily at call time. Prompt templates live in `config/prompts/` and load by name via `load_prompt(name)` → `config/prompts/<name>.yaml` (`tech_article.yaml` drives generation/humanizer; `style_guide.yaml` holds the inline `<style>` and per-style structure templates).

## Architecture

**Two entry points drive two different pipelines** — distinct classes that look similar; do not conflate them:
- `cli.py` and `web/api.py` → `src/pipeline.py::ArticleGenerationPipeline` — **source-driven** (a URL/file is given). Current/recommended path.
- `main.py` and `src/scheduler/job_runner.py` → `src/scheduler/job_runner.py::ArticlePipeline` — **topic-driven** (picks a hot topic, fetches material, generates). Used by the scheduler.

Both flow: fetch → generate → humanize → wrap HTML → save an `Article` row → optionally `WeChatAPIClient.create_draft`.

**AI provider abstraction** (`src/ai/provider.py`): `BaseProvider` + `get_provider(name)` factory, selected from `ai.provider` or `--model`. DeepSeek and Kimi use the OpenAI SDK against OpenAI-compatible base URLs; **MiniMax is the exception** — it talks the Anthropic-style `/v1/messages` API over httpx (`src/ai/minimax.py`). `generate_image()` is on the interface but every provider currently raises `NotImplementedError`, so AI image generation is effectively disabled even though `--no-images` defaults to attempting it.

**WeChat publishing has two complementary paths**:
- `src/wechat/api_client.py::WeChatAPIClient` — official API: `access_token` with auto-refresh, material/thumb upload, draft create/list/update/delete. Truncates `title`/`author`/`digest` to WeChat byte limits and strips `<style>` blocks before draft creation.
- `src/wechat/publisher.py::WeChatPublisher` — Playwright browser automation for actions the official API restricts: QR login (cookies persisted to `data/wechat_cookies.json`), mass-send (群发), and scheduled send. Randomized delays + failure screenshots aid anti-bot resilience.

**Content pipeline details**:
- `src/content/fetcher.py` — `ContentFetcher` distinguishes GitHub repos (GitHub API: repo meta + README + file tree) from generic web (BeautifulSoup extraction); `fetch_file()` handles local `.md/.html/.txt`.
- `src/content/screenshot.py` — `ScreenshotCapture` (Playwright) screenshots code/charts/tables/images/full-page by CSS selector, deduping by bounding box.
- `src/content/humanizer.py` — `Humanizer.full_pipeline()` runs `humanize_rounds` (config, default 4) iterations of (colloquial rewrite + emotion inject), then a de-template pass, banned-word stripping, and a heuristic `ai_score` (0–1, lower is better; based on banned words, AI-cliché regex, sentence-length variance, paragraph-opening diversity). Every prompt pass strips ```html fences.
- `src/content/template.py` — wraps final HTML with the inline style block from `style_guide.yaml`.

**Persistence**: SQLAlchemy + SQLite at `data/articles.db` (`src/db/models.py`). `get_session()` re-initializes the engine each call, so the DB and tables auto-create on first use. `Article.status` flows `draft → draft_created → published`; `HotTopic` tracks collected topics with a `used` flag; `PublishLog` records actions.

**Web layer**: `web/server.py` (FastAPI app + static frontend) + `web/api.py` (all `/api/*` routes). Generation runs in a background thread with its own event loop; loguru output is intercepted (`LogIntercept`) and streamed to the UI via SSE at `/api/logs/stream`. Task state lives in an in-memory `tasks` dict (lost on restart). Frontend is React 18 + Vite + TS in `web/frontend/`, served from `web/frontend/dist/` after `npm run build`.

### Conventions worth preserving
- ```html-fence extraction is duplicated in `generator.py`, `pipeline.py`, and `humanizer.py`.
- `data/` (cookies, screenshots, SQLite, logs) and `config/config.yaml` are gitignored.

## Coding principles (Karpathy-inspired — this project's dedicated skill)

Imported from https://github.com/multica-ai/andrej-karpathy-skills. The repo's per-project install method is to merge these into CLAUDE.md; to instead install it as a global Claude Code plugin run `/plugin marketplace add forrestchang/andrej-karpathy-skills` then `/plugin install andrej-karpathy-skills@karpathy-skills`.

1. **Think before coding.** Don't assume. State assumptions explicitly; if multiple interpretations exist, present them rather than picking silently; push back when a simpler approach exists; if something is unclear, stop, name the confusion, and ask.
2. **Simplicity first.** Minimum code that solves the problem — no speculative abstractions, no unrequested "flexibility"/"configurability," no error handling for impossible cases. If 200 lines could be 50, rewrite. Test: would a senior engineer call this overcomplicated?
3. **Surgical changes.** Touch only what the task requires; don't refactor adjacent code, reformat, or delete pre-existing dead code (mention it instead). Match existing style. Every changed line should trace directly to the request. Remove only the orphans your own changes create.
4. **Goal-driven execution.** Turn tasks into verifiable success criteria and loop until checks pass ("add validation" → "write tests for invalid inputs, then pass them"). For multi-step work, state a plan with per-step verification.

These bias toward caution over speed; use judgment for trivial tasks.

## GitHub workflow

**Commit then push as one atomic action.** After any meaningful change, commit it and push to `origin/main` directly — no separate confirmation needed. The remote and credentials are already configured (HTTPS, Git Credential Manager caches credentials, `http.sslBackend=openssl`).

**Commit action:**

1. `git add` only the files relevant to the task (don't blindly `git add -A`, to avoid sweeping in local artifacts).
2. Commit with a conventional message (see below).
3. `git push` to `origin/main` immediately — this is the default, triggered right after every commit.

**Commit message convention** — Conventional Commits, short imperative subject line, Chinese or English:

- `feat: <new capability>` — e.g. `feat: mock provider, persistent logs, test suite, UI refactor, background launch`
- `fix: <bug fix>`
- `docs: <docs only>`
- `refactor: <refactor>`
- `test: <tests>`
- `chore: <deps/build/misc>`

Multiple unrelated changes go as separate commits; an optional body separated by a blank line lists bullet-point details.

**Never commit secrets.** `config/config.yaml` and `data/` are gitignored; the tracked template is `config/config.example.yaml`. Local-only tooling/config that must NOT be committed: `.agents/` (installed skills), `.claude/settings.local.json` (machine-local permissions), `skills-lock.json`.
