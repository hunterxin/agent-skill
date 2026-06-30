"""Skill 数据模型，以及 SKILL.md 的解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml


KEBAB_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


class SkillFormatError(ValueError):
    """SKILL.md 解析失败或校验不通过时抛出。"""


@dataclass
class Skill:
    name: str
    description: str
    path: Path                          # skill 所在目录
    body: str = ""                      # SKILL.md 正文（registry 中懒加载）
    scripts: List[str] = field(default_factory=list)  # 捆绑的脚本文件名

    @property
    def md_path(self) -> Path:
        return self.path / "SKILL.md"


def validate_name(name: str) -> None:
    if not isinstance(name, str) or not KEBAB_RE.match(name):
        raise SkillFormatError(
            f"非法的 skill 名 {name!r}：必须是 kebab-case "
            "（仅小写字母、数字、'-'，且以字母开头）"
        )


def parse_skill_md(path: Path) -> Skill:
    """解析一个 SKILL.md 文件，返回包含 body 的 Skill。"""
    text = Path(path).read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise SkillFormatError(
            f"{path}: 缺少由 '---' 分隔的 YAML frontmatter"
        )
    raw_fm, body = m.group(1), m.group(2)
    try:
        fm = yaml.safe_load(raw_fm) or {}
    except yaml.YAMLError as e:
        raise SkillFormatError(f"{path}: frontmatter YAML 不合法：{e}") from e

    if not isinstance(fm, dict):
        raise SkillFormatError(f"{path}: frontmatter 必须是一个映射")

    name = fm.get("name")
    description = fm.get("description")
    if not name:
        raise SkillFormatError(f"{path}: frontmatter 缺少必填字段 'name'")
    if not description:
        raise SkillFormatError(
            f"{path}: frontmatter 缺少必填字段 'description'"
        )
    validate_name(name)
    if not isinstance(description, str) or "\n" in description.strip():
        raise SkillFormatError(
            f"{path}: 'description' 必须是单行字符串"
        )

    skill_dir = Path(path).parent
    scripts = sorted(
        p.name
        for p in skill_dir.iterdir()
        if p.is_file() and p.suffix in {".py", ".sh"} and p.name != "SKILL.md"
    ) if skill_dir.is_dir() else []

    return Skill(
        name=name,
        description=description.strip(),
        path=skill_dir,
        body=body,
        scripts=scripts,
    )


def render_skill_md(name: str, description: str, body: str) -> str:
    """根据字段渲染一份 SKILL.md。description 会被强制压成单行。"""
    desc = " ".join(description.split())
    fm = yaml.safe_dump(
        {"name": name, "description": desc},
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    body_text = body if body.endswith("\n") else body + "\n"
    return f"---\n{fm}\n---\n{body_text}"
