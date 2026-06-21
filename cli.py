import asyncio
import argparse
import json
import sys
from pathlib import Path
from src.config import Config, setup_logging
from loguru import logger


AI_MODELS = ["deepseek", "kimi", "minimax", "glm"]


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
  python cli.py doctor --model minimax --publish
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # from-url 命令
    url_parser = subparsers.add_parser("from-url", help="从URL生成公众号文章")
    url_parser.add_argument("url", help="目标URL（GitHub仓库、技术文章、文档等）")
    url_parser.add_argument("--model", "-m", choices=AI_MODELS,
                            help="指定AI模型（默认使用config中的配置）")
    url_parser.add_argument("--style", "-s", default="tech_explanation",
                            choices=["tech_explanation", "product_review", "industry_analysis", "tutorial"],
                            help="文章风格（默认: tech_explanation）")
    url_parser.add_argument("--prompt", "-p", default="", help="额外的写作指令")
    url_parser.add_argument("--screenshot", default="",
                            help="截图目标，逗号分隔: code,charts,tables,images,all（默认不截图）")
    url_parser.add_argument("--no-images", action="store_true", help="不生成AI配图")
    url_parser.add_argument("--image-model", choices=AI_MODELS, help="指定AI配图模型（默认自动选择MiniMax/GLM）")
    url_parser.add_argument("--publish", action="store_true", help="生成后直接创建草稿")
    url_parser.add_argument("--output", "-o", help="输出文章HTML到文件")

    # from-file 命令
    file_parser = subparsers.add_parser("from-file", help="从本地文件生成公众号文章")
    file_parser.add_argument("file", help="本地文件路径（.md/.html/.txt）")
    file_parser.add_argument("--model", "-m", choices=AI_MODELS, help="指定AI模型")
    file_parser.add_argument("--style", "-s", default="tech_explanation",
                             choices=["tech_explanation", "product_review", "industry_analysis", "tutorial"],
                             help="文章风格")
    file_parser.add_argument("--prompt", "-p", default="", help="额外的写作指令")
    file_parser.add_argument("--screenshot", default="", help="截图目标（仅对URL有效，文件模式忽略）")
    file_parser.add_argument("--no-images", action="store_true", help="不生成AI配图")
    file_parser.add_argument("--image-model", choices=AI_MODELS, help="指定AI配图模型（默认自动选择MiniMax/GLM）")
    file_parser.add_argument("--publish", action="store_true", help="生成后直接创建草稿")
    file_parser.add_argument("--output", "-o", help="输出文章HTML到文件")

    topic_parser = subparsers.add_parser("from-topic", help="根据议题自动检索素材并生成公众号文章")
    topic_parser.add_argument("topic", help="要写作的议题，例如：AI Agent 产品趋势")
    topic_parser.add_argument("--model", "-m", choices=AI_MODELS, help="指定AI模型")
    topic_parser.add_argument("--style", "-s", default="tech_explanation",
                              choices=["tech_explanation", "product_review", "industry_analysis", "tutorial"],
                              help="文章风格")
    topic_parser.add_argument("--prompt", "-p", default="", help="额外的写作指令")
    topic_parser.add_argument("--no-images", action="store_true", help="不生成或嵌入配图")
    topic_parser.add_argument("--image-model", choices=AI_MODELS, help="指定AI配图模型（默认自动选择MiniMax/GLM）")
    topic_parser.add_argument("--publish", action="store_true", help="生成后直接创建微信草稿")
    topic_parser.add_argument("--output", "-o", help="输出文章HTML到文件")

    # login 命令
    subparsers.add_parser("login", help="微信扫码登录")

    # list 命令
    subparsers.add_parser("list", help="查看文章列表")

    draft_parser = subparsers.add_parser("draft", help="将已保存文章创建为微信草稿")
    draft_parser.add_argument("id", type=int, help="文章ID")

    # topics 命令
    subparsers.add_parser("topics", help="采集热点话题")

    # models 命令
    subparsers.add_parser("models", help="查看可用模型配置")

    doctor_parser = subparsers.add_parser("doctor", help="检查模型、检索和微信草稿配置")
    doctor_parser.add_argument("--model", "-m", choices=AI_MODELS, help="指定要检查的模型")
    doctor_parser.add_argument("--image-model", choices=AI_MODELS, help="指定要检查的AI配图模型")
    doctor_parser.add_argument("--publish", action="store_true", help="同时检查微信草稿发布前置项")

    return parser


