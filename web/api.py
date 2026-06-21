import asyncio
import uuid
import json
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from loguru import logger
from src.config import Config
from src.ai.provider import list_provider_names, provider_supports_image
from src.content.sanitize import sanitize_article_html
from src.pipeline import ArticleGenerationPipeline
from src.db.models import get_session, Article, LogLine
from web.schemas import (
    GenerateRequest, GenerateResponse, TaskStatus,
    ArticleItem, ArticleDetail, ModelInfo, PublishResponse, UploadRequest,
)

router = APIRouter(prefix="/api")

log_buffer = deque(maxlen=500)
log_lock = threading.Lock()
log_event = threading.Event()

# 持久化日志引擎（懒加载，复用 articles.db，独立于 get_session 的每次重建）
_log_engine = None
_LogSession = None


def _get_log_session():
    global _log_engine, _LogSession
    if _log_engine is None:
        db_path = Config().get("database", "path", default="data/articles.db") or "data/articles.db"
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _log_engine = create_engine(
            f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
        )
        LogLine.__table__.create(_log_engine, checkfirst=True)
        _LogSession = sessionmaker(bind=_log_engine)
    return _LogSession()


def _broadcast(entry: dict):
    with log_lock:
        log_buffer.append(entry)
    # 同步落库，保证 Web UI 可回滚查看（重启不丢失）
    try:
        session = _get_log_session()
        session.add(LogLine(
            level=entry.get("level", "INFO"),
            message=entry.get("message", ""),
            module=entry.get("module", ""),
        ))
        session.commit()
        session.close()
    except Exception:
        pass
    log_event.set()


class LogIntercept:
    def __init__(self, original):
        self._original = original
        self._buf = ""

    def write(self, s):
        self._original.write(s)
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            self._parse_and_broadcast(line)

    def _parse_and_broadcast(self, line):
        parts = line.split("|")
        if len(parts) >= 3:
            time_part = parts[0].strip().split()[-1] if " " in parts[0] else parts[0].strip()
            level_part = parts[1].strip()
            msg_part = " | ".join(parts[2:]).strip()
        else:
            time_part = datetime.now().strftime("%H:%M:%S")
            level_part = "INFO"
            msg_part = line
        _broadcast({"time": time_part, "level": level_part, "message": msg_part})

    def flush(self):
        self._original.flush()


_interceptor = LogIntercept(sys.stderr)
logger.remove()
logger.add(sys.stderr, format="{time:HH:mm:ss} | {level: <8} | {message}", level="INFO")
logger.add(_interceptor, format="{time:HH:mm:ss} | {level: <8} | {message}", level="DEBUG")

tasks: dict = {}

_AI_PROVIDER_KEYS = {"deepseek", "kimi", "minimax", "glm"}
_SECRET_KEYS = {"api_key", "app_secret"}


def _run_pipeline_sync(task_id: str, req: GenerateRequest):
    import asyncio as _aio
    loop = _aio.new_event_loop()
    _aio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_generation_task_inner(task_id, req))
    finally:
        loop.close()


async def _run_generation_task_inner(task_id: str, req: GenerateRequest):
    tasks[task_id] = {"status": "running", "progress": 10, "message": "正在抓取内容..."}
    try:
        pipeline = ArticleGenerationPipeline(model=req.model)
        tasks[task_id] = {"status": "running", "progress": 30, "message": "正在生成文章..."}
        source_type = req.source_type or "url"
        source = req.topic if source_type == "topic" else req.url
        result = await pipeline.run(
            source=source,
            source_type=source_type,
            style=req.style,
            extra_prompt=req.prompt,
            screenshot_targets=_parse_screenshot_targets(req.screenshot) if source_type == "url" else [],
            generate_images=not req.no_images,
        )
        if not result:
            tasks[task_id] = {"status": "failed", "progress": 0, "message": "文章生成失败"}
            return

        tasks[task_id] = {
            "status": "running", "progress": 80,
            "message": f"生成完成，AI味: {result['ai_score']:.2f}",
            "article_id": result["id"],
        }

        if req.publish:
            tasks[task_id]["message"] = "正在推送到微信草稿..."
            pub_ok = await pipeline.publish(result)
            if pub_ok:
                tasks[task_id] = {
                    "status": "done", "progress": 100,
                    "message": "已推送到微信草稿箱",
                    "article_id": result["id"],
                }
            else:
                tasks[task_id] = {
                    "status": "done", "progress": 100,
                    "message": "文章已生成，但推送草稿失败",
                    "article_id": result["id"],
                }
        else:
            tasks[task_id] = {
                "status": "done", "progress": 100,
                "message": "文章生成完成",
                "article_id": result["id"],
            }
    except Exception as e:
        logger.error(f"任务失败: {e}")
        tasks[task_id] = {"status": "failed", "progress": 0, "message": str(e)}


