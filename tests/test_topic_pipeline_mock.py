import asyncio
from pathlib import Path

from src.content.fetcher import ContentResult
from src.content.researcher import ResearchImage, ResearchResult, TopicResearcher
from src.pipeline import ArticleGenerationPipeline
from src.wechat.api_client import WeChatAPIClient


def test_topic_pipeline_runs_offline_with_mocked_research(local_tmp, monkeypatch):
    image_path = local_tmp / "material.jpg"
    image_path.write_bytes(b"fake-image")

    async def fake_research(self, topic):
        return ResearchResult(
            topic=topic,
            query=f"{topic} latest",
            sources=[
                ContentResult(
                    url="https://example.com/source",
                    title="source title",
                    text_content="这是一段用于测试的议题素材，包含足够内容用于生成公众号文章。",
                    html_content="<article>source</article>",
                    source_type="web",
                )
            ],
            images=[
                ResearchImage(
                    url="https://example.com/material.jpg",
                    alt="素材图",
                    source_url="https://example.com/source",
                    path=str(image_path),
                )
            ],
        )

    monkeypatch.setattr(TopicResearcher, "research", fake_research)

    pipe = ArticleGenerationPipeline(model="mock")
    result = asyncio.run(pipe.run(
        source="AI Agent 产品趋势",
        source_type="topic",
        style="industry_analysis",
        generate_images=True,
    ))

    assert result is not None
    assert result["source_type"] == "topic"
    assert result["material_images"]
    assert result["ai_images"]
    assert "AI Agent 产品趋势" in result["content"] or result["title"]


def test_pipeline_run_exposes_last_error(monkeypatch):
    async def fail_fetch(self, source, source_type):
        raise RuntimeError("fetch exploded")

    monkeypatch.setattr(ArticleGenerationPipeline, "_fetch_content", fail_fetch)

    pipe = ArticleGenerationPipeline(model="mock")
    result = asyncio.run(pipe.run(
        source="https://example.com/fail",
        source_type="url",
        generate_images=False,
    ))

    assert result is None
    assert "内容抓取失败" in pipe.last_error
    assert "fetch exploded" in pipe.last_error


def test_publish_rewrites_local_images_and_uses_generated_thumb(local_tmp, monkeypatch):
    image_path = local_tmp / "cover.jpg"
    image_path.write_bytes(b"fake-image")
    captured = {}

    def fake_upload_content(self, path):
        assert Path(path) == image_path
        return "https://mock.wechat.local/content.jpg"

    def fake_upload_thumb(self, path):
        assert Path(path) == image_path
        return "thumb_mock"

    def fake_post(self, path, json_data=None, **kwargs):
        captured["path"] = path
        captured["json"] = json_data
        return {"media_id": "mock_media_id_001"}

    monkeypatch.setattr(WeChatAPIClient, "upload_content_image", fake_upload_content)
    monkeypatch.setattr(WeChatAPIClient, "upload_thumb_image", fake_upload_thumb)
    monkeypatch.setattr(WeChatAPIClient, "_post", fake_post)

    pipe = ArticleGenerationPipeline(model="mock")
    pipe.config._data.setdefault("wechat", {})["default_thumb_media_id"] = ""
    source = local_tmp / "source.md"
    source.write_text("# 标题\n\n正文内容", encoding="utf-8")
    result = asyncio.run(pipe.run(
        source=str(source),
        source_type="file",
        generate_images=False,
    ))
    result["content"] = f"<style>.x{{}}</style><p>x</p><img src=\"{image_path}\">"
    result["ai_images"] = [{"path": str(image_path), "description": "cover"}]

    publish_result = asyncio.run(pipe.publish(result))

    assert publish_result.ok is True
    assert publish_result.code == "ok"
    assert publish_result.media_id == "mock_media_id_001"
    assert publish_result.thumb_media_id == "thumb_mock"
    article = captured["json"]["articles"][0]
    assert captured["path"] == "draft/add"
    assert article["thumb_media_id"] == "thumb_mock"
    assert "<style>" not in article["content"]
    assert str(image_path) not in article["content"]
    assert "https://mock.wechat.local/content.jpg" in article["content"]


