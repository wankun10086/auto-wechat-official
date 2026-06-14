from loguru import logger
from src.config import load_prompt


class ArticleTemplate:
    def __init__(self):
        self.style_guide = load_prompt("style_guide")
        self.html_style = self.style_guide.get("html_style", "")

    def wrap_article(self, content_html):
        return f"""<div class="article-content">
{self.html_style}
{content_html}
</div>"""

    def get_template(self, template_name):
        templates = self.style_guide.get("templates", {})
        return templates.get(template_name, templates.get("tech_explanation", {}))

    def add_divider(self):
        return '<div style="text-align:center; margin:25px 0; color:#ccc;">· · ·</div>'

    def add_highlight_box(self, text):
        return f"""<blockquote style="background:#f0faf0; border-left:4px solid #07c160; padding:12px 16px; margin:15px 0;">
<strong style="color:#07c160;">划重点：</strong>{text}
</blockquote>"""

    def add_callout(self, text, style="info"):
        colors = {
            "info": ("#e8f4fd", "#1890ff"),
            "warning": ("#fff7e6", "#fa8c16"),
            "success": ("#f0faf0", "#07c160"),
        }
        bg, border = colors.get(style, colors["info"])
        return f"""<div style="background:{bg}; border-left:4px solid {border}; padding:12px 16px; margin:15px 0; border-radius:4px;">
{text}
</div>"""

    def format_with_emojis(self, content):
        replacements = [
            ("【重点】", " "),
            ("【注意】", "⚠️"),
            ("【提示】", " "),
            ("【推荐】", "⭐"),
        ]
        for old, new in replacements:
            content = content.replace(old, new)
        return content
