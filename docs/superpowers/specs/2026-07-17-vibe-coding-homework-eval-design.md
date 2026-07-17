# Vibe Coding 作业提交与智能评估系统 — 设计文档

- 日期：2026-07-17
- 状态：已通过分节评审，待实现
- 定位：先作课程项目交付 MVP（2–3 周可演示），架构按可投产标准设计，预留演进空间

## 1. 背景与目标

大学 Vibe Coding 课堂通常只能收到最终代码或截图。面对约 100 名学生、20–50 个小组，教师无法了解学生如何使用 Codex 迭代，也难以基于过程与结果进行一致评分和课堂展示。

本系统：

1. 学生端通过 **Codex 采集插件**（MCP 集成 + CLI 兜底）采集作业相关的完整 Codex 会话、代码快照、运行截图，上传至租赁服务器；
2. 服务器端评估 Agent **自动**（无需教师触发）对提交独立评估，生成 A–E 等级、维度小分、依据、针对学生工作的反馈建议；
3. 教师（**多教师同时登录**）在网页端查看全部课程数据、复核并调整最终等级、导出成绩；
4. 按小组生成课堂展示视图。

**规模假设**：~100 学生 / 20–50 组 / 每作业每人一次提交（允许 `--force` 重交覆盖）。单提交包 ≤50MB（服务器可配）。

## 2. 总体架构（方案 A：模块化单体）

```
学生机器                          租赁服务器 (Docker 单容器)
┌─────────────────┐              ┌──────────────────────────────────┐
│ vibe-submit     │   HTTPS      │  FastAPI 单体应用                 │
│  ├ MCP server   │ ───────────► │  ├─ submissions  上传/校验/存储   │
│  └ CLI 兜底     │  zip+manifest│  ├─ courses      课程/作业/花名册  │
│ 扫描 ~/.codex/  │              │  ├─ evaluation   评分Agent+LLM    │
│ 按 cwd 筛选会话  │              │  ├─ review       教师复核/调分    │
│ 收集代码+截图    │              │  └─ presentation 课堂展示视图     │
└─────────────────┘              │  SQLite(→可切PG) + 文件系统存储    │
                                 └──────────┬───────────────────────┘
                                            │ OpenAI 兼容 API
                                            ▼
                                     国内 LLM (DeepSeek/通义/智谱…)
```

**技术选型**：Python + FastAPI + SQLAlchemy（SQLite 起步，随时可切 PostgreSQL）；教师端 Jinja2 服务端渲染 + HTMX（不做前后端分离）；上传包与截图存文件系统，元数据与评分存数据库。

**演进路径**：模块化单体 → 把 `evaluation` 抽成独立 Worker + 队列 → PostgreSQL。模块边界从第一天就按此划分。

**端到端数据流**：

1. **准备**：教师创建课程 → 导入花名册 CSV（学号、姓名、小组）→ 创建作业（说明 + rubric + 开放/截止时间）→ 系统生成作业码发给学生；
2. **提交**：学生在项目根目录运行 `vibe-submit submit --code <作业码>`（或在 Codex 对话里说"提交作业"由 MCP 触发），CLI 筛选会话、打包代码与 `screenshots/`、生成带 manifest 的 zip 上传；服务器校验作业码 + 学号 + 截止时间，落盘登记；
3. **评估（全自动）**：提交到达即入评估队列，后台 worker 自动评估个人；小组成员个人评估齐了之后自动生成小组评估；截止后定时任务对缺员小组按已到齐成员补评并注明；
4. **复核**：教师在总览板按小组/个人查看等级、依据、会话时间线；可调最终等级并留备注（AI 原始评分永久保留）；
5. **展示**：按小组生成课堂展示视图（一页一组），方向键翻页投屏。

## 3. 学生端：采集插件

**形态：MCP 为主、CLI 兜底，同一 pip 包（`vibe-submit`）交付。**

| 组件 | 作用 |
|---|---|
| `vibe-submit install` | 自动把 MCP server 注册进 Codex（调 `codex mcp add` 或安全地追加 `~/.codex/config.toml` 一节，不动学生原有配置）；幂等，可反复运行自我修复；交互保存学号与服务器地址到 `~/.vibe-submit/config.toml` |
| MCP server（随包安装） | 暴露 `submit_homework` 工具，学生在 Codex 对话里说"提交作业"即可触发；注册时配置为信任该 server，免去每次确认 |
| `vibe-submit submit` | CLI 兜底：MCP 出问题、CI 环境、或学生习惯命令行时使用 |

