# P0 原型验证（Spikes P0–P8）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在正式实现前，用最小实验验证 spec §11 的 P0–P8 假设，产出决策记录并写回 spec。

**Architecture:** 全部实验隔离在项目仓库的 `spikes/` 目录内：一个最小测试包（单 PyPI 分发、双 console scripts、hello MCP server）+ 一个最小插件/Marketplace 目录，逐一在真实 Codex 环境（CLI / 桌面端 / IDE 扩展）中验证，结果记录到 `spikes/RESULTS.md`，最后汇总决策写回 spec。

**Tech Stack:** uv/uvx、hatchling、Python `mcp` SDK（FastMCP）、Codex CLI、ChatGPT 桌面端（Codex 模式）、VS Code Codex 扩展、GitHub/Gitee。

## Global Constraints

- 所有实验产物只进 `spikes/`（轮子 `spikes/hello-pkg/dist/` 不入库）；不改动全局 pip/uv 配置（spec §3.8/§11 P8）。
- 测试包名用最终名 `vibe-submit`，但 spike 阶段**不发布到公共 PyPI**，只用本地 wheel 与（可选）TestPyPI。
- 插件/Marketplace 清单字段以官方文档为准（[build-plugins](https://learn.chatgpt.com/docs/build-plugins)，2026-07 查阅），不臆造字段。
- 每个 spike 的结论只有三种：**成立 / 不成立 / 部分成立**，必须附命令与输出摘要作为证据。
- spec 回退路径已定（§11 各行的"不成立时的备选"列），本计划只做验证与记录，不重新设计。
- 环境前提（执行者自备）：已登录的 Codex CLI、ChatGPT 桌面端（Codex 模式可用）、VS Code + Codex 扩展、GitHub 与 Gitee 账号、一台 Windows 机器（可用 VM/另一用户模拟"干净学生机"）。无对应环境时跳过该 Task 并在 RESULTS.md 记"未验证-缺环境"。

---

### Task 1: spike 工作区与结果记录模板

**Files:**
- Create: `spikes/RESULTS.md`
- Create: `.gitignore`

**Interfaces:**
- Consumes: 无
- Produces: `spikes/RESULTS.md`（所有后续 Task 更新的结果表）；`.gitignore` 忽略 `spikes/**/dist/`、`__pycache__`

- [ ] **Step 1: 创建 RESULTS.md**

```markdown
# Spike 结果记录（P0–P8）

环境：OS=____  Codex CLI 版本=____  桌面端版本=____  uv 版本=____  日期=____

| # | 验证项摘要 | 结果 | 证据（命令+输出摘要） | 采用路径（主/备选/未验证） | 需更新的 spec 章节 |
|---|---|---|---|---|---|
| P0 | 仅桌面端环境的 marketplace 发现 |  |  |  | §3.2, §11 |
| P1 | 插件 .mcp.json 在 CLI 启动 MCP；env 字段 |  |  |  | §3.1, §11 |
| P2 | Windows 端到端；GUI PATH 陈旧 |  |  |  | §3.2, §7, §11 |
| P3 | 桌面端读取 CLI 注册的 marketplace |  |  |  | §3.2, §11 |
| P4 | IDE 扩展读 config.toml [mcp_servers] |  |  |  | §3.2, §11 |
| P5 | git-subdir 布局；Gitee 兼容 |  |  |  | §3.1, §9, §11 |
| P6 | 仓库级 marketplace 自动发现（可选） |  |  |  | §11 |
| P7 | uvx --from 钉版与升级行为 |  |  |  | §3.1, §3.3, §11 |
| P8 | 镜像局部化方案 |  |  |  | §3.2, §7, §11 |
```

- [ ] **Step 2: 创建 .gitignore**

```
spikes/**/dist/
spikes/**/__pycache__/
```

- [ ] **Step 3: 记录环境版本**

```powershell
codex --version
uvx --version
```
把输出填入 RESULTS.md 表头环境行；uv 不存在则先记录"未安装"（P2 会装）。

- [ ] **Step 4: Commit**

```bash
git add spikes/RESULTS.md .gitignore
git commit -m "spike: 工作区与结果记录模板"
```

---

### Task 2: 最小测试包（hello MCP + CLI，双 console scripts）

**Files:**
- Create: `spikes/hello-pkg/pyproject.toml`
- Create: `spikes/hello-pkg/src/vibe_submit/__init__.py`
- Create: `spikes/hello-pkg/src/vibe_submit/cli.py`
- Create: `spikes/hello-pkg/src/vibe_submit/mcp_server.py`

**Interfaces:**
- Consumes: 无
- Produces: 本地 wheel `spikes/hello-pkg/dist/vibe_submit-<ver>-py3-none-any.whl`；两个入口点 `vibe-submit` / `vibe-submit-mcp`（Task 3/5 使用）

- [ ] **Step 1: pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "vibe-submit"
version = "0.1.0"
description = "spike test package"
requires-python = ">=3.10"
dependencies = ["mcp>=1.2.0"]

[project.scripts]
vibe-submit = "vibe_submit.cli:main"
vibe-submit-mcp = "vibe_submit.mcp_server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/vibe_submit"]
```

- [ ] **Step 2: `__init__.py`（空文件）与 cli.py**

```python
# cli.py
import argparse
from importlib.metadata import version


