# Vibe Coding 作业提交与智能评估系统 — 设计文档

- 日期：2026-07-17（2026-07-18 修订：学生端升级为 Codex Plugin + 课程 Git Marketplace 分发；二次修订：打包与 uvx 命令统一、MCP 工具契约、客户端路径表述、发布/回退策略、隐私与文件安全、版本协商、镜像配置、P0/P8 验证项；三次修订：submit_token Bearer 认证、status API 与 force 传输、submission_attempts 版本化、ZIP 安全校验、preview/retry 精确化、单进程 worker 模型；2026-07-19 四次修订：§11 spike 全部结论回写——P1/P3/P4/P7/P8 成立、P0/P2/P5 部分成立、P6 不成立，bootstrap/发布/错误处理相应落定）
- 状态：已通过分节评审，待实现
- 定位：先作课程项目交付 MVP（2–3 周可演示），架构按可投产标准设计，预留演进空间

## 1. 背景与目标

大学 Vibe Coding 课堂通常只能收到最终代码或截图。面对约 100 名学生、20–50 个小组，教师无法了解学生如何使用 Codex 迭代，也难以基于过程与结果进行一致评分和课堂展示。

本系统：

1. 学生端通过 **Codex Plugin**（经课程 Git Marketplace 分发，可在 Codex 插件页面发现安装；CLI 兜底）采集作业相关的完整 Codex 会话、代码快照、运行截图，上传至租赁服务器；
2. 服务器端评估 Agent **自动**（无需教师触发）对提交独立评估，生成 A–E 等级、维度小分、依据、针对学生工作的反馈建议；
3. 教师（**多教师同时登录**）在网页端查看全部课程数据、复核并调整最终等级、导出成绩；
4. 按小组生成课堂展示视图。

**规模假设**：~100 学生 / 20–50 组 / 每作业每人可多次提交（重交产生新 attempt，旧提交与旧评估永久保留可追溯）。单提交包 ≤50MB（服务器可配）。

## 2. 总体架构（方案 A：模块化单体）

```
学生机器                          租赁服务器 (Docker 单容器)
┌─────────────────────────┐      ┌──────────────────────────────────┐
│ Codex Plugin            │      │  FastAPI 单体应用                 │
│ (课程 Git Marketplace    │      │  ├─ submissions  上传/校验/存储   │
│  分发, /plugins 安装)    │ HTTPS│  ├─ courses      课程/作业/花名册  │
│  ├ Skill 提交引导        │─────►│  ├─ evaluation   评分Agent+LLM    │
│  └ .mcp.json ─ uvx 启动  │ zip  │  ├─ review       教师复核/调分    │
│       vibe-submit-mcp    │      │  └─ presentation 课堂展示视图     │
│ 采集 ~/.codex 会话(按cwd) │      │  SQLite(→可切PG) + 文件系统存储    │
│ 收集代码+截图, CLI 兜底   │      └──────────┬───────────────────────┘
└─────────────────────────┘                 │ OpenAI 兼容 API
                                            ▼
                                     国内 LLM (DeepSeek/通义/智谱…)
```

**技术选型**：Python + FastAPI + SQLAlchemy（SQLite 起步，随时可切 PostgreSQL）；教师端 Jinja2 服务端渲染 + HTMX（不做前后端分离）；上传包与截图存文件系统，元数据与评分存数据库。

**演进路径**：模块化单体 → 把 `evaluation` 抽成独立 Worker + 队列 → PostgreSQL。模块边界从第一天就按此划分。

**端到端数据流**：

1. **准备**：教师创建课程 → 导入花名册 CSV（学号、姓名、小组）→ 创建作业（说明 + rubric + 开放/截止时间）→ 系统生成作业码发给学生；
2. **提交**：学生在项目根目录运行 `vibe-submit submit --code <作业码>`（或在 Codex 对话里说"提交作业"由 MCP 触发），CLI 筛选会话、打包代码与 `screenshots/`、生成带 manifest 的 zip 上传；服务器校验 **submit_token（Bearer）** + 作业码 + 截止时间，落盘登记为新的 submission attempt；
3. **评估（全自动）**：提交到达即入评估队列，后台 worker 自动评估个人；小组成员个人评估齐了之后自动生成小组评估；截止后定时任务对缺员小组按已到齐成员补评并注明；
4. **复核**：教师在总览板按小组/个人查看等级、依据、会话时间线；可调最终等级并留备注（AI 原始评分永久保留）；
5. **展示**：按小组生成课堂展示视图（一页一组），方向键翻页投屏。

