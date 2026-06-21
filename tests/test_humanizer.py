from src.ai.provider import GenerateResult
from src.content.humanizer import Humanizer


class BadRewriteProvider:
    def generate(self, prompt, **kwargs):
        return GenerateResult("请提供完整文章或主要内容摘要，我可以帮你改写。请保持HTML标签。")


def test_humanizer_keeps_previous_article_when_rewrite_loses_content():
    raw = (
        "<h2>AI Agent 落地观察</h2>"
        "<p>企业正在把 AI Agent 从演示环境推进到真实流程里，但预算、数据权限、"
        "稳定性和组织协同仍然是关键变量。</p>"
        "<h2>真正的难点</h2>"
        f"<p>{'真实业务流程需要持续校验、人工兜底和可追踪记录。' * 40}</p>"
    )
    humanizer = Humanizer(BadRewriteProvider())
    humanizer.rounds = 1

    result, score = humanizer.full_pipeline(raw)

    assert "AI Agent 落地观察" in result
    assert "真正的难点" in result
    assert "请提供完整文章" not in result
    assert 0 <= score <= 1
