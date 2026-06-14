import asyncio
import sys
from src.config import Config, setup_logging
from loguru import logger


def main():
    config = Config()
    config.load()
    setup_logging(config)

    if len(sys.argv) < 2:
        print_usage()
        return

    command = sys.argv[1]

    if command == "generate":
        asyncio.run(cmd_generate())
    elif command == "publish":
        article_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
        asyncio.run(cmd_publish(article_id))
    elif command == "full":
        strategy = sys.argv[2] if len(sys.argv) > 2 else "hot_tech"
        asyncio.run(cmd_full(strategy))
    elif command == "login":
        asyncio.run(cmd_login())
    elif command == "scheduler":
        asyncio.run(cmd_scheduler())
    elif command == "topics":
        asyncio.run(cmd_topics())
    elif command == "list":
        cmd_list()
    else:
        print(f"未知命令: {command}")
        print_usage()


def print_usage():
    print("""
微信公众号自动化发布系统
========================

用法:
  python main.py <命令> [参数]

命令:
  generate          生成文章（不发布）
  publish [id]      通过浏览器发布文章
  full [strategy]   完整流程：生成+创建草稿
  login             微信扫码登录
  scheduler         启动定时调度器
  topics            采集热点话题
  list              查看文章列表

示例:
  python main.py full hot_tech
  python main.py publish 1
  python main.py scheduler
""")


async def cmd_generate():
    from src.scheduler.job_runner import ArticlePipeline
    pipeline = ArticlePipeline()
    result = await pipeline.run_full_pipeline()
    if result:
        print(f"文章生成成功！")
        print(f"  标题: {result.title}")
        print(f"  AI味得分: {result.ai_score:.2f}")
        print(f"  状态: {result.status}")
    else:
        print("文章生成失败")


async def cmd_publish(article_id=None):
    from src.scheduler.job_runner import ArticlePipeline
    pipeline = ArticlePipeline()
    result = await pipeline.publish_via_browser(article_id)
    if result:
        print("发布成功！")
    else:
        print("发布失败")


async def cmd_full(strategy):
    from src.scheduler.job_runner import ArticlePipeline
    pipeline = ArticlePipeline()
    result = await pipeline.run_full_pipeline(strategy)
    if result:
        print(f"文章生成完成！")
        print(f"  标题: {result.title}")
        print(f"  AI味得分: {result.ai_score:.2f}")
        print(f"  草稿ID: {result.media_id or '未创建'}")
        print(f"  状态: {result.status}")

        if result.media_id:
            choice = input("\n是否立即通过浏览器发布？(y/n): ")
            if choice.lower() == "y":
                pub_result = await pipeline.publish_via_browser(result.id)
                if pub_result:
                    print("发布成功！")
                else:
                    print("发布失败，请手动在后台发布")
    else:
        print("流程失败")


async def cmd_login():
    from src.wechat.publisher import WeChatPublisher
    publisher = WeChatPublisher()
    await publisher.start()
    success = await publisher.login(force_qr=True)
    if success:
        print("登录成功！Cookie已保存。")
    else:
        print("登录失败，请重试。")
    await publisher.stop()


async def cmd_scheduler():
    from src.scheduler.job_runner import AppScheduler
    scheduler = AppScheduler()
    await scheduler.start()


async def cmd_topics():
    from src.content.hot_topics import HotTopicCollector
    collector = HotTopicCollector()
    topics = await collector.collect_all()
    print(f"\n采集到 {len(topics)} 条热点话题:\n")
    for i, t in enumerate(topics, 1):
        print(f"  {i}. [{t['source']}] {t['title']}")
        if t.get("url"):
            print(f"     {t['url']}")


def cmd_list():
    from src.db.models import get_session, Article
    session = get_session()
    articles = session.query(Article).order_by(Article.created_at.desc()).limit(20).all()
    if not articles:
        print("暂无文章记录")
        return
    print(f"\n最近 {len(articles)} 篇文章:\n")
    for a in articles:
        status_icon = {"draft": " ", "draft_created": " ", "published": "✅", "failed": "❌"}.get(a.status, "❓")
        print(f"  {status_icon} [{a.id}] {a.title}")
        print(f"     状态: {a.status} | AI味: {a.ai_score or 0:.2f} | 创建: {a.created_at.strftime('%m-%d %H:%M')}")
    session.close()


if __name__ == "__main__":
    main()