## 3. 学生端：Codex Plugin（课程 Git Marketplace 分发）

**形态：Codex CLI 与 ChatGPT 桌面端 Codex 为正式 Plugin 支持路径——在插件页面（`/plugins`）从课程 Marketplace 发现并安装；VS Code Codex IDE 扩展不支持安装 Plugin，仅直接注册同一 MCP Server，属兼容路径；纯 CLI 永远兜底。所有路径共用同一核心。**

### 3.1 组件关系

```
┌─ 课程 Marketplace 仓库 (git, GitHub/Gitee 均可) ─────────┐
│ .agents/plugins/marketplace.json   # 市场清单            │
│ plugins/vibe-submit/                                     │
│   ├── .codex-plugin/plugin.json  # 插件清单+界面信息     │
│   ├── .mcp.json                  # {"vibe-submit": {"command":"uvx",
│   │     "args":["--from","vibe-submit==X.Y.Z","vibe-submit-mcp"]}}  │
│   ├── skills/submit-homework/SKILL.md  # 提交引导提示词  │
│   └── assets/                                            │
└──────────────────────────────────────────────────────────┘
                    │ /plugins 安装（缓存到 ~/.codex/plugins/cache/）
                    ▼
PyPI: vibe-submit 包
  ├── vibe_submit/core/         # 采集/筛选/打包/上传（单一事实源）
  ├── vibe_submit/mcp_server.py # MCP 薄封装（submit_homework 工具）
  └── vibe_submit/cli.py        # CLI：submit / retry / uninstall / doctor
```

- **Codex Plugin** = 纯包装与分发单元，本身几乎不含逻辑（声明 + 提示词 + 图标）；
- **Skill**（`submit-homework`）= 告诉 Codex 何时建议提交、如何向学生解释将上传什么、失败如何引导；
- **MCP server** = 核心的薄封装，暴露 5 个工具：`get_assignment_meta` / `preview_submission` / `submit_homework` / `retry_submission` / `get_submission_status`（契约见 §3.5）。以 `uvx --from vibe-submit==X.Y.Z vibe-submit-mcp` 启动（形式已经 §11 P7 spike 验证）——**单一 PyPI 分发 `vibe-submit`**，其 pyproject.toml 暴露 `vibe-submit` 与 `vibe-submit-mcp` 两个 console scripts；**核心版本钉死在插件内**，插件升级才带动核心升级；`.mcp.json` 支持 `env` 字段（0.144.6 实测，文档未列），用于注入局部 PyPI 镜像（§11 P1/P8）；
- **CLI** = 同一核心的命令行入口（`submit / retry / uninstall / doctor`），兼兜底路径与诊断工具；
- **核心模块**与任何宿主解耦，单测覆盖；未来加新宿主零改动核心。

### 3.2 首次安装（bootstrap，幂等，可重跑自愈）

课程 README 提供一条命令（Windows PowerShell / macOS·Linux shell 各一），依次：

1. 检测并无则安装 uv；如需 PyPI 镜像加速，**只配置在 vibe-submit 自身调用/局部范围内**，未经用户确认不得改动全局 pip/uv 配置（机制经 §11 P8 验证）；
2. 注册课程 marketplace：**有 Codex CLI 时** `codex plugin marketplace add <课程仓库URL>`；**无 CLI 时**（纯桌面端环境）bootstrap 以 TOML 解析安全写入 `config.toml [marketplaces.*]` 注册节（机制已经 §11 P0/P3 验证），并引导补装 codex CLI——桌面端插件目录不含自定义 marketplace 插件，无法经桌面 UI 安装；
3. 交互询问学号与 **submit_token**（教师随花名册下发，每人一个），写入 `~/.vibe-submit/config.toml`；
4. 自检（等价 `doctor`）并打印使用指引。

| 客户端路径 | bootstrap 之后 |
|---|---|
| **A. Codex CLI** | `codex` → `/plugins` → 课程 tab → 安装；对话里说"提交作业"即可（首次调用时 uvx 拉包数秒） |
| **B. ChatGPT 桌面应用 Codex 模式** | 同上（与 CLI 共享 `~/.codex` 配置，已经 §11 P3 验证） |
| **C. VS Code IDE 扩展（兼容路径，非 Plugin）** | bootstrap 把 `[mcp_servers.vibe-submit]`（同一 `uvx --from vibe-submit==X.Y.Z vibe-submit-mcp` 命令）写入 `~/.codex/config.toml`；IDE 会话内工具直接可用（已经 §11 P4 验证） |

