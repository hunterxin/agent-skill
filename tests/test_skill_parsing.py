"""SKILL.md 解析以及 name 校验的测试。"""

from __future__ import annotations

import pytest

from skill_agent.skill import SkillFormatError, parse_skill_md, render_skill_md


def test_parse_valid(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("---\nname: my-skill\ndescription: does X\n---\nBody here.")
    skill = parse_skill_md(p)
    assert skill.name == "my-skill"
    assert skill.description == "does X"
    assert "Body here" in skill.body


def test_missing_frontmatter(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("Just body, no frontmatter.")
    with pytest.raises(SkillFormatError):
        parse_skill_md(p)


def test_missing_name_field(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("---\ndescription: oops\n---\nbody")
    with pytest.raises(SkillFormatError, match="name"):
        parse_skill_md(p)


def test_missing_description_field(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("---\nname: ok\n---\nbody")
    with pytest.raises(SkillFormatError, match="description"):
        parse_skill_md(p)


@pytest.mark.parametrize("bad", ["MySkill", "my_skill", "my skill", "1bad", "-leading", "trailing-"])
def test_invalid_name(tmp_path, bad):
    p = tmp_path / "SKILL.md"
    p.write_text(f"---\nname: '{bad}'\ndescription: x\n---\n")
    with pytest.raises(SkillFormatError, match="kebab"):
        parse_skill_md(p)


def test_body_preserved(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("---\nname: x\ndescription: y\n---\n" + "lorem\n" * 1000)
    s = parse_skill_md(p)
    assert s.body.count("lorem") == 1000


def test_render_roundtrip(tmp_path):
    text = render_skill_md("foo-bar", "do a thing", "Run wc -l.\n")
    p = tmp_path / "SKILL.md"
    p.write_text(text)
    s = parse_skill_md(p)
    assert s.name == "foo-bar"
    assert s.description == "do a thing"
    assert "Run wc -l." in s.body


def test_render_normalizes_multiline_description():
    text = render_skill_md("x", "line1\nline2  extra", "body\n")
    # description 必须是单行。
    assert "line1 line2 extra" in text
    assert "line1\nline2" not in text


def test_scripts_listed(tmp_path):
    sk = tmp_path / "x"
    sk.mkdir()
    (sk / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\nbody")
    (sk / "run.py").write_text("print(1)")
    (sk / "helper.sh").write_text("echo hi")
    (sk / "notes.txt").write_text("ignored")
    s = parse_skill_md(sk / "SKILL.md")
    assert s.scripts == ["helper.sh", "run.py"]
