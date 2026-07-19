# Spike 结果记录（P0–P8）

环境：OS=Windows 11  Codex CLI 版本=0.144.6  桌面端版本=未知  uv 版本=uvx 0.11.9 (7829a03b6 2026-05-05 x86_64-pc-windows-msvc)  日期=2026-07-18

| # | 验证项摘要 | 结果 | 证据（命令+输出摘要） | 采用路径（主/备选/未验证） | 需更新的 spec 章节 |
|---|---|---|---|---|---|
| P0 | 仅桌面端环境的 marketplace 发现 |  |  |  | §3.2, §11 |
| P1 | 插件 .mcp.json 在 CLI 启动 MCP；env 字段 | 成立 | `codex plugin marketplace add ./spikes/marketplace` 注册成功；`codex plugin add vibe-submit-spike@vibe-course-spike` 安装成功（缓存于 `~/.codex/plugins/cache/vibe-course-spike/vibe-submit-spike/0.1.0/`）。`codex exec --dangerously-bypass-approvals-and-sandbox "调用…ping…"` → `mcp: vibe-submit-spike/ping (completed)` → `pong v0.1.0 python=3.13.13`。Skill 随插件可用（agent 读取插件缓存中的 SKILL.md 并按其引导行动）。env 字段：`.mcp.json` 加 `"env":{"UV_INDEX_URL":…}`，remove+add 重装后 `env_check` → `UV_INDEX_URL=SET`（**文档未列但 0.144.6 实测支持**）。注意：Windows 沙箱助手缺失（`codex-windows-sandbox-setup.exe program not found`）导致带沙箱运行时 shell 命令失败、MCP 调用被取消，须 `--dangerously-bypass-approvals-and-sandbox` 绕过（详情交 P2 跟进）。 | 主路径：插件 `.mcp.json`（`uvx --from vibe-submit==X.Y.Z vibe-submit-mcp`）直启 MCP；镜像可经 `env` 字段注入。 | §3.1, §11 |
| P2 | Windows 端到端；GUI PATH 陈旧 |  |  |  | §3.2, §7, §11 |
| P3 | 桌面端读取 CLI 注册的 marketplace |  |  |  | §3.2, §11 |
| P4 | IDE 扩展读 config.toml [mcp_servers] |  |  |  | §3.2, §11 |
| P5 | git-subdir 布局；Gitee 兼容 |  |  |  | §3.1, §9, §11 |
| P6 | 仓库级 marketplace 自动发现（可选） |  |  |  | §11 |
| P7 | uvx --from 钉版与升级行为 | 成立 | 本地 wheel：`uvx --from ./dist/vibe_submit-0.1.0-py3-none-any.whl vibe-submit --version` → `vibe-submit 0.1.0`；改 `pyproject.toml` version 为 `0.2.0` 后 `uv build` 生成 `vibe_submit-0.2.0-py3-none-any.whl`；`uvx --from ./dist/vibe_submit-0.2.0-py3-none-any.whl vibe-submit --version` → `vibe-submit 0.2.0`；再次调用 0.1.0 wheel 仍返回 `vibe-submit 0.1.0`。PyPI 钉版：`uvx --from "httpx==0.28.0" python -c "import httpx;print(httpx.__version__)"` → `0.28.0`；同命令 `==0.27.0` 在主 PyPI 因解析到不兼容 h11 而 ImportError，经 Tsinghua 镜像重试后成功：`UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple uvx --from "httpx==0.27.0" python -c "import httpx;print(httpx.__version__)"` → `0.27.0`。 | 主路径：`uvx --from vibe-submit==X.Y.Z vibe-submit-mcp`（本地 wheel/PyPI 均可按版本隔离）；旧版与新版本可并存调用，互不影响。 | §3.1, §3.3, §11 |
| P8 | 镜像局部化方案 | 成立 | 基线：`Test-Path $env:APPDATA\uv\uv.toml` → `False`；`pip config list` → 无输出（无全局 index-url）。<br>子进程 env：`$env:UV_INDEX_URL='https://pypi.tuna.tsinghua.edu.cn/simple'; uvx --from ./spikes/hello-pkg/dist/vibe_submit-0.1.0-py3-none-any.whl vibe-submit --version` → `vibe-submit 0.1.0`；新 shell `Test-Path env:UV_INDEX_URL` → `False`。<br>cwd-local uv.toml：`spikes/uv.toml` 含 `[[index]] url = "https://pypi.tuna.tsinghua.edu.cn/simple" default = true`；在 `spikes/` 下 `uvx --from ./hello-pkg/dist/vibe_submit-0.1.0-py3-none-any.whl vibe-submit --version` → `vibe-submit 0.1.0`；复查 `%APPDATA%\uv\uv.toml` 仍不存在。 | 优先子进程环境变量（作用域最小）；cwd-local `uv.toml` 为备选。 | §3.2, §7, §11 |