**兜底**：任何集成失效时，`uvx vibe-submit submit --code <作业码>` 纯 CLI 永远可用。`uvx vibe-submit doctor` 诊断（uv 在 PATH？marketplace 已注册？MCP 能启动？服务器可达？）并尽量自动修复（如 PATH 失效时把配置中的 command 改写为 uvx 绝对路径）。

### 3.3 更新 / 卸载 / 回退

- **更新**：课程仓库维护 `stable` 稳定分支，学生端固定跟踪该分支；**每次发布提升插件 SemVer** 并打**不可变 tag**；仓库内维护"插件版本 ↔ 核心版本"映射表（每次发布新增一行）；核心版本被 `.mcp.json` 钉死、随插件升级。学生重跑 bootstrap（内含 `codex plugin marketplace upgrade`）或手动执行之获得最新 stable；客户端与服务器经 `min_client_version` / `supported_manifest_versions` 协商（见 §4）；
- **卸载**：`/plugins` 内卸载/禁用；`vibe-submit uninstall` 移除 `config.toml` 注册（幂等）；`~/.vibe-submit/` 本地数据（含 outbox 未上传包）卸载时提示、学生自决；
- **回退**：**发布新的补丁版本**（SemVer 递增），其内容恢复至旧的稳定内容；**不重用旧版本号、不修改不可变 tag**；学生按常规升级流程即获得回退后的版本。

### 3.4 目录约定

```
项目根目录/
├── .vibe-submit.toml        # 可选：本项目作业码等
├── screenshots/             # 学生放运行效果截图（手动截图）
└── (源代码…)
~/.vibe-submit/config.toml   # bootstrap 时保存学号、submit_token、服务器地址
~/.vibe-submit/outbox/       # 上传失败的包，可重试
```

### 3.5 提交流程与 MCP 工具契约（CLI 与 MCP 共用核心）

MCP 调用时，作业码由 Codex 从对话中获取（如学生说"提交作业，作业码 HW3"），学号与 submit_token 读取 `~/.vibe-submit/config.toml`；CLI 则由参数/配置文件提供。**身份认证一律为 `Authorization: Bearer <submit_token>`；作业码只用于定位作业。** **MCP 工具绝不在 stdio 内做 `input()` 交互**——所有确认以显式工具参数表达，由学生在与 Codex 的对话中作出。

**MCP 工具契约**：

| 工具 | 参数 | 返回/行为 |
|---|---|---|
| `get_assignment_meta` | assignment_code | 作业元数据（含 `min_client_version`、`supported_manifest_versions`） |
| `preview_submission` | assignment_code, project_root | 构建暂存包，返回 **preview_id**（绑定 canonical project_root + 项目指纹 + 有效期）、会话列表摘要、文件数、截图数、总大小、敏感文件过滤结果、项目指纹 |
| `submit_homework` | preview_id, confirmed, force_confirmed? | **preview_id 无效/过期/与 project_root 不符，或 confirmed≠true 时，代码层拒绝上传**；遇 409 需另行 `force_confirmed=true`（仅客户端确认逻辑，确认后向服务器传 `force=true`）；成功返回 submission_id |
| `retry_submission` | outbox_id 或 assignment_code（必填其一） | 精确重传指定失败包；**无参数时只返回 outbox 列表（只读，不执行）** |
| `get_submission_status` | assignment_code（必填） | 服务器回执：`{submission_id, assignment_code, status(none/received/queued/evaluating/evaluated/failed), submitted_at, size_bytes, error?}` |

**步骤**：

1. **取作业元数据**（`get_assignment_meta`）：标题、开放日期、截止时间、大小上限、`min_client_version`、`supported_manifest_versions`；客户端不满足 → 提示升级（见 §7）；
2. **筛选会话**：扫描 `~/.codex/sessions/**/*.jsonl`，逐文件只读首行 `session_meta`（含 `cwd`、起始时间），保留 `cwd` 等于项目根目录且时间不早于作业开放日的会话。解析容忍未知行类型（Codex 升级不炸）；正在写入的当前会话做只读复制、跳过不完整末行；
3. **代码快照**：复制项目树，遵守 `.gitignore`，额外排除 `.git/`、`node_modules/`、虚拟环境等；安全约束见 §3.8；
4. **截图**：收集 `screenshots/` 下常见图片格式；
5. **预览**（`preview_submission`）：展示每会话摘要（起止时间/消息数/cwd）、文件数、截图数、总大小、**被过滤的敏感文件清单**与项目指纹，**明确告知完整对话内容将上传**；CLI 为交互确认（`--yes` 跳过），MCP 由 Codex 向学生转述、学生明确同意后 Codex 以 `confirmed=true` 发起提交；
6. **打包上传**（`submit_homework`）：zip + manifest，`Authorization: Bearer <submit_token>`，httpx 流式上传 + 进度；preview 暂存包有有效期并绑定 project_root，过期或不符需重新预览；重复提交服务器返回 409，客户端经 `force_confirmed=true` 确认后以 multipart 字段 `force=true` 重传；失败存 outbox（分配 outbox_id），经 `retry_submission(outbox_id)` / CLI `retry` 精确重传。

