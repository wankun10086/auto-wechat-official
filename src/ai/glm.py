import httpx
from loguru import logger

from src.ai.image_utils import save_image_url
from src.ai.provider import BaseProvider, GenerateResult


class GLMProvider(BaseProvider):
    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = (self.base_url or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        self.image_model = config.get("image_model", "glm-image")
        self.image_size = config.get("image_size", "1280x1280")

    def generate(self, prompt: str, system: str = "", temperature: float = 0.85, max_tokens: int = 4000) -> GenerateResult:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=120,
        )
        data = resp.json()
        if resp.status_code != 200:
            raise Exception(f"GLM调用失败: {data}")

        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        logger.info(f"GLM生成完成，tokens: {usage}")
        return GenerateResult(text=text, usage=usage)

    def generate_image(self, prompt: str, **kwargs) -> str:
        payload = {
            "model": kwargs.get("model") or self.image_model,
            "prompt": prompt[:1000],
            "size": kwargs.get("size") or self.image_size,
        }
        if "quality" in kwargs:
            payload["quality"] = kwargs["quality"]

        resp = httpx.post(
            f"{self.base_url}/images/generations",
            headers=self._headers(),
            json=payload,
            timeout=120,
        )
        data = resp.json()
        if resp.status_code != 200:
            raise Exception(f"GLM图片生成失败: {data}")

        image_url = (data.get("data") or [{}])[0].get("url")
        if not image_url:
            raise Exception(f"GLM图片生成未返回URL: {data}")
        return save_image_url(image_url, "glm")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
