"""click CLI 子命令的测试。"""

from __future__ import annotations

from click.testing import CliRunner

from skill_agent.cli import main


def test_skill_list_empty(tmp_skills_dir):
    runner = CliRunner()
    res = runner.invoke(main, ["--skills-dir", str(tmp_skills_dir),
                               "skill", "list"])
    assert res.exit_code == 0, res.output
    assert "暂无 skill" in res.output


def test_skill_create_and_show(tmp_skills_dir):
    runner = CliRunner()
    res = runner.invoke(main, [
        "--skills-dir", str(tmp_skills_dir),
        "skill", "create",
        "--name", "hello",
        "--description", "say hi",
        "--body", "Output hi.",
    ])
    assert res.exit_code == 0, res.output
    res2 = runner.invoke(main, ["--skills-dir", str(tmp_skills_dir),
                                "skill", "show", "hello"])
    assert res2.exit_code == 0, res2.output
    assert "say hi" in res2.output
    assert "Output hi." in res2.output


def test_skill_show_unknown(tmp_skills_dir):
    runner = CliRunner()
    res = runner.invoke(main, ["--skills-dir", str(tmp_skills_dir),
                               "skill", "show", "ghost"])
    assert res.exit_code != 0
    assert "未知 skill" in res.output


def test_skill_delete(tmp_skills_dir, sample_skill):
    runner = CliRunner()
    res = runner.invoke(main, ["--skills-dir", str(tmp_skills_dir),
                               "skill", "delete", "greet", "--yes"])
    assert res.exit_code == 0, res.output
    assert not (tmp_skills_dir / "greet").exists()
    assert any((tmp_skills_dir / ".trash").glob("greet-*"))


def test_config_subcommand_shows_skills_dir(tmp_skills_dir, monkeypatch):
    # 让 DEEPSEEK_API_KEY 的状态可预期，并避免仓库 .env 干扰。
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    runner = CliRunner()
    res = runner.invoke(main, ["--skills-dir", str(tmp_skills_dir), "config"])
    assert res.exit_code == 0, res.output
    assert str(tmp_skills_dir) in res.output
    assert "未设置" in res.output
    assert "debug      : false" in res.output


def test_debug_option_is_shown_in_config(tmp_skills_dir):
    runner = CliRunner()
    res = runner.invoke(main, ["--skills-dir", str(tmp_skills_dir), "--debug", "config"])
    assert res.exit_code == 0, res.output
    assert "debug      : true" in res.output