### 3.6 包结构

```
package.zip
├── manifest.json        # 格式版本、学号（仅展示，身份以 Bearer token 为准）、作业码、提交时间、工具版本、
│                        # 每文件 sha256、会话数/大小统计
├── sessions/            # 筛出的 rollout .jsonl
├── sessions_index.json  # 客户端预解析索引：每会话 id、起止时间、消息数
├── code/                # 项目快照（过滤后）
└── screenshots/
```

### 3.7 诚实性边界：客户端无法技术上防止篡改；manifest 哈希 + 服务器端时间合理性检查抓低级作弊；真正防线是教师可审阅完整原始对话——伪造多会话连贯迭代轨迹成本极高。MVP 不做重客户端防篡改。

### 3.8 隐私与文件安全

- **遍历安全**：不跟随符号链接/junction；所有待打包路径规范化后必须位于项目根目录内（防路径穿越）；
- **限额**：单文件 ≤10MB、文件总数 ≤5000、总包 ≤ 服务器下发上限（默认 50MB）（默认值，均可配）；
- **敏感文件 denylist**（命中即排除，并在预览中逐条列出）：`.env*`、`*.key`、`*.pem`、`*.p12`、`*.pfx`、`*.ppk`、`id_rsa*`、`.ssh/`、`.aws/`、`.azure/`、`.gnupg/`、`.kube/`、`*.kubeconfig`、`.netrc`、`.git-credentials`、`*credentials*`、`*secret*`；
- **日志纪律**：客户端日志只记计数、哈希与错误信息，**不记录对话正文、文件内容或任何秘密**；
- **预览透明**：预览展示具体会话摘要与敏感过滤结果（见 §3.5），上传前必须显式确认；
- manifest 中本机路径的家目录替换为 `~`；
- **上传服务器地址**只以全局 `~/.vibe-submit/config.toml` 为准；项目内 `.vibe-submit.toml` 若出现服务器地址且与全局不同，**必须经用户显式确认**才生效（CLI 交互确认；MCP 路径拒绝并引导学生运行 CLI 确认），不得静默替换；
- **HTTPS 证书错误不可绕过**：不提供 `--insecure` 类开关、不降级 HTTP；自签部署由用户自行将 CA 加入系统信任。

## 4. 服务器：数据模型与 API

**数据表**：

| 表 | 关键字段 | 说明 |
|---|---|---|
| `teachers` | id, username, password_hash, display_name | 多教师；管理员 CLI 创建账号；MVP 阶段所有教师可见全部课程 |
| `courses` | id, name, term | |
| `groups` | id, course_id, name | |
| `students` | id, course_id, group_id, student_no, name, **submit_token_hash** | 花名册 CSV 导入；`student_no` 每课程唯一；token 只存哈希，明文仅在生成/重置时可导出 |
| `assignments` | id, course_id, **code**, title, description, **rubric_json**, opens_at, deadline, max_package_mb | rubric_json = 维度/权重/描述列表 |
| `submissions` | id, assignment_id, student_id, current_attempt_id, **status**, error | (assignment, student) 唯一，指向当前 attempt 的"当前态"指针 |
| `submission_attempts` | id, submission_id, attempt_no, submitted_at, package_path, size_bytes, manifest_version, status, error | **每次提交一条，不可变**；旧包永久保留在磁盘 |
| `evaluations` | id, **attempt_id**, **grade**(A–E), dimension_scores_json, rationale, feedback_json, flags_json, evidence_json, model, prompt_version, created_at | AI 个人评估；**append-only，每次评估一条**，关联具体 attempt——AI 原始评分、模型版本与证据全程可追溯 |
| `group_evaluations` | id, assignment_id, group_id, **generation**, grade, rationale, contribution_json, evidence_json, created_at | (assignment, group, generation) 唯一；重评 generation+1 追加，旧代保留 |
| `grade_overrides` | id, target_type(individual/group), target_id, final_grade, comment, teacher_id, updated_at, **stale** | individual→(assignment_id, student_id)，group→(assignment_id, group_id)；**新 attempt 产生后旧 override 保留但标记 stale**，总览板提示"基于旧提交"，教师一键确认沿用或修改；冲突后写覆盖 |
| `eval_jobs` | id, assignment_id, kind(individual/group), target_id, status, attempts, last_error, updated_at | 自动创建；总览板据此展示进度 |

