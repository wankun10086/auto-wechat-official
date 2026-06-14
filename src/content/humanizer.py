import re
from loguru import logger
from src.config import Config, load_prompt
from src.ai.provider import BaseProvider


class Humanizer:
    def __init__(self, provider: BaseProvider):
        self.provider = provider
        config = Config()
        self.banned_words = config.get("content", "banned_words", default=[])
        self.rounds = config.get("content", "humanize_rounds", default=2)
        self.prompts = load_prompt("tech_article")

    def full_pipeline(self, raw_article):
        article = raw_article

        for i in range(self.rounds):
            logger.info(f"去AI味处理: 第{i + 1}/{self.rounds}轮")

            prompt_colloquial = self.prompts["colloquial_rewrite"].format(article=article)
            result = self.provider.generate(prompt_colloquial, temperature=0.85)
            article = self._extract_html(result.text)

            prompt_emotion = self.prompts["emotion_inject"].format(article=article)
            result = self.provider.generate(prompt_emotion, temperature=0.85)
            article = self._extract_html(result.text)

        prompt_de_template = self.prompts["de_template"].format(article=article)
        result = self.provider.generate(prompt_de_template, temperature=0.85)
        article = self._extract_html(result.text)

        article = self._clean_banned_words(article)
        ai_score = self._calculate_ai_score(article)

        logger.info(f"去AI味完成，AI味得分: {ai_score:.2f}")
        return article, ai_score

    def _extract_html(self, text):
        if "```html" in text:
            text = text.split("```html", 1)[1]
            text = text.split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1]
            text = text.split("```", 1)[0]
        return text.strip()

    def _clean_banned_words(self, text):
        for word in self.banned_words:
            if word in text:
                text = text.replace(word, "")
                logger.debug(f"移除禁用词: {word}")
        text = re.sub(r"[\n]{3,}", "\n\n", text)
        return text

    def _calculate_ai_score(self, text):
        score = 0.0
        plain = re.sub(r"<[^>]+>", "", text)

        for word in self.banned_words:
            if word in plain:
                score += 0.08

        ai_patterns = [
            r"首先[，,].*其次[，,].*最后",
            r"总的来说",
            r"综上所述",
            r"值得注意的是",
            r"需要指出的是",
            r"不可否认",
            r"随着.*的发展",
            r"在当今",
            r"众所周知",
        ]
        for pattern in ai_patterns:
            if re.search(pattern, plain):
                score += 0.1

        sentences = re.split(r"[。！？]", plain)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
        if sentences:
            lengths = [len(s) for s in sentences]
            avg_len = sum(lengths) / len(lengths)
            variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
            if variance < 100:
                score += 0.15

        paragraphs = plain.split("\n\n")
        if len(paragraphs) > 3:
            first_words = []
            for p in paragraphs[:6]:
                p = p.strip()
                if len(p) > 2:
                    first_words.append(p[:2])
            if len(set(first_words)) <= 2:
                score += 0.1

        return min(score, 1.0)
