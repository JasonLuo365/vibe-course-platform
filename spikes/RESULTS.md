# Spike 结果记录（P0–P8）

环境：OS=Windows 11  Codex CLI 版本=未安装(本机)  桌面端版本=未知  uv 版本=uvx 0.11.9 (7829a03b6 2026-05-05 x86_64-pc-windows-msvc)  日期=2026-07-18

| # | 验证项摘要 | 结果 | 证据（命令+输出摘要） | 采用路径（主/备选/未验证） | 需更新的 spec 章节 |
|---|---|---|---|---|---|
| P0 | 仅桌面端环境的 marketplace 发现 |  |  |  | §3.2, §11 |
| P1 | 插件 .mcp.json 在 CLI 启动 MCP；env 字段 |  |  |  | §3.1, §11 |
| P2 | Windows 端到端；GUI PATH 陈旧 |  |  |  | §3.2, §7, §11 |
| P3 | 桌面端读取 CLI 注册的 marketplace |  |  |  | §3.2, §11 |
| P4 | IDE 扩展读 config.toml [mcp_servers] |  |  |  | §3.2, §11 |
| P5 | git-subdir 布局；Gitee 兼容 |  |  |  | §3.1, §9, §11 |
| P6 | 仓库级 marketplace 自动发现（可选） |  |  |  | §11 |
| P7 | uvx --from 钉版与升级行为 | 成立 | 本地 wheel：`uvx --from ./dist/vibe_submit-0.1.0-py3-none-any.whl vibe-submit --version` → `vibe-submit 0.1.0`；改 `pyproject.toml` version 为 `0.2.0` 后 `uv build` 生成 `vibe_submit-0.2.0-py3-none-any.whl`；`uvx --from ./dist/vibe_submit-0.2.0-py3-none-any.whl vibe-submit --version` → `vibe-submit 0.2.0`；再次调用 0.1.0 wheel 仍返回 `vibe-submit 0.1.0`。PyPI 钉版：`uvx --from "httpx==0.28.0" python -c "import httpx;print(httpx.__version__)"` → `0.28.0`；同命令 `==0.27.0` 在主 PyPI 因解析到不兼容 h11 而 ImportError，经 Tsinghua 镜像重试后成功：`UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple uvx --from "httpx==0.27.0" python -c "import httpx;print(httpx.__version__)"` → `0.27.0`。 | 主路径：`uvx --from vibe-submit==X.Y.Z vibe-submit-mcp`（本地 wheel/PyPI 均可按版本隔离）；旧版与新版本可并存调用，互不影响。 | §3.1, §3.3, §11 |
| P8 | 镜像局部化方案 |  |  |  | §3.2, §7, §11 |
