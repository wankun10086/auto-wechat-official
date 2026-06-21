from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
import hashlib
import re

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from src.config import Config
from src.content.fetcher import ContentFetcher, ContentResult


@dataclass
class ResearchImage:
    url: str
    alt: str = ""
    source_url: str = ""
    path: str = ""


@dataclass
class ResearchResult:
    topic: str
    query: str
    sources: list[ContentResult] = field(default_factory=list)
    images: list[ResearchImage] = field(default_factory=list)

    @property
    def source_urls(self) -> list[str]:
        return [s.url for s in self.sources if s.url]

    def to_content_result(self) -> ContentResult:
        sections = []
        for idx, item in enumerate(self.sources, 1):
            source_label = f"[{idx}] {item.title}\nURL: {item.url}"
            body = item.text_content.strip()
            sections.append(f"{source_label}\n{body}")

        text = "\n\n---\n\n".join(sections)
        if not text:
            text = f"议题: {self.topic}\n未检索到可用网页素材，请基于议题进行谨慎创作。"

        return ContentResult(
            url="; ".join(self.source_urls),
            title=self.topic,
            text_content=text[:12000],
            html_content="",
            images=[img.__dict__ for img in self.images],
            source_type="topic",
            metadata={
                "query": self.query,
                "source_urls": self.source_urls,
                "images": [img.__dict__ for img in self.images],
            },
        )


class TopicResearcher:
    def __init__(self, fetcher: ContentFetcher | None = None):
        self.config = Config()
        self.fetcher = fetcher or ContentFetcher()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        self.material_count = int(self.config.get("research", "material_count", default=5))
        self.image_count = int(self.config.get("research", "image_count", default=4))
        self.download_images = bool(self.config.get("research", "download_images", default=True))
        self.search_provider = self.config.get("research", "search_provider", default="duckduckgo")

    async def research(self, topic: str) -> ResearchResult:
        topic = topic.strip()
        query = self._build_query(topic)
        urls = await self.search(query, limit=self.material_count)
        logger.info(f"议题检索完成: {topic} / {len(urls)} 个候选来源")

        sources = []
        for url in urls:
            try:
                item = await self.fetcher.fetch(url)
                if item and len(item.text_content.strip()) >= 120:
                    sources.append(item)
            except Exception as e:
                logger.warning(f"素材抓取失败 {url}: {e}")
            if len(sources) >= self.material_count:
                break

        images = self._collect_images(sources)
        if self.download_images:
            await self._download_images(images[: self.image_count])

        return ResearchResult(
            topic=topic,
            query=query,
            sources=sources,
            images=images[: self.image_count],
        )

    async def search(self, query: str, limit: int = 5) -> list[str]:
        preferred = (self.search_provider or "duckduckgo").lower()
        providers = [preferred] + [p for p in ("duckduckgo", "bing", "serper") if p != preferred]

        for provider in providers:
            try:
                urls = await self._search_with_provider(provider, query, limit)
                urls = self._dedupe_urls(urls)
                if urls:
                    if provider != preferred:
                        logger.info(f"搜索源 {preferred} 无可用结果，已降级到 {provider}")
                    return urls[:limit]
            except Exception as e:
                logger.warning(f"搜索源 {provider} 失败: {e}")

        logger.warning("所有搜索源均未返回可用结果，将按议题直接生成")
        return []

    async def _search_with_provider(self, provider: str, query: str, limit: int) -> list[str]:
        if provider == "serper":
            return await self._search_serper(query, limit)
        if provider == "bing":
            return await self._search_bing_html(query, limit)
        return await self._search_duckduckgo_html(query, limit)

    def _build_query(self, topic: str) -> str:
        suffix = self.config.get("research", "query_suffix", default="最新 解读 分析")
        return f"{topic} {suffix}".strip()

    async def _search_serper(self, query: str, limit: int) -> list[str]:
        api_key = self.config.get("research", "serper_api_key", default="")
        if not api_key:
            return []

        async with httpx.AsyncClient(headers=self.headers, timeout=20) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": limit},
            )
            resp.raise_for_status()
            data = resp.json()
        return [item.get("link", "") for item in data.get("organic", []) if item.get("link")]

    async def _search_duckduckgo_html(self, query: str, limit: int) -> list[str]:
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        async with httpx.AsyncClient(headers=self.headers, timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        urls = []
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            if href:
                urls.append(href)
            if len(urls) >= limit:
                break
        return urls

    async def _search_bing_html(self, query: str, limit: int) -> list[str]:
        url = f"https://www.bing.com/search?q={quote_plus(query)}"
        async with httpx.AsyncClient(headers=self.headers, timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        urls = []
        for a in soup.select("li.b_algo h2 a"):
            href = a.get("href", "")
            if href:
                urls.append(href)
            if len(urls) >= limit:
                break
        return urls

    def _collect_images(self, sources: list[ContentResult]) -> list[ResearchImage]:
        images = []
        seen = set()
        for source in sources:
            for meta in source.metadata.get("images_meta", [])[:8]:
                src = meta.get("src", "")
                if not src:
                    continue
                url = urljoin(source.url, src)
                if url in seen or not self._looks_like_image_url(url):
                    continue
                seen.add(url)
                images.append(ResearchImage(url=url, alt=meta.get("alt", ""), source_url=source.url))
        return images

    async def _download_images(self, images: list[ResearchImage]) -> None:
        output_dir = Path("data/research_images")
        output_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            for image in images:
                try:
                    resp = await client.get(image.url)
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "").split(";")[0].lower()
                    if not content_type.startswith("image/"):
                        continue
                    ext = self._extension_from_content_type(content_type) or ".jpg"
                    digest = hashlib.sha256(resp.content).hexdigest()[:16]
                    path = output_dir / f"{digest}{ext}"
                    if not path.exists():
                        path.write_bytes(resp.content)
                    image.path = str(path)
                except Exception as e:
                    logger.debug(f"素材图片下载失败 {image.url}: {e}")

    def _looks_like_image_url(self, url: str) -> bool:
        if url.startswith("data:"):
            return False
        if re.search(r"\.(jpg|jpeg|png|webp|gif)(\?|$)", url, re.I):
            return True
        return any(host in url.lower() for host in ["image", "img", "cdn", "pic"])

    def _extension_from_content_type(self, content_type: str) -> str:
        return {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }.get(content_type, "")

    def _dedupe_urls(self, urls: list[str]) -> list[str]:
        result = []
        seen = set()
        for url in urls:
            clean = self._normalize_result_url(url)
            if not clean or clean in seen:
                continue
            seen.add(clean)
            result.append(clean)
        return result

    def _normalize_result_url(self, url: str) -> str:
        clean = (url or "").strip()
        if clean.startswith("//"):
            clean = "https:" + clean

        parsed = urlparse(clean)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            clean = unquote(target)

        if clean.startswith("http://") or clean.startswith("https://"):
            return clean
        return ""
