from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from pathlib import Path

Base = declarative_base()


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 文章标题
    title = Column(String(200), nullable=False)
    # 原始AI生成内容
    raw_content = Column(Text)
    # 处理后的HTML内容
    final_content = Column(Text)
    # 摘要
    digest = Column(String(500))
    # 作者
    author = Column(String(50))
    # 话题/主题
    topic = Column(String(200))
    # 话题策略
    topic_strategy = Column(String(50))
    # 微信草稿media_id
    media_id = Column(String(200))
    # 微信发布article_id
    article_id = Column(String(200))
    # 文章永久链接
    article_url = Column(String(500))
    # 封面图media_id
    thumb_media_id = Column(String(200))
    # 状态：draft / published / failed
    status = Column(String(20), default="draft")
    # 阅读数据
    read_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    favorite_count = Column(Integer, default=0)
    # 完读率
    completion_rate = Column(Float, default=0.0)
    # AI味检测分数（0-1，越低越好）
    ai_score = Column(Float)
    # 创建时间
    created_at = Column(DateTime, default=datetime.now)
    # 发布时间
    published_at = Column(DateTime)
    # 备注
    notes = Column(Text)


class HotTopic(Base):
    __tablename__ = "hot_topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 话题标题
    title = Column(String(500), nullable=False)
    # 来源
    source = Column(String(50))
    # 原始链接
    url = Column(String(1000))
    # 话题描述/摘要
    description = Column(Text)
    # 热度分数
    hot_score = Column(Float, default=0.0)
    # 是否已使用
    used = Column(Boolean, default=False)
    # 采集时间
    fetched_at = Column(DateTime, default=datetime.now)


class PublishLog(Base):
    __tablename__ = "publish_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer)
    # 操作类型：create_draft / publish / schedule
    action = Column(String(50))
    # 状态：success / failed
    status = Column(String(20))
    # 错误信息
    error_message = Column(Text)
    # 操作时间
    created_at = Column(DateTime, default=datetime.now)


class LogLine(Base):
    """持久化的运行日志，供 Web UI 回滚查看（重启不丢失）。"""
    __tablename__ = "log_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.now)
    level = Column(String(20), default="INFO")
    message = Column(Text)
    module = Column(String(50), default="")


def init_db(db_path="data/articles.db"):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session


def get_session(db_path=None):
    """返回一个 Session。

    db_path 留空时走配置里的 database.path，确保 web/pipeline/tests 三方
    始终指向同一个库（测试时 conftest 只改这一处即可完全隔离）。
    """
    if db_path is None:
        from src.config import Config
        db_path = Config().get("database", "path", default="data/articles.db")
    engine, Session = init_db(db_path)
    return Session()
