import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from pathlib import Path
from loguru import logger
import re
import json


@dataclass
class ImageInfo:
    path: str
    description: str
    img_type: str


@dataclass
class ContentResult:
    url: str
    title: str
    text_content: str
    html_content: str
    images: list = field(default_factory=list)
    source_type: str = "web"
    metadata: dict = field(default_factory=dict)


class ContentFetcher:
    def __init__(self, screenshot_dir="data/screenshots"):
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def fetch(self, url: str) -> ContentResult:
        if "github.com" in url:
            return await self._fetch_github(url)
        else:
            return await self._fetch_web(url)

    async def fetch_file(self, file_path: str) -> ContentResult:
        path = Path(file_path)
        content = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()

        if suffix in (".md", ".markdown"):
            html = self._markdown_to_html(content)
            source_type = "markdown"
        elif suffix in (".html", ".htm"):
            html = content
            source_type = "html"
        else:
            html = f"<pre>{content}</pre>"
            source_type = "text"

        return ContentResult(
            url=str(path),
            title=path.stem,
            text_content=content,
            html_content=html,
            source_type=source_type,
        )

    async def _fetch_web(self, url: str) -> ContentResult:
        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        soup = BeautifulSoup(html, "lxml")

        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()

        article = soup.find("article") or soup.find("main") or soup.find("div", class_=re.compile(r"content|article|post|entry", re.I))
        target = article if article else soup.body

        text = target.get_text(separator="\n", strip=True) if target else ""

        images_meta = []
        for img in (target or soup).find_all("img"):
            src = img.get("src", "")
            alt = img.get("alt", "")
            if src and not src.startswith("data:"):
                images_meta.append({"src": src, "alt": alt})

        return ContentResult(
            url=url,
            title=title,
            text_content=text[:8000],
            html_content=str(target) if target else html,
            source_type="web",
            metadata={"images_meta": images_meta[:20]},
        )

    async def _fetch_github(self, url: str) -> ContentResult:
        parts = url.rstrip("/").split("/")
        github_idx = parts.index("github.com") if "github.com" in parts else -1
        if github_idx >= 0 and len(parts) > github_idx + 2:
            owner = parts[github_idx + 1]
            repo = parts[github_idx + 2]
        else:
            owner, repo = parts[-2], parts[-1]
        api_base = f"https://api.github.com/repos/{owner}/{repo}"

        async with httpx.AsyncClient(headers={**self.headers, "Accept": "application/vnd.github.v3+json"}, timeout=30) as client:
            repo_resp = await client.get(api_base)
            repo_data = repo_resp.json() if repo_resp.status_code == 200 else {}

            readme_resp = await client.get(f"{api_base}/readme")
            readme_text = ""
            if readme_resp.status_code == 200:
                import base64
                readme_data = readme_resp.json()
                readme_text = base64.b64decode(readme_data.get("content", "")).decode("utf-8", errors="replace")

            tree_resp = await client.get(f"{api_base}/git/trees/HEAD?recursive=1")
            tree_text = ""
            if tree_resp.status_code == 200:
                tree_data = tree_resp.json()
                files = [t["path"] for t in tree_data.get("tree", []) if t["type"] == "blob"]
                tree_text = "\n".join(files[:100])

        title = repo_data.get("full_name", f"{owner}/{repo}")
        description = repo_data.get("description", "")
        stars = repo_data.get("stargazers_count", 0)
        language = repo_data.get("language", "")

        text = f"# {title}\n\n{description}\n\nStars: {stars} | Language: {language}\n\n## README\n\n{readme_text}\n\n## 文件结构\n\n{tree_text}"

        return ContentResult(
            url=url,
            title=title,
            text_content=text[:8000],
            html_content=f"<h1>{title}</h1><p>{description}</p><pre>{readme_text}</pre>",
            source_type="github",
            metadata={
                "stars": stars,
                "language": language,
                "description": description,
                "file_tree": tree_text,
            },
        )

    def _markdown_to_html(self, md_text: str) -> str:
        html = md_text
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"`(.+?)`", r"<code>\1</code>", html)
        html = re.sub(r"\n\n", "</p><p>", html)
        return f"<p>{html}</p>"
