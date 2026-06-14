from openai import OpenAI
from loguru import logger
from src.ai.provider import BaseProvider, GenerateResult


class DeepSeekProvider(BaseProvider):
    def __init__(self, config: dict):
        super().__init__(config)
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate(self, prompt: str, system: str = "", temperature: float = 0.85, max_tokens: int = 4000) -> GenerateResult:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = resp.choices[0].message.content
        usage = {}
        if resp.usage:
            usage = {"prompt_tokens": resp.usage.prompt_tokens, "completion_tokens": resp.usage.completion_tokens}
        logger.info(f"DeepSeek生成完成，tokens: {usage}")
        return GenerateResult(text=text, usage=usage)

    def generate_image(self, prompt: str, **kwargs) -> str:
        raise NotImplementedError("DeepSeek不支持图片生成")
