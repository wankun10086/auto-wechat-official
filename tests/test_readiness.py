from src.config import Config
from src.ai.provider import GenerateResult
import src.readiness as readiness_module
from src.readiness import collect_live_readiness, collect_readiness, readiness_ok


def test_readiness_reports_missing_provider_config():
    cfg = Config()
    old_ai = cfg._data.get("ai", {}).copy()
    cfg._data["ai"] = {
        "provider": "glm",
        "glm": {"api_key": "", "base_url": "", "model": ""},
    }
    try:
        checks = collect_readiness(model="glm", publish=False)
    finally:
        cfg._data["ai"] = old_ai

    assert readiness_ok(checks) is False
    assert any(c.name == "model_config" and not c.ok for c in checks)


def test_readiness_rejects_placeholder_provider_config():
    cfg = Config()
    old_ai = cfg._data.get("ai", {}).copy()
    cfg._data["ai"] = {
        "provider": "deepseek",
        "deepseek": {
            "api_key": "sk-your-deepseek-key",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
        },
    }
    try:
        checks = collect_readiness(model="deepseek", publish=False)
    finally:
        cfg._data["ai"] = old_ai

    assert readiness_ok(checks) is False
    assert any(c.name == "model_config" and not c.ok and "api_key" in c.message for c in checks)


def test_readiness_publish_checks_wechat_without_exposing_values():
    cfg = Config()
    old_ai = cfg._data.get("ai", {}).copy()
    old_wechat = cfg._data.get("wechat", {}).copy()
    cfg._data["ai"] = {
        "provider": "minimax",
        "minimax": {
            "api_key": "secret-ai",
            "base_url": "https://text.example",
            "model": "MiniMax-M3",
            "image_model": "image-01",
        },
    }
    cfg._data["wechat"] = {
        "app_id": "wx-secret",
        "app_secret": "wechat-secret",
        "default_thumb_media_id": "",
    }
    try:
        checks = collect_readiness(model="minimax", publish=True)
    finally:
        cfg._data["ai"] = old_ai
        cfg._data["wechat"] = old_wechat

    assert readiness_ok(checks) is True
    messages = "\n".join(c.message for c in checks)
    assert "secret-ai" not in messages
    assert "wechat-secret" not in messages
    assert any(c.name == "cover" and c.severity == "warning" for c in checks)


def test_readiness_rejects_placeholder_wechat_credentials():
    cfg = Config()
    old_ai = cfg._data.get("ai", {}).copy()
    old_wechat = cfg._data.get("wechat", {}).copy()
    cfg._data["ai"] = {
        "provider": "mock",
        "mock": {},
    }
    cfg._data["wechat"] = {
        "app_id": "your-app-id",
        "app_secret": "your-app-secret",
        "default_thumb_media_id": "your-thumb-media-id",
    }
    try:
        checks = collect_readiness(model="mock", publish=True)
    finally:
        cfg._data["ai"] = old_ai
        cfg._data["wechat"] = old_wechat

    assert readiness_ok(checks) is False
    assert any(c.name == "wechat" and not c.ok for c in checks)
    assert any(c.name == "cover" and c.severity == "warning" for c in checks)


def test_publish_only_readiness_skips_model_config():
    cfg = Config()
    old_ai = cfg._data.get("ai", {}).copy()
    old_wechat = cfg._data.get("wechat", {}).copy()
    cfg._data["ai"] = {
        "provider": "glm",
        "glm": {"api_key": "", "base_url": "", "model": ""},
    }
    cfg._data["wechat"] = {
        "app_id": "wx",
        "app_secret": "secret",
        "default_thumb_media_id": "thumb",
    }
    try:
        checks = collect_readiness(publish=True, check_model=False, check_research=False)
    finally:
        cfg._data["ai"] = old_ai
        cfg._data["wechat"] = old_wechat

    assert readiness_ok(checks) is True
    assert {c.name for c in checks} == {"wechat", "cover"}


def test_readiness_uses_configured_image_provider_for_text_model():
    cfg = Config()
    old_ai = cfg._data.get("ai", {}).copy()
    cfg._data["ai"] = {
        "provider": "deepseek",
        "deepseek": {
            "api_key": "deepseek-key",
            "base_url": "https://deepseek.example",
            "model": "deepseek-chat",
        },
        "glm": {
            "api_key": "glm-key",
            "base_url": "https://glm.example",
            "model": "glm-4",
            "image_model": "glm-image",
        },
    }
    try:
        checks = collect_readiness(model="deepseek", publish=False)
    finally:
        cfg._data["ai"] = old_ai

    assert readiness_ok(checks) is True
    assert any(c.name == "image_config" and "glm" in c.message for c in checks)


