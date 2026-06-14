from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class GenerateRequest(BaseModel):
    url: str                       # URL 或已上传文件的本地路径
    source_type: str = "url"       # url | file
    model: Optional[str] = None
    style: str = "tech_explanation"
    prompt: str = ""
    screenshot: str = ""
    no_images: bool = False
    publish: bool = False


class GenerateResponse(BaseModel):
    task_id: str
    status: str


class UploadRequest(BaseModel):
    name: str
    content: str                   # base64 编码的文件内容


class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: int
    message: str
    article_id: Optional[int] = None


class ArticleItem(BaseModel):
    id: int
    title: str
    status: str
    ai_score: float
    digest: str
    created_at: str
    topic: str
    model: str


class ArticleDetail(BaseModel):
    id: int
    title: str
    content: str
    raw_content: str
    digest: str
    author: str
    topic: str
    ai_score: float
    status: str
    media_id: str
    created_at: str
    published_at: Optional[str]
    screenshots: list
    ai_images: list


class ModelInfo(BaseModel):
    name: str
    model: str
    has_key: bool
    supports_image: bool
    is_current: bool


class PublishResponse(BaseModel):
    success: bool
    message: str
    media_id: Optional[str] = None
