# skill-agent

一个轻量的 CLI Agent，用来管理并运行 **Claude Code 风格的 Skill**，由 **DeepSeek**（通过 OpenAI 兼容 API）驱动。

这里的 **skill** 是一个目录，通常包含一份 `SKILL.md`（YAML frontmatter + 指令正文）以及可选的捆绑脚本。Agent 采用 **两阶段加载**：启动时只把每个 skill 的 `name + description` 注入系统提示词；真正需要某个 skill 时，再调用 `load_skill` 拉取完整正文。

## 项目功能

### 1. Skill 管理

支持通过 CLI 对 skill 做完整 CRUD：

- 创建 skill
- 查看 skill
- 列出 skill
- 更新 skill
- 删除 skill
- 运行 skill

既可以使用确定性的子命令：

```bash
skill-agent skill list
skill-agent skill show example-greet
skill-agent skill create --name lint-fix --description "用 ruff 修复 Python lint 错误" --body "执行 ruff check --fix . 并报告 diff。"
skill-agent skill update lint-fix --description "修复 Python lint 问题"
skill-agent skill delete lint-fix --yes
```

也可以在 `chat` 对话中用自然语言让 Agent 通过工具调用完成 `create_skill`、`update_skill`、`delete_skill` 等操作。

### 2. 对话式 Agent

进入 REPL 后，可以直接用自然语言描述任务，Agent 会根据当前 skill catalog 判断是否需要加载并执行某个 skill。

REPL 支持的斜杠命令：

```text
/help      显示帮助
/skills    列出当前可用 skill
/reset     清空对话历史
/exit      退出
/quit      退出
```

### 3. 两阶段 Skill 加载

Agent 启动时不会把所有 `SKILL.md` 正文一次性塞进上下文，而是只加载：

```text
skill name + description
```

当模型判断某个 skill 适合当前任务时，才会调用：

```text
load_skill(name)
```

再读取完整 skill 指令和捆绑脚本信息。这样可以避免 prompt 随 skill 数量增长而快速膨胀。

### 4. 子 Agent 调用

Agent 可以通过：

```text
call_skill(name, input)
```

把某个 skill 作为子 agent 运行。子 agent 会把该 skill 的完整正文作为 system prompt，并使用传入的 `input` 执行任务。

为了避免 skill 之间互相调用导致无限递归，项目内置了递归深度限制。

### 5. 内置工具

Agent 可通过 function calling 使用以下工具：

| 工具 | 功能 |
| --- | --- |
| `list_skills` | 列出所有可用 skill |
| `load_skill` | 读取某个 skill 的完整正文和脚本信息 |
| `create_skill` | 创建新 skill |
| `update_skill` | 更新已有 skill |
| `delete_skill` | 软删除 skill |
| `call_skill` | 把 skill 作为子 agent 调用 |
| `read_file` | 读取允许目录内的文本文件 |
| `write_file` | 写入允许目录内的文本文件 |
| `run_bash` | 执行 bash 命令并返回 stdout/stderr/exit_code |

### 6. 安全限制

项目内置了几类基础安全保护：

- `read_file` / `write_file` 只能访问允许的根目录。
- `run_bash` 带超时控制。
- `run_bash` 输出会截断，避免超长输出撑爆上下文。
- 删除 skill 时不会直接永久删除，而是移动到 `.trash/`。
- `call_skill` 有最大递归深度限制。

## 安装

推荐在虚拟环境中安装：

