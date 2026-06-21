import re
from bs4 import BeautifulSoup
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
            article = self._accept_candidate(article, self._extract_html(result.text), "口语化改写")

            prompt_emotion = self.prompts["emotion_inject"].format(article=article)
            result = self.provider.generate(prompt_emotion, temperature=0.85)
            article = self._accept_candidate(article, self._extract_html(result.text), "情绪注入")

        prompt_de_template = self.prompts["de_template"].format(article=article)
        result = self.provider.generate(prompt_de_template, temperature=0.85)
        article = self._accept_candidate(article, self._extract_html(result.text), "去模板化")

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

    def _accept_candidate(self, previous: str, candidate: str, step: str) -> str:
        if self._candidate_is_safe(previous, candidate):
            return candidate
        logger.warning(f"{step}结果疑似丢失正文，已保留上一版内容")
        return previous

    def _candidate_is_safe(self, previous: str, candidate: str) -> bool:
        if not candidate.strip():
            return False

        previous_text = self._plain_text(previous)
        candidate_text = self._plain_text(candidate)
        if len(previous_text) >= 600 and len(candidate_text) < len(previous_text) * 0.55:
            return False
        if len(previous_text) >= 200 and len(candidate_text) < 120:
            return False

        previous_headings = self._heading_count(previous)
        candidate_headings = self._heading_count(candidate)
        if previous_headings >= 2 and candidate_headings < max(1, previous_headings // 2):
            return False

        candidate_text_lower = candidate_text.lower()
        meta_hits = sum(1 for phrase in self._meta_phrases() if phrase in candidate_text_lower)
        if meta_hits >= 2:
            return False
        return True

    def _plain_text(self, html: str) -> str:
        return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)

    def _heading_count(self, html: str) -> int:
        soup = BeautifulSoup(html or "", "html.parser")
        return len(soup.find_all(["h2", "h3"]))

    def _meta_phrases(self):
        return (
            "请提供",
            "提供完整",
            "主要内容摘要",
            "我可以帮",
            "我可以为",
            "无法改写",
            "没有提供",
            "原文都没",
            "修改要求",
            "改写要求",
            "保持html标签",
            "html标签",
        )

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
