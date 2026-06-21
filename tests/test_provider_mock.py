from pathlib import Path

from src.ai.mock import MockProvider
from src.ai.provider import get_provider


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
