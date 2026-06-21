import httpx
from loguru import logger
from src.ai.image_utils import save_base64_image, save_image_url
from src.ai.provider import BaseProvider, GenerateResult


class MiniMaxProvider(BaseProvider):
    def __init__(self, config: dict):
        super().__init__(config)
        self.messages_url = f"{self.base_url}/v1/messages"
        self.image_base_url = config.get("image_base_url", "https://api.minimax.io").rstrip("/")
        self.image_model = config.get("image_model", "image-01")

    def generate(self, prompt: str, system: str = "", temperature: float = 0.85, max_tokens: int = 4000) -> GenerateResult:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        messages = [{"role": "user", "content": prompt}]
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            payload["system"] = system

        resp = httpx.post(self.messages_url, headers=headers, json=payload, timeout=120)
        data = resp.json()

        if resp.status_code != 200:
            err = data.get("error", {}).get("message", str(data))
            raise Exception(f"MiniMax调用失败: {err}")

        content = data.get("content", [])
        text = content[0].get("text", "") if content else ""
        usage = data.get("usage", {})
        logger.info(f"MiniMax生成完成，tokens: {usage}")
        return GenerateResult(text=text, usage=usage)

    def generate_image(self, prompt: str, **kwargs) -> str:
        payload = {
            "model": kwargs.get("model") or self.image_model,
            "prompt": prompt[:1500],
            "aspect_ratio": kwargs.get("aspect_ratio", "16:9"),
            "response_format": kwargs.get("response_format", "base64"),
            "n": int(kwargs.get("n", 1)),
            "prompt_optimizer": kwargs.get("prompt_optimizer", True),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = httpx.post(
            f"{self.image_base_url}/v1/image_generation",
            headers=headers,
            json=payload,
            timeout=120,
        )
        data = resp.json()
        if resp.status_code != 200:
            err = data.get("error", {}).get("message", str(data))
            raise Exception(f"MiniMax图片生成失败: {err}")

        base_resp = data.get("base_resp", {})
        if base_resp and base_resp.get("status_code", 0) != 0:
            raise Exception(f"MiniMax图片生成失败: {base_resp}")

        image_data = data.get("data", {})
        image_base64 = image_data.get("image_base64") or []
        if image_base64:
            return save_base64_image(image_base64[0], "minimax", ".jpg")

        image_urls = image_data.get("image_urls") or []
        if image_urls:
            return save_image_url(image_urls[0], "minimax")

        raise Exception(f"MiniMax图片生成未返回图片: {data}")
