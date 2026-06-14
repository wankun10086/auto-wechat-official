import re
from pathlib import Path
from datetime import datetime
from loguru import logger
from src.config import Config, load_prompt
from src.ai.provider import get_provider
from src.content.fetcher import ContentFetcher, ContentResult
from src.content.screenshot import ScreenshotCapture
from src.content.humanizer import Humanizer
from src.content.template import ArticleTemplate
from src.wechat.api_client import WeChatAPIClient
from src.db.models import get_session, Article


class ArticleGenerationPipeline:
    def __init__(self, model: str = None):
        self.config = Config()
        self.provider = get_provider(model)
        self.fetcher = ContentFetcher()
        self.template = ArticleTemplate()
        self.prompts = load_prompt("tech_article")

        wechat_cfg = self.config.wechat
        self.api_client = WeChatAPIClient(wechat_cfg["app_id"], wechat_cfg["app_secret"])
        self.author = wechat_cfg.get("author", "")
        self.db_path = self.config.get("database", "path", default="data/articles.db")

    async def run(self, source: str, source_type: str = "url", style: str = "tech_explanation",
                  extra_prompt: str = "", screenshot_targets: list = None,
                  generate_images: bool = True) -> dict:
        session = get_session(self.db_path)
        article_record = None

        try:
            content_result = await self._fetch_content(source, source_type)
            if not content_result:
                logger.error("内容抓取失败")
                return None

            logger.info(f"内容抓取成功: {content_result.title} ({len(content_result.text_content)} 字)")

            screenshots = []
            if screenshot_targets and source_type == "url":
                screenshots = await self._take_screenshots(source, screenshot_targets)
                logger.info(f"截图完成: {len(screenshots)} 张")

            raw_content = self._generate_article(content_result, style, extra_prompt)

            humanizer = Humanizer(self.provider)
            final_content, ai_score = humanizer.full_pipeline(raw_content)

            if screenshots:
                final_content = self._embed_images(final_content, screenshots)

            ai_images = []
            if generate_images:
                ai_images = await self._generate_ai_images(content_result, final_content)
                if ai_images:
                    final_content = self._embed_images(final_content, ai_images)

            final_content = self.template.wrap_article(final_content)

            titles = self._generate_titles(content_result, final_content)
            title = titles[0] if titles else content_result.title
            digest = self._generate_digest(final_content)

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
                "ai_images": ai_images,
                "source_type": source_type,
            }

        except Exception as e:
            logger.error(f"流程失败: {e}")
            if article_record:
                article_record.status = "failed"
                session.commit()
            return None
        finally:
            session.close()

    async def publish(self, result: dict) -> bool:
        session = get_session(self.db_path)
        try:
            thumb_media_id = self.config.get("wechat", "default_thumb_media_id", default="")
            if not thumb_media_id:
                logger.warning("未配置默认封面图 thumb_media_id")
                return False

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
                article.status = "draft_created"
                session.commit()

            logger.info(f"草稿创建成功: {media_id}")
            return True
        except Exception as e:
            logger.error(f"草稿创建失败: {e}")
            return False
        finally:
            session.close()

    async def _fetch_content(self, source: str, source_type: str):
        if source_type == "file":
            return await self.fetcher.fetch_file(source)
        else:
            return await self.fetcher.fetch(source)

    async def _take_screenshots(self, url: str, targets: list) -> list:
        capture = ScreenshotCapture()
        try:
            await capture.start()
            results = await capture.capture_url(url, targets)
            return results
        except Exception as e:
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
        source_text = content_result.text_content[:6000]

        prompt = prompt_template.format(
            topic=content_result.title,
            source_materials=source_text,
        )

        if extra_prompt:
            prompt += f"\n\n【额外要求】{extra_prompt}"

        if content_result.source_type == "github":
            prompt += f"\n\n【补充信息】这是一个GitHub仓库。仓库描述：{content_result.metadata.get('description', '')}。主要语言：{content_result.metadata.get('language', '')}。Star数：{content_result.metadata.get('stars', '')}。"
        elif content_result.source_type == "web":
            prompt += f"\n\n【补充信息】源链接：{content_result.url}"

        prompt += "\n\n请用HTML格式输出，使用 <h2> <h3> <p> <blockquote> <strong> <em> <ul> <li> <code> <pre> 等标签。文章中如果有代码示例，请用 <pre><code> 包裹。"

        result = self.provider.generate(prompt, temperature=0.85, max_tokens=6000)
        return self._extract_html(result.text)

    def _generate_titles(self, content_result: ContentResult, article: str) -> list:
        prompt_template = self.prompts.get("title_generation", "")
        summary = article[:1500]
        prompt = prompt_template.format(summary=summary)
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
            image_prompt = f"为以下公众号文章生成一张封面配图，风格简洁现代，科技感：{content_result.title}"
            image_path = self.provider.generate_image(image_prompt)
            return [{"path": image_path, "description": "AI生成配图", "type": "ai_generated"}]
        except NotImplementedError:
            logger.info("当前模型不支持图片生成，跳过AI配图")
            return []
        except Exception as e:
            logger.warning(f"AI配图生成失败: {e}")
            return []

    def _embed_images(self, html: str, images: list) -> str:
        for img in images:
            path = img.get("path", "")
            desc = img.get("description", "")
            if path and Path(path).exists():
                img_tag = f'<figure><img src="{path}" alt="{desc}" style="max-width:100%;"/><figcaption>{desc}</figcaption></figure>'
                html = img_tag + "\n" + html
        return html

    def _extract_html(self, text: str) -> str:
        if "```html" in text:
            text = text.split("```html", 1)[1]
            text = text.split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1]
            text = text.split("```", 1)[0]
        return text.strip()



