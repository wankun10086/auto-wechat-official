import asyncio

from src.db.models import Article, HotTopic, PublishLog, get_session
from src.pipeline import PublishResult
from src.scheduler import job_runner
from src.scheduler.job_runner import ArticlePipeline


def test_scheduler_pipeline_reuses_topic_generation_pipeline(monkeypatch):
    calls = {}

    class FakePipeline:
        def __init__(self):
            pass

        async def run(self, **kwargs):
            calls["run"] = kwargs
            session = get_session()
            article = Article(
                title="调度文章",
                raw_content="<p>raw</p>",
                final_content="<p>final</p>",
                digest="digest",
                topic=kwargs["source"],
                topic_strategy=kwargs["style"],
                ai_score=0.1,
                status="draft",
            )
            session.add(article)
            session.commit()
            article_id = article.id
            session.close()
            return {
                "id": article_id,
                "title": "调度文章",
                "content": "<p>final</p>",
                "digest": "digest",
                "ai_score": 0.1,
                "ai_images": [],
                "material_images": [],
                "screenshots": [],
                "source_type": "topic",
            }

        async def publish(self, result):
            calls["publish"] = result["id"]
            session = get_session()
            article = session.query(Article).get(result["id"])
            article.media_id = "mock_media_id"
            article.status = "draft_created"
            session.commit()
            session.close()
            return PublishResult(True, "ok", "草稿创建成功", media_id="mock_media_id", thumb_media_id="thumb")

    monkeypatch.setattr(job_runner, "ArticleGenerationPipeline", FakePipeline)

    session = get_session()
    session.add(HotTopic(
        title="AI Agent 趋势",
        source="unit",
        url="https://example.com/topic",
        description="desc",
        hot_score=1.0,
        used=False,
    ))
    session.commit()
    session.close()

    result = asyncio.run(ArticlePipeline().run_full_pipeline("deep_analysis"))

    assert result is not None
    assert calls["run"]["source"] == "AI Agent 趋势"
    assert calls["run"]["source_type"] == "topic"
    assert calls["run"]["style"] == "industry_analysis"
    assert calls["publish"] == result.id
    assert result.status == "draft_created"
    assert result.topic_strategy == "deep_analysis"

    session = get_session()
    logs = session.query(PublishLog).filter_by(article_id=result.id).all()
    session.close()
    assert any(log.action == "create_draft" and log.status == "success" for log in logs)


def test_scheduler_records_publish_failure_message(monkeypatch):
    class FakePipeline:
        def __init__(self):
            pass

        async def run(self, **kwargs):
            session = get_session()
            article = Article(
                title="调度失败文章",
                raw_content="<p>raw</p>",
                final_content="<p>final</p>",
                digest="digest",
                topic=kwargs["source"],
                topic_strategy=kwargs["style"],
                ai_score=0.1,
                status="draft",
            )
            session.add(article)
            session.commit()
            article_id = article.id
            session.close()
            return {
                "id": article_id,
                "title": "调度失败文章",
                "content": "<p>final</p>",
                "digest": "digest",
                "ai_score": 0.1,
                "ai_images": [],
                "material_images": [],
                "screenshots": [],
                "source_type": "topic",
            }

        async def publish(self, result):
            return PublishResult(False, "wechat_api_failed", "invalid credential")

    monkeypatch.setattr(job_runner, "ArticleGenerationPipeline", FakePipeline)

    session = get_session()
    session.add(HotTopic(
        title="AI Agent 发布失败",
        source="unit",
        url="https://example.com/fail-topic",
        description="desc",
        hot_score=2.0,
        used=False,
    ))
    session.commit()
    session.close()

    result = asyncio.run(ArticlePipeline().run_full_pipeline("hot_tech"))

    assert result is not None
    session = get_session()
    logs = session.query(PublishLog).filter_by(article_id=result.id).all()
    session.close()
    assert any(
        log.action == "create_draft"
        and log.status == "failed"
        and log.error_message == "invalid credential"
        for log in logs
    )


def test_publish_via_browser_marks_article_published(monkeypatch):
    calls = []

    class FakePublisher:
        async def start(self):
            calls.append("start")

        async def stop(self):
            calls.append("stop")

        async def is_logged_in(self):
            calls.append("is_logged_in")
            return True

        async def publish_draft_via_mass_send(self):
            calls.append("publish")
            return True

    session = get_session()
    article = Article(
        title="待发布文章",
        raw_content="<p>raw</p>",
        final_content="<p>final</p>",
        digest="digest",
        topic="topic",
        topic_strategy="hot_tech",
        ai_score=0.1,
        status="draft_created",
        media_id="mock_media_id",
    )
    session.add(article)
    session.commit()
    article_id = article.id
    session.close()

    pipeline = ArticlePipeline()
    pipeline.publisher = FakePublisher()

    ok = asyncio.run(pipeline.publish_via_browser(article_id))

    assert ok is True
    assert calls == ["start", "is_logged_in", "publish", "stop"]

    session = get_session()
    updated = session.query(Article).get(article_id)
    session.close()
    assert updated.status == "published"
    assert updated.published_at is not None
