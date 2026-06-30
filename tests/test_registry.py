"""SkillRegistry 的测试（扫描 + CRUD + 软删除）。"""

from __future__ import annotations

import pytest

from skill_agent.skill import SkillFormatError


def test_scan_finds_skill(registry, sample_skill):
    registry.refresh()
    catalog = registry.catalog_for_prompt()
    assert ("greet", "Say hello in different languages") in catalog


def test_scan_skips_dotdirs_and_invalid(registry, tmp_skills_dir, capsys):
    # 隐藏目录应被忽略。
    (tmp_skills_dir / ".trash").mkdir()
    (tmp_skills_dir / ".trash" / "x-1").mkdir()
    (tmp_skills_dir / ".trash" / "x-1" / "SKILL.md").write_text(
        "---\nname: x\ndescription: y\n---\nb"
    )
    # 非法 skill：缺少 description。
    bad = tmp_skills_dir / "broken"
    bad.mkdir()
    (bad / "SKILL.md").write_text("---\nname: broken\n---\nbody")
    registry.refresh()
    err = capsys.readouterr().err
    assert "broken" in err
    assert "x" not in registry.names()
    assert "broken" not in registry.names()


def test_load_full_reads_body(registry, sample_skill):
    registry.refresh()
    full = registry.load_full("greet")
    assert "Hello, <name>!" in full.body


def test_catalog_for_prompt_omits_body(registry, sample_skill):
    registry.refresh()
    # 刷新后内存中的 body 应为空（两阶段加载）。
    assert registry.get("greet").body == ""


def test_create_skill(registry):
    s = registry.create(
        name="counter",
        description="Count lines in files",
        body="Use wc -l to count lines.",
    )
    assert (registry.root / "counter" / "SKILL.md").exists()
    assert s.name == "counter"
    assert "counter" in dict(registry.catalog_for_prompt())


def test_create_with_scripts(registry):
    registry.create(
        name="greet2",
        description="Greet via script",
        body="Run greet.py",
        scripts={"greet.py": "print('hi')\n"},
    )
    assert (registry.root / "greet2" / "greet.py").read_text() == "print('hi')\n"


def test_create_rejects_invalid_name(registry):
    with pytest.raises(SkillFormatError):
        registry.create(name="Bad Name", description="x", body="y")


def test_create_rejects_duplicate(registry, sample_skill):
    registry.refresh()
    with pytest.raises(FileExistsError):
        registry.create(name="greet", description="dup", body="z")


def test_update_partial(registry, sample_skill):
    registry.refresh()
    registry.update("greet", description="Updated desc")
    catalog = dict(registry.catalog_for_prompt())
    assert catalog["greet"] == "Updated desc"
    # body 未变。
    assert "Hello, <name>!" in registry.load_full("greet").body


def test_update_body_only(registry, sample_skill):
    registry.refresh()
    registry.update("greet", body="New body content.\n")
    full = registry.load_full("greet")
    assert "New body content." in full.body
    assert full.description == "Say hello in different languages"


def test_delete_is_soft(registry, sample_skill):
    registry.refresh()
    registry.delete("greet")
    assert not (registry.root / "greet").exists()
    trash = list((registry.root / ".trash").glob("greet-*"))
    assert len(trash) == 1
    assert (trash[0] / "SKILL.md").exists()


def test_delete_unknown_raises(registry):
    with pytest.raises(KeyError):
        registry.delete("nope")
