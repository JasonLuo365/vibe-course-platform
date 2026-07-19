# P1-lite 学生端实施计划（12h 冲刺压缩版）

> 执行方式：subagent-driven，每任务 TDD + 评审。范围比原 P1 计划压缩：纯 CLI + MCP server，无 bootstrap/插件仓库装配。

**Goal:** 交付 PyPI 形态包 `vibe-submit`（client/ 目录）：会话采集→打包→上传核心、CLI（submit/retry/doctor）、MCP server（5 工具，preview 绑定+确认强制）。

**Tech:** Python ≥3.10，httpx，mcp SDK，pytest。测试用 httpx.MockTransport 模拟服务器。

## Global Constraints（spec §3/§3.5/§3.8 逐字约束）

- 单一分发 `vibe-submit`，console scripts：`vibe-submit`、`vibe-submit-mcp`。
- 会话筛选：`~/.codex/sessions/**/*.jsonl`，读首行 `session_meta` 的 `cwd`/`timestamp`，保留 cwd==项目根 且 timestamp ≥ 作业 opens_at；逐行容错（坏行/未知类型跳过）；正在写入的文件只读复制。
- denylist：`.env*`、`*.key`、`*.pem`、`*.p12`、`*.pfx`、`*.ppk`、`id_rsa*`、`.ssh/`、`.aws/`、`.azure/`、`.gnupg/`、`.kube/`、`*.kubeconfig`、`.netrc`、`.git-credentials`、`*credentials*`、`*secret*`；排除目录 `.git`、`node_modules`、`.venv`、`venv`、`__pycache__`、`dist`、`build`。
- 限额：单文件 ≤10MB、文件数 ≤5000、总包 ≤50MB；不跟随符号链接/junction；路径必须在项目根内。
- manifest.json：`{format_version:"1", assignment_code, student_no, client_version, submitted_at(ISO UTC), files:[{path,sha256}], stats:{sessions,files,bytes}}`；学号仅展示。
- zip 结构：`manifest.json`、`sessions/`、`sessions_index.json`、`code/`、`screenshots/`。
- 上传：`Authorization: Bearer <submit_token>`，multipart 字段 manifest+file+force；处理 201/401/404/409/422/426；HTTPS 证书错误不绕过。
- MCP 契约：`get_assignment_meta(assignment_code)`、`preview_submission(assignment_code, project_root)`（返回 preview_id+摘要+指纹）、`submit_homework(preview_id, confirmed, force_confirmed=False)`（preview 无效/过期/根不符或 confirmed≠true 拒绝；409 时须 force_confirmed=true 才以 force=true 重传）、`retry_submission(outbox_id=None, assignment_code=None)`（无参→只读列表）、`get_submission_status(assignment_code)`。**禁 stdio input()**。
- preview 暂存：`~/.vibe-submit/previews/{preview_id}/`（zip+meta.json：project_root、fingerprint、created_at、expires 1h）；preview_id = token_urlsafe(12)。
- 全局配置 `~/.vibe-submit/config.toml`：`server_url`、`student_no`、`submit_token`；项目 `.vibe-submit.toml` 可出现 server_url 但与全局不同时必须显式确认（CLI 交互；MCP 拒绝并提示用 CLI 确认）。
- outbox：`~/.vibe-submit/outbox/{outbox_id}/`（zip+meta.json）。
- 日志不记对话正文/秘密，仅计数与错误。

## Task 1: 核心采集（sessions + collect + package）

**Files:** client/pyproject.toml、client/vibe_submit/__init__.py、client/vibe_submit/errors.py、client/vibe_submit/sessions.py、client/vibe_submit/collect.py、client/vibe_submit/package.py、client/tests/conftest.py、client/tests/test_sessions.py、client/tests/test_collect.py、client/tests/test_package.py

**Interfaces:**
- `find_sessions(codex_home: Path, project_root: Path, since: datetime|None) -> list[SessionInfo]`；SessionInfo(path, session_id, cwd, started_at(datetime))
- `read_session_info(path: Path) -> SessionInfo|None`（容错：无 meta/坏首行→None）
- `session_index(path: Path) -> dict`：{session_id, started_at, ended_at, message_count}（遍历全部行，容错计数 type=="response_item"/"event_msg" 等含 user/assistant 的行）
- `collect_project(root: Path) -> list[FileEntry]`；FileEntry(relpath(str,posix), abspath, size)；违反 denylist 的跳过并记录 skipped: list[str]；超限抛 CollectError；符号链接不跟随（os.walk(followlinks=False) + 跳过 islink）
- `build_package(root, sessions: list[SessionInfo], code_files, screenshots, meta: dict, dest: Path) -> tuple[Path, dict, dict]`：(zip_path, manifest, stats)
- 测试 fixture：tmp_path 造 rollout jsonl（首行 `{"type":"session_meta","payload":{"id","timestamp","cwd"}}` + 若干消息行 + 一行坏 json）、项目树（含 .env、*.key、符号链接、超 10MB 文件、截图）

