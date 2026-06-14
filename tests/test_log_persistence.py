from src.db.models import LogLine


def test_broadcast_persists_to_db():
    """_broadcast 应同时写入内存缓冲和持久化 LogLine 表。"""
    from web import api as webapi

    webapi._broadcast({"time": "00:00:01", "level": "INFO", "message": "测试日志条目-persist", "module": "test"})

    session = webapi._get_log_session()
    rows = session.query(LogLine).filter(LogLine.message.like("%persist%")).all()
    session.close()
    assert len(rows) >= 1


def test_get_logs_returns_history():
    from web import api as webapi
    import asyncio

    webapi._broadcast({"time": "00:00:02", "level": "INFO", "message": "测试日志条目-history", "module": "test"})
    history = asyncio.run(webapi.get_logs())
    assert any("history" in (e.get("message") or "") for e in history)
