import asyncio
import signal
import sys
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from src.config import Config, setup_logging
from src.db.models import get_session, Article, HotTopic, PublishLog
from src.content.generator import ContentGenerator
from src.content.humanizer import Humanizer
from src.content.template import ArticleTemplate
from src.content.hot_topics import HotTopicCollector
from src.wechat.api_client import WeChatAPIClient
from src.wechat.publisher import WeChatPublisher


class ArticlePipeline:
    def __init__(self):
        config = Config()
        self.config = config

        wechat_cfg = config.wechat
        self.api_client = WeChatAPIClient(wechat_cfg["app_id"], wechat_cfg["app_secret"])
        self.author = wechat_cfg.get("author", "")

        self.generator = ContentGenerator()
        self.humanizer = Humanizer(self.generator)
        self.template = ArticleTemplate()
        self.hot_collector = HotTopicCollector()
        self.publisher = WeChatPublisher()

        self.db_path = config.get("database", "path", default="data/articles.db")

    async def run_full_pipeline(self, topic_strategy="hot_tech"):
        session = get_session(self.db_path)
        article_record = None
        try:
            topic_info = await self._select_topic(topic_strategy, session)
            if not topic_info:
                logger.warning("未找到合适的话题")
                return None

            logger.info(f"选定话题: {topic_info['title']}")

            source_materials = ""
            if topic_info.get("url"):
                source_materials = await self.hot_collector.fetch_article_content(topic_info["url"])

            raw_content = self.generator.generate_article(
                topic_info["title"], source_materials
            )

            final_content, ai_score = self.humanizer.full_pipeline(raw_content)
            final_content = self.template.wrap_article(final_content)

            summary = self.generator.generate_digest(final_content)
            titles = self.generator.generate_titles(summary)
            title = titles[0] if titles else topic_info["title"]
            digest = self.generator.generate_digest(final_content)

            article_record = Article(
                title=title,
                raw_content=raw_content,
                final_content=final_content,
                digest=digest,
                author=self.author,
                topic=topic_info["title"],
                topic_strategy=topic_strategy,
                ai_score=ai_score,
                status="draft",
            )
            session.add(article_record)
            session.commit()
            logger.info(f"文章已保存到数据库，ID: {article_record.id}")

            thumb_media_id = self.config.get("wechat", "default_thumb_media_id", default="")
            if not thumb_media_id:
                logger.warning("未配置默认封面图 thumb_media_id，跳过草稿创建")
                return article_record

            media_id = self.api_client.create_draft(
                title=title,
                content=final_content,
                thumb_media_id=thumb_media_id,
                author=self.author,
                digest=digest,
            )
            article_record.media_id = media_id
            article_record.status = "draft_created"
            session.commit()

            self._log_action(session, article_record.id, "create_draft", "success")
            logger.info(f"流程完成，草稿media_id: {media_id}")
            return article_record

        except Exception as e:
            logger.error(f"流程失败: {e}")
            if article_record:
                article_record.status = "failed"
                session.commit()
                self._log_action(session, article_record.id, "pipeline", "failed", str(e))
            return None
        finally:
            session.close()

    async def publish_via_browser(self, article_id=None):
        session = get_session(self.db_path)
        try:
            await self.publisher.start()

            if not await self.publisher.is_logged_in():
                success = await self.publisher.login()
                if not success:
                    logger.error("登录失败，无法发布")
                    return False

            result = await self.publisher.publish_draft_via_mass_send()
            if result and article_id:
                article = session.query(Article).get(article_id)
                if article:
                    article.status = "published"
                    article.published_at = datetime.now()
                    session.commit()
            return result
        finally:
            await self.publisher.stop()
            session.close()

    async def _select_topic(self, strategy, session):
        existing = session.query(HotTopic).filter_by(used=False).order_by(
            HotTopic.hot_score.desc()
        ).first()
        if existing:
            existing.used = True
            session.commit()
            return {
                "title": existing.title,
                "source": existing.source,
                "url": existing.url,
                "description": existing.description,
            }

        topics = await self.hot_collector.collect_all()
        for t in topics:
            topic = HotTopic(
                title=t["title"],
                source=t["source"],
                url=t.get("url", ""),
                description=t.get("description", ""),
                hot_score=t.get("hot_score", 0),
            )
            session.add(topic)
        session.commit()

        if topics:
            topic = topics[0]
            db_topic = session.query(HotTopic).filter_by(title=topic["title"]).first()
            if db_topic:
                db_topic.used = True
                session.commit()
            return {
                "title": topic["title"],
                "source": topic["source"],
                "url": topic.get("url", ""),
                "description": topic.get("description", ""),
            }
        return None

    def _log_action(self, session, article_id, action, status, error=None):
        log = PublishLog(
            article_id=article_id,
            action=action,
            status=status,
            error_message=error,
        )
        session.add(log)
        session.commit()