**测试点：** cwd 匹配/不匹配、since 过滤、坏行容错、meta 缺失跳过；denylist 命中并列入 skipped、排除目录、符号链接不收集、超 10MB→CollectError、总数→CollectError；package 的 zip 含 manifest/sessions/code/screenshots、manifest sha256 与实际一致、stats 正确。

## Task 2: 上传客户端 + outbox + config + CLI

**Files:** client/vibe_submit/config.py、client/vibe_submit/api.py、client/vibe_submit/outbox.py、client/vibe_submit/cli.py、client/tests/test_api.py、client/tests/test_outbox.py、client/tests/test_cli.py

**Interfaces:**
- `load_config() -> Config`、Config(server_url, student_no, submit_token, source)（全局 toml 优先；项目级 server_url 冲突→需 confirm_server_change(url) 确认）
- `get_meta(cfg, code) -> dict`；`upload(cfg, zip_path, manifest, force=False) -> dict`；`get_status(cfg, code) -> dict`；全部用 httpx.Client(timeout=60)，错误→ApiError(status, code, message, payload)
- `save_outbox(zip_path, manifest, cfg) -> outbox_id`；`list_outbox() -> list[dict]`（id, assignment_code, size, saved_at）；`get_outbox(outbox_id) -> (zip_path, manifest)`
- CLI（argparse）：`submit --code X [--yes] [--force]`、`retry [outbox_id]`（无参列出）、`doctor`（检查 config/codex 目录/服务器 /health/uvx 自身版本，逐项 ✓/✗）
- submit 流程：load_config → get_meta（accepts=false→退出码 2 提示）→ find_sessions(since=opens_at) → collect_project → build_package 到临时目录 → 打印预览摘要（会话表/文件数/截图数/大小/skipped）→ --yes 或 input 确认 → upload（409 且无 --force→提示；--force→force=true 重传）→ 成功打印 submission_id/attempt_no；网络/5xx→save_outbox 并提示 retry

**测试点：** MockTransport 模拟 201/401/404/409/422/426/网络错误；outbox save/list/retry；CLI submit 全流程（mock 各模块）确认与非交互 --yes；409→--force 路径。

## Task 3: MCP server（5 工具，确认强制）

**Files:** client/vibe_submit/mcp_server.py、client/vibe_submit/preview.py、client/tests/test_mcp_tools.py

**Interfaces:**
- preview.py：`create_preview(cfg, assignment_code, project_root) -> dict`（构建包存入 previews/{id}/，返回 {preview_id, sessions:[...摘要], files, screenshots, bytes, skipped, fingerprint}；fingerprint = sha256(canonical_root+stats) 前 12 位）；`load_preview(preview_id) -> PreviewRecord`（过期/不存在→PreviewError）；`resolve_project_root(p) -> canonical str`
- mcp_server.py：FastMCP("vibe-submit")，5 个工具按 Global Constraints 契约；submit_homework 调用 load_preview 校验 confirmed==True、project_root 一致，再 upload；409 且 force_confirmed → force=True 重传；否则返回结构化错误 dict（不抛 stdio input）
- 工具返回均为 dict（MCP 结构化输出）；失败返回 {"ok": False, "error": {"code", "message"}}

**测试点：** preview 创建/过期/根不符；submit_homework：无 preview→拒绝、confirmed=False→拒绝、成功路径（mock upload）、409→force_confirmed=False 拒绝 + True 成功；retry_submission 无参只读、带 id 执行；get_assignment_meta/get_submission_status 透传（mock api 层）。

## Task 4: 端到端串联（mock 服务器全链路）+ 回归

**Files:** client/tests/test_e2e.py

**Interfaces:** 用 MockTransport 实现 mini 服务器行为（meta→201 上传→409→force→status），驱动 CLI submit + MCP 工具两条路径各一遍；全量回归 pytest。

**测试点：** CLI 路径 e2e（提交成功+状态查询）；MCP 路径 e2e（meta→preview→confirm→submit）；重交 409→force。