两条路径共用同一套"采集 → 打包 → 上传"核心模块，核心模块代码与传输层分离，未来加其他宿主（新 IDE 等）零改动核心。

**目录约定**：

```
项目根目录/
├── .vibe-submit.toml        # 可选：本项目作业码等
├── screenshots/             # 学生放运行效果截图（手动截图）
└── (源代码…)
~/.vibe-submit/config.toml   # install 时保存学号、服务器地址
~/.vibe-submit/outbox/       # 上传失败的包，可重试
```

**提交流程**（CLI 与 MCP 共用）：

1. **取作业元数据**：`GET /api/assignments/{code}/meta` → 标题、开放日期、截止时间、大小上限；
2. **筛选会话**：扫描 `~/.codex/sessions/**/*.jsonl`，逐文件只读首行 `session_meta`（含 `cwd`、起始时间），保留 `cwd` 等于项目根目录且时间不早于作业开放日的会话。解析容忍未知行类型（Codex 升级不炸）；正在写入的当前会话做只读复制、跳过不完整末行；
3. **代码快照**：复制项目树，遵守 `.gitignore`，额外排除 `.git/`、`node_modules/`、虚拟环境等；denylist 排除 `.env`、`*.key`、`*.pem`；
4. **截图**：收集 `screenshots/` 下常见图片格式；
5. **预览确认**：`--dry-run` 或交互确认，列出会话数、文件数、总大小，**明确告知完整对话内容将上传**；
6. **打包上传**：zip + manifest，httpx 流式上传 + 进度条；失败存 outbox，`submit --retry`；重复提交服务器返回 409，需 `--force`。

**包结构**：

```
package.zip
├── manifest.json        # 格式版本、学号、作业码、提交时间、工具版本、
│                        # 每文件 sha256、会话数/大小统计
├── sessions/            # 筛出的 rollout .jsonl
├── sessions_index.json  # 客户端预解析索引：每会话 id、起止时间、消息数
├── code/                # 项目快照（过滤后）
└── screenshots/
```

**诚实性边界**：客户端无法技术上防止篡改；manifest 哈希 + 服务器端时间合理性检查抓低级作弊；真正防线是教师可审阅完整原始对话——伪造多会话连贯迭代轨迹成本极高。MVP 不做重客户端防篡改。

**隐私**：manifest 中本机路径的家目录替换为 `~`；上传前显式确认。

## 4. 服务器：数据模型与 API

**数据表**：

| 表 | 关键字段 | 说明 |
|---|---|---|
| `teachers` | id, username, password_hash, display_name | 多教师；管理员 CLI 创建账号；MVP 阶段所有教师可见全部课程 |
| `courses` | id, name, term | |
| `groups` | id, course_id, name | |
| `students` | id, course_id, group_id, student_no, name | 花名册 CSV 导入；`student_no` 每课程唯一 |
| `assignments` | id, course_id, **code**, title, description, **rubric_json**, opens_at, deadline, max_package_mb | rubric_json = 维度/权重/描述列表 |
| `submissions` | id, assignment_id, student_id, submitted_at, package_path, size_bytes, **status**, error | status: `received→queued→evaluating→evaluated / failed`；(assignment, student) 唯一，重交**更新同一行**（旧包保留在磁盘） |
| `evaluations` | id, submission_id, **grade**(A–E), dimension_scores_json, rationale, feedback_json, flags_json, evidence_json, model, prompt_version, created_at | AI 个人评估；**每 submission 一条，重评就地更新** |
| `group_evaluations` | id, assignment_id, group_id, grade, rationale, contribution_json, evidence_json, created_at | AI 小组评估；(assignment, group) 唯一，**重评就地更新** |
| `grade_overrides` | id, target_type(individual/group), target_id, final_grade, comment, teacher_id, updated_at | individual→submission_id，group→(assignment_id, group_id)；**键不随重评变化，调分跨重评保留**；冲突后写覆盖 |
| `eval_jobs` | id, assignment_id, kind(individual/group), target_id, status, attempts, last_error, updated_at | 自动创建；总览板据此展示进度 |