class AppScheduler:
    def __init__(self):
        self.config = Config()
        self.scheduler = AsyncIOScheduler()
        self.pipeline = ArticlePipeline()

    def setup_jobs(self):
        jobs = self.config.get("schedule", "jobs", default=[])
        for job_cfg in jobs:
            if not job_cfg.get("enabled", True):
                continue

            name = job_cfg["name"]
            cron_expr = job_cfg["cron"]
            topic_strategy = job_cfg.get("topic_strategy", "hot_tech")

            parts = cron_expr.split()
            if len(parts) == 5:
                trigger = CronTrigger(
                    minute=parts[0],
                    hour=parts[1],
                    day=parts[2],
                    month=parts[3],
                    day_of_week=parts[4],
                )
                self.scheduler.add_job(
                    self._run_job,
                    trigger=trigger,
                    args=[topic_strategy],
                    id=name,
                    name=name,
                    replace_existing=True,
                )
                logger.info(f"已添加定时任务: {name} ({cron_expr})")

    async def _run_job(self, topic_strategy):
        logger.info(f"开始执行定时任务: {topic_strategy}")
        try:
            result = await self.pipeline.run_full_pipeline(topic_strategy)
            if result:
                logger.info(f"任务完成: {result.title}")
            else:
                logger.warning("任务未产出文章")
        except Exception as e:
            logger.error(f"任务执行失败: {e}")

    async def run_once(self, topic_strategy="hot_tech"):
        logger.info(f"手动执行一次: {topic_strategy}")
        return await self.pipeline.run_full_pipeline(topic_strategy)

    async def start(self):
        self.setup_jobs()
        self.scheduler.start()
        logger.info("调度器已启动，等待定时任务...")

        stop_event = asyncio.Event()

        def signal_handler():
            logger.info("收到停止信号")
            stop_event.set()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                pass

        await stop_event.wait()
        self.scheduler.shutdown()
        logger.info("调度器已停止")


def main():
    config = Config()
    config.load()
    setup_logging(config)

    if len(sys.argv) > 1:
        command = sys.argv[1]
        scheduler = AppScheduler()

        if command == "run":
            strategy = sys.argv[2] if len(sys.argv) > 2 else "hot_tech"
            asyncio.run(scheduler.run_once(strategy))
        elif command == "start":
            asyncio.run(scheduler.start())
        elif command == "login":
            from src.wechat.publisher import WeChatPublisher
            publisher = WeChatPublisher()
            asyncio.run(_login(publisher))
        else:
            print("用法:")
            print("  python -m src.scheduler.job_runner run [strategy]  - 手动执行一次")
            print("  python -m src.scheduler.job_runner start           - 启动定时调度")
            print("  python -m src.scheduler.job_runner login           - 微信扫码登录")
    else:
        print("用法:")
        print("  python -m src.scheduler.job_runner run [strategy]  - 手动执行一次")
        print("  python -m src.scheduler.job_runner start           - 启动定时调度")
        print("  python -m src.scheduler.job_runner login           - 微信扫码登录")


async def _login(publisher):
    await publisher.start()
    success = await publisher.login(force_qr=True)
    if success:
        print("登录成功，Cookie已保存")
    else:
        print("登录失败")
    await publisher.stop()


if __name__ == "__main__":
    main()