**文件存储**：`data/packages/{assignment}/{student}/…zip`（原始包，按 attempt 归档）+ `data/extracted/{attempt_id}/`（解压内容，供浏览与评估）。

**上传包安全校验（不可信输入，先校验后落盘）**：拒绝路径穿越（`..`）、绝对路径/盘符、符号链接条目、重复路径；限制文件数量、单文件大小、总解压大小与压缩比（防 zip bomb）；manifest 声明的文件集合须与包内实际条目一致，且逐文件 SHA-256 回查通过；仅在 per-submission 临时目录内安全解压（逐条规范化并确认目标路径位于临时目录内），全部通过后才原子移入正式位置。

**API 契约**：

学生端（作业码只定位作业；写操作与状态查询需 `Authorization: Bearer <submit_token>`，身份由 token 决定；速率限制）：

```
GET  /api/assignments/{code}/meta          # 公开
     → {title, opens_at, deadline, max_package_mb, accepts, reason,
        min_client_version, supported_manifest_versions}

POST /api/submissions            (multipart: manifest json + zip + 表单字段 force=true?)
     校验：Bearer token 有效（→student）/ 作业码存在且属该生课程 / 未过截止 /
           大小合规 / 客户端版本 ≥ min_client_version / manifest 版本受支持 /
           ZIP 安全校验（见下）
     → 201 {submission_id, attempt_no}
     | 401 token 无效或已重置
     | 409 已提交（客户端确认后以 force=true 重传）
     | 422 校验失败原因（含 ZIP 安全校验失败）
     | 426 {"error":{"code":"CLIENT_OUTDATED","min_client_version","upgrade_instructions"}}
     | 422 {"error":{"code":"UNSUPPORTED_MANIFEST_VERSION","supported_manifest_versions"}}

GET  /api/submissions/status?assignment_code=X     (Bearer)
     → {submission_id, assignment_code,
        status: none|received|queued|evaluating|evaluated|failed,
        submitted_at, size_bytes, error?}
```

**token 管理（教师侧）**：花名册导入时为每学生生成 submit_token（数据库只存哈希，明文随 CSV **一次性导出**供下发）；教师可为单个学生重置，旧 token 即时失效。

教师端（登录 + session cookie，页面服务端渲染，少量 JSON API 供 HTMX）：

```
POST /login
POST /courses/{id}/roster        # CSV 导入（学号,姓名,小组名），小组自动创建；为每学生生成 submit_token，明文 CSV 一次性导出
POST /courses/{id}/assignments   # 创建作业 + rubric 编辑器
GET  /assignments/{id}/board     # 总览：小组×成员矩阵（纯展示，自动刷新）
GET  /api/assignments/{id}/progress  # 进度轮询
GET  /submissions/{id}           # 详情：评估/会话时间线/代码/截图
POST /evaluations/{id}/override  # {final_grade, comment}
GET  /assignments/{id}/present   # 课堂展示模式
GET  /assignments/{id}/export    # 成绩 CSV（含 AI 原评与最终评）
```

**调分纪律**：最终成绩 = override 存在则取 override，否则取 AI 等级；导出 CSV 同时含两者。成绩责任始终在教师。

## 5. 评估 Agent

**总原则：证据可追溯、输出结构化、调用可恢复、全自动触发。**

**触发**：每次提交（含 force 重交）产生新的 `submission_attempts` 行并入队；小组成员个人评估齐 → 自动小组评估；**成员重交 → 对新 attempt 追加个人评估（旧评估保留），若小组评估已存在则连带触发新一代（generation+1）小组评估**；截止后定时任务补评缺员小组（注明缺员）；失败自动指数退避重试 3 次 → 标 failed 在总览板标红，提供运维用手动重试。

