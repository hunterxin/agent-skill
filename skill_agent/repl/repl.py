"""交互式 REPL：与 agent 的多轮对话。"""

from __future__ import annotations

from typing import List

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from ..llm import Agent


HELP = """\
[bold]命令[/bold]
  /help          显示帮助
  /skills        列出已知的 skill
  /reset         清空对话历史
  /exit, /quit   退出 REPL
其他输入都会作为用户消息发送给 agent。
"""


def run_repl(agent: Agent) -> None:
    console = Console()
    session = PromptSession(history=InMemoryHistory())
    console.print(Panel.fit(
        "[bold]skill-agent[/bold] —— 由 DeepSeek 驱动的 Skill 调度器\n"
        f"模型: [cyan]{agent.model}[/cyan]   "
        f"skills: [cyan]{agent.registry.root}[/cyan]\n"
        "输入 [yellow]/help[/yellow] 查看命令，[yellow]/exit[/yellow] 退出",
        border_style="cyan",
    ))

    history: List[dict] = []

    while True:
        try:
            user = session.prompt("you ❯ ").strip()
            console.print(Panel(Markdown(user),
                               border_style="yellow", title="you"))
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见。[/dim]")
            return

        if not user:
            continue

        if user in {"/exit", "/quit"}:
            return
        if user == "/help":
            console.print(HELP)
            continue
        if user == "/reset":
            history.clear()
            console.print("[dim]历史已清空。[/dim]")
            continue
        if user == "/skills":
            catalog = agent.registry.catalog_for_prompt()
            if not catalog:
                console.print("[dim]暂无 skill[/dim]")
            else:
                for n, d in catalog:
                    console.print(f"  [bold cyan]{n}[/bold cyan] — {d}")
            continue

        try:
            reply = agent.run_chat(history, user)
            console.print(Panel(Markdown(reply),
                               border_style="green", title="agent"))
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]错误: {type(e).__name__}: {e}[/red]")
            continue

        # 把这一轮对话追加到 history，供下一轮使用。
        history.append({"role": "user", "content": user})
        history.append({"role": "assistant", "content": reply})