def test_readiness_explicit_image_model_missing_config_is_blocking():
    cfg = Config()
    old_ai = cfg._data.get("ai", {}).copy()
    cfg._data["ai"] = {
        "provider": "deepseek",
        "deepseek": {
            "api_key": "deepseek-key",
            "base_url": "https://deepseek.example",
            "model": "deepseek-chat",
        },
        "glm": {
            "api_key": "",
            "base_url": "",
            "model": "",
            "image_model": "",
        },
    }
    try:
        checks = collect_readiness(model="deepseek", image_model="glm", publish=False)
    finally:
        cfg._data["ai"] = old_ai

    assert readiness_ok(checks) is False
    assert any(c.name == "image_config" and not c.ok for c in checks)


def test_readiness_accepts_mock_provider_without_secrets():
    cfg = Config()
    old_ai = cfg._data.get("ai", {}).copy()
    cfg._data["ai"] = {"provider": "mock", "mock": {}}
    try:
        checks = collect_readiness(model="mock", publish=False, check_research=False)
    finally:
        cfg._data["ai"] = old_ai

    assert readiness_ok(checks) is True
    assert any(c.name == "model_config" and c.ok for c in checks)


def test_live_readiness_accepts_mock_provider():
    cfg = Config()
    old_ai = cfg._data.get("ai", {}).copy()
    cfg._data["ai"] = {"provider": "mock", "mock": {}}
    try:
        checks = collect_live_readiness(model="mock", publish=False)
    finally:
        cfg._data["ai"] = old_ai

    assert readiness_ok(checks) is True
    assert any(c.name == "model_live" and c.ok for c in checks)
    assert any(c.name == "image_live" and c.ok for c in checks)


def test_live_readiness_reports_image_api_failure_without_secret(monkeypatch):
    cfg = Config()
    old_ai = cfg._data.get("ai", {}).copy()
    cfg._data["ai"] = {
        "provider": "deepseek",
        "deepseek": {
            "api_key": "deepseek-key",
            "base_url": "https://deepseek.example",
            "model": "deepseek-chat",
        },
        "minimax": {
            "api_key": "sk-sensitive-minimax-key",
            "base_url": "https://minimax.example",
            "model": "MiniMax-M3",
            "image_model": "image-01",
        },
    }

    class TextProvider:
        def generate(self, prompt, **kwargs):
            return GenerateResult("OK")

    class ImageProvider:
        def generate_image(self, prompt, **kwargs):
            raise RuntimeError("invalid api_key sk-sensitive-minimax-key")

    def fake_get_provider(name=None):
        return ImageProvider() if name == "minimax" else TextProvider()

    monkeypatch.setattr(readiness_module, "get_provider", fake_get_provider)
    try:
        checks = collect_live_readiness(model="deepseek", image_model="minimax", publish=False)
    finally:
        cfg._data["ai"] = old_ai

    assert readiness_ok(checks) is False
    image_check = next(c for c in checks if c.name == "image_live")
    assert image_check.ok is False
    assert "invalid" in image_check.message
    assert "sk-sensitive-minimax-key" not in image_check.message


def test_live_readiness_checks_wechat_when_publish(monkeypatch):
    cfg = Config()
    old_ai = cfg._data.get("ai", {}).copy()
    old_wechat = cfg._data.get("wechat", {}).copy()
    cfg._data["ai"] = {"provider": "mock", "mock": {}}
    cfg._data["wechat"] = {
        "app_id": "wx-live-test",
        "app_secret": "wechat-secret",
        "default_thumb_media_id": "thumb",
    }

    class FakeWeChatClient:
        def __init__(self, app_id, app_secret):
            self.app_id = app_id
            self.app_secret = app_secret

        def get_draft_count(self):
            return {"total_count": 3}

    monkeypatch.setattr(readiness_module, "WeChatAPIClient", FakeWeChatClient)
    try:
        checks = collect_live_readiness(model="mock", publish=True, generate_images=False)
    finally:
        cfg._data["ai"] = old_ai
        cfg._data["wechat"] = old_wechat

    assert readiness_ok(checks) is True
    assert any(c.name == "wechat_live" and c.ok for c in checks)
