import sys
from types import SimpleNamespace

import main as legacy_main
from src.pipeline import PublishResult
from src.scheduler import job_runner


def _stub_startup(monkeypatch):
    monkeypatch.setattr(legacy_main, "Config", lambda: SimpleNamespace(load=lambda: None))
    monkeypatch.setattr(legacy_main, "setup_logging", lambda config: None)


def test_main_publish_creates_wechat_draft(monkeypatch, capsys):
    _stub_startup(monkeypatch)
    calls = {}

    class FakePipeline:
        async def create_draft(self, article_id):
            calls["create_draft"] = article_id
            return PublishResult(True, "ok", "草稿创建成功", media_id="draft_media_id")

        async def publish_via_browser(self, *args, **kwargs):
            raise AssertionError("main.py publish must not mass-send")

    monkeypatch.setattr(job_runner, "ArticlePipeline", FakePipeline)
    monkeypatch.setattr(sys, "argv", ["main.py", "publish", "42"])

    legacy_main.main()

    assert calls == {"create_draft": 42}
    assert "草稿创建成功: draft_media_id" in capsys.readouterr().out


def test_main_full_does_not_prompt_for_browser_publish(monkeypatch, capsys):
    _stub_startup(monkeypatch)
    calls = {}

    class FakePipeline:
        async def run_full_pipeline(self, strategy):
            calls["run_full_pipeline"] = strategy
            return SimpleNamespace(
                id=7,
                title="自动草稿",
                ai_score=0.12,
                media_id="draft_media_id",
                status="draft_created",
            )

        async def publish_via_browser(self, *args, **kwargs):
            raise AssertionError("main.py full must not mass-send")

    def fail_input(*args, **kwargs):
        raise AssertionError("main.py full must not ask for final publish")

    monkeypatch.setattr(job_runner, "ArticlePipeline", FakePipeline)
    monkeypatch.setattr("builtins.input", fail_input)
    monkeypatch.setattr(sys, "argv", ["main.py", "full", "hot_tech"])

    legacy_main.main()

    assert calls == {"run_full_pipeline": "hot_tech"}
    assert "请在微信公众号后台确认后手动发布" in capsys.readouterr().out
