import base64
import hashlib
from pathlib import Path
from urllib.parse import urlparse

import httpx


def image_output_dir(provider: str) -> Path:
    path = Path("data/generated_images") / provider
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_base64_image(value: str, provider: str, suffix: str = ".jpg") -> str:
    raw = base64.b64decode(value)
    digest = hashlib.sha256(raw).hexdigest()[:16]
    path = image_output_dir(provider) / f"{digest}{suffix}"
    if not path.exists():
        path.write_bytes(raw)
    return str(path)


def save_image_url(url: str, provider: str, suffix: str = "") -> str:
    resp = httpx.get(url, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "").split(";")[0].lower()
    ext = suffix or _extension_from_content_type(content_type) or _extension_from_url(url) or ".jpg"
    digest = hashlib.sha256(resp.content).hexdigest()[:16]
    path = image_output_dir(provider) / f"{digest}{ext}"
    if not path.exists():
        path.write_bytes(resp.content)
    return str(path)


def _extension_from_content_type(content_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(content_type, "")


def _extension_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ""
