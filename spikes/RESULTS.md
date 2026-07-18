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
| P7 | uvx --from 钉版与升级行为 |  |  |  | §3.1, §3.3, §11 |
| P8 | 镜像局部化方案 |  |  |  | §3.2, §7, §11 |
