import asyncio
from src.pipeline import ArticleGenerationPipeline


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
