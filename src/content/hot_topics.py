import httpx
from bs4 import BeautifulSoup
from loguru import logger
from src.config import Config


class HotTopicCollector:
    def __init__(self):
        config = Config()
        self.sources = config.get("hot_topics", "sources", default=[])
        self.fetch_count = config.get("hot_topics", "fetch_count", default=10)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    async def collect_all(self):
        all_topics = []
        for source in self.sources:
            if not source.get("enabled", True):
                continue
            try:
                topics = await self._fetch_source(source)
                all_topics.extend(topics)
                logger.info(f"从 {source['name']} 采集到 {len(topics)} 条话题")
            except Exception as e:
                logger.warning(f"采集 {source['name']} 失败: {e}")
        all_topics.sort(key=lambda x: x.get("hot_score", 0), reverse=True)
        return all_topics[: self.fetch_count]

    async def _fetch_source(self, source):
        name = source["name"]
        url = source["url"]

        if name == "v2ex":
            return await self._fetch_v2ex(url)
        elif name == "hackernews":
            return await self._fetch_hackernews(url)
        elif name == "36kr":
            return await self._fetch_36kr(url)
        else:
            return await self._fetch_generic(url, name)

    async def _fetch_v2ex(self, url):
        topics = []
        async with httpx.AsyncClient(headers=self.headers, timeout=15) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "lxml")
            items = soup.select("span.item_title a")
            for item in items[: self.fetch_count]:
                title = item.get_text(strip=True)
                link = "https://www.v2ex.com" + item.get("href", "")
                topics.append({
                    "title": title,
                    "source": "v2ex",
                    "url": link,
                    "description": "",
                    "hot_score": 0.5,
                })
        return topics

    async def _fetch_hackernews(self, url):
        topics = []
        async with httpx.AsyncClient(headers=self.headers, timeout=15) as client:
            resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
            story_ids = resp.json()[: self.fetch_count]
            for sid in story_ids:
                try:
                    sresp = await client.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{sid}.json"
                    )
                    story = sresp.json()
                    if story and story.get("title"):
                        topics.append({
                            "title": story["title"],
                            "source": "hackernews",
                            "url": story.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                            "description": "",
                            "hot_score": story.get("score", 0) / 1000,
                        })
                except Exception:
                    continue
        return topics

    async def _fetch_36kr(self, url):
        topics = []
        async with httpx.AsyncClient(headers=self.headers, timeout=15) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "lxml")
            items = soup.select("a.article-item-title")
            for item in items[: self.fetch_count]:
                title = item.get_text(strip=True)
                link = "https://36kr.com" + item.get("href", "")
                topics.append({
                    "title": title,
                    "source": "36kr",
                    "url": link,
                    "description": "",
                    "hot_score": 0.6,
                })
        return topics

    async def _fetch_generic(self, url, source_name):
        topics = []
        async with httpx.AsyncClient(headers=self.headers, timeout=15) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.find_all("a", href=True):
                title = a.get_text(strip=True)
                if len(title) > 10 and len(title) < 100:
                    topics.append({
                        "title": title,
                        "source": source_name,
                        "url": a["href"],
                        "description": "",
                        "hot_score": 0.3,
                    })
        return topics[: self.fetch_count]

    async def fetch_article_content(self, url):
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=15, follow_redirects=True) as client:
                resp = await client.get(url)
                soup = BeautifulSoup(resp.text, "lxml")
                for tag in soup(["script", "style", "nav", "header", "footer"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                return text[:3000]
        except Exception as e:
            logger.warning(f"抓取文章内容失败: {e}")
            return ""
