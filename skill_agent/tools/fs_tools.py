"""带路径白名单的文件系统工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


class PathNotAllowed(PermissionError):
    """当路径落在允许的根目录之外时抛出。"""


def _resolve_within(path: str, allowed_roots: Iterable[Path]) -> Path:
    target = Path(path).expanduser().resolve()
    roots = [Path(r).expanduser().resolve() for r in allowed_roots]
    for root in roots:
        try:
            target.relative_to(root)
            return target
        except ValueError:
            continue
    raise PathNotAllowed(
        f"路径 {target} 不在任何允许的根目录下：{[str(r) for r in roots]}"
    )


def read_file(path: str, allowed_roots: Iterable[Path]) -> str:
    target = _resolve_within(path, allowed_roots)
    return target.read_text(encoding="utf-8")


def write_file(path: str, content: str, allowed_roots: Iterable[Path]) -> str:
    target = _resolve_within(path, allowed_roots)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)
