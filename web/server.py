import os
import sys
from pathlib import Path

# pythonw.exe（无窗口后台启动器）会把 stdout/stderr 置为 None。
# loguru 的 stderr sink 与我们的 LogIntercept 都需要真实流，这里重定向到 devnull。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.config import Config, setup_logging
from web.api import router

app = FastAPI(title="Auto WeChat", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        item.strip()
        for item in os.environ.get(
            "AUTOWECHAT_CORS_ORIGINS",
            "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
        if item.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

frontend_dist = Path(__file__).parent / "frontend" / "dist"


@app.get("/")
async def index():
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Auto WeChat API is running. Frontend not built yet. Run: cd web/frontend && npm run build"}


if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")


@app.on_event("startup")
async def startup():
    config = Config()
    config.load()
    setup_logging(config)


def main():
    import uvicorn
    config = Config()
    config.load()
    setup_logging(config)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    host = os.environ.get("AUTOWECHAT_HOST", "127.0.0.1")
    background = os.environ.get("AUTOWECHAT_BACKGROUND") == "1"
    if background:
        # 无窗口模式：写 PID 便于停止；关闭 reload（reload 会再开子进程）
        try:
            Path("data").mkdir(parents=True, exist_ok=True)
            (Path("data") / "server.pid").write_text(str(os.getpid()), encoding="utf-8")
        except Exception:
            pass
    uvicorn.run("web.server:app", host=host, port=port, reload=not background)


if __name__ == "__main__":
    main()
