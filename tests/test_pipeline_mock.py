import asyncio
from pathlib import Path
from src.ai.provider import GenerateResult
from src.pipeline import ArticleGenerationPipeline
import src.pipeline as pipeline_module


def test_source_driven_pipeline_with_mock(local_tmp):
    """用本地 markdown 作为源 + mock 模型，零密钥跑通整条流水线。"""
    src = local_tmp / "demo.md"
    src.write_text(
        "# 测试项目\n\n这是一个用于自动化测试的示例 markdown 源。\n\n## 特性\n\n- 离线\n- 快速\n- 可重复\n",
        encoding="utf-8",
    )

    pipe = ArticleGenerationPipeline(model="mock")
    result = asyncio.run(pipe.run(
        source=str(src),
        source_type="file",
        style="tech_explanation",
        generate_images=False,
    ))

    assert result is not None, "流水线应成功产出结果"
    assert result["id"], "应写入数据库并返回 id"
    assert isinstance(result["ai_score"], float)
    assert 0.0 <= result["ai_score"] <= 1.0
    assert "<" in result["content"], "最终内容应是 HTML"
    assert "<style>" in result["content"] or "<h2>" in result["content"], "应经过模板包装"


def test_pipeline_failure_returns_none_on_missing_file():
    pipe = ArticleGenerationPipeline(model="mock")
    result = asyncio.run(pipe.run(
        source="does-not-exist.md",
        source_type="file",
        generate_images=False,
    ))
    assert result is None
    assert "内容抓取失败" in pipe.last_error
    assert "does-not-exist.md" in pipe.last_error


def test_pipeline_collects_nonfatal_image_warnings(local_tmp):
    src = local_tmp / "demo.md"
    src.write_text("# 标题\n\n正文内容", encoding="utf-8")

    pipe = ArticleGenerationPipeline(model="mock")

    def fail_image(prompt, **kwargs):
        raise RuntimeError("image quota exhausted")

    pipe.provider.generate_image = fail_image
    result = asyncio.run(pipe.run(
        source=str(src),
        source_type="file",
        generate_images=True,
    ))

    assert result is not None
    assert result["ai_images"] == []
    assert any("image quota exhausted" in warning for warning in result["warnings"])


def test_pipeline_can_use_separate_image_provider(local_tmp, monkeypatch):
    src = local_tmp / "demo.md"
    image_path = local_tmp / "generated.png"
    src.write_text("# 标题\n\n正文内容", encoding="utf-8")
    calls = []

    class FakeTextProvider:
        def generate(self, prompt, **kwargs):
            return GenerateResult("<h2>正文</h2><p>内容</p>")

        def generate_image(self, prompt, **kwargs):
            raise NotImplementedError("text only")

    class FakeImageProvider:
        def generate(self, prompt, **kwargs):
            return GenerateResult("unused")

        def generate_image(self, prompt, **kwargs):
            calls.append(("image", prompt))
            image_path.write_bytes(b"fake-image")
            return str(image_path)

    def fake_get_provider(name=None):
        if name == "glm":
            return FakeImageProvider()
        return FakeTextProvider()

    monkeypatch.setattr(pipeline_module, "get_provider", fake_get_provider)

    pipe = ArticleGenerationPipeline(model="deepseek", image_model="glm")
    result = asyncio.run(pipe.run(
        source=str(src),
        source_type="file",
        generate_images=True,
    ))

    assert result is not None
    assert calls and calls[0][0] == "image"
    assert result["image_provider"] == "glm"
    assert result["ai_images"][0]["provider"] == "glm"
    assert Path(result["ai_images"][0]["path"]).exists()