**文件存储**：`data/packages/{assignment}/{student}/…zip`（原始包）+ `data/extracted/{submission_id}/`（解压内容，供浏览与评估）。

**API 契约**：

学生端（无账号，速率限制，作业码即凭证）：

```
GET  /api/assignments/{code}/meta
     → {title, opens_at, deadline, max_package_mb, accepts, reason}

POST /api/submissions            (multipart: manifest json + zip)
     校验：作业码存在 / 学号在花名册 / 未过截止 / 大小合规
     → 201 {submission_id} | 409 已提交(提示 --force) | 422 校验失败原因
```

教师端（登录 + session cookie，页面服务端渲染，少量 JSON API 供 HTMX）：

```
POST /login
POST /courses/{id}/roster        # CSV 导入（学号,姓名,小组名），小组自动创建
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

**触发**：提交（含 `--force` 重交）校验通过即入队；小组成员个人评估齐 → 自动小组评估；**成员重交 → 个人重评（就地更新），若小组评估已存在则连带触发小组重评**；截止后定时任务补评缺员小组（注明缺员）；失败自动指数退避重试 3 次 → 标 failed 在总览板标红，提供运维用手动重试。

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
4. **作业总览板（纯展示）**：小组×成员矩阵（提交状态 + AI 等级 + 最终等级，调过分高亮），进度自动轮询刷新，失败标红，导出成绩 CSV；
5. **提交详情页**四标签：**评估**（等级、维度小分、依据可点击跳转原文、feedback、flags、调分表单）；**会话时间线**（分会话完整对话 + 硬指标条）；**代码**（树 + 只读查看器）；**截图**（画廊）；
6. **课堂展示模式**：全屏投影友好，一页一组，方向键翻页；展示组名/成员/最终等级/截图轮播/AI 迭代亮点（2–3 个关键时刻）/硬指标速览；不含维度小分与 feedback/flags。

## 7. 错误处理

| 环节 | 故障 | 行为 |
|---|---|---|
| 学生端 | 找不到会话 / `~/.codex` 不存在 | 明确报错 + 排查提示 |
| 学生端 | 包超限 / 网络失败 | 超限给清理建议；失败存 outbox，`submit --retry` |
| 学生端 | 409 重复提交 | 提示需 `--force` |
| 服务器 | 上传校验失败 | 422 + 具体原因 |
| 评估 | LLM 超时/限流/5xx | 自动重试 3 次（指数退避）→ failed，总览板标红，可手动重试 |
| 评估 | 非法 JSON / 证据回查不过 | 更严格措辞重试 2 次 → failed |
| 解析 | rollout 行损坏/未知类型 | 逐行容错跳过并计数，绝不因单行炸掉评估 |
| 服务器 | 500 类 | 结构化日志 + `/health` 探活 |

## 8. 测试策略

- **学生端**：会话筛选（各 cwd/时间组合 fixture rollout 文件）、打包与 manifest、denylist、dry-run；对 mock 服务器的上传集成测试；
- **服务器**：API 契约测试（TestClient）；rollout 解析器（真实样例文件）；评估流水线用 **FakeLLMProvider**（固定 JSON）全程可测；
- **端到端**：fixture 提交包 → 自动评估（假模型）→ 教师调分 → 导出 CSV 冒烟；
- **评估质量**：小型 golden 集（若干真实感提交 + 期望等级区间），开发期手动跑用于调 prompt，不进 CI；
- 核心模块（解析、评估、API）覆盖率 ≥80%。

## 9. 部署

单 Dockerfile（FastAPI + SQLite + data 卷）；环境变量：LLM 密钥、初始管理员、服务器地址（写进学生端 install 指引）。备份 = 定期拷贝 SQLite 文件 + `data/`（文档附 cron 示例）。HTTPS 由前置反代（Caddy/Nginx）或云平台负载均衡终止。

## 10. 明确不做（YAGNI）

- 学生门户/学生自助查分（反馈由教师传达）
- 实时/定时自动截屏、客户端防篡改加固
- 前后端分离 SPA、多租户权限隔离
- VL 模型看图评分（留扩展口）
- Celery/Redis/PostgreSQL（演进路径预留，MVP 不上）
