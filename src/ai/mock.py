from src.ai.provider import BaseProvider, GenerateResult


class MockProvider(BaseProvider):
    """离线确定性 provider：不调用任何外部 API。

    供自动化测试与无 API Key 的界面演示使用，让整条生成流水线可以零密钥跑通。
    根据提示词的关键词返回标题/摘要/正文，输出与真实 provider 同构的 HTML。
    """

    _ARTICLE = '''```html
<h2>开篇</h2>
<p>这是一篇由 Mock 模型生成的示例文章，用于在没有 API Key 的情况下端到端验证流水线。它的逻辑清晰，段落分明，结构合理。</p>
<h2>核心要点</h2>
<p>第一，抓取与生成各司其职。第二，去 AI 味处理会让文字读起来更像人写的。第三，截图与配图会被嵌入正文，让排版更舒服。</p>
<blockquote>好的工具应当减少重复劳动，而不是制造新的麻烦。</blockquote>
<h2>小结</h2>
<p>到这里整条流程已经跑通：抓取、生成、去 AI 味、HTML 包装、入库。剩下的就是推送到公众号草稿箱。</p>
```'''

    def generate(self, prompt: str, system: str = "", temperature: float = 0.85, max_tokens: int = 4000) -> GenerateResult:
        text = self._respond(prompt)
        return GenerateResult(text=text, usage={"total_tokens": len(text)})

    def generate_image(self, prompt: str, **kwargs) -> str:
        raise NotImplementedError("MockProvider 不支持图片生成")

    def _respond(self, prompt: str) -> str:
        p = prompt or ""
        if "标题" in p or "title" in p.lower():
            return "1. 用一段话讲清楚它是什么\n2. 三分钟看懂这个项目\n3. 从源码到上手：实战指南"
        if "摘要" in p or "digest" in p.lower():
            return "这是一篇用 Mock 模型生成的示例摘要，用于离线测试与界面演示。"
        return self._ARTICLE