def _parse_screenshot_targets(value: str) -> list[str]:
    aliases = {"chart": "charts", "table": "tables", "image": "images"}
    result = []
    for item in (value or "").split(","):
        item = item.strip()
        if item:
            result.append(aliases.get(item, item))
    return result


@router.post("/upload")
async def upload_source(body: UploadRequest):
    """接收本地文件（base64），存到 data/uploads/，返回路径供 /generate 的 file 模式使用。"""
    import base64
    allowed = {".md", ".markdown", ".txt", ".html", ".htm"}
    suffix = Path(body.name or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"仅支持 {', '.join(sorted(allowed))}")
    try:
        raw = base64.b64decode(body.content or "")
    except Exception:
        raise HTTPException(status_code=400, detail="文件内容解码失败")
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（>5MB）")
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{uuid.uuid4().hex[:8]}-{body.name}"
    dest.write_bytes(raw)
    logger.info(f"上传源文件: {body.name} ({len(raw)} 字节)")
    return {"path": str(dest), "name": body.name, "size": len(raw)}


@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {"status": "pending", "progress": 0, "message": "等待执行..."}
    background_tasks.add_task(_run_pipeline_in_thread, task_id, req)
    return GenerateResponse(task_id=task_id, status="pending")


async def _run_pipeline_in_thread(task_id: str, req: GenerateRequest):
    await asyncio.to_thread(_run_pipeline_sync, task_id, req)


@router.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskStatus(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        message=task["message"],
        article_id=task.get("article_id"),
    )


@router.get("/articles", response_model=list[ArticleItem])
async def list_articles():
    session = get_session()
    articles = session.query(Article).order_by(Article.created_at.desc()).limit(50).all()
    result = []
    for a in articles:
        result.append(ArticleItem(
            id=a.id,
            title=a.title or "",
            status=a.status or "draft",
            ai_score=a.ai_score or 0.0,
            digest=a.digest or "",
            created_at=a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
            topic=a.topic or "",
            model=a.topic_strategy or "",
        ))
    session.close()
    return result


@router.get("/articles/{article_id}", response_model=ArticleDetail)
async def get_article(article_id: int):
    session = get_session()
    a = session.query(Article).get(article_id)
    if not a:
        session.close()
        raise HTTPException(status_code=404, detail="文章不存在")
    result = ArticleDetail(
        id=a.id,
        title=a.title or "",
        content=sanitize_article_html(a.final_content or ""),
        raw_content=a.raw_content or "",
        digest=a.digest or "",
        author=a.author or "",
        topic=a.topic or "",
        ai_score=a.ai_score or 0.0,
        status=a.status or "draft",
        media_id=a.media_id or "",
        created_at=a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
        published_at=a.published_at.strftime("%Y-%m-%d %H:%M") if a.published_at else None,
        screenshots=[],
        ai_images=[],
    )
    session.close()
    return result


@router.post("/articles/{article_id}/publish", response_model=PublishResponse)
async def publish_article(article_id: int):
    session = get_session()
    a = session.query(Article).get(article_id)
    if not a:
        session.close()
        raise HTTPException(status_code=404, detail="文章不存在")
    if a.status == "draft_created" and a.media_id:
        media_id = a.media_id
        session.close()
        return PublishResponse(success=True, message=f"已存在微信草稿: {media_id}")

    result = {
        "id": a.id,
        "title": a.title,
        "content": a.final_content,
        "digest": a.digest or "",
    }
    session.close()

    def _do_publish():
        import asyncio as _aio
        loop = _aio.new_event_loop()
        _aio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_publish_inner(article_id, result))
        finally:
            loop.close()

    return await asyncio.to_thread(_do_publish)


