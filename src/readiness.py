from dataclasses import dataclass

from src.ai.provider import (
    is_placeholder_value,
    list_provider_names,
    provider_config_missing,
    provider_supports_image,
    resolve_image_provider_name,
)
from src.config import Config


@dataclass
class ReadinessCheck:
    name: str
    ok: bool
    message: str
    severity: str = "error"


def collect_readiness(
    model: str | None = None,
    image_model: str | None = None,
    publish: bool = False,
    check_model: bool = True,
    check_research: bool = True,
    generate_images: bool = True,
) -> list[ReadinessCheck]:
    config = Config()
    checks = []
    ai_config = config.ai
    provider = model or ai_config.get("provider", "deepseek")

    if check_model:
        if provider not in list_provider_names(include_mock=True):
            checks.append(ReadinessCheck("model", False, f"不支持的模型: {provider}"))
            return checks

        provider_config = ai_config.get(provider, {})
        missing = provider_config_missing(provider, provider_config)
        if missing:
            checks.append(ReadinessCheck(
                "model_config",
                False,
                f"{provider} 缺少配置: {', '.join(missing)}",
            ))
        else:
            checks.append(ReadinessCheck("model_config", True, f"{provider} 文本模型配置完整", "info"))

        if generate_images:
            explicitly_requested_image = bool(image_model and image_model.strip().lower() not in {"auto", "none"})
            image_provider = resolve_image_provider_name(image_model, provider)
            if not image_provider:
                checks.append(ReadinessCheck(
                    "image_config",
                    True,
                    "未配置可用 AI 配图模型；会使用素材图片并跳过 AI 配图",
                    "warning",
                ))
            elif image_provider not in list_provider_names(include_mock=True):
                checks.append(ReadinessCheck(
                    "image_config",
                    not explicitly_requested_image,
                    (
                        f"不支持的 AI 配图模型: {image_provider}"
                        if explicitly_requested_image
                        else f"不支持的 AI 配图模型: {image_provider}；会跳过 AI 配图"
                    ),
                    "error" if explicitly_requested_image else "warning",
                ))
            elif not provider_supports_image(image_provider):
                checks.append(ReadinessCheck(
                    "image_config",
                    not explicitly_requested_image,
                    (
                        f"{image_provider} 不支持图片生成"
                        if explicitly_requested_image
                        else f"{image_provider} 只支持文本；会跳过 AI 配图"
                    ),
                    "error" if explicitly_requested_image else "warning",
                ))
            else:
                image_missing = provider_config_missing(
                    image_provider,
                    ai_config.get(image_provider, {}),
                    require_image=True,
                )
                if image_missing:
                    checks.append(ReadinessCheck(
                        "image_config",
                        not explicitly_requested_image,
                        (
                            f"{image_provider} 图片生成缺少配置: {', '.join(image_missing)}"
                            if explicitly_requested_image
                            else f"{image_provider} 图片生成缺少配置: {', '.join(image_missing)}；会跳过 AI 配图"
                        ),
                        "error" if explicitly_requested_image else "warning",
                    ))
                else:
                    checks.append(ReadinessCheck("image_config", True, f"AI 配图模型可用: {image_provider}", "info"))
        else:
            checks.append(ReadinessCheck("image_config", True, "本次不生成 AI 配图", "info"))

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
        missing_wechat = [
            key
            for key in ("app_id", "app_secret")
            if not wechat_config.get(key) or is_placeholder_value(wechat_config.get(key))
        ]
        if missing_wechat:
            checks.append(ReadinessCheck(
                "wechat",
                False,
                f"微信草稿缺少有效配置: {', '.join(missing_wechat)}",
            ))
        else:
            checks.append(ReadinessCheck("wechat", True, "微信 AppID/AppSecret 已配置", "info"))

        thumb_media_id = wechat_config.get("default_thumb_media_id")
        if thumb_media_id and not is_placeholder_value(thumb_media_id):
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
