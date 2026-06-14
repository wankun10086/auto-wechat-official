import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.config import Config, setup_logging
from web.api import router

app = FastAPI(title="Auto WeChat", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    uvicorn.run("web.server:app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    main()
