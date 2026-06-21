from src.content.sanitize import sanitize_article_html
from src.wechat.api_client import WeChatAPIClient


def test_sanitize_article_html_removes_active_content():
    dirty = """
    <html><head><style>body{background:red}</style></head><body>
      <script>alert(1)</script>
      <iframe src="https://evil.example"></iframe>
      <p onclick="steal()" style="color:red">正文</p>
      <a href="javascript:alert(1)">bad link</a>
      <img src="data:text/html;base64,abc" onerror="steal()">
      <img src="data:image/png;base64,abc">
      <img src="data/research_images/cover.png">
    </body></html>
    """

    clean = sanitize_article_html(dirty)

    assert "<script" not in clean
    assert "<iframe" not in clean
    assert "onclick" not in clean
    assert "onerror" not in clean
    assert "style=" not in clean
    assert "javascript:" not in clean
    assert "data:text/html" not in clean
    assert "data:image/png" in clean
    assert "data/research_images/cover.png" in clean
    assert "正文" in clean


def test_wechat_draft_content_uses_sanitizer():
    client = WeChatAPIClient("app", "secret")

    clean = client._prepare_draft_content(
        '<p onclick="steal()">正文</p><script>alert(1)</script>'
        '<a href="javascript:alert(1)">bad</a>'
    )

    assert "<script" not in clean
    assert "onclick" not in clean
    assert "javascript:" not in clean
    assert "正文" in clean
