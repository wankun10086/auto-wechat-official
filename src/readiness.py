from dataclasses import dataclass

from src.ai.provider import list_provider_names, provider_supports_image
from src.config import Config


@dataclass
class ReadinessCheck:
    name: str
    ok: bool
    message: str
    severity: str = "error"


def collect_readiness(
    model: str | None = None,
    publish: bool = False,
    check_model: bool = True,
    check_research: bool = True,
) -> list[ReadinessCheck]:
    config = Config()
    checks = []
    ai_config = config.ai
    provider = model or ai_config.get("provider", "deepseek")

    if check_model:
        if provider not in list_provider_names():
            checks.append(ReadinessCheck("model", False, f"不支持的模型: {provider}"))
            return checks

        provider_config = ai_config.get(provider, {})
        missing = [key for key in ("api_key", "base_url", "model") if not provider_config.get(key)]
        if missing:
            checks.append(ReadinessCheck(
                "model_config",
                False,
                f"{provider} 缺少配置: {', '.join(missing)}",
            ))
        else:
            checks.append(ReadinessCheck("model_config", True, f"{provider} 文本模型配置完整", "info"))

        if provider_supports_image(provider):
            image_missing = []
            if provider in {"minimax", "glm"} and not provider_config.get("image_model"):
                image_missing.append("image_model")
            if image_missing:
                checks.append(ReadinessCheck(
                    "image_config",
                    False,
                    f"{provider} 图片生成缺少配置: {', '.join(image_missing)}",
                ))
            else:
                checks.append(ReadinessCheck("image_config", True, f"{provider} 支持 AI 配图", "info"))
        else:
            checks.append(ReadinessCheck(
                "image_config",
                True,
                f"{provider} 只支持文本；AI 配图会跳过，可依赖素材图片或改用 MiniMax/GLM",
                "warning",
            ))

    if check_research:
        research_config = config.get("research", default={}) or {}
        search_provider = research_config.get("search_provider", "duckduckgo")
        image_search_provider = research_config.get("image_search_provider", "auto")
        if search_provider == "serper" and not research_config.get("serper_api_key"):
            checks.append(ReadinessCheck("research", False, "网页检索选择 serper，但缺少 serper_api_key"))
        elif image_search_provider == "serper" and not research_config.get("serper_api_key"):
            checks.append(ReadinessCheck("research", False, "图片检索选择 serper，但缺少 serper_api_key"))
        else:
            checks.append(ReadinessCheck(
                "research",
                True,
                f"检索配置可用: search={search_provider}, image={image_search_provider}",
                "info",
            ))

    if publish:
        wechat_config = config.wechat
        missing_wechat = [key for key in ("app_id", "app_secret") if not wechat_config.get(key)]
        if missing_wechat:
            checks.append(ReadinessCheck(
                "wechat",
                False,
                f"微信草稿缺少配置: {', '.join(missing_wechat)}",
            ))
        else:
            checks.append(ReadinessCheck("wechat", True, "微信 AppID/AppSecret 已配置", "info"))

        if wechat_config.get("default_thumb_media_id"):
            checks.append(ReadinessCheck("cover", True, "默认封面 thumb_media_id 已配置", "info"))
        else:
            checks.append(ReadinessCheck(
                "cover",
                True,
                "未配置默认封面；发布时需要本次生成/检索到本地图片作为封面兜底",
                "warning",
            ))

    return checks


def readiness_ok(checks: list[ReadinessCheck]) -> bool:
    return all(check.ok or check.severity == "warning" for check in checks)
