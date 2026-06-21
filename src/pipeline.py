import html as html_lib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from loguru import logger

from src.ai.provider import get_provider, provider_supports_image, resolve_image_provider_name, resolve_provider_name
from src.config import Config, load_prompt
from src.content.fetcher import ContentFetcher, ContentResult
from src.content.humanizer import Humanizer
from src.content.researcher import TopicResearcher
from src.content.screenshot import ScreenshotCapture
from src.content.template import ArticleTemplate
from src.db.models import Article, get_session
from src.wechat.api_client import WeChatAPIClient


@dataclass
class PublishResult:
    ok: bool
    code: str
    message: str
    media_id: str = ""
    thumb_media_id: str = ""

    def __bool__(self) -> bool:
        return self.ok


class ArticleGenerationPipeline:
    def __init__(self, model: str = None, image_model: str = None, init_provider: bool = True):
        self.config = Config()
        self.provider_name = resolve_provider_name(model)
        self.image_provider_name = resolve_image_provider_name(image_model, self.provider_name)
        self.provider = get_provider(model) if init_provider else None
        self.image_provider = None
        self.fetcher = ContentFetcher()
        self.template = ArticleTemplate()
        self.prompts = load_prompt("tech_article")

        wechat_cfg = self.config.wechat
        self.api_client = WeChatAPIClient(wechat_cfg.get("app_id", ""), wechat_cfg.get("app_secret", ""))
        self.author = wechat_cfg.get("author", "")
        self.db_path = self.config.get("database", "path", default="data/articles.db")
        self.last_error = ""
        self.warnings = []

    async def run(
        self,
        source: str,
        source_type: str = "url",
        style: str = "tech_explanation",
        extra_prompt: str = "",
        screenshot_targets: list = None,
        generate_images: bool = True,
    ) -> dict:
        session = None
        article_record = None
        source_type = (source_type or "url").lower()
        self.last_error = ""
        self.warnings = []
        stage = "初始化"

        try:
            stage = "数据库初始化"
            session = get_session(self.db_path)

            stage = "内容抓取"
            content_result = await self._fetch_content(source, source_type)
            if not content_result:
                self.last_error = "内容抓取失败：未获得可用素材"
                logger.error(self.last_error)
                return None
            if source_type == "topic" and not self._topic_has_materials(content_result):
                self.last_error = "内容抓取失败：议题检索未获得可用网页素材"
                logger.error(self.last_error)
                return None

            logger.info(f"内容抓取成功: {content_result.title} ({len(content_result.text_content)} 字)")

            screenshots = []
            if screenshot_targets and source_type == "url":
                stage = "截图"
                screenshots = await self._take_screenshots(source, screenshot_targets)
                logger.info(f"截图完成: {len(screenshots)} 张")

            stage = "文章生成"
            raw_content = self._generate_article(content_result, style, extra_prompt)

            stage = "去AI味处理"
            humanizer = Humanizer(self.provider)
            final_content, ai_score = humanizer.full_pipeline(raw_content)

            if screenshots:
                final_content = self._embed_images(final_content, screenshots)

            final_content = self._append_reference_sources(final_content, content_result)

            material_images = []
            ai_images = []
            if generate_images:
                stage = "素材配图处理"
                material_images = self._material_images(content_result)
                if material_images:
                    final_content = self._embed_images(final_content, material_images)

                stage = "AI配图生成"
                ai_images = await self._generate_ai_images(content_result, final_content)
                if ai_images:
                    final_content = self._embed_images(final_content, ai_images)

            stage = "模板包装"
            final_content = self.template.wrap_article(final_content)

            stage = "标题/摘要生成"
            titles = self._generate_titles(final_content)
            title = titles[0] if titles else content_result.title
            digest = self._generate_digest(final_content)

            stage = "数据库保存"
            result_metadata = self._result_metadata(
                content_result,
                source_type,
                screenshots,
                material_images,
                ai_images,
            )

            article_record = Article(
                title=title,
                raw_content=raw_content,
                final_content=final_content,
                digest=digest,
                author=self.author,
                topic=content_result.title,
                topic_strategy=style,
                ai_score=ai_score,
                status="draft",
                notes=json.dumps(result_metadata, ensure_ascii=False),
            )
            session.add(article_record)
            session.commit()
            logger.info(f"文章已保存到数据库，ID: {article_record.id}")

            return {
                "id": article_record.id,
                "title": title,
                "content": final_content,
                "digest": digest,
                "ai_score": ai_score,
                "screenshots": screenshots,
                "material_images": material_images,
                "ai_images": ai_images,
                "source_type": source_type,
                "warnings": list(self.warnings),
                "source_urls": result_metadata["source_urls"],
                "research_query": result_metadata["research_query"],
                "image_provider": result_metadata["image_provider"],
            }

        except Exception as e:
            self.last_error = f"{stage}失败: {e}"
            logger.error(self.last_error)
            if article_record and session:
                article_record.status = "failed"
                session.commit()
            return None
        finally:
            if session:
                session.close()

    async def publish(self, result: dict) -> PublishResult:
        session = get_session(self.db_path)
        try:
            if not self.api_client.app_id or not self.api_client.app_secret:
                message = "微信 AppID/AppSecret 未配置，无法创建草稿"
                logger.warning(message)
                return PublishResult(False, "missing_wechat_credentials", message)

            quality_error = self._draft_quality_error(result)
            if quality_error is not None:
                logger.warning(quality_error.message)
                return quality_error

            try:
                thumb_media_id = self._resolve_thumb_media_id(result)
            except Exception as e:
                message = f"封面图上传失败: {e}"
                logger.error(message)
                return PublishResult(False, "thumb_upload_failed", message)
            if not thumb_media_id:
                message = "未配置默认封面图 thumb_media_id，且没有可上传的本地图片"
                logger.warning(message)
                return PublishResult(False, "missing_thumb", message)

            media_id = self.api_client.create_draft(
                title=result["title"],
                content=result["content"],
                thumb_media_id=thumb_media_id,
                author=self.author,
                digest=result.get("digest", ""),
            )

            article = session.query(Article).get(result["id"])
            if article:
                article.media_id = media_id
                article.thumb_media_id = thumb_media_id
                article.status = "draft_created"
                session.commit()

            logger.info(f"草稿创建成功: {media_id}")
            return PublishResult(True, "ok", "草稿创建成功", media_id=media_id, thumb_media_id=thumb_media_id)
        except Exception as e:
            message = f"草稿创建失败: {e}"
            logger.error(message)
            return PublishResult(False, "wechat_api_failed", message)
        finally:
            session.close()

    def _draft_quality_error(self, result: dict) -> PublishResult | None:
        threshold = self.config.get("content", "max_ai_score_for_draft", default=0.5)
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            threshold = 0.5
        if threshold <= 0:
            return None

        score = result.get("ai_score")
        if score is None and result.get("id"):
            session = get_session(self.db_path)
            try:
                article = session.query(Article).get(result["id"])
                score = article.ai_score if article else None
            finally:
                session.close()
        if score is None:
            return None

        try:
            score = float(score)
        except (TypeError, ValueError):
            return None

        if score <= threshold:
            return None

        message = f"AI味得分 {score:.2f} 高于草稿阈值 {threshold:.2f}，请先人工检查或重新去AI味"
        return PublishResult(False, "ai_score_too_high", message)

    async def _fetch_content(self, source: str, source_type: str):
        if source_type == "file":
            return await self.fetcher.fetch_file(source)
        if source_type == "topic":
            researcher = TopicResearcher(self.fetcher)
            research = await researcher.research(source)
            return research.to_content_result()
        return await self.fetcher.fetch(source)

    def _topic_has_materials(self, content_result: ContentResult) -> bool:
        if content_result.source_type != "topic":
            return True
        if self.config.get("research", "allow_no_materials", default=False):
            return True
        return bool(content_result.metadata.get("source_urls"))

    async def _take_screenshots(self, url: str, targets: list) -> list:
        capture = ScreenshotCapture()
        try:
            await capture.start()
            return await capture.capture_url(url, targets)
        except Exception as e:
            self._add_warning(f"截图失败: {e}")
            logger.error(f"截图失败: {e}")
            return []
        finally:
            await capture.stop()

    def _generate_article(self, content_result: ContentResult, style: str, extra_prompt: str) -> str:
        style_map = {
            "tech_explanation": "article_generation",
            "tutorial": "style_tutorial",
            "industry_analysis": "style_deep",
            "product_review": "style_review",
        }
        template_key = style_map.get(style, "article_generation")
        prompt_template = self.prompts.get(template_key, self.prompts.get("article_generation", ""))

        prompt = prompt_template.format(
            topic=content_result.title,
            source_materials=content_result.text_content[:9000],
        )

        if extra_prompt:
            prompt += f"\n\n【额外要求】{extra_prompt}"

        if content_result.source_type == "github":
            prompt += (
                "\n\n【补充信息】这是一个GitHub仓库。"
                f"仓库描述：{content_result.metadata.get('description', '')}。"
                f"主要语言：{content_result.metadata.get('language', '')}。"
                f"Star数：{content_result.metadata.get('stars', '')}。"
            )
        elif content_result.source_type == "web":
            prompt += f"\n\n【补充信息】源链接：{content_result.url}"
        elif content_result.source_type == "topic":
            urls = content_result.metadata.get("source_urls", [])
            if urls:
                prompt += "\n\n【检索来源】\n" + "\n".join(f"- {url}" for url in urls[:8])
            prompt += "\n\n请基于检索素材写作，避免编造来源；如果素材之间存在冲突，请在文中用审慎语气处理。"

        prompt += (
            "\n\n请用HTML格式输出，使用 <h2> <h3> <p> <blockquote> <strong> "
            "<em> <ul> <li> <code> <pre> 等标签。文章中如果有代码示例，"
            "请用 <pre><code> 包裹。"
        )

        result = self.provider.generate(prompt, temperature=0.85, max_tokens=6000)
        return self._extract_html(result.text)

    def _generate_titles(self, article: str) -> list:
        prompt_template = self.prompts.get("title_generation", "")
        prompt = prompt_template.format(summary=article[:1500])
        result = self.provider.generate(prompt, temperature=0.9, max_tokens=500)

        titles = []
        for line in result.text.strip().split("\n"):
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-") or line.startswith("*")):
                title = line.lstrip("0123456789.-*) ").strip()
                if title:
                    titles.append(title)
        return titles[:5]

    def _generate_digest(self, article: str) -> str:
        prompt_template = self.prompts.get("digest_generation", "")
        prompt = prompt_template.format(article=article[:2000])
        result = self.provider.generate(prompt, temperature=0.8, max_tokens=300)
        return result.text.strip()

    async def _generate_ai_images(self, content_result: ContentResult, article: str) -> list:
        try:
            provider = self._get_image_provider()
            if not provider:
                self._add_warning("未配置可用AI配图模型，已跳过AI配图")
                return []

            article_summary = BeautifulSoup(article or "", "html.parser").get_text(" ", strip=True)[:500]
            image_prompt = (
                "为微信公众号文章生成一张原创封面配图，中文科技媒体风格，"
                "现代、清晰、不要文字水印、不要品牌商标。"
                f"文章议题：{content_result.title}。"
                f"文章摘要：{article_summary}"
            )
            image_path = provider.generate_image(image_prompt)
            return [{
                "path": image_path,
                "description": "AI生成配图",
                "type": "ai_generated",
                "provider": self.image_provider_name,
            }]
        except NotImplementedError as e:
            message = f"{self.image_provider_name or '当前模型'} 不支持图片生成，已跳过AI配图: {e}"
            self._add_warning(message)
            logger.info(message)
            return []
        except Exception as e:
            self._add_warning(f"AI配图生成失败: {e}")
            logger.warning(f"AI配图生成失败: {e}")
            return []

    def _add_warning(self, message: str) -> None:
        if message and message not in self.warnings:
            self.warnings.append(message)

    def _get_image_provider(self):
        if not self.image_provider_name:
            return None
        if not provider_supports_image(self.image_provider_name):
            self._add_warning(f"{self.image_provider_name} 不支持图片生成，已跳过AI配图")
            return None
        if self.provider and self.image_provider_name == self.provider_name:
            return self.provider
        if self.image_provider is None:
            self.image_provider = get_provider(self.image_provider_name)
        return self.image_provider

    def _append_reference_sources(self, article_html: str, content_result: ContentResult) -> str:
        urls = content_result.metadata.get("source_urls") or []
        if not urls:
            return article_html

        items = []
        for idx, url in enumerate(urls[:8], 1):
            safe_url = html_lib.escape(url, quote=True)
            items.append(f'<li><a href="{safe_url}">{idx}. {safe_url}</a></li>')
        return (
            f"{article_html}\n"
            '<section class="reference-sources">'
            "<h2>参考来源</h2>"
            f"<ul>{''.join(items)}</ul>"
            "</section>"
        )

    def _result_metadata(
        self,
        content_result: ContentResult,
        source_type: str,
        screenshots: list,
        material_images: list,
        ai_images: list,
    ) -> dict:
        source_urls = content_result.metadata.get("source_urls") or []
        if not source_urls and content_result.url:
            source_urls = [content_result.url]
        return {
            "source_type": source_type,
            "research_query": content_result.metadata.get("query", ""),
            "source_urls": source_urls,
            "screenshots": screenshots,
            "material_images": material_images,
            "ai_images": ai_images,
            "warnings": list(self.warnings),
            "text_provider": self.provider_name,
            "image_provider": self.image_provider_name,
        }

    def _embed_images(self, article_html: str, images: list) -> str:
        for img in images:
            path = img.get("path", "")
            desc = img.get("description", "")
            if path and Path(path).exists():
                img_tag = (
                    f'<figure><img src="{html_lib.escape(path)}" alt="{html_lib.escape(desc)}" '
                    f'style="max-width:100%;"/><figcaption>{html_lib.escape(desc)}</figcaption></figure>'
                )
                article_html = img_tag + "\n" + article_html
        return article_html

    def _material_images(self, content_result: ContentResult) -> list:
        images = []
        for img in content_result.images or []:
            path = img.get("path", "")
            if path and Path(path).exists():
                images.append({
                    "path": path,
                    "description": img.get("alt") or "素材配图",
                    "type": "material",
                })
        return images[:3]

    def _resolve_thumb_media_id(self, result: dict) -> str:
        thumb_media_id = self.config.get("wechat", "default_thumb_media_id", default="")
        if thumb_media_id:
            return thumb_media_id

        for key in ("ai_images", "material_images", "screenshots"):
            for image in result.get(key, []) or []:
                path = image.get("path", "")
                if path and Path(path).exists():
                    return self.api_client.upload_thumb_image(path)

        for path in self._local_image_paths_from_html(result.get("content", "")):
            return self.api_client.upload_thumb_image(path)
        return ""

    def _local_image_paths_from_html(self, content: str) -> list[str]:
        soup = BeautifulSoup(content or "", "html.parser")
        paths = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if not src or re.match(r"^(https?:|data:)", src, re.I):
                continue
            path = Path(src)
            if path.exists():
                paths.append(str(path))
        return paths

    def _extract_html(self, text: str) -> str:
        if "```html" in text:
            text = text.split("```html", 1)[1]
            text = text.split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1]
            text = text.split("```", 1)[0]
        return text.strip()