**MVP 并发模型**：单 Uvicorn 进程（`--workers 1`）+ 应用内后台 worker，从持久化 `eval_jobs` 表**原子认领**任务（事务性 UPDATE 认领；崩溃恢复 = 重置 stale claimed）；**禁止多进程运行（会重复消费）**；演进路径即 §2 所述抽 Worker + 队列。

**流水线（三段）**：

1. **解析与机械特征提取（无 LLM，确定性）**：rollout JSONL → 统一时间线（user / assistant / 工具调用 / 文件改动）；计算硬指标：会话数、总时长、迭代轮数、报错-修复循环数、测试运行痕迹、触及文件与语言、截止前时间分布。**同时**喂给 LLM 与教师 UI。
2. **证据包构建（token 预算控制）**：压缩时间线 < 阈值（~60k tokens）直接评估；超出则 map-reduce（逐会话摘要保留关键 prompt 原文与转折点，再对摘要集 + 关键摘录评估）。代码只送"仓库摘要"（目录树 + 关键文件节选，封顶）。截图 MVP 不进 LLM，仅教师查看（VL 模型留扩展口）。
3. **结构化评估（带 rubric）**：system prompt = 角色 + 该作业 rubric + 评分纪律（temperature≈0）+ 必须引用证据；输出强校验 JSON：

```json
{
  "grade": "B",
  "dimension_scores": [{"name": "prompt质量", "weight": 30, "score": 82, "rationale": "…"}],
  "evidence": [{"session_id": "…", "turn": 17, "quote": "≤200字原文"}],
  "rationale": "总评…",
  "feedback": ["针对该生过程与结果的改进建议…"],
  "flags": ["真实性警示，仅供教师：疑似一次性生成/大段粘贴…"]
}
```

- pydantic 校验 + **证据回查**（session_id/turn 必须存在），不合法换更严格措辞自动重试 2 次 → failed；
- 教师点击任一条依据可跳到原始对话位置（信任前提）；
- `feedback` = 针对学生提交内容的反馈（过程哪里好、哪里可改进），教师端展示，由教师传达给学生；
- `flags` = 仅供教师的真实性警示，不进展示视图。

**小组评估**：输入 = 小组合并硬指标 + 各成员评估摘要 + 仓库摘要；输出小组等级 + 各成员贡献说明（`contribution_json`）。

**Provider 抽象**：

```python
class LLMProvider(Protocol):
    def complete(self, messages, *, json_schema, max_tokens) -> str: ...
```

OpenAI 兼容客户端（DeepSeek / 通义 DashScope 兼容模式 / 智谱均可），环境变量配 `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`；限流 + 指数退避 + 超时；单次失败只标该提交 failed、队列继续。`evaluations` 存 `model + prompt_version`，可审计、可对比复现。

## 6. 教师端页面

多教师同时登录（`teachers` 表，账号由管理员 CLI `vibe-server create-teacher` 创建）。Jinja2 + HTMX，6 页：

1. **登录**；
2. **课程仪表盘**：课程卡片 → 作业列表（已交/应交、评估进度、未复核数）；
3. **课程设置**：花名册 CSV 导入；作业创建 + **rubric 编辑器**（维度行增删：名称/权重%/描述，权重和校验 =100，默认模板：prompt 质量 30 / 迭代策略 25 / 调试与问题解决 20 / 完成度 15 / 代码质量 10）；
4. **作业总览板（纯展示）**：小组×成员矩阵（提交状态 + AI 等级 + 最终等级，调过分高亮、**stale override（基于旧提交）标记**），进度自动轮询刷新，失败标红，导出成绩 CSV；
5. **提交详情页**四标签：**评估**（等级、维度小分、依据可点击跳转原文、feedback、flags、调分表单）；**会话时间线**（分会话完整对话 + 硬指标条）；**代码**（树 + 只读查看器）；**截图**（画廊）；
6. **课堂展示模式**：全屏投影友好，一页一组，方向键翻页；展示组名/成员/最终等级/截图轮播/AI 迭代亮点（2–3 个关键时刻）/硬指标速览；不含维度小分与 feedback/flags。

## 7. 错误处理

