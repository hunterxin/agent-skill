"""内置工具的测试（文件系统 + bash）。"""

from __future__ import annotations

import pytest

from skill_agent.tools.bash_tool import run_bash
from skill_agent.tools.fs_tools import PathNotAllowed, read_file, write_file


def test_read_file_inside_allowed(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello")
    out = read_file(str(f), allowed_roots=[tmp_path])
    assert out == "hello"


def test_read_file_blocks_outside(tmp_path):
    with pytest.raises(PathNotAllowed):
        read_file("/etc/passwd", allowed_roots=[tmp_path])


def test_write_file_creates_parent(tmp_path):
    p = tmp_path / "sub" / "b.txt"
    write_file(str(p), "x", allowed_roots=[tmp_path])
    assert p.read_text() == "x"


def test_write_file_blocks_outside(tmp_path):
    other = tmp_path / "ok"
    other.mkdir()
    with pytest.raises(PathNotAllowed):
        write_file("/tmp/skill-agent-evil.txt", "x", allowed_roots=[other])


def test_run_bash_captures_output(tmp_path):
    res = run_bash("echo hi", cwd=str(tmp_path), timeout=5)
    assert res["exit_code"] == 0
    assert "hi" in res["stdout"]
    assert res["timed_out"] is False


def test_run_bash_nonzero_exit(tmp_path):
    res = run_bash("false", cwd=str(tmp_path), timeout=5)
    assert res["exit_code"] != 0


def test_run_bash_timeout(tmp_path):
    res = run_bash("sleep 3", cwd=str(tmp_path), timeout=1)
    assert res["timed_out"] is True


def test_run_bash_truncates_long_output(tmp_path):
    # 100 KB 输出应被截断到 ~5 KB + 截断标记。
    res = run_bash("yes hi | head -c 100000", cwd=str(tmp_path), timeout=5)
    assert len(res["stdout"]) <= 5 * 1024 + 32
    assert res["stdout"].endswith("[truncated]")