```bash
cd /home/hunter/Documents/code/python/agent-skill
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

项目要求 Python `>=3.10`。

## 配置

复制示例环境变量文件：

```bash
cp .env.example .env
```

然后编辑 `.env`，填入真实的 API Key：

```env
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
SKILL_AGENT_MODEL=deepseek-chat
SKILL_AGENT_SKILLS_DIR=./skills
SKILL_AGENT_DEBUG=false
```

配置优先级：

```text
CLI 参数 > 环境变量 > .env > 默认值
```

可以用下面的命令查看当前解析后的配置：

```bash
skill-agent config
```

输出会显示：

- `skills_dir`
- `model`
- `base_url`
- `api_key` 是否已设置
- `debug` 是否开启

不会打印真实 API Key。

## Debug 调试

当需要排查大模型调用过程时，可以开启 debug 模式。开启后，每次调用大模型前后都会格式化打印当前 `messages` 列表。

### 通过 CLI 参数开启

`--debug` 是全局参数，需要放在子命令前面：

```bash
skill-agent --debug chat
```

也可以用于非交互式运行 skill：

```bash
skill-agent --debug skill run example-greet --input "Alice"
```

### 通过环境变量开启

```bash
SKILL_AGENT_DEBUG=true skill-agent chat
```

或写入 `.env`：

```env
SKILL_AGENT_DEBUG=true
```

支持的 true 值包括：

```text
1, true, yes, on
```

### Debug 输出示例

```text
=== LLM call #1 request messages ===
[
  {
    "role": "system",
    "content": "..."
  },
  {
    "role": "user",
    "content": "帮我向 Alice 打个招呼"
  }
]
=== end LLM call #1 request messages ===

=== LLM call #1 response messages ===
[
  ...
]
=== end LLM call #1 response messages ===
```

如果一次用户请求中模型多次调用工具，会继续出现：

```text
=== LLM call #2 request messages ===
=== LLM call #2 response messages ===
```

## 快速上手

### 1. 列出自带示例 skill

```bash
skill-agent skill list
```

### 2. 查看某个 skill 的完整内容

```bash
skill-agent skill show example-greet
```

### 3. 进入对话式 REPL

```bash
skill-agent chat
```

或直接执行：

```bash
skill-agent
```

进入后可以输入：

```text
帮我向 Alice 打个招呼
```

### 4. 非交互式运行单个 skill

```bash
skill-agent skill run example-greet --input "Alice"
```

### 5. 创建一个新 skill

```bash
skill-agent skill create \
  --name lint-fix \
  --description "用 ruff 修复 Python lint 错误" \
  --body "执行 'ruff check --fix .' 并报告 diff。"
```

也可以在 `skill-agent chat` 中直接说：

```text
创建一个能用 ruff 修复 Python lint 错误的 skill
```

Agent 会在确认意图后通过 `create_skill` 工具创建。

## 不安装时运行

如果不想先安装 console script，也可以从源码直接运行：

```bash
python -m skill_agent.cli config
python -m skill_agent.cli skill list
python -m skill_agent.cli chat
```

注意必须使用 `-m`。

不要这样执行：

```bash
python skill_agent.cli
python skill_agent/cli.py
```

否则可能因为包相对导入失败而报错。

## 执行流程

以用户在 REPL 中输入：

```text
给 Alice 打个招呼
```

为例，执行流程大致如下：

1. `skill-agent chat` 启动 REPL。
2. REPL 把用户输入交给 `Agent.run_chat(...)`。
3. Agent 构造 system prompt，其中只包含 skill catalog。
4. 模型判断 `example-greet` 适合当前需求。
5. 模型调用 `load_skill("example-greet")` 读取完整 `SKILL.md`。
6. 模型根据 skill 指令调用 `run_bash` 执行捆绑脚本。
7. `run_bash` 返回 stdout、stderr、exit_code 等信息。
8. 模型根据工具结果生成最终 JSON 回复。
9. REPL 渲染最终回复。

更详细的调用链可以查看 `EXECUTION_FLOW.md`。

## 当前内置 Skill

| Skill | 功能 |
| --- | --- |
| `example-greet` | 通过运行 Python 脚本向某人打招呼 |
| `hello-world` | 运行脚本输出 Hello World |
| `brainstorming` | 用于需求澄清、方案探索和设计讨论 |
| `task-splitter` | 根据用户需求拆分阶段计划 |

## 目录结构

```text
skill_agent/
  __init__.py
  cli.py                  # click 命令入口：chat / config / skill 子命令
  config/
    __init__.py           # 仅导出配置模块公开对象
    config.py             # 配置加载：CLI 参数、环境变量、.env、默认值
  llm/
    __init__.py           # 仅导出 Agent
    agent.py              # DeepSeek/OpenAI function-calling 主循环
  prompts/
    __init__.py           # 仅导出 prompt 渲染函数和模板
    prompts.py            # 顶层 Agent 和子 Agent 的 system prompt 模板
  registry/
    __init__.py           # 仅导出 SkillRegistry
    registry.py           # skills 目录扫描、两阶段加载、CRUD、软删除
  repl/
    __init__.py           # 仅导出 REPL 入口
    repl.py               # 交互式 REPL
  skill/
    __init__.py           # 仅导出 Skill 模型和解析函数
    skill.py              # Skill 数据模型、SKILL.md 解析与渲染
  tools/
    __init__.py           # 仅导出 tools schema 与 ToolDispatcher
    dispatcher.py         # OpenAI tools schema 与 ToolDispatcher
    bash_tool.py          # bash 执行工具，带超时和输出截断
    fs_tools.py           # 带路径白名单的文件读写工具
    skill_tools.py        # 暴露给 Agent 的 skill 管理工具

