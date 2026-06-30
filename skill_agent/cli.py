"""CLI 入口 —— click 子命令。

这是整个 `skill-agent` 命令行工具的入口模块。

外部世界进入本模块有两种方式（最终都会落到 `main` 上）：

1. `pip install -e .` 之后 PATH 里多出的可执行脚本 ``skill-agent``。
   它由 ``pyproject.toml`` 中的
   ``[project.scripts] skill-agent = "skill_agent.cli:main"`` 注册。
2. ``python -m skill_agent.cli <subcommand>``。
   此时 Python 把本文件当成 ``__main__`` 模块执行，文件末尾的
   ``if __name__ == "__main__": main()`` 触发 click。

整个模块只做一件事：
    用 click 构造一棵"命令树"，并在每个叶子命令里把
    ``Config / SkillRegistry / Agent / REPL`` 这几个核心对象装配起来。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from .llm import Agent
from .config import Config, load_config
from .registry import SkillRegistry
from .repl import run_repl


# 全局共享的 rich Console，用来给终端输出上色 / 渲染样式。
# 之所以做成模块级单例，是因为所有子命令的"打印"都走它，没必要每次新建。
CONSOLE = Console()


def _make_client(cfg: Config):
    """构造一个与 DeepSeek 通讯的 OpenAI 兼容客户端。

    参数说明
    --------
    cfg : Config
        通过 :func:`skill_agent.config.load_config` 解析出的配置对象，里面已经
        合并好了 CLI 参数 / 环境变量 / `.env` / 默认值。本函数只用到三个字段：
        ``api_key``、``base_url`` 以及 ``has_api_key`` 这个布尔便捷属性。

    返回值
    ------
    ``openai.OpenAI`` 实例。它的 ``chat.completions.create(...)`` 接口和
    DeepSeek HTTP API 完全兼容，所以可以无缝接到 :class:`Agent` 的主循环里。

    设计要点
    --------
    * **延迟导入**：``from openai import OpenAI`` 写在函数体内而不是模块顶部。
      这样做有两个好处：
        1. 跑测试时 ``ScriptedClient`` 直接替代真实客户端，根本不需要 ``openai``
           包，避免给测试环境塞重型依赖；
        2. 像 ``skill-agent skill list`` 这种**纯本地**的命令不需要 LLM，也就
           不会触发 ``openai`` 的导入，启动更轻。
    * **先校验后创建**：缺 API key 时立刻抛 ``click.ClickException``，click 会
      用红色友好地打到 stderr 并返回非零退出码，比让 openai 库自己报错更清晰。
    """
    if not cfg.has_api_key:
        # 用 click 的异常类抛错，框架会把 message 漂亮地打印出来，且退出码为 1。
        raise click.ClickException(
            "未设置 DEEPSEEK_API_KEY。请把它放进 .env 或 `export`，"
            "或通过 --api-key 传入。"
        )
    from openai import OpenAI  # noqa: WPS433 —— 延迟导入是有意为之
    return OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)


@click.group(invoke_without_command=True)
@click.option("--skills-dir", default=None, help="skills 目录路径。")
@click.option("--model", default=None, help="DeepSeek 模型 id（默认 deepseek-chat）。")
@click.option("--api-key", default=None, help="覆盖 DEEPSEEK_API_KEY。")
@click.option("--base-url", default=None, help="覆盖 DeepSeek base URL。")
@click.option("--debug", is_flag=True, help="打印每次大模型调用前后的 messages。")
@click.pass_context
def main(ctx: click.Context, skills_dir, model, api_key, base_url, debug):
    """skill-agent：用 DeepSeek 管理并运行 Skill。

    这个函数同时充当三种角色：

    1. **CLI 总入口**（被 `pyproject.toml` 中的 console script 引用）；
    2. **顶层选项解析器**：把全局选项收口到这里，所有子命令共享；
    3. **依赖装配器**：构造 ``Config`` 与 ``SkillRegistry``，挂到 ``ctx.obj``
       供任意子命令取用。

    参数
    ----
    ctx : click.Context
        click 自动注入的上下文对象，用来在父子命令之间传递依赖。
    skills_dir, model, api_key, base_url
        与同名选项一一对应；用户没传的字段是 ``None``，会被 ``load_config``
        视为"未指定"并回退到下一优先级的来源（env → .env → 默认值）。

    控制流
    ------
    * ``load_config`` 把四个 None 透传进去，由它负责"CLI > env > .env > default"
      的优先级合并并返回 :class:`Config`。
    * ``ctx.ensure_object(dict)`` 确保 ``ctx.obj`` 是一个 ``dict``——之后可以
      按 key 塞东西，子命令通过 ``ctx.obj["config"]`` 等读取。
    * ``SkillRegistry(cfg.skills_dir)`` 仅 ``mkdir``，**不**触发磁盘扫描；
      真正的 ``refresh`` 发生在首次查询。
    * ``ctx.invoked_subcommand`` 为 ``None`` 表示用户只敲了 ``skill-agent``、
      没指定子命令；此时 ``ctx.invoke(chat)`` 直接转跳到 chat 子命令。
    """
    cfg = load_config(
        skills_dir=skills_dir,
        model=model,
        api_key=api_key,
        base_url=base_url,
        debug=debug,
    )
    ctx.ensure_object(dict)
    ctx.obj["config"] = cfg
    ctx.obj["registry"] = SkillRegistry(cfg.skills_dir)
    if ctx.invoked_subcommand is None:
        # 没有显式给子命令时，等价于 `skill-agent chat`。
        # ctx.invoke 会复用当前 ctx，不会重新走一遍父命令的初始化。
        ctx.invoke(chat)


# --------------------------------------------------------------------- chat

@main.command()
@click.pass_context
def chat(ctx: click.Context):
    """进入交互式 REPL。

    这是真正会"花钱"的命令——它会构造 OpenAI 客户端、产生 LLM 调用。

    步骤
    ----
    1. 从 ``ctx.obj`` 取出已经准备好的 ``Config`` 与 ``SkillRegistry``；
       这两个对象是父命令 :func:`main` 装配的。
    2. ``_make_client(cfg)`` 校验 API key 并延迟构造 ``openai.OpenAI``。
    3. 用 client + registry + 模型名构造 :class:`Agent`——注意 ``Agent``
       本身**不持有对话历史**，是无状态的，history 由 REPL 维护。
    4. 调 :func:`run_repl` 进入"读输入 → 调 ``Agent.run_chat`` → 渲染回复"
       的死循环；唯一的退出方式是 Ctrl-D / Ctrl-C / ``/exit``。

    参数
    ----
    ctx : click.Context
        click 上下文，用来读父命令塞进来的 ``Config`` / ``SkillRegistry``。
    """
    cfg: Config = ctx.obj["config"]
    registry: SkillRegistry = ctx.obj["registry"]
    client = _make_client(cfg)
    agent = Agent(client=client, registry=registry, model=cfg.model, debug=cfg.debug)
    run_repl(agent)


# --------------------------------------------------------------------- config

@main.command()
@click.pass_context
def config(ctx: click.Context):
    """显示已解析的配置。

    用于排查"为什么我设置了环境变量却没生效"之类的问题。

    特别注意：``api_key`` 字段**只显示是否已设置**，不会泄露 key 的真实内容，
    避免在演示 / 截屏时不小心走光。
    """
    cfg: Config = ctx.obj["config"]
    CONSOLE.print(f"skills_dir : [cyan]{cfg.skills_dir}[/cyan]")
    CONSOLE.print(f"model      : [cyan]{cfg.model}[/cyan]")
    CONSOLE.print(f"base_url   : [cyan]{cfg.base_url}[/cyan]")
    CONSOLE.print(f"api_key    : [cyan]{'已设置' if cfg.has_api_key else '未设置'}[/cyan]")
    CONSOLE.print(f"debug      : [cyan]{str(cfg.debug).lower()}[/cyan]")


# ----------------------------------------------------------------- skill 组

@main.group()
def skill():
    """管理 skill（CRUD）。

    这是一个**嵌套**命令组——``main`` 是根、``skill`` 是它的子组，再往下挂
    ``list / show / create / update / delete / run`` 这些叶子命令。

    所有 skill 子命令的共同点：**直接调用 SkillRegistry，完全不经过 LLM**。
    这是"确定性 CRUD 通道"——保证哪怕模型挂掉/没 key，用户也能可靠地管理
    skill。和自然语言版（chat 里让 agent 调 ``create_skill`` 工具）形成对照。
    """


@skill.command("list")
@click.pass_context
def skill_list(ctx: click.Context):
    """列出所有已知的 skill。

    输出每个 skill 的名字与一行简介，用 rich 染色。
    首次访问 ``catalog_for_prompt`` 时会触发 ``SkillRegistry.refresh()``
    扫描磁盘——所以即便外部刚 ``cp -r`` 了一个新 skill 进来，这条命令也能
    马上看见它。
    """
    registry: SkillRegistry = ctx.obj["registry"]
    catalog = registry.catalog_for_prompt()
    if not catalog:
        CONSOLE.print("暂无 skill。")
        return
    for n, d in catalog:
        CONSOLE.print(f"  [bold cyan]{n}[/bold cyan] — {d}")


# --------------------------------------------------------------- skill show

@skill.command("show")
@click.argument("name")
@click.pass_context
def skill_show(ctx: click.Context, name: str):
    """显示一个 skill 的完整 SKILL.md。

    装饰器要点
    ----------
    * ``@click.argument("name")``
        声明一个**位置参数**（不是 ``--name`` 选项）。用法是
        ``skill-agent skill show <name>``。argument 默认必填，且类型默认为
        字符串；不像 option 那样能写 default。
    * ``@click.pass_context``
        与其它子命令一致，用来读父命令塞进 ``ctx.obj`` 的 registry。

    行为
    ----
    * 调用 ``registry.load_full(name)`` 拉取完整正文（包括 body 与捆绑脚本
      列表）。它内部会重新 ``parse_skill_md`` 一次，确保读到的是磁盘最新值。
    * 找不到时 ``KeyError`` 被翻译成 ``click.ClickException``，CLI 退出码
      非零，提示 "未知 skill: xxx"——这是 ``test_cli.py`` 里约定好的行为。
    """
    registry: SkillRegistry = ctx.obj["registry"]
    try:
        skill_obj = registry.load_full(name)
    except KeyError:
        raise click.ClickException(f"未知 skill: {name}")
    CONSOLE.print(f"[bold]{skill_obj.name}[/bold] — {skill_obj.description}")
    CONSOLE.print(f"[dim]{skill_obj.md_path}[/dim]\n")
    CONSOLE.print(skill_obj.body)
    if skill_obj.scripts:
        CONSOLE.print("\n[bold]scripts:[/bold]")
        for fn in skill_obj.scripts:
            CONSOLE.print(f"  - {fn}")


# ------------------------------------------------------------- skill create

@skill.command("create")
@click.option("--name", required=True, help="kebab-case 标识符。")
@click.option("--description", required=True, help="一行简介。")
@click.option("--body", required=True, help="SKILL.md 正文（指令）。")
@click.pass_context
def skill_create(ctx: click.Context, name: str, description: str, body: str):
    """创建一个新的 skill（确定性通道，不经过模型）。

    装饰器要点
    ----------
    * ``@click.option("--name", required=True, ...)``
        ``required=True`` 意味着没传该选项时 click 会自动报错退出，免去我们
        手写参数校验。
    * 三个 option 全部强制必填，于是这条命令完全是"幂等可脚本化"的——非常
      适合塞进 Makefile / CI 里批量造 skill。

    行为
    ----
    ``registry.create`` 内部做了：
        1. ``validate_name`` 校验 kebab-case；
        2. 在 ``skills/<name>/`` ``mkdir``（已存在则 ``FileExistsError``）；
        3. 调 ``render_skill_md`` 写出 SKILL.md；
        4. ``refresh`` 重建内存索引。
    任何步骤抛 ``ValueError / FileExistsError`` 都会被 click 包成异常退出。
    """
    registry: SkillRegistry = ctx.obj["registry"]
    skill_obj = registry.create(name=name, description=description, body=body)
    CONSOLE.print(f"已创建 [bold cyan]{skill_obj.name}[/bold cyan] → {skill_obj.path}")


# ------------------------------------------------------------- skill update

@skill.command("update")
@click.argument("name")
@click.option("--description", default=None, help="新的一行简介；不传则保留。")
@click.option("--body", default=None, help="新的正文；不传则保留。")
@click.pass_context
def skill_update(ctx: click.Context, name: str, description, body):
    """更新一个已存在的 skill。

    设计上**只覆盖显式传入的字段**：``description`` / ``body`` 默认 None，
    传给 ``registry.update`` 后由它做 "None 就保留原值" 的逻辑——这样可以
    只改 description 不动 body，反之亦然。
    """
    registry: SkillRegistry = ctx.obj["registry"]
    try:
        skill_obj = registry.update(name=name, description=description, body=body)
    except KeyError:
        raise click.ClickException(f"未知 skill: {name}")
    CONSOLE.print(f"已更新 [bold cyan]{skill_obj.name}[/bold cyan]")


# ------------------------------------------------------------- skill delete

@skill.command("delete")
@click.argument("name")
@click.option("--yes", is_flag=True, help="跳过确认。")
@click.pass_context
def skill_delete(ctx: click.Context, name: str, yes: bool):
    """软删除一个 skill（移动到 ``<skills_dir>/.trash/<name>-<ts>/``）。

    装饰器要点
    ----------
    * ``@click.option("--yes", is_flag=True)``
        声明一个布尔开关，``is_flag=True`` 表示它**没有值**——传了 ``--yes``
        就是 True，没传就是 False。这里作为"跳过交互确认"的逃生口，方便
        脚本化使用。

    行为
    ----
    * 没传 ``--yes`` 时调 ``click.confirm`` 弹出 y/N 提示；用户拒绝就 ``return``。
    * ``registry.delete`` 是软删除：把目录 mv 进 ``.trash/`` 并打时间戳，
      所以"删错了"也能从 trash 里捡回来。
    """
    registry: SkillRegistry = ctx.obj["registry"]
    if not yes:
        click.confirm(f"确认删除 skill {name!r}？", abort=False, default=False) or (_ for _ in ()).throw(SystemExit(0))
    try:
        dest = registry.delete(name)
    except KeyError:
        raise click.ClickException(f"未知 skill: {name}")
    CONSOLE.print(f"已删除 [bold cyan]{name}[/bold cyan] → {dest}")


# ---------------------------------------------------------------- skill run

@skill.command("run")
@click.argument("name")
@click.option("--input", "user_input", default="", help="给 skill 的用户输入。")
@click.pass_context
def skill_run(ctx: click.Context, name: str, user_input: str):
    """以"子 agent"的方式跑一个 skill，一次性把结果打到终端。

    这是 chat 的非交互版本：不进 REPL，直接借助 ``Agent._call_skill`` 通道
    把整条流程跑完。适合放进 shell 管道、定时任务、CI 步骤里。

    装饰器要点
    ----------
    * ``@click.option("--input", "user_input", ...)``
        第二个位置参数 ``user_input`` 是**目标变量名**——click 默认会把
        ``--input`` 映射成同名变量，但 ``input`` 与 Python 内建函数重名，
        所以这里显式改名。

    行为
    ----
    1. 构造 ``OpenAI client`` 与 ``Agent``（与 ``chat`` 同样的初始化路径）；
    2. 调 ``agent._call_skill(name, user_input)`` —— 这是 Agent 内部的子
       agent 入口：它会 ``load_full`` 拿 skill 正文、用 ``SUBAGENT_TEMPLATE``
       渲染 system prompt，再起一个 ``_depth+1`` 的子 ``Agent`` 跑 ``_loop``，
       最终把子 agent 的回复返回。
    3. 用 rich 把回复打到 stdout。
    """
    cfg: Config = ctx.obj["config"]
    registry: SkillRegistry = ctx.obj["registry"]
    client = _make_client(cfg)
    agent = Agent(client=client, registry=registry, model=cfg.model, debug=cfg.debug)
    try:
        reply = agent._call_skill(name, user_input)
    except KeyError:
        raise click.ClickException(f"未知 skill: {name}")
    CONSOLE.print(reply)


# =====================================================================
# 模块级入口：让 `python -m skill_agent.cli` 也能直接跑
# ---------------------------------------------------------------------
# 安装后的 `skill-agent` 命令走的是 console script（pyproject.toml 里注册
# 的 entry point），不会经过这一段；但只想 `python -m skill_agent.cli ...`
# 不安装就跑的话，必须有这一段把 main 触发起来。
# =====================================================================
if __name__ == "__main__":
    main()