def test_publish_thumb_fallback_reads_local_image_from_html(local_tmp, monkeypatch):
    image_path = local_tmp / "cover.png"
    image_path.write_bytes(b"fake-image")
    captured = {}

    def fake_upload_thumb(self, path):
        captured["path"] = path
        return "thumb_from_html"

    monkeypatch.setattr(WeChatAPIClient, "upload_thumb_image", fake_upload_thumb)

    pipe = ArticleGenerationPipeline(model="mock")
    pipe.config._data.setdefault("wechat", {})["default_thumb_media_id"] = ""
    thumb = pipe._resolve_thumb_media_id({
        "content": f"<p>x</p><img src=\"{image_path}\">",
        "ai_images": [],
        "material_images": [],
        "screenshots": [],
    })

    assert thumb == "thumb_from_html"
    assert Path(captured["path"]) == image_path


def test_wechat_image_mime_uses_file_suffix():
    client = WeChatAPIClient("app", "secret")

    assert client._image_mime("cover.png") == "image/png"
    assert client._image_mime("cover.unknown") == "image/jpeg"


def test_publish_returns_structured_error_when_wechat_credentials_missing(monkeypatch):
    pipe = ArticleGenerationPipeline(model="mock")
    pipe.api_client.app_id = ""
    pipe.api_client.app_secret = ""

    def fail_upload(path):
        raise AssertionError("publish should stop before uploading images")

    monkeypatch.setattr(pipe.api_client, "upload_thumb_image", fail_upload)

    publish_result = asyncio.run(pipe.publish({
        "id": 0,
        "title": "title",
        "content": "<p>x</p>",
        "digest": "",
        "ai_images": [],
        "material_images": [],
        "screenshots": [],
    }))

    assert publish_result.ok is False
    assert publish_result.code == "missing_wechat_credentials"
    assert "AppID/AppSecret" in publish_result.message


def test_publish_returns_structured_error_when_thumb_upload_fails(local_tmp, monkeypatch):
    image_path = local_tmp / "cover.jpg"
    image_path.write_bytes(b"fake-image")

    pipe = ArticleGenerationPipeline(model="mock")
    pipe.config._data.setdefault("wechat", {})["default_thumb_media_id"] = ""

    def fail_upload(path):
        raise RuntimeError("thumb rejected")

    monkeypatch.setattr(pipe.api_client, "upload_thumb_image", fail_upload)

    publish_result = asyncio.run(pipe.publish({
        "id": 0,
        "title": "title",
        "content": "<p>x</p>",
        "digest": "",
        "ai_images": [{"path": str(image_path)}],
        "material_images": [],
        "screenshots": [],
    }))

    assert publish_result.ok is False
    assert publish_result.code == "thumb_upload_failed"
    assert "thumb rejected" in publish_result.message


def test_publish_returns_structured_error_when_create_draft_fails(monkeypatch):
    pipe = ArticleGenerationPipeline(model="mock")
    pipe.api_client.app_id = "wx"
    pipe.api_client.app_secret = "secret"
    pipe.config._data.setdefault("wechat", {})["default_thumb_media_id"] = "thumb_test"

    def fail_create_draft(**kwargs):
        raise RuntimeError("invalid thumb media")

    monkeypatch.setattr(pipe.api_client, "create_draft", fail_create_draft)

    publish_result = asyncio.run(pipe.publish({
        "id": 0,
        "title": "title",
        "content": "<p>x</p>",
        "digest": "",
        "ai_images": [],
        "material_images": [],
        "screenshots": [],
    }))

    assert publish_result.ok is False
    assert publish_result.code == "wechat_api_failed"
    assert "invalid thumb media" in publish_result.message
