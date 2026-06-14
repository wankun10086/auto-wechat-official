import json as _json
import re
import time
import requests
from pathlib import Path
from loguru import logger


def _truncate_bytes(s, max_bytes):
    while len(s.encode('utf-8')) > max_bytes:
        s = s[:-1]
    return s


class WeChatAPIClient:
    BASE_URL = "https://api.weixin.qq.com/cgi-bin"

    def __init__(self, app_id, app_secret):
        self.app_id = app_id
        self.app_secret = app_secret
        self.access_token = None
        self.token_expires_at = 0

    def _ensure_token(self):
        if self.access_token and time.time() < self.token_expires_at - 60:
            return
        self._refresh_token()

    def _refresh_token(self):
        url = f"{self.BASE_URL}/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.app_id,
            "secret": self.app_secret,
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if "access_token" in data:
            self.access_token = data["access_token"]
            self.token_expires_at = time.time() + data.get("expires_in", 7200)
            logger.info("access_token 获取成功")
        else:
            raise Exception(f"获取access_token失败: {data}")

    def _post(self, path, json_data=None, **kwargs):
        self._ensure_token()
        url = f"{self.BASE_URL}/{path}?access_token={self.access_token}"
        if json_data is not None:
            payload = _json.dumps(json_data, ensure_ascii=False).encode('utf-8')
            resp = requests.post(
                url,
                data=payload,
                headers={'Content-Type': 'application/json; charset=utf-8'},
                timeout=30,
                **kwargs
            )
        else:
            resp = requests.post(url, timeout=30, **kwargs)
        resp.encoding = 'utf-8'
        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise Exception(f"API调用失败 [{path}]: {data}")
        return data

    def _get(self, path, **params):
        self._ensure_token()
        url = f"{self.BASE_URL}/{path}?access_token={self.access_token}"
        resp = requests.get(url, params=params, timeout=10)
        return resp.json()

    def upload_thumb_image(self, image_path):
        """上传封面图，返回 thumb_media_id"""
        self._ensure_token()
        url = f"{self.BASE_URL}/material/add_material?access_token={self.access_token}&type=image"
        with open(image_path, "rb") as f:
            files = {"media": (Path(image_path).name, f, "image/jpeg")}
            resp = requests.post(url, files=files, timeout=30)
        data = resp.json()
        if "media_id" in data:
            logger.info(f"封面图上传成功: {data['media_id']}")
            return data["media_id"]
        raise Exception(f"封面图上传失败: {data}")

    def upload_content_image(self, image_path):
        """上传文章内图片，返回URL"""
        self._ensure_token()
        url = f"{self.BASE_URL}/media/uploadimg?access_token={self.access_token}"
        with open(image_path, "rb") as f:
            files = {"media": (Path(image_path).name, f, "image/jpeg")}
            resp = requests.post(url, files=files, timeout=30)
        data = resp.json()
        if "url" in data:
            return data["url"]
        raise Exception(f"内容图片上传失败: {data}")

    def create_draft(self, title, content, thumb_media_id, author="", digest=""):
        """创建草稿，返回 media_id"""
        import re as _re
        content = _re.sub(r'<style>.*?</style>', '', content, flags=_re.DOTALL).strip()
        article = {
            "title": _truncate_bytes(title, 30),
            "content": content,
            "thumb_media_id": thumb_media_id,
            "author": _truncate_bytes(author, 6),
            "digest": _truncate_bytes(digest, 54),
            "need_open_comment": 1,
            "only_fans_can_comment": 0,
        }
        data = self._post("draft/add", json_data={"articles": [article]})
        media_id = data.get("media_id")
        logger.info(f"草稿创建成功: {media_id}")
        return media_id

    def get_draft_list(self, offset=0, count=20):
        """获取草稿列表"""
        return self._post("draft/batchget", json_data={
            "offset": offset,
            "count": count,
            "no_content": 0,
        })

    def get_draft_count(self):
        """获取草稿总数"""
        return self._get("draft/count")

    def delete_draft(self, media_id):
        """删除草稿"""
        return self._post("draft/delete", json_data={"media_id": media_id})

    def update_draft(self, media_id, index, article):
        """更新草稿"""
        return self._post("draft/update", json_data={
            "media_id": media_id,
            "index": index,
            "articles": article,
        })
