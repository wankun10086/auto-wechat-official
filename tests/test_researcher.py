import asyncio
from io import BytesIO
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from PIL import Image

import src.content.researcher as researcher_module
from src.content.fetcher import ContentFetcher, ContentResult
from src.content.researcher import TopicResearcher


def test_duckduckgo_redirect_urls_are_normalized():
    researcher = TopicResearcher()
    urls = researcher._dedupe_urls([
        "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa%3Fx%3D1&rut=abc",
        "https://example.com/b",
        "#",
    ])

    assert urls == ["https://example.com/a?x=1", "https://example.com/b"]


def test_image_search_payloads_are_parsed():
    researcher = TopicResearcher()

    serper_images = researcher._images_from_serper_payload(
        {
            "images": [
                {
                    "title": "配图标题",
                    "imageUrl": "https://cdn.example.com/cover.jpg",
                    "link": "https://example.com/article",
                    "imageWidth": 1200,
                    "imageHeight": 630,
                }
            ]
        },
        limit=3,
    )
    assert serper_images[0].url == "https://cdn.example.com/cover.jpg"
    assert serper_images[0].source_url == "https://example.com/article"
    assert serper_images[0].width == 1200

    bing_images = researcher._images_from_bing_html(
        '<a class="iusc" m=\'{"murl":"https://img.example.com/a.png",'
        '"purl":"https://example.com/a","t":"Bing title"}\'></a>',
        limit=2,
    )
    assert bing_images[0].url == "https://img.example.com/a.png"
    assert bing_images[0].alt == "Bing title"


def test_fetcher_extracts_meta_lazy_and_srcset_images():
    html = """
    <html>
      <head>
        <meta property="og:image" content="https://cdn.example.com/og.jpg">
      </head>
      <body>
        <main>
          <img data-src="https://cdn.example.com/lazy.webp" alt="lazy">
          <img srcset="https://cdn.example.com/srcset-small.jpg 480w, https://cdn.example.com/srcset-large.jpg 960w">
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "lxml")
    fetcher = ContentFetcher()

    images = fetcher._extract_images_meta(soup, soup.find("main"))

    assert images == [
        {"src": "https://cdn.example.com/og.jpg", "alt": ""},
        {"src": "https://cdn.example.com/lazy.webp", "alt": "lazy"},
        {"src": "https://cdn.example.com/srcset-small.jpg", "alt": ""},
    ]


def test_download_images_skips_bad_candidates(monkeypatch):
    valid_png = _png_bytes(320, 180)
    tiny_png = _png_bytes(16, 16)

    responses = {
        "https://example.com/not-image": httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<html></html>",
            request=httpx.Request("GET", "https://example.com/not-image"),
        ),
        "https://example.com/tiny.png": httpx.Response(
            200,
            headers={"content-type": "image/png"},
            content=tiny_png,
            request=httpx.Request("GET", "https://example.com/tiny.png"),
        ),
        "https://example.com/valid-a.png": httpx.Response(
            200,
            headers={"content-type": "image/png"},
            content=valid_png,
            request=httpx.Request("GET", "https://example.com/valid-a.png"),
        ),
        "https://example.com/valid-b.png": httpx.Response(
            200,
            headers={"content-type": "image/png"},
            content=valid_png + b"b",
            request=httpx.Request("GET", "https://example.com/valid-b.png"),
        ),
    }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            return responses[url]

    monkeypatch.setattr(researcher_module.httpx, "AsyncClient", FakeAsyncClient)

    researcher = TopicResearcher()
    images = [
        researcher_module.ResearchImage("https://example.com/not-image"),
        researcher_module.ResearchImage("https://example.com/tiny.png"),
        researcher_module.ResearchImage("https://example.com/valid-a.png"),
        researcher_module.ResearchImage("https://example.com/valid-b.png"),
    ]

    downloaded = asyncio.run(researcher._download_images(images, target_count=2))

    assert [Path(img.path).suffix for img in downloaded] == [".png", ".png"]
    assert [img.width for img in downloaded] == [320, 320]
    assert all(Path(img.path).exists() for img in downloaded)


def test_research_returns_downloaded_images_first(monkeypatch):
    valid_png = _png_bytes(320, 180)

    class FakeFetcher(ContentFetcher):
        async def fetch(self, url: str) -> ContentResult:
            return ContentResult(
                url=url,
                title="source",
                text_content="这是一段足够长的测试素材，用来模拟议题检索后的正文内容。" * 8,
                html_content="",
                source_type="web",
                metadata={"images_meta": [{"src": "https://example.com/bad.html", "alt": "bad"}]},
            )

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            if url == "https://example.com/good.png":
                return httpx.Response(
                    200,
                    headers={"content-type": "image/png"},
                    content=valid_png,
                    request=httpx.Request("GET", url),
                )
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"bad",
                request=httpx.Request("GET", url),
            )

    async def fake_search(self, query, limit=5):
        return ["https://example.com/source"]

    async def fake_search_images(self, query, limit=6):
        return [researcher_module.ResearchImage("https://example.com/good.png", alt="good")]

    monkeypatch.setattr(researcher_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(TopicResearcher, "search", fake_search)
    monkeypatch.setattr(TopicResearcher, "search_images", fake_search_images)

    researcher = TopicResearcher(FakeFetcher())
    researcher.image_count = 1
    result = asyncio.run(researcher.research("AI Agent"))

    assert len(result.images) == 1
    assert result.images[0].url == "https://example.com/good.png"
    assert result.images[0].path


def _png_bytes(width: int, height: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color=(40, 80, 160)).save(buf, format="PNG")
    return buf.getvalue()
