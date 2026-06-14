from openai import OpenAI
from loguru import logger
from src.config import Config, load_prompt


class ContentGenerator:
    def __init__(self):
        config = Config()
        ai_config = config.ai
        provider = ai_config.get("provider", "deepseek")
        provider_config = ai_config.get(provider, {})

        self.client = OpenAI(
            api_key=provider_config["api_key"],
            base_url=provider_config["base_url"],
        )
        self.model = provider_config["model"]
        self.temperature = ai_config.get("temperature", 0.85)
        self.max_tokens = ai_config.get("max_tokens", 4000)
        self.prompts = load_prompt("tech_article")

    def _call(self, prompt, temperature=None):
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature or self.temperature,
            max_tokens=self.max_tokens,
        )
        return resp.choices[0].message.content

    def _extract_html_body(self, text):
        if "```html" in text:
            text = text.split("```html", 1)[1]
            text = text.split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1]
            text = text.split("```", 1)[0]
        return text.strip()

    def generate_article(self, topic, source_materials=""):
        prompt_template = self.prompts["article_generation"]
        prompt = prompt_template.format(
            topic=topic,
            source_materials=source_materials or "（无额外素材，请基于你的知识创作）",
        )
        logger.info(f"开始生成文章，主题: {topic}")
        raw = self._call(prompt)
        return self._extract_html_body(raw)

    def generate_titles(self, summary):
        prompt_template = self.prompts["title_generation"]
        prompt = prompt_template.format(summary=summary)
        raw = self._call(prompt, temperature=0.9)
        titles = []
        for line in raw.strip().split("\n"):
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-") or line.startswith("*")):
                title = line.lstrip("0123456789.-*) ").strip()
                if title:
                    titles.append(title)
        return titles[:5]

    def generate_digest(self, article):
        prompt_template = self.prompts["digest_generation"]
        prompt = prompt_template.format(article=article[:2000])
        return self._call(prompt, temperature=0.8).strip()