async def cmd_from_url(args):
    from src.pipeline import ArticleGenerationPipeline

    if args.publish and not _ensure_ready_for_publish(args.model, args.image_model, not args.no_images):
        return

    pipeline = ArticleGenerationPipeline(model=args.model, image_model=args.image_model)
    result = await pipeline.run(
        source=args.url,
        source_type="url",
        style=args.style,
        extra_prompt=args.prompt,
        screenshot_targets=args.screenshot.split(",") if args.screenshot else [],
        generate_images=not args.no_images,
    )

    if not result:
        print(f"文章生成失败: {_pipeline_error(pipeline)}")
        return

    print(f"\n文章生成成功！")
    print(f"  标题: {result['title']}")
    print(f"  AI味得分: {result['ai_score']:.2f}")
    print(f"  截图数量: {len(result.get('screenshots', []))}")
    print(f"  AI配图: {len(result.get('ai_images', []))}")
    _print_warnings(result)

    if args.output:
        Path(args.output).write_text(result["content"], encoding="utf-8")
        print(f"  已保存到: {args.output}")

    if args.publish:
        pub_result = await pipeline.publish(result)
        if pub_result:
            print(f"  {_format_publish_success(pub_result)}")
        else:
            print(f"  草稿创建失败: {_publish_message(pub_result)}")


async def cmd_from_file(args):
    from src.pipeline import ArticleGenerationPipeline

    if not Path(args.file).exists():
        print(f"文件不存在: {args.file}")
        return

    if args.publish and not _ensure_ready_for_publish(args.model, args.image_model, not args.no_images):
        return

    pipeline = ArticleGenerationPipeline(model=args.model, image_model=args.image_model)
    result = await pipeline.run(
        source=args.file,
        source_type="file",
        style=args.style,
        extra_prompt=args.prompt,
        screenshot_targets=[],
        generate_images=not args.no_images,
    )

    if not result:
        print(f"文章生成失败: {_pipeline_error(pipeline)}")
        return

    print(f"\n文章生成成功！")
    print(f"  标题: {result['title']}")
    print(f"  AI味得分: {result['ai_score']:.2f}")
    _print_warnings(result)

    if args.output:
        Path(args.output).write_text(result["content"], encoding="utf-8")
        print(f"  已保存到: {args.output}")

    if args.publish:
        pub_result = await pipeline.publish(result)
        if pub_result:
            print(f"  {_format_publish_success(pub_result)}")
        else:
            print(f"  草稿创建失败: {_publish_message(pub_result)}")


async def cmd_from_topic(args):
    from src.pipeline import ArticleGenerationPipeline

    if args.publish and not _ensure_ready_for_publish(args.model, args.image_model, not args.no_images):
        return

    pipeline = ArticleGenerationPipeline(model=args.model, image_model=args.image_model)
    result = await pipeline.run(
        source=args.topic,
        source_type="topic",
        style=args.style,
        extra_prompt=args.prompt,
        screenshot_targets=[],
        generate_images=not args.no_images,
    )

    if not result:
        print(f"文章生成失败: {_pipeline_error(pipeline)}")
        return

    print("\n文章生成成功：")
    print(f"  标题: {result['title']}")
    print(f"  AI味得分: {result['ai_score']:.2f}")
    print(f"  素材配图: {len(result.get('material_images', []))}")
    print(f"  AI配图: {len(result.get('ai_images', []))}")
    if result.get("image_provider"):
        print(f"  AI配图模型: {result['image_provider']}")
    if result.get("research_query"):
        print(f"  检索词: {result['research_query']}")
    _print_sources(result)
    _print_warnings(result)

    if args.output:
        Path(args.output).write_text(result["content"], encoding="utf-8")
        print(f"  已保存到: {args.output}")

    if args.publish:
        pub_result = await pipeline.publish(result)
        if pub_result:
            print(f"  {_format_publish_success(pub_result)}")
        else:
            print(f"  草稿创建失败: {_publish_message(pub_result)}")


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


