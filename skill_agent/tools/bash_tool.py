"""Bash 执行工具，带超时与输出截断。"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


MAX_OUTPUT_BYTES = 5 * 1024
TRUNC_NOTE = "\n...[truncated]"


def _truncate(s: str) -> str:
    if len(s.encode("utf-8")) <= MAX_OUTPUT_BYTES:
        return s
    # 先按字符截断；如果是多字节字符密集，再按字节继续裁。
    cut = s[:MAX_OUTPUT_BYTES]
    while len(cut.encode("utf-8")) > MAX_OUTPUT_BYTES:
        cut = cut[:-1]
    return cut + TRUNC_NOTE


def run_bash(
    command: str,
    cwd: Optional[str] = None,
    timeout: float = 60.0,
) -> dict:
    """通过 `bash -lc` 执行命令。返回 {stdout, stderr, exit_code, timed_out}。"""
    # 打印 command
    print(f"[cyan]bash -lc '{command}'[/cyan]")
    cwd_path = str(Path(cwd).expanduser().resolve()) if cwd else None
    try:
        proc = subprocess.run(
            ["bash", "-lc", command],
            cwd=cwd_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return {
            "exit_code": -1,
            "stdout": _truncate(e.stdout or ""),
            "stderr": _truncate(e.stderr or ""),
            "timed_out": True,
        }
    return {
        "exit_code": proc.returncode,
        "stdout": _truncate(proc.stdout),
        "stderr": _truncate(proc.stderr),
        "timed_out": False,
    }
