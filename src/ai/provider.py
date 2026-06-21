from abc import ABC, abstractmethod
from dataclasses import dataclass
import re
from loguru import logger
from src.config import Config


@dataclass
class GenerateResult:
    text: str
    usage: dict = None


class BaseProvider(ABC):
    def __init__(self, config: dict):
        self.config = config
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "")
        self.model = config.get("model", "")

    @abstractmethod
    def generate(self, prompt: str, system: str = "", temperature: float = 0.85, max_tokens: int = 4000) -> GenerateResult:
        pass

    @abstractmethod
    def generate_image(self, prompt: str, **kwargs) -> str:
        pass


IMAGE_PROVIDER_NAMES = ["minimax", "glm"]
PLACEHOLDER_MARKERS = (
    "your-",
    "your_",
    "sk-your-",
    "replace-",
    "todo-",
    "请填写",
    "填入",
    "待填写",
)


def get_provider(name: str = None) -> BaseProvider:
    config = Config()
    ai_config = config.ai
    provider_name = resolve_provider_name(name)
    provider_config = ai_config.get(provider_name, {})

    from src.ai.deepseek import DeepSeekProvider
    from src.ai.glm import GLMProvider
    from src.ai.kimi import KimiProvider
    from src.ai.minimax import MiniMaxProvider
    from src.ai.mock import MockProvider

    providers = {
        "deepseek": DeepSeekProvider,
        "glm": GLMProvider,
        "kimi": KimiProvider,
        "minimax": MiniMaxProvider,
        "mock": MockProvider,
    }

    cls = providers.get(provider_name)
    if not cls:
        raise ValueError(f"不支持的provider: {provider_name}，可选: {list(providers.keys())}")

    _validate_provider_config(provider_name, provider_config)
    logger.info(f"使用AI模型: {provider_name} / {provider_config.get('model', '')}")
    return cls(provider_config)


def _validate_provider_config(provider_name: str, provider_config: dict) -> None:
    if provider_name == "mock":
        return
    missing = provider_config_missing(provider_name, provider_config)
    if missing:
        raise ValueError(
            f"{provider_name} 配置缺失: {', '.join(missing)}。"
            "请在 config/config.yaml 或 Web 设置中填写后再使用。"
        )


def resolve_provider_name(name: str = None) -> str:
    return (name or Config().ai.get("provider", "deepseek") or "deepseek").strip().lower()


def resolve_image_provider_name(name: str = None, text_provider: str = None) -> str:
    config = Config()
    ai_config = config.ai
    provider = (text_provider or resolve_provider_name()).strip().lower()
    requested = name if name is not None else ai_config.get("image_provider", "")
    requested = (requested or "").strip().lower()

    if requested == "none":
        return ""
    if requested and requested != "auto":
        return requested
    if provider_supports_image(provider) and not provider_config_missing(
        provider,
        ai_config.get(provider, {}),
        require_image=True,
    ):
        return provider

    for candidate in IMAGE_PROVIDER_NAMES:
        if not provider_config_missing(candidate, ai_config.get(candidate, {}), require_image=True):
            return candidate
    return ""


def provider_config_missing(provider_name: str, provider_config: dict = None, require_image: bool = False) -> list[str]:
    if provider_name == "mock":
        return []

    config = Config()
    provider_config = provider_config if provider_config is not None else config.ai.get(provider_name, {})
    required = ["api_key", "base_url", "model"]
    missing = [key for key in required if not provider_config.get(key) or is_placeholder_value(provider_config.get(key))]
    if require_image and provider_name in {"minimax", "glm"}:
        missing.extend(_image_config_issues(provider_name, provider_config))
    return missing


def list_provider_names(include_mock: bool = False) -> list:
    names = ["deepseek", "kimi", "minimax", "glm"]
    if include_mock:
        names.append("mock")
    return names


def provider_supports_image(name: str) -> bool:
    return name in {"minimax", "glm", "mock"}


def _image_config_issues(provider_name: str, provider_config: dict) -> list[str]:
    issues = []
    image_model_issue = _image_model_issue(provider_name, provider_config)
    if image_model_issue:
        issues.append(image_model_issue)

    if provider_name == "minimax":
        image_base_url_issue = _minimax_image_base_url_issue(provider_config)
        if image_base_url_issue:
            issues.append(image_base_url_issue)

    if provider_name == "glm":
        image_size_issue = _glm_image_size_issue(provider_config)
        if image_size_issue:
            issues.append(image_size_issue)
    return issues


def _image_model_issue(provider_name: str, provider_config: dict) -> str:
    image_model = str(provider_config.get("image_model") or "").strip()
    if not image_model or is_placeholder_value(image_model):
        return "image_model"

    text_model = str(provider_config.get("model") or "").strip()
    if text_model and image_model.lower() == text_model.lower():
        return "image_model(不能与文本模型相同)"
    if provider_name == "minimax":
        if image_model.lower().startswith("minimax-"):
            return "image_model(疑似文本模型，请填写图片模型如 image-01)"
    return ""


def _minimax_image_base_url_issue(provider_config: dict) -> str:
    url = str(provider_config.get("image_base_url") or "").strip()
    if not url:
        return ""
    url_lower = url.lower().rstrip("/")
    if is_placeholder_value(url):
        return "image_base_url"
    if not re.match(r"^https?://", url_lower):
        return "image_base_url(必须是 http(s) URL)"
    if url_lower.endswith(("/anthropic", "/v1/messages", "/v1/image_generation")):
        return "image_base_url(疑似填成文本或完整图片接口地址)"
    return ""


def _glm_image_size_issue(provider_config: dict) -> str:
    image_size = str(provider_config.get("image_size") or "").strip()
    if not image_size:
        return ""
    if not re.match(r"^\d{3,5}x\d{3,5}$", image_size):
        return "image_size(格式应为 WIDTHxHEIGHT，如 1280x1280)"
    return ""


def is_placeholder_value(value) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    return any(marker in text for marker in PLACEHOLDER_MARKERS)