| 环节 | 故障 | 行为 |
|---|---|---|
| 学生端 | 找不到会话 / `~/.codex` 不存在 | 明确报错 + 排查提示 |
| 学生端 | 包超限 / 网络失败 | 超限给清理建议；失败存 outbox，`retry` 重传 |
| 学生端 | 409 重复提交 | 客户端需 `force_confirmed=true` 确认（独立于普通 confirmed），随后以 `force=true` 重传 |
| 学生端 | preview_id 无效/过期 | 代码层拒绝上传，提示重新预览 |
| 学生端 | confirmed / force_confirmed 缺失 | 代码层拒绝；MCP 不做 stdio `input()` 交互 |
| 学生端 | 客户端版本过旧（426 CLIENT_OUTDATED） | 按 upgrade_instructions 提示升级，不继续上传 |
| 学生端 | HTTPS 证书错误 | 报错失败，不绕过、不降级 |
| 学生端 | 项目配置试图变更上传服务器 | 默认不生效，需用户显式确认 |
| 学生端 | 镜像加速需全局配置才生效 | 请求用户确认；未确认则保持局部配置或不配置 |
| 学生端 | bootstrap 任一步失败（装 uv / marketplace add / 写配置） | 幂等可重跑；每步明确报错与手动备选指引 |
| 学生端 | uvx 首次拉包失败（网络） | 自动用已配镜像重试；提示检查后重跑 |
| 学生端 | GUI 应用 PATH 陈旧找不到 uvx | `doctor` 检测并改写配置为 uvx 绝对路径 |
| 学生端 | 插件 MCP 启动失败 | `doctor` 诊断；兜底 `uvx vibe-submit submit` 纯 CLI |
| 学生端 | Codex Windows 沙箱助手缺失（0.144.6 实测：`codex-windows-sandbox-setup.exe` 不在安装目录，所有沙箱模式 shell 命令失败） | **MCP 调用不受影响**，提交通道正常；属 Codex 平台问题（Windows 支持官方标注 experimental），课程 FAQ 提示并跟踪官方修复 |
| 服务器 | 上传校验失败 | 422 + 具体原因 |
| 服务器 | token 无效/已重置 | 401，客户端提示重新 bootstrap 或联系教师重置 |
| 服务器 | ZIP 安全校验失败（穿越/链接/超限/压缩比/哈希不符） | 422 + 具体原因，包不落盘 |
| 评估 | LLM 超时/限流/5xx | 自动重试 3 次（指数退避）→ failed，总览板标红，可手动重试 |
| 评估 | 非法 JSON / 证据回查不过 | 更严格措辞重试 2 次 → failed |
| 解析 | rollout 行损坏/未知类型 | 逐行容错跳过并计数，绝不因单行炸掉评估 |
| 服务器 | 500 类 | 结构化日志 + `/health` 探活 |

## 8. 测试策略

- **学生端**：会话筛选（各 cwd/时间组合 fixture rollout 文件）、打包与 manifest、denylist、预览输出；对 mock 服务器的上传集成测试；
- **客户端安全与契约**：不跟随符号链接/路径穿越拒绝/denylist 命中/限额生效/日志无敏感内容；preview→submit 绑定（preview_id 无效、过期、与 project_root 不符、未确认、force 未额外确认均被拒绝）的契约测试；`retry_submission` 无参数只读列表、带 `outbox_id`/`assignment_code` 精确重试；版本协商（`min_client_version`、`UNSUPPORTED_MANIFEST_VERSION`）测试；
- **服务器**：API 契约测试（TestClient，含 Bearer token 认证与 401/409/426 分支）；**ZIP 安全校验**（穿越/绝对路径/链接/重复路径/超限/压缩比/manifest 哈希不符 fixture）；rollout 解析器（真实样例文件）；评估流水线用 **FakeLLMProvider**（固定 JSON）全程可测；attempt 版本化（重交产生新 attempt、旧评估保留、override 标 stale）；单 worker 原子认领并发测试；
- **端到端**：fixture 提交包 → 自动评估（假模型）→ 教师调分 → 导出 CSV 冒烟；
- **插件与分发**：marketplace.json / plugin.json 结构校验（CI 中 schema 检查）；bootstrap 脚本幂等性测试；§11 原型验证清单（P0–P8）先行，三客户端路径各一次人工冒烟；
- **评估质量**：小型 golden 集（若干真实感提交 + 期望等级区间），开发期手动跑用于调 prompt，不进 CI；
- 核心模块（解析、评估、API）覆盖率 ≥80%。

## 9. 部署

单 Dockerfile（FastAPI + SQLite + data 卷，**单进程运行，应用内 worker 消费 eval_jobs**）；环境变量：LLM 密钥、初始管理员、服务器地址（写进学生端 bootstrap 指引）。备份 = 定期拷贝 SQLite 文件 + `data/`（文档附 cron 示例）。HTTPS 由前置反代（Caddy/Nginx）或云平台负载均衡终止。

