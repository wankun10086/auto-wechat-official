from types import SimpleNamespace

import pytest

import src.ai.deepseek as deepseek_module
import src.ai.glm as glm_module
import src.ai.kimi as kimi_module
import src.ai.minimax as minimax_module
from src.ai.deepseek import DeepSeekProvider
from src.ai.glm import GLMProvider
from src.ai.kimi import KimiProvider
from src.ai.minimax import MiniMaxProvider


class FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


def test_deepseek_openai_compatible_payload(monkeypatch):
    capture = {}
    monkeypatch.setattr(deepseek_module, "OpenAI", _fake_openai(capture))

    provider = DeepSeekProvider({
        "api_key": "deepseek-key",
        "base_url": "https://api.deepseek.example",
        "model": "deepseek-chat",
    })
    result = provider.generate("user prompt", system="system prompt", temperature=0.4, max_tokens=123)

    assert result.text == "provider ok"
    assert result.usage == {"prompt_tokens": 7, "completion_tokens": 11}
    assert capture["init"] == {
        "api_key": "deepseek-key",
        "base_url": "https://api.deepseek.example",
    }
    assert capture["payload"]["model"] == "deepseek-chat"
    assert capture["payload"]["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user prompt"},
    ]
    assert capture["payload"]["temperature"] == 0.4
    assert capture["payload"]["max_tokens"] == 123


def test_kimi_openai_compatible_payload(monkeypatch):
    capture = {}
    monkeypatch.setattr(kimi_module, "OpenAI", _fake_openai(capture))

    provider = KimiProvider({
        "api_key": "kimi-key",
        "base_url": "https://api.moonshot.example/v1",
        "model": "moonshot-v1-8k",
    })
    result = provider.generate("user prompt", temperature=0.7, max_tokens=321)

    assert result.text == "provider ok"
    assert capture["init"]["api_key"] == "kimi-key"
    assert capture["payload"]["model"] == "moonshot-v1-8k"
    assert capture["payload"]["messages"] == [{"role": "user", "content": "user prompt"}]
    assert capture["payload"]["temperature"] == 0.7
    assert capture["payload"]["max_tokens"] == 321


def test_minimax_messages_payload(monkeypatch):
    capture = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        capture.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse(200, {
            "content": [{"type": "text", "text": "minimax ok"}],
            "usage": {"input_tokens": 3, "output_tokens": 5},
        })

    monkeypatch.setattr(minimax_module.httpx, "post", fake_post)
    provider = MiniMaxProvider({
        "api_key": "minimax-key",
        "base_url": "https://api.minimaxi.example/anthropic",
        "model": "MiniMax-M3",
    })

    result = provider.generate("hello", system="sys", max_tokens=88)

    assert result.text == "minimax ok"
    assert capture["url"] == "https://api.minimaxi.example/anthropic/v1/messages"
    assert capture["headers"]["Authorization"] == "Bearer minimax-key"
    assert capture["headers"]["anthropic-version"] == "2023-06-01"
    assert capture["json"]["model"] == "MiniMax-M3"
    assert capture["json"]["system"] == "sys"
    assert capture["json"]["messages"] == [{"role": "user", "content": "hello"}]
    assert capture["json"]["max_tokens"] == 88


def test_minimax_image_payload_and_base64_save(monkeypatch):
    capture = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        capture.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse(200, {
            "base_resp": {"status_code": 0},
            "data": {"image_base64": ["base64-image"]},
        })

    def fake_save(value, provider, suffix):
        capture["saved"] = {"value": value, "provider": provider, "suffix": suffix}
        return "data/generated_images/minimax/fake.jpg"

    monkeypatch.setattr(minimax_module.httpx, "post", fake_post)
    monkeypatch.setattr(minimax_module, "save_base64_image", fake_save)
    provider = MiniMaxProvider({
        "api_key": "minimax-key",
        "image_base_url": "https://minimax-image.example/",
        "image_model": "image-01",
    })

    path = provider.generate_image("prompt", aspect_ratio="1:1", n=1)

    assert path == "data/generated_images/minimax/fake.jpg"
    assert capture["url"] == "https://minimax-image.example/v1/image_generation"
    assert capture["headers"]["Authorization"] == "Bearer minimax-key"
    assert capture["json"]["model"] == "image-01"
    assert capture["json"]["prompt"] == "prompt"
    assert capture["json"]["aspect_ratio"] == "1:1"
    assert capture["json"]["response_format"] == "base64"
    assert capture["saved"] == {"value": "base64-image", "provider": "minimax", "suffix": ".jpg"}


def test_minimax_image_empty_response_raises(monkeypatch):
    monkeypatch.setattr(
        minimax_module.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(200, {"base_resp": {"status_code": 0}, "data": {}}),
    )
    provider = MiniMaxProvider({"api_key": "minimax-key"})

    with pytest.raises(Exception, match="未返回图片"):
        provider.generate_image("prompt")


def test_glm_chat_payload(monkeypatch):
    capture = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        capture.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse(200, {
            "choices": [{"message": {"content": "glm ok"}}],
            "usage": {"total_tokens": 8},
        })

    monkeypatch.setattr(glm_module.httpx, "post", fake_post)
    provider = GLMProvider({
        "api_key": "glm-key",
        "base_url": "https://open.bigmodel.example/api/paas/v4",
        "model": "glm-4-flash",
    })

    result = provider.generate("hello", system="sys", temperature=0.3, max_tokens=77)

    assert result.text == "glm ok"
    assert capture["url"] == "https://open.bigmodel.example/api/paas/v4/chat/completions"
    assert capture["headers"]["Authorization"] == "Bearer glm-key"
    assert capture["json"]["model"] == "glm-4-flash"
    assert capture["json"]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]
    assert capture["json"]["temperature"] == 0.3
    assert capture["json"]["max_tokens"] == 77
    assert capture["json"]["stream"] is False


def test_glm_image_payload_and_url_save(monkeypatch):
    capture = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        capture.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse(200, {"data": [{"url": "https://images.example.com/a.png"}]})

    def fake_save(url, provider):
        capture["saved"] = {"url": url, "provider": provider}
        return "data/generated_images/glm/fake.png"

    monkeypatch.setattr(glm_module.httpx, "post", fake_post)
    monkeypatch.setattr(glm_module, "save_image_url", fake_save)
    provider = GLMProvider({
        "api_key": "glm-key",
        "base_url": "https://open.bigmodel.example/api/paas/v4",
        "image_model": "glm-image",
        "image_size": "1024x1024",
    })

    path = provider.generate_image("cover prompt", quality="hd")

    assert path == "data/generated_images/glm/fake.png"
    assert capture["url"] == "https://open.bigmodel.example/api/paas/v4/images/generations"
    assert capture["json"] == {
        "model": "glm-image",
        "prompt": "cover prompt",
        "size": "1024x1024",
        "quality": "hd",
    }
    assert capture["saved"] == {"url": "https://images.example.com/a.png", "provider": "glm"}


def _fake_openai(capture):
    class FakeOpenAI:
        def __init__(self, api_key, base_url):
            capture["init"] = {"api_key": api_key, "base_url": base_url}
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            capture["payload"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="provider ok"))],
                usage=SimpleNamespace(prompt_tokens=7, completion_tokens=11),
            )

    return FakeOpenAI
