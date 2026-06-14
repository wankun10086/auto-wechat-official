"""
Phase 3 — 网站功能模块分步测试。

每个测试对应一个用户可见的功能模块，全部通过即视为该模块门禁通过。
生成/发布用 mock provider + monkeypatch，避免触碰真实 LLM 与微信。
"""
import asyncio
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
    r = client.get("/api/settings")
    assert r.status_code == 200
    d = r.json()
    assert {"ai", "wechat", "content"} <= set(d.keys())
    assert "provider" in d["ai"]


# 2) 模型模块
def test_module_models():
    r = client.get("/api/models")
    assert r.status_code == 200
    names = {m["name"] for m in r.json()}
    assert {"deepseek", "kimi", "minimax"} <= names
    assert any(m.get("is_current") for m in r.json())


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


# 7) 发布模块（契约：monkeypatch 微信，验证状态流转，绝不触达真实微信）
def test_module_publish_contract(monkeypatch):
    from src.wechat.api_client import WeChatAPIClient
    from src.config import Config

    monkeypatch.setattr(WeChatAPIClient, "create_draft", lambda self, **kw: "mock_media_id_001")
    Config()._data.setdefault("wechat", {})["default_thumb_media_id"] = "thumb_test"

    aid = _generate_one("pub.md")
    r = client.post(f"/api/articles/{aid}/publish")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True, body

    # 状态应流转到 draft_created
    from src.db.models import get_session, Article
    s = get_session()
    a = s.query(Article).get(aid)
    s.close()
    assert a.status == "draft_created"
    assert a.media_id == "mock_media_id_001"
