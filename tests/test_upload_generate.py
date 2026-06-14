"""文件上传 + file 模式生成的端到端测试（mock provider，零密钥）。"""
import base64
import time
from pathlib import Path

from fastapi.testclient import TestClient
from web.server import app

client = TestClient(app)


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode()


def test_upload_md_returns_path():
    content = "# 上传测试\n\n一段用于验证上传的 markdown 正文。\n"
    r = client.post("/api/upload", json={"name": "demo.md", "content": _b64(content)})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name"] == "demo.md"
    assert d["size"] == len(content.encode("utf-8"))
    assert Path(d["path"]).exists()


def test_upload_rejects_disallowed_type():
    r = client.post("/api/upload", json={"name": "bad.exe", "content": _b64("x")})
    assert r.status_code == 400


def test_upload_rejects_bad_base64():
    r = client.post("/api/upload", json={"name": "x.md", "content": "!!!not-base64!!!"})
    assert r.status_code == 400


def test_generate_from_file_source_end_to_end():
    """上传 .md → file 模式 + mock 生成 → 文章落库。验证 source_type 贯通。"""
    up = client.post("/api/upload", json={
        "name": "src.md",
        "content": _b64("# 文件来源\n\n这是一段用于端到端测试的正文。\n"),
    }).json()

    g = client.post("/api/generate", json={
        "url": up["path"],
        "source_type": "file",
        "model": "mock",
        "no_images": True,
    })
    assert g.status_code == 200, g.text
    tid = g.json()["task_id"]

    # TestClient 通常在 POST 返回前就跑完了 background task；保险起见轮询。
    tk = {}
    for _ in range(30):
        tk = client.get(f"/api/tasks/{tid}").json()
        if tk.get("status") in ("done", "failed"):
            break
        time.sleep(0.5)

    assert tk.get("status") == "done", tk
    assert tk.get("article_id"), tk
