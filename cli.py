import asyncio
import argparse
import sys
from pathlib import Path
from src.config import Config, setup_logging
from loguru import logger


def build_parser():
    parser = argparse.ArgumentParser(
        prog="auto-wechat",
        description="微信公众号自动化发布系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cli.py from-url https://github.com/user/repo
  python cli.py from-url https://36kr.com/p/123 --style deep
  python cli.py from-url https://example.com --model kimi --screenshot code,charts
  python cli.py from-file ./readme.md --style tech
  python cli.py from-url https://... --prompt "写成入门教程风格"
  python cli.py from-url https://... --model minimax --publish
  python cli.py login
  python cli.py list
  python cli.py topics
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # from-url 命令
    url_parser = subparsers.add_parser("from-url", help="从URL生成公众号文章")
    url_parser.add_argument("url", help="目标URL（GitHub仓库、技术文章、文档等）")
    url_parser.add_argument("--model", "-m", choices=["deepseek", "kimi", "minimax"],
                            help="指定AI模型（默认使用config中的配置）")
    url_parser.add_argument("--style", "-s", default="tech_explanation",
                            choices=["tech_explanation", "product_review", "industry_analysis", "tutorial"],
                            help="文章风格（默认: tech_explanation）")
    url_parser.add_argument("--prompt", "-p", default="", help="额外的写作指令")
    url_parser.add_argument("--screenshot", default="",
                            help="截图目标，逗号分隔: code,charts,tables,images,all（默认不截图）")
    url_parser.add_argument("--no-images", action="store_true", help="不生成AI配图")
    url_parser.add_argument("--publish", action="store_true", help="生成后直接创建草稿")
    url_parser.add_argument("--output", "-o", help="输出文章HTML到文件")

    # from-file 命令
    file_parser = subparsers.add_parser("from-file", help="从本地文件生成公众号文章")
    file_parser.add_argument("file", help="本地文件路径（.md/.html/.txt）")
    file_parser.add_argument("--model", "-m", choices=["deepseek", "kimi", "minimax"], help="指定AI模型")
    file_parser.add_argument("--style", "-s", default="tech_explanation",
                             choices=["tech_explanation", "product_review", "industry_analysis", "tutorial"],
                             help="文章风格")
    file_parser.add_argument("--prompt", "-p", default="", help="额外的写作指令")
    file_parser.add_argument("--screenshot", default="", help="截图目标（仅对URL有效，文件模式忽略）")
    file_parser.add_argument("--no-images", action="store_true", help="不生成AI配图")
    file_parser.add_argument("--publish", action="store_true", help="生成后直接创建草稿")
    file_parser.add_argument("--output", "-o", help="输出文章HTML到文件")

    # login 命令
    subparsers.add_parser("login", help="微信扫码登录")

    # list 命令
    subparsers.add_parser("list", help="查看文章列表")

    # topics 命令
    subparsers.add_parser("topics", help="采集热点话题")

    # models 命令
    subparsers.add_parser("models", help="查看可用模型配置")

    return parser


async def cmd_from_url(args):
    from src.pipeline import ArticleGenerationPipeline

    pipeline = ArticleGenerationPipeline(model=args.model)
    result = await pipeline.run(
        source=args.url,
        source_type="url",
        style=args.style,
        extra_prompt=args.prompt,
        screenshot_targets=args.screenshot.split(",") if args.screenshot else [],
        generate_images=not args.no_images,
    )

    if not result:
        print("文章生成失败")
        return

    print(f"\n文章生成成功！")
    print(f"  标题: {result['title']}")
    print(f"  AI味得分: {result['ai_score']:.2f}")
    print(f"  截图数量: {len(result.get('screenshots', []))}")
    print(f"  AI配图: {len(result.get('ai_images', []))}")

    if args.output:
        Path(args.output).write_text(result["content"], encoding="utf-8")
        print(f"  已保存到: {args.output}")

    if args.publish:
        from src.pipeline import ArticleGenerationPipeline
        pub_result = await pipeline.publish(result)
        if pub_result:
            print("  草稿创建成功！")
        else:
            print("  草稿创建失败")


async def cmd_from_file(args):
    from src.pipeline import ArticleGenerationPipeline

    if not Path(args.file).exists():
        print(f"文件不存在: {args.file}")
        return

    pipeline = ArticleGenerationPipeline(model=args.model)
    result = await pipeline.run(
        source=args.file,
        source_type="file",
        style=args.style,
        extra_prompt=args.prompt,
        screenshot_targets=[],
        generate_images=not args.no_images,
    )

    if not result:
        print("文章生成失败")
        return

    print(f"\n文章生成成功！")
    print(f"  标题: {result['title']}")
    print(f"  AI味得分: {result['ai_score']:.2f}")

    if args.output:
        Path(args.output).write_text(result["content"], encoding="utf-8")
        print(f"  已保存到: {args.output}")

    if args.publish:
        pub_result = await pipeline.publish(result)
        if pub_result:
            print("  草稿创建成功！")


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


async def cmd_topics():
    from src.content.hot_topics import HotTopicCollector
    collector = HotTopicCollector()
    topics = await collector.collect_all()
    print(f"\n采集到 {len(topics)} 条热点话题:\n")
    for i, t in enumerate(topics, 1):
        print(f"  {i}. [{t['source']}] {t['title']}")
        if t.get("url"):
            print(f"     {t['url']}")


def cmd_models():
    config = Config()
    ai_config = config.ai
    current = ai_config.get("provider", "deepseek")

    print(f"\n当前模型: {current}\n")
    print("可用模型:")
    for name in ["deepseek", "kimi", "minimax"]:
        provider_config = ai_config.get(name, {})
        model = provider_config.get("model", "未配置")
        has_key = "✅" if provider_config.get("api_key") else "❌ 未配置API Key"
        marker = " ← 当前" if name == current else ""
        print(f"  {name:12s} | 模型: {model:20s} | {has_key}{marker}")

    print(f"\n切换方式: python cli.py from-url <url> --model <name>")


def main():
    parser = build_parser()
    args = parser.parse_args()

    config = Config()
    config.load()
    setup_logging(config)

    if not args.command:
        parser.print_help()
        return

    if args.command == "from-url":
        asyncio.run(cmd_from_url(args))
    elif args.command == "from-file":
        asyncio.run(cmd_from_file(args))
    elif args.command == "login":
        asyncio.run(cmd_login())
    elif args.command == "list":
        cmd_list()
    elif args.command == "topics":
        asyncio.run(cmd_topics())
    elif args.command == "models":
        cmd_models()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