async def _publish_inner(article_id: int, result: dict):
    try:
        pipeline = ArticleGenerationPipeline()
        ok = await pipeline.publish(result)
        if ok:
            session2 = get_session()
            art = session2.query(Article).get(article_id)
            if art:
                art.status = "draft_created"
                session2.commit()
            session2.close()
            return PublishResponse(success=True, message="已推送到微信草稿箱")
        else:
            return PublishResponse(success=False, message="推送失败")
    except Exception as e:
        return PublishResponse(success=False, message=str(e))


@router.get("/models", response_model=list[ModelInfo])
async def list_models():
    config = Config()
    ai_config = config.ai
    current = ai_config.get("provider", "deepseek")
    result = []
    for name in list_provider_names():
        pc = ai_config.get(name, {})
        result.append(ModelInfo(
            name=name,
            model=pc.get("model", ""),
            has_key=bool(pc.get("api_key")),
            supports_image=provider_supports_image(name),
            is_current=(name == current),
        ))
    logger.debug(f"模型列表请求，当前: {current}")
    return result


@router.get("/settings")
async def get_settings():
    config = Config()
    ai_config = config.ai
    wechat_config = config.wechat
    return {
        "ai": {
            "provider": ai_config.get("provider", "deepseek"),
            "deepseek": _safe_config_section(ai_config.get("deepseek", {})),
            "kimi": _safe_config_section(ai_config.get("kimi", {})),
            "minimax": _safe_config_section(ai_config.get("minimax", {})),
            "glm": _safe_config_section(ai_config.get("glm", {})),
            "temperature": ai_config.get("temperature", 0.85),
            "max_tokens": ai_config.get("max_tokens", 4000),
        },
        "wechat": {
            "app_id": wechat_config.get("app_id", ""),
            "author": wechat_config.get("author", ""),
            "default_thumb_media_id": wechat_config.get("default_thumb_media_id", ""),
        },
        "content": {
            "min_length": config.get("content", "min_length", default=1500),
            "max_length": config.get("content", "max_length", default=2500),
            "humanize_rounds": config.get("content", "humanize_rounds", default=2),
        },
    }


@router.post("/settings")
async def update_settings(body: dict):
    import yaml
    from pathlib import Path
    config_path = Path(__file__).parent.parent / "config" / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    _apply_settings_update(data, body)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    Config().load()
    return {"success": True, "message": "配置已保存"}


def _safe_config_section(section: dict) -> dict:
    result = dict(section or {})
    for key in _SECRET_KEYS:
        if key in result:
            result[f"{key}_set"] = bool(result.get(key))
            result[key] = ""
    return result


def _apply_settings_update(data: dict, body: dict) -> None:
    if "ai" in body:
        data.setdefault("ai", {})
        for key, value in body["ai"].items():
            if key in _AI_PROVIDER_KEYS and isinstance(value, dict):
                target = data["ai"].setdefault(key, {})
                _merge_public_config(target, value)
            else:
                data["ai"][key] = value
    if "wechat" in body:
        data.setdefault("wechat", {})
        for key, value in body["wechat"].items():
            if key in data["wechat"]:
                if key in _SECRET_KEYS and _is_blank_secret(value):
                    continue
                data["wechat"][key] = value
    if "content" in body:
        data.setdefault("content", {})
        for key, value in body["content"].items():
            if key in data["content"]:
                data["content"][key] = value


def _merge_public_config(target: dict, incoming: dict) -> None:
    for key, value in incoming.items():
        if key.endswith("_set"):
            continue
        if key in _SECRET_KEYS and _is_blank_secret(value):
            continue
        target[key] = value


def _is_blank_secret(value) -> bool:
    return value is None or value == ""


@router.get("/logs")
async def get_logs():
    # 读取持久化历史（重启后仍可回滚查看），失败时回退到内存缓冲
    try:
        session = _get_log_session()
        rows = session.query(LogLine).order_by(LogLine.id.desc()).limit(500).all()
        session.close()
        return [
            {
                "time": r.created_at.strftime("%H:%M:%S") if r.created_at else "",
                "level": r.level or "INFO",
                "message": r.message or "",
                "module": r.module or "",
            }
            for r in reversed(rows)
        ]
    except Exception:
        with log_lock:
            return list(log_buffer)


@router.get("/logs/stream")
async def stream_logs():
    async def event_generator():
        sent = 0
        while True:
            with log_lock:
                current = list(log_buffer)
            for entry in current[sent:]:
                yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
            sent = len(current)
            log_event.clear()
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
