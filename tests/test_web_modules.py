"""
Phase 3 — 网站功能模块分步测试。

每个测试对应一个用户可见的功能模块，全部通过即视为该模块门禁通过。
生成/发布用 mock provider + monkeypatch，避免触碰真实 LLM 与微信。
"""
import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
from web.server import app

client = TestClient(app)

_TMP = Path("data/.pytest_tmp")


def _make_source(name: str, text: str = "# 模块测试源\n\n这是一段用于测试的示例内容。\n") -> str:
    _TMP.mkdir(parents=True, exist_ok=True)
    p = _TMP / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def _generate_one(name: str) -> int:
    from src.pipeline import ArticleGenerationPipeline
    pipe = ArticleGenerationPipeline(model="mock")
    src = _make_source(name)
    result = asyncio.run(pipe.run(source=src, source_type="file", generate_images=False))
    assert result, "mock 流水线应产出文章"
    return result["id"]


# 1) 设置模块（仅读，不写真实 config.yaml）
def test_module_settings_read():
    from src.config import Config

    cfg = Config()
    cfg._data.setdefault("ai", {}).setdefault("deepseek", {})["api_key"] = "unit-secret-key"
    cfg._data.setdefault("wechat", {})["app_secret"] = "unit-wechat-secret"
    r = client.get("/api/settings")
    assert r.status_code == 200
    d = r.json()
    assert {"ai", "wechat", "content"} <= set(d.keys())
    assert "provider" in d["ai"]
    assert d["ai"]["deepseek"]["api_key"] == ""
    assert d["ai"]["deepseek"]["api_key_set"] is True
    assert d["wechat"]["app_secret"] == ""
    assert d["wechat"]["app_secret_set"] is True
    assert "unit-secret-key" not in json.dumps(d, ensure_ascii=False)
    assert "unit-wechat-secret" not in json.dumps(d, ensure_ascii=False)


def test_settings_update_does_not_overwrite_blank_secrets():
    from web.api import _apply_settings_update

    data = {
        "ai": {
            "provider": "deepseek",
            "deepseek": {
                "api_key": "keep-me",
                "base_url": "https://old.example",
                "model": "old-model",
            },
        },
        "wechat": {"app_id": "wx", "app_secret": "wechat-secret", "author": "A"},
        "content": {"humanize_rounds": 4},
    }

    _apply_settings_update(data, {
        "ai": {
            "deepseek": {
                "api_key": "",
                "api_key_set": True,
                "base_url": "https://new.example",
            },
            "provider": "kimi",
        },
        "wechat": {"app_secret": "", "author": "B"},
        "content": {"humanize_rounds": 2},
    })

    assert data["ai"]["provider"] == "kimi"
    assert data["ai"]["deepseek"]["api_key"] == "keep-me"
    assert data["ai"]["deepseek"]["base_url"] == "https://new.example"
    assert "api_key_set" not in data["ai"]["deepseek"]
    assert data["wechat"]["app_secret"] == "wechat-secret"
    assert data["wechat"]["author"] == "B"
    assert data["content"]["humanize_rounds"] == 2


# 2) 模型模块
def test_module_models():
    r = client.get("/api/models")
    assert r.status_code == 200
    models = r.json()
    names = {m["name"] for m in models}
    assert {"deepseek", "kimi", "minimax"} <= names
    assert all("is_ready" in m for m in models)
    assert any(m.get("is_current") for m in models)