def main():
    p = argparse.ArgumentParser(prog="vibe-submit")
    p.add_argument("--version", action="store_true")
    p.parse_args()
    print(f"vibe-submit {version('vibe-submit')}")
```

- [ ] **Step 3: mcp_server.py**

```python
import os
import sys
from importlib.metadata import version

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("vibe-submit-spike")


@mcp.tool()
def ping() -> str:
    """健康检查：返回版本与 Python 版本"""
    return f"pong v{version('vibe-submit')} python={sys.version.split()[0]}"


@mcp.tool()
def env_check(name: str) -> str:
    """报告指定环境变量是否存在于 MCP server 进程"""
    return f"{name}={'SET' if name in os.environ else 'MISSING'}"


def main():
    mcp.run()
```

- [ ] **Step 4: 构建 wheel**

```powershell
cd spikes/hello-pkg
uv build
```
预期：`dist/vibe_submit-0.1.0-py3-none-any.whl` 生成。

- [ ] **Step 5: 冒烟——两个入口点都能跑**

```powershell
uvx --from ./dist/vibe_submit-0.1.0-py3-none-any.whl vibe-submit --version
```
预期输出：`vibe-submit 0.1.0`。MCP 入口在 Task 5 验证。

- [ ] **Step 6: Commit**

```bash
git add spikes/hello-pkg/
git commit -m "spike: 最小测试包（双 console scripts）"
```

---

### Task 3: P7——uvx --from 准确形式、钉版与升级行为

**Files:**
- Modify: `spikes/hello-pkg/pyproject.toml`（版本 0.1.0→0.2.0 实验）
- Modify: `spikes/RESULTS.md`（P7 行）

**Interfaces:**
- Consumes: Task 2 的 wheel 与入口点
- Produces: P7 结论：①`uvx --from <dist>==<ver> <script>` 形式成立性；②同一缓存是否按版本隔离；③升级后旧版可否共存

- [ ] **Step 1: 包名≠入口点形式验证（本地 wheel）**

```powershell
uvx --from ./dist/vibe_submit-0.1.0-py3-none-any.whl vibe-submit --version
```
预期：`vibe-submit 0.1.0`（证明 `--from <分发> <脚本名>` 形式正确）。

- [ ] **Step 2: 版本隔离——构建 0.2.0**

把 `pyproject.toml` 的 `version = "0.1.0"` 改为 `"0.2.0"`，`uv build`，得到 `dist/vibe_submit-0.2.0-py3-none-any.whl`。

- [ ] **Step 3: 两版本并存调用**

```powershell
uvx --from ./dist/vibe_submit-0.2.0-py3-none-any.whl vibe-submit --version
uvx --from ./dist/vibe_submit-0.1.0-py3-none-any.whl vibe-submit --version
```
预期：分别输出 `0.2.0` / `0.1.0`（换源即换环境，钉版可靠）。

- [ ] **Step 4: PyPI 钉版语义（在线，可选 TestPyPI）**

不发布公共 PyPI。改为验证等价语义——`uvx --from "httpx==0.27.0" python -c "import httpx;print(httpx.__version__)"`，再换 `==0.28.0` 各跑一次。预期：严格按 pin 解析，互不影响。

- [ ] **Step 5: 记录**

把 Step 1/3/4 的命令与输出摘要填入 RESULTS.md P7 行；结论写入"采用路径"。若 `--from` 形式不成立，按 spec 备选改记 `uv tool install` + 显式升级。

- [ ] **Step 6: Commit**

```bash
git add spikes/
git commit -m "spike: P7 uvx 钉版与升级行为"
```

---

### Task 4: P8——镜像加速的局部化方案

**Files:**
- Modify: `spikes/RESULTS.md`（P8 行）

**Interfaces:**
- Consumes: Task 2 的 wheel
- Produces: P8 结论：可行的局部镜像注入方式（子进程环境变量 / cwd 局部 uv.toml），及"未触碰全局配置"的证据

- [ ] **Step 1: 基线——确认当前无全局 uv 配置**

```powershell
Test-Path $env:APPDATA\uv\uv.toml
pip config list
```
预期：`False`、pip 无 index-url 全局项（若有，先记录原值，实验后必须保持原样）。

- [ ] **Step 2: 子进程环境变量注入（PowerShell）**

```powershell
$env:UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
uvx --from ./spikes/hello-pkg/dist/vibe_submit-0.1.0-py3-none-any.whl vibe-submit --version
Remove-Item Env:UV_INDEX_URL
```
预期：正常输出 `vibe-submit 0.1.0`；变量随会话结束消失。

- [ ] **Step 3: cwd 局部 uv.toml**

在 `spikes/` 下放 `uv.toml`：

```toml
[[index]]
url = "https://pypi.tuna.tsinghua.edu.cn/simple"
default = true
```

```powershell
cd spikes; uvx --from ./hello-pkg/dist/vibe_submit-0.1.0-py3-none-any.whl vibe-submit --version; cd ..
```
预期：生效且仅对该 cwd 生效；`$env:APPDATA\uv\uv.toml` 依旧不存在。

- [ ] **Step 4: 记录**

两种方式何者可行、证据、以及"全局配置未改动"的复查输出填入 P8 行；采用路径 = 可行的局部方式（两者皆可行时优先子进程环境变量，作用域最小）。

- [ ] **Step 5: Commit**

```bash
git add spikes/
git commit -m "spike: P8 镜像局部化"
```

---

### Task 5: P1——插件 .mcp.json 在 Codex CLI 实际启动 MCP（含 env 字段试验）

**Files:**
- Create: `spikes/marketplace/.agents/plugins/marketplace.json`
- Create: `spikes/marketplace/plugins/vibe-submit-spike/.codex-plugin/plugin.json`
- Create: `spikes/marketplace/plugins/vibe-submit-spike/.mcp.json`
- Create: `spikes/marketplace/plugins/vibe-submit-spike/skills/submit-homework-spike/SKILL.md`
- Modify: `spikes/RESULTS.md`（P1 行）

**Interfaces:**
- Consumes: Task 2 的 wheel（.mcp.json 的 args 引用其绝对路径）
- Produces: P1 结论：插件 MCP 在 CLI 会话可调；env 字段是否被支持；Skill 是否随插件出现

- [ ] **Step 1: plugin.json**

```json
{
  "name": "vibe-submit-spike",
  "version": "0.1.0",
  "description": "spike: 验证插件 MCP 启动",
  "mcpServers": "./.mcp.json",
  "skills": "./skills/"
}
```

- [ ] **Step 2: .mcp.json（先用绝对路径 wheel，隔离变量）**

```json
{
  "vibe-submit-spike": {
    "command": "uvx",
    "args": [
      "--from",
      "E:/myprogramfiles/Vibe Coding 作业提交与智能评估系统/spikes/hello-pkg/dist/vibe_submit-0.1.0-py3-none-any.whl",
      "vibe-submit-mcp"
    ]
  }
}
```
（路径按实际位置调整，正斜杠避免转义问题。）

- [ ] **Step 3: SKILL.md**

```markdown
---
name: submit-homework-spike
description: spike 技能：验证插件内 Skill 随插件可用
---

