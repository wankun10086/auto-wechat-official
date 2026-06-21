from abc import ABC, abstractmethod
from dataclasses import dataclass
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
    if provider_supports_image(provider):
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
    missing = [key for key in required if not provider_config.get(key)]
    if require_image and provider_name in {"minimax", "glm"} and not provider_config.get("image_model"):
        missing.append("image_model")
    return missing


def list_provider_names(include_mock: bool = False) -> list:
    names = ["deepseek", "kimi", "minimax", "glm"]
    if include_mock:
        names.append("mock")
    return names


def provider_supports_image(name: str) -> bool:
    return name in {"minimax", "glm", "mock"}
