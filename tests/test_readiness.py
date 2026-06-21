from src.config import Config
from src.readiness import collect_readiness, readiness_ok


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