**学生端发布**：单一 PyPI 分发 `vibe-submit`（pyproject.toml 暴露 `vibe-submit`、`vibe-submit-mcp` 两个 console scripts；包版本即 `.mcp.json` 中钉的核心版本）。课程 Marketplace 仓库（GitHub/Gitee）维护 `stable` 分支：每次发布提升插件 SemVer、打**不可变 tag**、更新仓库内"插件版本 ↔ 核心版本"映射表；升级 = `stable` 分支前进，学生 `codex plugin marketplace upgrade` 或重跑 bootstrap 获取；**回退 = 发布 SemVer 递增的新补丁版本（内容恢复至旧稳定内容），不重用旧版本号、不修改不可变 tag**。bootstrap 命令与仓库 URL 随课程 README 发布。**仓库布局要求（§11 P5 已验证）**：`.agents/plugins/marketplace.json` 必须位于**仓库根**（`marketplace add` 不支持子目录）；使用 `--sparse` 优化时必须同时给 `.agents/plugins` 与 `plugins` 两条路径。

## 10. 明确不做（YAGNI）

- 学生门户/学生自助查分（反馈由教师传达）
- 实时/定时自动截屏、客户端防篡改加固
- 前后端分离 SPA、多租户权限隔离
- VL 模型看图评分（留扩展口）
- Celery/Redis/PostgreSQL（演进路径预留，MVP 不上）
- 官方公共插件目录上架（审核周期不可控，学期后再议）
- 插件 hooks 自动提醒提交（需用户信任审核，摩擦大）

## 11. 原型验证（已于 2026-07-19 完成 spike，结果如下）

完整证据见 `spikes/RESULTS.md`（分支 spike/p0-prototype）。结论：

| # | 验证项 | 结论 | 落定决策 |
|---|---|---|---|
| P0 | 仅桌面端（无 CLI）的发现/安装 | **部分成立** | `marketplace add` 本质是写 `config.toml [marketplaces.*]`，bootstrap 可无 CLI 安全注册；但桌面端插件目录不含自定义 marketplace 插件，**无 CLI 时无法经桌面 UI 安装**——bootstrap 在无 CLI 环境引导补装 codex CLI（一条命令），手工填充缓存为文档化兜底（未实测） |
| P1 | 插件 .mcp.json 启动 MCP；env 字段 | **成立** | 主路径定稿：`uvx --from vibe-submit==X.Y.Z vibe-submit-mcp`；**env 字段文档未列但 0.144.6 实测支持**，镜像经 env 注入 |
| P2 | Windows 端到端；GUI PATH | **部分成立** | GUI PATH 陈旧未复现；**意外发现：`codex-windows-sandbox-setup.exe` 缺失致所有沙箱模式 shell 命令失败（MCP 不受影响）**——属平台问题，进课程 FAQ 并跟踪官方修复；干净用户装机流程上线前补测 |
| P3 | 桌面端共享 CLI 配置 | **成立** | 桌面端与 CLI 同等待遇 |
| P4 | IDE 扩展读 config.toml | **成立**（用户实测 pong） | 兼容路径定稿：bootstrap 写 `[mcp_servers.*]` |
| P5 | git 分发；Gitee | **部分成立** | GitHub 全流程通过；**marketplace 必须根布局**（`.agents/plugins/marketplace.json` 在仓库根，子目录不支持）；`--sparse` 仅优化且须 `--sparse .agents/plugins --sparse plugins` 双路径；Gitee 上线前补验 |
| P6 | 仓库级 marketplace 自动发现 | **不成立**（CLI 层） | 放弃自动发现，仅显式 add（bootstrap 完成） |
| P7 | uvx --from 钉版与升级 | **成立** | 主路径定稿 |
| P8 | 镜像局部化 | **成立** | 子进程 `UV_INDEX_URL`（作用域最小）；cwd 局部 uv.toml 备选 |

**官方文档已确认**（[plugins](https://learn.chatgpt.com/docs/plugins) / [build-plugins](https://learn.chatgpt.com/docs/build-plugins)，2026-07 查阅）：插件目录结构与 plugin.json 字段；`.mcp.json` 的 command/args 形式；Marketplace source 类型；`codex plugin marketplace add|list|upgrade|remove` 命令集；安装缓存路径；`/plugins` 浏览器；插件在 CLI 与桌面应用可用、在 IDE 扩展与移动端不可用。