这是 spike 技能。被调用时说明：正式版将引导调用 submit_homework；当前请调用 ping 工具验证 MCP。
```

- [ ] **Step 4: marketplace.json**

```json
{
  "name": "vibe-course-spike",
  "interface": { "displayName": "Vibe 课程 Spike" },
  "plugins": [
    {
      "name": "vibe-submit-spike",
      "source": { "source": "local", "path": "./plugins/vibe-submit-spike" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Education"
    }
  ]
}
```

- [ ] **Step 5: 注册并安装**

```powershell
codex plugin marketplace add ./spikes/marketplace
codex plugin marketplace list
```
预期：list 含 `vibe-course-spike`。然后 `codex` 进 TUI → `/plugins` → 该 marketplace tab → 安装 `vibe-submit-spike`（人工操作）。

- [ ] **Step 6: 会话内验证 MCP 与 Skill**

新会话中输入：`请调用 vibe-submit-spike 的 ping 工具，然后使用 submit-homework-spike 技能`。
预期：返回 `pong v0.1.0 python=…`；技能内容被遵循。记录确认工具存在的方式（TUI 工具列表/agent 实际调用截图或日志）。

- [ ] **Step 7: env 字段试验**

在 `.mcp.json` 的 server 条目加 `"env": {"UV_INDEX_URL": "https://pypi.tuna.tsinghua.edu.cn/simple"}`，刷新/重装插件，会话中调用 `env_check`，参数 `UV_INDEX_URL`。
预期二选一：`SET`（env 被支持，记录格式）或 `MISSING`/报错（不支持，记为 P1 部分成立，镜像注入走 P8 结论）。

- [ ] **Step 8: 记录 + Commit**

填写 RESULTS.md P1 行（含 env 结论）；

```bash
git add spikes/
git commit -m "spike: P1 插件 MCP 启动与 env 字段"
```

---

### Task 6: P2——Windows 端到端与 GUI PATH 陈旧

**Files:**
- Modify: `spikes/RESULTS.md`（P2 行）

**Interfaces:**
- Consumes: Task 5 已安装的插件（CLI 路径已通）
- Produces: P2 结论：干净 Windows 会话中 uv 安装 → PATH → 插件 MCP 可用；GUI 启动的桌面端 PATH 问题是否存在、绝对路径兜底是否有效

- [ ] **Step 1: 模拟干净学生机**

新开一个 Windows 用户（或 VM）。确认无 uv：`uvx --version` 应报不存在。

- [ ] **Step 2: 官方一行装 uv**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
**关闭并重开终端**后 `uvx --version` 应有输出。记录安装路径（预期 `%USERPROFILE%\.local\bin\uvx.exe`）。

- [ ] **Step 3: CLI 路径复验**

在该环境重复 Task 5 Step 5–6（marketplace add → 安装 → ping）。
预期：成功；若 uvx 拉包慢/失败，用 Task 4 的局部镜像重试并记录。

- [ ] **Step 4: GUI PATH 检查**

从开始菜单启动 ChatGPT 桌面端（不从终端启动），在 Codex 模式会话中调用 ping。
预期二选一：成功（PATH 无陈旧问题）；失败（PATH 陈旧，MCP 起不来）。

- [ ] **Step 5: 绝对路径兜底验证（仅 Step 4 失败时做）**

把插件 `.mcp.json`（或 config.toml）中 `command` 改为 `%USERPROFILE%\.local\bin\uvx.exe` 的展开绝对路径，重试 Step 4。
预期：成功——证实 `doctor` 自动改写绝对路径的兜底有效。

- [ ] **Step 6: 记录 + Commit**

填写 RESULTS.md P2 行（含 GUI PATH 结论与兜底有效性）；

```bash
git add spikes/
git commit -m "spike: P2 Windows 端到端与 PATH"
```

---

### Task 7: P5——git 分发（GitHub / Gitee / git-subdir）

**Files:**
- Modify: `spikes/RESULTS.md`（P5 行）

**Interfaces:**
- Consumes: Task 5 的 marketplace 目录内容
- Produces: P5 结论：`codex plugin marketplace add` 对 GitHub shorthand、完整 git URL、Gitee URL 的支持；`git-subdir` source 的布局要求

- [ ] **Step 1: 推送 marketplace 到 GitHub**

新建私有或公开仓库（如 `vibe-course-marketplace`），把 `spikes/marketplace/` 的内容推到仓库根（`.agents/plugins/marketplace.json` 与 `plugins/` 位于根）。

- [ ] **Step 2: GitHub shorthand 注册**

```powershell
codex plugin marketplace add <owner>/vibe-course-marketplace
codex plugin marketplace list
```
预期：注册成功，`/plugins` 中出现该源并可安装。

- [ ] **Step 3: Gitee 完整 URL 注册**

在 Gitee 建同名仓库并推送；

```powershell
codex plugin marketplace add https://gitee.com/<owner>/vibe-course-marketplace.git
```
预期：同 Step 2（本质是 git clone）；失败则记录错误并按备选记"GitHub + 镜像说明"。

- [ ] **Step 4: git-subdir 布局验证**

把 marketplace 文件移到仓库子目录（如 `course/`，使 `course/.agents/plugins/marketplace.json` 存在），用 sparse 方式注册：

```powershell
codex plugin marketplace add https://github.com/<owner>/vibe-course-marketplace.git --sparse course/.agents/plugins
```
预期：注册成功；记录 marketplace 根与 plugin `source.path` 的相对解析规则（`./plugins/...` 相对 marketplace 根）。

- [ ] **Step 5: 记录 + Commit**

填写 RESULTS.md P5 行（三种注册形式结论 + 布局规则）；

```bash
git add spikes/
git commit -m "spike: P5 git 分发"
```

---

### Task 8: P0——仅桌面端（无 Codex CLI）环境的发现机制

**Files:**
- Modify: `spikes/RESULTS.md`（P0 行）

**Interfaces:**
- Consumes: Task 5 的 marketplace 目录
- Produces: P0 结论：无 CLI 时桌面端能否添加课程 marketplace；个人 marketplace 文件方案是否成立

- [ ] **Step 1: 确认环境**

在干净 Windows 用户/VM 上只装 ChatGPT 桌面端（Codex 模式可用），确认终端中 `codex --version` 不存在。

- [ ] **Step 2: 桌面端 UI 寻找 marketplace 入口**

桌面端 → Codex 模式 → Plugins：记录是否有"添加 marketplace/添加源"的 UI（预期：无，文档只写了 CLI 命令与工作区共享）。

- [ ] **Step 3: 个人 marketplace 文件实验**

把 Task 5 的 marketplace 内容放到磁盘（如 `E:/spikes/marketplace`），写个人 marketplace 注册文件 `~/.agents/plugins/marketplace.json`（若不存在则新建，存在则用 JSON 解析追加、不动其他内容）：

```json
{
  "name": "vibe-course-spike",
  "interface": { "displayName": "Vibe 课程 Spike" },
  "plugins": [
    {
      "name": "vibe-submit-spike",
      "source": { "source": "local", "path": "./plugins/vibe-submit-spike" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Education"
    }
  ]
}
```

**重启桌面端**，查看 Plugins 页面是否出现该源与插件。
注意：个人 marketplace 文件的语义是"marketplace 本身"还是"已注册源列表"文档不明，两种都试：①直接放 marketplace 文件；②若无效，改放指向 `E:/spikes/marketplace` 的注册项（字段参照 CLI 注册后生成的同类文件——可在有 CLI 的机器上对照 `codex plugin marketplace add` 后该文件的变化获得准确格式）。

- [ ] **Step 4: 记录 + Commit**

填写 RESULTS.md P0 行（桌面端发现机制结论 + bootstrap 在该环境的可行做法）；

```bash
git add spikes/
git commit -m "spike: P0 仅桌面端发现机制"
```

---

### Task 9: P3——桌面端是否共享 CLI 的 marketplace/插件状态

**Files:**
- Modify: `spikes/RESULTS.md`（P3 行）

**Interfaces:**
- Consumes: Task 5/6 在同一机器上 CLI 已注册并安装的插件
- Produces: P3 结论：CLI 注册/安装的源与插件，桌面端是否可见可用

- [ ] **Step 1: 对照检查**

同一 Windows 用户下：CLI 已 `marketplace add` + `/plugins` 安装 spike 插件；打开桌面端 Codex 模式 Plugins 页。
记录：课程源 tab 是否出现；插件是否已在 Installed；启用状态是否一致（`~/.codex/config.toml` 是共享文件，预期一致）。

- [ ] **Step 2: 桌面端会话内调用 ping**

预期：成功（与 Task 6 Step 4 互证）；失败则记录并与 P2 的 PATH 结论交叉分析（是共享问题还是 PATH 问题）。

- [ ] **Step 3: 记录 + Commit**

填写 RESULTS.md P3 行；

```bash
git add spikes/
git commit -m "spike: P3 桌面端共享状态"
```

---

### Task 10: P4——VS Code Codex 扩展读取 config.toml [mcp_servers]

**Files:**
- Modify: `spikes/RESULTS.md`（P4 行）

**Interfaces:**
- Consumes: Task 2 的 wheel
- Produces: P4 结论：手写 `[mcp_servers]` 在 IDE 扩展当前版本生效与否

- [ ] **Step 1: 写配置**

在 `~/.codex/config.toml` 追加（保留原有内容）：

```toml
[mcp_servers.vibe-submit-spike]
command = "uvx"
args = ["--from", "E:/myprogramfiles/Vibe Coding 作业提交与智能评估系统/spikes/hello-pkg/dist/vibe_submit-0.1.0-py3-none-any.whl", "vibe-submit-mcp"]
```

- [ ] **Step 2: 扩展内验证**

VS Code → Codex 扩展 → 新会话：输入 `调用 vibe-submit-spike 的 ping 工具`。
预期：返回 pong；记录工具在扩展 UI 中的可见性。

- [ ] **Step 3: 还原与记录**

实验后移除该配置节（bootstrap 的 uninstall 语义验证素材）。填写 RESULTS.md P4 行；不成立则按备选记"放弃 IDE 路径"。

- [ ] **Step 4: Commit**

```bash
git add spikes/
git commit -m "spike: P4 IDE 扩展 MCP"
```

---

### Task 11: P6——仓库级 marketplace 自动发现（可选增强）

**Files:**
- Modify: `spikes/RESULTS.md`（P6 行）

**Interfaces:**
- Consumes: Task 5 的 marketplace 目录
- Produces: P6 结论：仓库内 `.agents/plugins/marketplace.json` 是否自动出现在 `/plugins`、有无信任流程

- [ ] **Step 1: 构造测试仓库**

```powershell
mkdir spikes/repo-test
cd spikes/repo-test
git init
xcopy /E /I ..\marketplace\.agents .agents
git add -A; git commit -m "repo marketplace"
```

- [ ] **Step 2: 在该仓库打开 Codex**

```powershell
codex
```
TUI 中 `/plugins`：记录是否出现该仓库源 tab；是否先弹信任/确认；插件是否可安装。

- [ ] **Step 3: 记录 + Commit**

填写 RESULTS.md P6 行（成立则标记为"可选增强可用"，否则记"仅显式 add"）；

```bash
git add spikes/
git commit -m "spike: P6 仓库级 marketplace"
```

---

### Task 12: 决策汇总并写回 spec

**Files:**
- Modify: `spikes/RESULTS.md`（结论汇总段）
- Modify: `docs/superpowers/specs/2026-07-17-vibe-coding-homework-eval-design.md`（§3.1/§3.2/§3.3/§7/§9/§11 中受结论影响的行）

**Interfaces:**
- Consumes: Task 1–11 的全部记录
- Produces: spec §11 每行标注"已验证：成立/不成立（日期）"；受影响章节按备选列落定；修订记录追加"四次修订：spike 结论回写"

- [ ] **Step 1: 汇总表定稿**

RESULTS.md 每行补齐：结果、证据、采用路径；缺环境的项标"未验证-缺环境"，并在 spec §11 对应行注明"上线前必须补验"。

- [ ] **Step 2: 逐项写回 spec**

按各 P 行的"采用路径"更新 spec 对应章节（如 P0 不成立 → §3.2 步骤 2 改为个人 marketplace 文件方案；P1 env 不支持 → §3.1/.mcp.json 去掉 env 依赖、镜像注入按 P8 结论写死；P6 成立 → §3.2 增补"作业模板仓库自动发现（可选）"）。

- [ ] **Step 3: 一致性复读**

通读 spec §2/§3/§4/§7/§8/§9/§11，确认改动互洽、无残留旧表述。

- [ ] **Step 4: Commit**

```bash
git add spikes/RESULTS.md docs/superpowers/specs/
git commit -m "spike: P0-P8 结论汇总并写回 spec"
```

---

## Self-Review 记录

- **spec 覆盖**：§11 的 P0–P8 每行恰好一个 Task（P0→T8、P1→T5、P2→T6、P3→T9、P4→T10、P5→T7、P6→T11、P7→T3、P8→T4），执行顺序按依赖重排（包与 uvx 先行，桌面端相关在其后）。
- **占位符扫描**：所有命令、JSON、TOML、Python 均为完整可用内容；仅两处需按实际环境调整（.mcp.json 中的 wheel 绝对路径、GitHub/Gitee 的 `<owner>`），已在步骤内明说。
- **类型/命名一致**：包名 `vibe-submit`、入口点 `vibe-submit`/`vibe-submit-mcp`、插件名 `vibe-submit-spike`、marketplace 名 `vibe-course-spike` 全计划一致；与 spec §3.1 的最终命名（插件 `vibe-submit`、课程 marketplace）不冲突——spike 用 `-spike` 后缀防混淆。