async def cmd_draft(args):
    from src.db.models import get_session, Article
    from src.pipeline import ArticleGenerationPipeline

    if not _ensure_ready_for_draft():
        return

    session = get_session()
    article = session.query(Article).get(args.id)
    if not article:
        session.close()
        print(f"文章不存在: {args.id}")
        return
    if article.status == "draft_created" and article.media_id:
        media_id = article.media_id
        session.close()
        print(f"已存在微信草稿: {media_id}")
        return

    result = {
        "id": article.id,
        "title": article.title,
        "content": article.final_content,
        "digest": article.digest or "",
    }
    result.update(_article_publish_metadata(article))
    session.close()

    pipeline = ArticleGenerationPipeline(init_provider=False)
    pub_result = await pipeline.publish(result)
    if pub_result:
        print(_format_publish_success(pub_result))
    else:
        print(f"草稿创建失败: {_publish_message(pub_result)}")


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
    for name in AI_MODELS:
        provider_config = ai_config.get(name, {})
        model = provider_config.get("model", "未配置")
        has_key = "✅" if provider_config.get("api_key") else "❌ 未配置API Key"
        marker = " ← 当前" if name == current else ""
        print(f"  {name:12s} | 模型: {model:20s} | {has_key}{marker}")

    print(f"\n切换方式: python cli.py from-url <url> --model <name>")


def cmd_doctor(args) -> int:
    from src.readiness import collect_readiness, readiness_ok

    checks = collect_readiness(model=args.model, image_model=args.image_model, publish=args.publish)
    print("\n配置检查:\n")
    icons = {"error": "[ERR]", "warning": "[WARN]", "info": "[OK]"}
    for item in checks:
        icon = icons.get(item.severity, "•")
        if item.ok and item.severity != "warning":
            icon = "[OK]"
        elif not item.ok:
            icon = "[ERR]"
        print(f"  {icon} {item.name}: {item.message}")

    ok = readiness_ok(checks)
    print("\n结果: " + ("可运行" if ok else "存在阻断项，请先补齐配置"))
    return 0 if ok else 1


def _ensure_ready_for_publish(model: str | None, image_model: str | None, generate_images: bool) -> bool:
    from src.readiness import collect_readiness, readiness_ok

    checks = collect_readiness(
        model=model,
        image_model=image_model,
        publish=True,
        generate_images=generate_images,
    )
    if readiness_ok(checks):
        return True

    print("\n草稿发布前置检查未通过：")
    for item in checks:
        if not item.ok and item.severity != "warning":
            print(f"  - {item.message}")
    print("可运行 `python cli.py doctor --publish` 查看完整检查。")
    return False


def _ensure_ready_for_draft() -> bool:
    from src.readiness import collect_readiness, readiness_ok

    checks = collect_readiness(publish=True, check_model=False, check_research=False)
    if readiness_ok(checks):
        return True

    print("\n草稿创建前置检查未通过：")
    for item in checks:
        if not item.ok and item.severity != "warning":
            print(f"  - {item.message}")
    print("可运行 `python cli.py doctor --publish` 查看完整检查。")
    return False


def _publish_message(result) -> str:
    return getattr(result, "message", "") or "推送失败"


def _format_publish_success(result) -> str:
    message = getattr(result, "message", "") or "草稿创建成功"
    media_id = getattr(result, "media_id", "") or ""
    return f"{message}: {media_id}" if media_id else message


def _pipeline_error(pipeline) -> str:
    return getattr(pipeline, "last_error", "") or "未知错误"


def _print_sources(result: dict) -> None:
    urls = result.get("source_urls", []) or []
    if not urls:
        return
    print("  检索来源:")
    for idx, url in enumerate(urls[:5], 1):
        print(f"    {idx}. {url}")


def _print_warnings(result: dict) -> None:
    for warning in result.get("warnings", []) or []:
        print(f"  注意: {warning}")


def _article_publish_metadata(article) -> dict:
    metadata = _article_notes(article)
    return {
        "screenshots": metadata.get("screenshots", []) or [],
        "material_images": metadata.get("material_images", []) or [],
        "ai_images": metadata.get("ai_images", []) or [],
    }


def _article_notes(article) -> dict:
    try:
        data = json.loads(article.notes or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


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
    elif args.command == "from-topic":
        asyncio.run(cmd_from_topic(args))
    elif args.command == "login":
        asyncio.run(cmd_login())
    elif args.command == "list":
        cmd_list()
    elif args.command == "draft":
        asyncio.run(cmd_draft(args))
    elif args.command == "topics":
        asyncio.run(cmd_topics())
    elif args.command == "models":
        cmd_models()
    elif args.command == "doctor":
        raise SystemExit(cmd_doctor(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
