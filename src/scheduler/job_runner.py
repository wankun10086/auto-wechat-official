import asyncio
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from src.config import Config, setup_logging
from src.content.hot_topics import HotTopicCollector
from src.db.models import Article, HotTopic, PublishLog, get_session
from src.pipeline import ArticleGenerationPipeline
from src.readiness import collect_readiness, readiness_ok
from src.wechat.publisher import WeChatPublisher


STYLE_BY_STRATEGY = {
    "hot_tech": "tech_explanation",
    "deep_analysis": "industry_analysis",
}
VALID_STYLES = {"tech_explanation", "product_review", "industry_analysis", "tutorial"}


class ArticlePipeline:
    def __init__(self):
        self.config = Config()
        self.hot_collector = HotTopicCollector()
        self.publisher = WeChatPublisher()
        self.db_path = self.config.get("database", "path", default="data/articles.db")

    async def run_full_pipeline(self, topic_strategy="hot_tech"):
        session = get_session(self.db_path)
        try:
            checks = collect_readiness(publish=True)
            if not readiness_ok(checks):
                blockers = "；".join(item.message for item in checks if not item.ok and item.severity != "warning")
                logger.error(f"配置检查未通过，跳过调度任务: {blockers}")
                return None

            topic_info = await self._select_topic(topic_strategy, session)
            if not topic_info:
                logger.warning("未找到合适的话题")
                return None

            logger.info(f"选定话题: {topic_info['title']}")
            style = self._style_for_strategy(topic_strategy)
            extra_prompt = self._topic_context_prompt(topic_info, topic_strategy)

            pipeline = ArticleGenerationPipeline()
            result = await pipeline.run(
                source=topic_info["title"],
                source_type="topic",
                style=style,
                extra_prompt=extra_prompt,
                screenshot_targets=[],
                generate_images=True,
            )
            if not result:
                logger.warning(f"流水线未产出文章: {getattr(pipeline, 'last_error', '') or '未知错误'}")
                return None
            for warning in result.get("warnings", []) or []:
                logger.warning(f"流水线警告: {warning}")

            publish_result = await pipeline.publish(result)
            self._log_action(
                session,
                result["id"],
                "create_draft",
                "success" if publish_result else "failed",
                None if publish_result else getattr(publish_result, "message", "draft creation returned false"),
            )

            article = session.query(Article).get(result["id"])
            if article:
                article.topic_strategy = topic_strategy
                session.commit()
                logger.info(f"流程完成: {article.title} / {article.status}")
            return article

        except Exception as e:
            logger.error(f"流程失败: {e}")
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

    def _style_for_strategy(self, strategy):
        if strategy in VALID_STYLES:
            return strategy
        return STYLE_BY_STRATEGY.get(strategy, "tech_explanation")

    def _topic_context_prompt(self, topic_info, strategy):
        parts = [f"调度策略：{strategy}。"]
        if topic_info.get("source"):
            parts.append(f"热点来源：{topic_info['source']}。")
        if topic_info.get("url"):
            parts.append(f"热点原始链接：{topic_info['url']}。")
        if topic_info.get("description"):
            parts.append(f"话题描述：{topic_info['description']}。")
        return "\n".join(parts)

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