# 3) 日志模块（历史可读 + 持久化）
def test_module_logs_history():
    from web import api as webapi
    webapi._broadcast({"time": "12:00:00", "level": "INFO", "message": "模块测试日志-history", "module": "test"})
    r = client.get("/api/logs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert any("history" in (e.get("message") or "") for e in r.json())


# 4) 抓取模块（本地文件，离线）
def test_module_fetcher_file():
    from src.content.fetcher import ContentFetcher
    f = ContentFetcher()
    src = _make_source("fetch.md", "# 抓取测试\n\n正文段落。\n")
    res = asyncio.run(f.fetch_file(src))
    assert res.title == "fetch"
    assert "抓取测试" in res.text_content


# 5) 列表模块
def test_module_articles_list():
    r = client.get("/api/articles")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# 6) 生成 + 详情模块
def test_module_generate_and_detail():
    aid = _generate_one("gen.md")
    r = client.get(f"/api/articles/{aid}")
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == aid
    assert d["title"]
    assert d["content"]
    assert 0.0 <= float(d["ai_score"]) <= 1.0


def test_generate_publish_uses_readiness_gate(monkeypatch):
    from src.readiness import ReadinessCheck
    from web import api as webapi

    monkeypatch.setattr(
        webapi,
        "collect_readiness",
        lambda **kwargs: [ReadinessCheck("wechat", False, "微信配置缺失")],
    )

    r = client.post("/api/generate", json={
        "source_type": "topic",
        "topic": "AI Agent 产品趋势",
        "style": "tech_explanation",
        "publish": True,
    })
    assert r.status_code == 200
    task_id = r.json()["task_id"]

    status = client.get(f"/api/tasks/{task_id}").json()
    assert status["status"] == "failed"
    assert "微信配置缺失" in status["message"]


def test_generate_task_reports_pipeline_last_error(monkeypatch):
    from web import api as webapi

    class FakePipeline:
        def __init__(self, model=None):
            self.last_error = ""

        async def run(self, **kwargs):
            self.last_error = "模型调用失败: quota exceeded"
            return None

    monkeypatch.setattr(webapi, "ArticleGenerationPipeline", FakePipeline)

    r = client.post("/api/generate", json={
        "source_type": "topic",
        "topic": "AI Agent 产品趋势",
        "style": "tech_explanation",
        "publish": False,
    })
    assert r.status_code == 200
    task_id = r.json()["task_id"]

    status = client.get(f"/api/tasks/{task_id}").json()
    assert status["status"] == "failed"
    assert "quota exceeded" in status["message"]


def test_generate_task_reports_pipeline_warnings(monkeypatch):
    from web import api as webapi

    class FakePipeline:
        def __init__(self, model=None):
            self.last_error = ""

        async def run(self, **kwargs):
            return {
                "id": 99,
                "title": "demo",
                "content": "<p>demo</p>",
                "digest": "demo",
                "ai_score": 0.2,
                "warnings": ["AI配图生成失败: image quota exhausted"],
            }

    monkeypatch.setattr(webapi, "ArticleGenerationPipeline", FakePipeline)

    r = client.post("/api/generate", json={
        "source_type": "topic",
        "topic": "AI Agent 产品趋势",
        "style": "tech_explanation",
        "publish": False,
    })
    assert r.status_code == 200
    task_id = r.json()["task_id"]

    status = client.get(f"/api/tasks/{task_id}").json()
    assert status["status"] == "done"
    assert "文章生成完成" in status["message"]
    assert "image quota exhausted" in status["message"]


def test_article_detail_sanitizes_preview_html():
    from src.db.models import get_session, Article

    s = get_session()
    article = Article(
        title="sanitize",
        final_content='<p onclick="steal()">正文</p><script>alert(1)</script><a href="javascript:bad()">x</a>',
        raw_content="raw",
        status="draft",
    )
    s.add(article)
    s.commit()
    aid = article.id
    s.close()

    r = client.get(f"/api/articles/{aid}")

    assert r.status_code == 200
    content = r.json()["content"]
    assert "<script" not in content
    assert "onclick" not in content
    assert "javascript:" not in content
    assert "正文" in content


def test_article_detail_rewrites_local_media_for_preview():
    from src.db.models import get_session, Article

    media_dir = Path("data/research_images")
    media_dir.mkdir(parents=True, exist_ok=True)
    image_path = media_dir / "preview-test.png"
    image_path.write_bytes(b"preview-image")

    s = get_session()
    article = Article(
        title="media preview",
        final_content=f'<p>正文</p><img src="{image_path}">',
        raw_content="raw",
        status="draft",
    )
    s.add(article)
    s.commit()
    aid = article.id
    s.close()

    r = client.get(f"/api/articles/{aid}")

    assert r.status_code == 200
    content = r.json()["content"]
    assert str(image_path) not in content
    assert '/api/media/research/preview-test.png' in content

    media = client.get("/api/media/research/preview-test.png")
    assert media.status_code == 200
    assert media.content == b"preview-image"


def test_article_detail_rewrites_mock_images_for_preview():
    from src.db.models import get_session, Article

    media_dir = Path("data/mock_images")
    media_dir.mkdir(parents=True, exist_ok=True)
    image_path = media_dir / "mock-preview.png"
    image_path.write_bytes(b"mock-image")

    s = get_session()
    article = Article(
        title="mock media preview",
        final_content=f'<p>正文</p><img src="{image_path}">',
        raw_content="raw",
        status="draft",
    )
    s.add(article)
    s.commit()
    aid = article.id
    s.close()

    r = client.get(f"/api/articles/{aid}")

    assert r.status_code == 200
    assert '/api/media/mock/mock-preview.png' in r.json()["content"]


def test_article_detail_returns_research_metadata():
    from src.db.models import get_session, Article

    media_dir = Path("data/research_images")
    media_dir.mkdir(parents=True, exist_ok=True)
    image_path = media_dir / "metadata-preview.png"
    image_path.write_bytes(b"metadata-image")

    s = get_session()
    article = Article(
        title="metadata",
        final_content="<p>正文</p>",
        raw_content="raw",
        status="draft",
        notes=json.dumps({
            "source_urls": ["https://example.com/source"],
            "research_query": "AI Agent 最新 解读 分析",
            "material_images": [{"path": str(image_path), "description": "素材图"}],
            "ai_images": [],
            "screenshots": [],
            "warnings": ["AI配图生成失败: image quota exhausted"],
        }, ensure_ascii=False),
    )
    s.add(article)
    s.commit()
    aid = article.id
    s.close()

    r = client.get(f"/api/articles/{aid}")

    assert r.status_code == 200
    body = r.json()
    assert body["source_urls"] == ["https://example.com/source"]
    assert body["research_query"] == "AI Agent 最新 解读 分析"
    assert body["warnings"] == ["AI配图生成失败: image quota exhausted"]
    assert body["material_images"][0]["preview_url"] == "/api/media/research/metadata-preview.png"


def test_media_endpoint_rejects_traversal():
    r = client.get("/api/media/research/../articles.db")

    assert r.status_code == 404


# 7) 发布模块（契约：monkeypatch 微信，验证状态流转，绝不触达真实微信）
def test_module_publish_contract(monkeypatch):
    from src.wechat.api_client import WeChatAPIClient
    from src.config import Config

    calls = {"create_draft": 0}

    def fake_create_draft(self, **kw):
        calls["create_draft"] += 1
        return "mock_media_id_001"

    monkeypatch.setattr(WeChatAPIClient, "create_draft", fake_create_draft)
    Config()._data.setdefault("wechat", {})["default_thumb_media_id"] = "thumb_test"

    aid = _generate_one("pub.md")
    r = client.post(f"/api/articles/{aid}/publish")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True, body
    assert body["media_id"] == "mock_media_id_001"
    assert body["message"] == "草稿创建成功"
    assert body["code"] == "ok"
    assert body["thumb_media_id"] == "thumb_test"

    # 状态应流转到 draft_created
    from src.db.models import get_session, Article
    s = get_session()
    a = s.query(Article).get(aid)
    s.close()
    assert a.status == "draft_created"
    assert a.media_id == "mock_media_id_001"
    assert calls["create_draft"] == 1

    r2 = client.post(f"/api/articles/{aid}/publish")
    assert r2.status_code == 200
    assert r2.json()["success"] is True
    assert "已存在微信草稿" in r2.json()["message"]
    assert r2.json()["media_id"] == "mock_media_id_001"
    assert r2.json()["code"] == "already_created"
    assert calls["create_draft"] == 1


def test_manual_publish_does_not_require_text_model(monkeypatch):
    from src.config import Config
    from src.db.models import get_session, Article
    from src.wechat.api_client import WeChatAPIClient

    calls = {"create_draft": 0}

    def fake_create_draft(self, **kw):
        calls["create_draft"] += 1
        return "mock_media_without_model"

    monkeypatch.setattr(WeChatAPIClient, "create_draft", fake_create_draft)

    cfg = Config()
    cfg._data.setdefault("ai", {})["provider"] = "deepseek"
    cfg._data.setdefault("ai", {}).setdefault("deepseek", {})["api_key"] = ""
    cfg._data.setdefault("wechat", {})["app_id"] = "wx-test"
    cfg._data.setdefault("wechat", {})["app_secret"] = "secret-test"
    cfg._data.setdefault("wechat", {})["default_thumb_media_id"] = "thumb_test"

    s = get_session()
    article = Article(
        title="manual draft",
        final_content="<p>正文</p>",
        raw_content="raw",
        digest="digest",
        status="draft",
    )
    s.add(article)
    s.commit()
    aid = article.id
    s.close()

    r = client.post(f"/api/articles/{aid}/publish")

    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["media_id"] == "mock_media_without_model"
    assert calls["create_draft"] == 1