skills/                   # 默认 skill 根目录
  example-greet/
  hello-world/
  brainstorming/
  task-splitter/

tests/                    # pytest 测试套件
  test_agent_loop.py      # Agent 主循环测试
  test_cli.py             # CLI 测试
  test_registry.py        # SkillRegistry 测试
  test_skill_parsing.py   # SKILL.md 解析测试
  test_tools.py           # 内置工具测试
```

## 模块说明

### `skill_agent.cli`

CLI 入口模块，负责：

- 定义 `skill-agent` 命令；
- 加载配置；
- 初始化 `SkillRegistry`；
- 组装 `Agent`；
- 提供 `chat`、`config`、`skill list/show/create/update/delete/run` 等命令。

### `skill_agent.config`

负责加载配置并合并不同来源：

- CLI 参数；
- 环境变量；
- `.env` 文件；
- 默认值。

默认值包括：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
SKILL_AGENT_MODEL=deepseek-chat
SKILL_AGENT_SKILLS_DIR=./skills
```

### `skill_agent.skill`

负责 `SKILL.md` 的解析、校验和渲染。

主要规则：

- 必须包含 YAML frontmatter；
- 必须有 `name`；
- 必须有 `description`；
- `name` 必须是 kebab-case；
- `description` 必须是单行字符串；
- 同目录下的 `.py` / `.sh` 文件会被识别为捆绑脚本。

### `skill_agent.registry`

封装 `skills/` 目录，维护 skill 索引。

负责：

- 扫描 skill 目录；
- 跳过隐藏目录和格式错误的 skill；
- catalog 懒加载；
- 完整正文按需加载；
- 创建、更新、软删除 skill；
- 将删除的 skill 移动到 `.trash/`。

### `skill_agent.llm.agent`

Agent 核心循环。

负责：

- 构造 messages；
- 调用 DeepSeek/OpenAI 兼容接口；
- 处理 tool calls；
- 调度工具；
- 把工具结果写回 messages；
- 检查最终回复必须是 JSON 对象；
- 支持子 agent 调用；
- 通过 `max_iters` 防止模型无限调用工具。

### `skill_agent.prompts`

集中管理 prompt 模板：

- 顶层 Agent system prompt；
- 子 Agent system prompt；
- skill catalog 渲染；
- 最终 JSON 回复格式约束。

### `skill_agent.repl`

交互式命令行界面。

负责：

- 读取用户输入；
- 维护多轮对话历史；
- 处理 `/help`、`/skills`、`/reset`、`/exit`；
- 调用 `Agent.run_chat(...)`；
- 用 rich 渲染用户输入和 Agent 回复。

### `skill_agent.tools`

工具层，提供给模型 function calling 使用。

包含：

- skill 管理工具；
- 文件读写工具；
- bash 执行工具；
- OpenAI tools schema；
- 工具分发器 `ToolDispatcher`。

## 测试

运行全量测试：

```bash
pytest -q
```

运行单个测试文件：

```bash
pytest tests/test_agent_loop.py -q
pytest tests/test_registry.py -q
```

按名称过滤：

```bash
pytest -k "registry" -q
```

Agent loop 的测试使用脚本化伪客户端，不会消耗真实 DeepSeek API 配额。
