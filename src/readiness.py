from dataclasses import dataclass
from pathlib import Path
import re

from src.ai.provider import (
    get_provider,
    is_placeholder_value,
    list_provider_names,
    provider_config_missing,
    provider_supports_image,
    resolve_provider_name,
    resolve_image_provider_name,
)
from src.config import Config
from src.wechat.api_client import WeChatAPIClient


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
            configured_image_provider = str(ai_config.get("image_provider") or "").strip().lower()
            explicitly_requested_image = bool(
                image_model and image_model.strip().lower() not in {"auto", "none"}
            ) or bool(configured_image_provider and configured_image_provider not in {"auto", "none"})
            image_provider = resolve_image_provider_name(image_model, provider)
            if not image_provider:
                configured_issue = _configured_image_provider_issue(ai_config)
                if configured_issue:
                    checks.append(ReadinessCheck(
                        "image_config",
                        True,
                        f"{configured_issue}；会跳过 AI 配图",
                        "warning",
                    ))
                else:
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


def _configured_image_provider_issue(ai_config: dict) -> str:
    for provider_name in ("minimax", "glm"):
        provider_config = ai_config.get(provider_name, {}) or {}
        configured = any(
            provider_config.get(key)
            for key in ("api_key", "base_url", "image_base_url", "model", "image_model")
        )
        if not configured:
            continue
        missing = provider_config_missing(provider_name, provider_config, require_image=True)
        if missing:
            return f"{provider_name} 图片生成配置不可用: {', '.join(missing)}"
    return ""


def collect_live_readiness(
    model: str | None = None,
    image_model: str | None = None,
    publish: bool = False,
    generate_images: bool = True,
) -> list[ReadinessCheck]:
    """Run explicit live checks that may call paid or rate-limited remote APIs."""
    config = Config()
    ai_config = config.ai
    provider_name = resolve_provider_name(model)
    checks = []

    try:
        provider = get_provider(provider_name)
        result = provider.generate("连通性测试：请只回复 OK。", temperature=0, max_tokens=20)
        if result and (result.text or "").strip():
            checks.append(ReadinessCheck("model_live", True, f"{provider_name} 文本模型实测可用", "info"))
        else:
            checks.append(ReadinessCheck("model_live", False, f"{provider_name} 文本模型返回空内容"))
    except Exception as e:
        checks.append(ReadinessCheck("model_live", False, f"{provider_name} 文本模型实测失败: {_safe_error(e)}"))

    if generate_images:
        image_provider = resolve_image_provider_name(image_model, provider_name)
        if not image_provider:
            configured_issue = _configured_image_provider_issue(ai_config)
            if configured_issue:
                checks.append(ReadinessCheck("image_live", False, f"{configured_issue}；无法实测 AI 配图"))
            else:
                checks.append(ReadinessCheck("image_live", True, "未配置可用 AI 配图模型；跳过图片实测", "warning"))
        elif not provider_supports_image(image_provider):
            checks.append(ReadinessCheck("image_live", False, f"{image_provider} 不支持图片生成"))
        elif provider_config_missing(image_provider, ai_config.get(image_provider, {}), require_image=True):
            checks.append(ReadinessCheck("image_live", False, f"{image_provider} 图片生成配置不完整，无法实测"))
        else:
            try:
                image_provider_obj = provider if image_provider == provider_name else get_provider(image_provider)
                image_path = image_provider_obj.generate_image(
                    "微信公众号封面连通性测试图：AI Agent 产品趋势，科技媒体风格，不要文字水印。"
                )
                if image_path and Path(image_path).exists():
                    checks.append(ReadinessCheck("image_live", True, f"{image_provider} AI 配图实测可用", "info"))
                else:
                    checks.append(ReadinessCheck("image_live", False, f"{image_provider} 图片接口未返回本地文件"))
            except Exception as e:
                checks.append(ReadinessCheck("image_live", False, f"{image_provider} AI 配图实测失败: {_safe_error(e)}"))
    else:
        checks.append(ReadinessCheck("image_live", True, "已跳过 AI 配图实测", "info"))

    if publish:
        wechat = config.wechat
        try:
            data = WeChatAPIClient(wechat.get("app_id", ""), wechat.get("app_secret", "")).get_draft_count()
            if isinstance(data, dict) and data.get("errcode"):
                checks.append(ReadinessCheck("wechat_live", False, f"微信草稿接口实测失败: {_safe_error(data)}"))
            else:
                checks.append(ReadinessCheck("wechat_live", True, "微信草稿接口实测可用", "info"))
        except Exception as e:
            checks.append(ReadinessCheck("wechat_live", False, f"微信草稿接口实测失败: {_safe_error(e)}"))

    return checks


def _safe_error(error) -> str:
    message = str(error)
    message = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-***", message)
    message = re.sub(r"(?i)(api[_-]?key['\"]?\s*[:=]\s*['\"]?)[^,'\"}\s]+", r"\1***", message)
    return message[:300]
