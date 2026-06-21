import sys
import uuid
import shutil
from pathlib import Path

# 让 tests/ 可以 import src.* / web.*
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

# 项目内临时目录：绕过本机系统 Temp 目录可能存在的权限问题（data/ 已可写）
TMP_ROOT = ROOT / "data" / ".pytest_tmp"


@pytest.fixture(scope="session", autouse=True)
def _isolate_db():
    """把数据库指向项目内临时文件，测试绝不污染真实的 data/articles.db。"""
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    db_path = TMP_ROOT / f"test-{uuid.uuid4().hex[:8]}.db"
    from src.config import Config
    cfg = Config()
    if cfg._data is None:
        cfg.load()
    cfg._data.setdefault("database", {})
    cfg._data["database"]["path"] = str(db_path)
    yield


@pytest.fixture()
def local_tmp():
    """每个测试一个独立的项目内临时目录。"""
    d = TMP_ROOT / uuid.uuid4().hex[:8]
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)
