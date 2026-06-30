"""配置加载：环境变量 + .env 文件 + CLI 参数覆盖。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_SKILLS_DIR = "./skills"


def _parse_bool(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    api_key: Optional[str]
    base_url: str
    model: str
    skills_dir: Path
    debug: bool = True

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)


def load_config(
    skills_dir: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    debug: bool = False,
) -> Config:
    """按优先级解析配置：CLI 参数 > 环境变量 > .env 文件 > 默认值。"""
    # 把 .env 加载到 os.environ（不覆盖已存在的变量）。
    load_dotenv(override=False)

    resolved_dir = Path(
        skills_dir
        or os.environ.get("SKILL_AGENT_SKILLS_DIR")
        or DEFAULT_SKILLS_DIR
    ).expanduser().resolve()

    return Config(
        api_key=api_key or os.environ.get("DEEPSEEK_API_KEY"),
        base_url=base_url or os.environ.get("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL,
        model=model or os.environ.get("SKILL_AGENT_MODEL") or DEFAULT_MODEL,
        skills_dir=resolved_dir,
        debug=debug or _parse_bool(os.environ.get("SKILL_AGENT_DEBUG")),
    )
