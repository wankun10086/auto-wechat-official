import yaml
from pathlib import Path
from loguru import logger


CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.yaml"


class Config:
    _instance = None
    _data = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, path=None):
        config_path = Path(path) if path else CONFIG_PATH
        with open(config_path, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f)
        return self

    def get(self, *keys, default=None):
        obj = self._data
        for key in keys:
            if isinstance(obj, dict):
                obj = obj.get(key)
            else:
                return default
            if obj is None:
                return default
        return obj

    @property
    def wechat(self):
        return self._data.get("wechat", {})

    @property
    def ai(self):
        return self._data.get("ai", {})

    @property
    def content(self):
        return self._data.get("content", {})

    @property
    def schedule(self):
        return self._data.get("schedule", {})

    @property
    def browser(self):
        return self._data.get("browser", {})

    @property
    def database(self):
        return self._data.get("database", {})


def load_prompt(name):
    prompt_path = Path(__file__).parent.parent / "config" / "prompts" / f"{name}.yaml"
    with open(prompt_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(config):
    log_config = config.get("logging", default={})
    log_file = log_config.get("file", "data/app.log")
    log_level = log_config.get("level", "INFO")
    rotation = log_config.get("rotation", "10 MB")

    logger.add(log_file, rotation=rotation, level=log_level, encoding="utf-8")
