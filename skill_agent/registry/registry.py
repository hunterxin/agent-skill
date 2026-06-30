"""Skill 注册表：扫描 skills 目录，支持两阶段加载 + CRUD。"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from ..skill import (
    Skill,
    SkillFormatError,
    parse_skill_md,
    render_skill_md,
    validate_name,
)


TRASH_DIRNAME = ".trash"


class SkillRegistry:
    """skills 的内存索引；SKILL.md 的 body 采用懒加载。"""

    def __init__(self, root: Path):
        self.root: Path = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._skills: Dict[str, Skill] = {}
        self._loaded: bool = False

    # ------------------------------------------------------------------ 扫描

    def refresh(self) -> None:
        """重新扫描 skills 根目录并重建索引。"""
        self._skills.clear()
        for child in sorted(self.root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            md = child / "SKILL.md"
            if not md.is_file():
                continue
            try:
                skill = parse_skill_md(md)
            except SkillFormatError as e:
                # 跳过格式不合法的 skill，并把警告打到 stderr。
                import sys
                print(f"[warn] 跳过 {md}: {e}", file=sys.stderr)
                continue
            # 两阶段加载：丢掉 body，让索引保持轻量。
            skill.body = ""
            self._skills[skill.name] = skill
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.refresh()

    # ----------------------------------------------------------------- 查询

    def names(self) -> List[str]:
        self._ensure_loaded()
        return sorted(self._skills.keys())

    def catalog_for_prompt(self) -> List[Tuple[str, str]]:
        """返回 [(name, description), ...]，用于渲染系统提示词。"""
        self._ensure_loaded()
        return [(s.name, s.description) for s in self._skills.values()]

    def get(self, name: str) -> Skill:
        self._ensure_loaded()
        if name not in self._skills:
            raise KeyError(name)
        return self._skills[name]

    def load_full(self, name: str) -> Skill:
        """读取完整的 SKILL.md 正文以及捆绑脚本列表。"""
        self._ensure_loaded()
        if name not in self._skills:
            raise KeyError(name)
        # 重新从磁盘解析一次，捕获外部编辑过的内容以及 body。
        fresh = parse_skill_md(self._skills[name].md_path)
        self._skills[name] = fresh
        return fresh

    # ------------------------------------------------------------------ CRUD

    def create(
        self,
        name: str,
        description: str,
        body: str,
        scripts: Optional[Mapping[str, str]] = None,
    ) -> Skill:
        validate_name(name)
        skill_dir = self.root / name
        if skill_dir.exists():
            raise FileExistsError(f"skill {name!r} 已存在于 {skill_dir}")
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            render_skill_md(name, description, body), encoding="utf-8"
        )
        for filename, content in (scripts or {}).items():
            self._write_script(skill_dir, filename, content)
        self.refresh()
        return self.get(name)

    def update(
        self,
        name: str,
        description: Optional[str] = None,
        body: Optional[str] = None,
        scripts: Optional[Mapping[str, str]] = None,
    ) -> Skill:
        self._ensure_loaded()
        if name not in self._skills:
            raise KeyError(name)
        current = parse_skill_md(self._skills[name].md_path)
        new_desc = description if description is not None else current.description
        new_body = body if body is not None else current.body
        (current.md_path).write_text(
            render_skill_md(name, new_desc, new_body), encoding="utf-8"
        )
        for filename, content in (scripts or {}).items():
            self._write_script(current.path, filename, content)
        self.refresh()
        return self.get(name)

    def delete(self, name: str) -> Path:
        """软删除：把 skill 目录移到 <root>/.trash/<name>-<ts>/。"""
        self._ensure_loaded()
        if name not in self._skills:
            raise KeyError(name)
        src = self._skills[name].path
        trash = self.root / TRASH_DIRNAME
        trash.mkdir(exist_ok=True)
        dest = trash / f"{name}-{int(time.time() * 1000)}"
        shutil.move(str(src), str(dest))
        self.refresh()
        return dest

    # ----------------------------------------------------------------- 辅助

    @staticmethod
    def _write_script(skill_dir: Path, filename: str, content: str) -> None:
        if "/" in filename or filename.startswith("."):
            raise ValueError(f"非法的脚本文件名 {filename!r}")
        (skill_dir / filename).write_text(content, encoding="utf-8")
