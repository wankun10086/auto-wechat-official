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

    ok = asyncio.run(pipe.publish(result))

    assert ok is True
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
