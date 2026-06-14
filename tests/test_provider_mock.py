import pytest
from src.ai.provider import get_provider
from src.ai.mock import MockProvider


def test_mock_provider_registered():
    p = get_provider("mock")
    assert isinstance(p, MockProvider)


def test_mock_generate_returns_html_article():
    p = get_provider("mock")
    res = p.generate("请帮我写一篇技术解析文章")
    assert res.text
    assert "<h2>" in res.text  # 正文返回 HTML


def test_mock_generate_titles_and_digest_branches():
    p = get_provider("mock")
    titles = p.generate("请给出3个候选标题").text
    assert "1." in titles
    digest = p.generate("请生成摘要 digest").text
    assert "摘要" in digest or len(digest) > 0


def test_mock_generate_image_not_supported():
    p = get_provider("mock")
    with pytest.raises(NotImplementedError):
        p.generate_image("封面图")
