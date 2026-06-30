"""暴露给 agent 的 skill 管理工具（list / load / create / update / delete / call）。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..registry import SkillRegistry


def list_skills(registry: SkillRegistry) -> Dict[str, Any]:
    return {
        "skills": [
            {"name": n, "description": d}
            for n, d in registry.catalog_for_prompt()
        ]
    }


def load_skill(registry: SkillRegistry, name: str) -> Dict[str, Any]:
    skill = registry.load_full(name)
    return {
        "name": skill.name,
        "description": skill.description,
        "body": skill.body,
        "scripts": [
            {"filename": fn, "path": str(skill.path / fn)} for fn in skill.scripts
        ],
        "directory": str(skill.path),
    }


def create_skill(
    registry: SkillRegistry,
    name: str,
    description: str,
    body: str,
    scripts: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    skill = registry.create(name, description, body, scripts=scripts)
    return {"ok": True, "name": skill.name, "path": str(skill.path)}


def update_skill(
    registry: SkillRegistry,
    name: str,
    description: Optional[str] = None,
    body: Optional[str] = None,
    scripts: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    skill = registry.update(name, description=description, body=body, scripts=scripts)
    return {"ok": True, "name": skill.name, "path": str(skill.path)}


def delete_skill(registry: SkillRegistry, name: str) -> Dict[str, Any]:
    dest = registry.delete(name)
    return {"ok": True, "moved_to": str(dest)}
