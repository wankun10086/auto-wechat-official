import httpx
from pathlib import Path
from datetime import datetime
from loguru import logger
from src.ai.provider import BaseProvider, GenerateResult


class MiniMaxProvider(BaseProvider):
    def __init__(self, config: dict):
        super().__init__(config)
        self.messages_url = f"{self.base_url}/v1/messages"

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
        raise NotImplementedError("MiniMax当前API不支持图片生成")
