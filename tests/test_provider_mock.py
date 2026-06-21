from pathlib import Path

from src.ai.mock import MockProvider
from src.ai.provider import get_provider, provider_config_missing, resolve_image_provider_name
from src.config import Config
import pytest


def test_mock_provider_registered():
    p = get_provider("mock")
    assert isinstance(p, MockProvider)


def test_mock_generate_returns_html_article():
    p = get_provider("mock")
    res = p.generate("请帮我写一篇技术解析文章")
    assert res.text
    assert "<h2>" in res.text


def test_mock_generate_titles_and_digest_branches():
    p = get_provider("mock")
    titles = p.generate("title candidates").text
    assert "1." in titles
    digest = p.generate("请生成摘要digest").text
    assert "摘要" in digest or len(digest) > 0


def test_mock_generate_image_returns_local_file():
    p = get_provider("mock")
    path = p.generate_image("封面图")
    assert Path(path).exists()


def test_non_mock_provider_requires_basic_config():
    cfg = Config()
    old = dict(cfg._data.get("ai", {}).get("glm", {}))
    cfg._data.setdefault("ai", {})["glm"] = {"api_key": "", "base_url": "", "model": ""}
    try:
        with pytest.raises(ValueError, match="glm 配置缺失"):
            get_provider("glm")
    finally:
        cfg._data["ai"]["glm"] = old


def test_minimax_image_model_rejects_text_model_name():
    missing = provider_config_missing(
        "minimax",
        {
            "api_key": "minimax-key",
            "base_url": "https://api.minimaxi.com/anthropic",
            "model": "MiniMax-M3",
            "image_model": "MiniMax-M3",
        },
        require_image=True,
    )

    assert any("image_model" in item and "文本模型" in item for item in missing)


def test_glm_image_model_rejects_text_model_name():
    missing = provider_config_missing(
        "glm",
        {
            "api_key": "glm-key",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4-flash",
            "image_model": "glm-4-flash",
        },
        require_image=True,
    )

    assert any("image_model" in item and "文本模型" in item for item in missing)


def test_auto_image_provider_skips_invalid_minimax_image_model():
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
            "api_key": "minimax-key",
            "base_url": "https://api.minimaxi.com/anthropic",
            "model": "MiniMax-M3",
            "image_model": "MiniMax-M3",
        },
        "glm": {
            "api_key": "",
            "base_url": "",
            "model": "",
            "image_model": "",
        },
    }
    try:
        assert resolve_image_provider_name(None, "deepseek") == ""
    finally:
        cfg._data["ai"] = old_ai


def test_auto_image_provider_skips_invalid_active_minimax():
    cfg = Config()
    old_ai = cfg._data.get("ai", {}).copy()
    cfg._data["ai"] = {
        "provider": "minimax",
        "minimax": {
            "api_key": "minimax-key",
            "base_url": "https://api.minimaxi.com/anthropic",
            "model": "MiniMax-M3",
            "image_model": "MiniMax-M3",
        },
        "glm": {
            "api_key": "",
            "base_url": "",
            "model": "",
            "image_model": "",
        },
    }
    try:
        assert resolve_image_provider_name(None, "minimax") == ""
    finally:
        cfg._data["ai"] = old_ai


def test_auto_image_provider_falls_back_to_valid_glm():
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
            "api_key": "minimax-key",
            "base_url": "https://api.minimaxi.com/anthropic",
            "model": "MiniMax-M3",
            "image_model": "MiniMax-M3",
        },
        "glm": {
            "api_key": "glm-key",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4-flash",
            "image_model": "glm-image",
        },
    }
    try:
        assert resolve_image_provider_name(None, "deepseek") == "glm"
    finally:
        cfg._data["ai"] = old_ai


def test_minimax_image_base_url_rejects_text_endpoint():
    missing = provider_config_missing(
        "minimax",
        {
            "api_key": "minimax-key",
            "base_url": "https://api.minimaxi.com/anthropic",
            "model": "MiniMax-M3",
            "image_base_url": "https://api.minimaxi.com/anthropic",
            "image_model": "image-01",
        },
        require_image=True,
    )

    assert any("image_base_url" in item for item in missing)


def test_glm_image_size_rejects_bad_shape():
    missing = provider_config_missing(
        "glm",
        {
            "api_key": "glm-key",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4-flash",
            "image_model": "glm-image",
            "image_size": "1024*1024",
        },
        require_image=True,
    )

    assert any("image_size" in item for item in missing)
