# 项目交接文档 — Vibe Coding 作业提交与智能评估系统

> **给接手者（Codex / 开发者）**：本文档是当前进度的完整快照。请先读 §1 了解系统全貌，§2 看已完成清单，§4 看已验证的硬事实（不要重新验证），§5 是剩余工作的优先级路线图（目标：生产级）。
> 更新日期：2026-07-20 ｜ 分支：main ｜ 测试：服务器 88 + 客户端 75 全绿

---

## 1. 系统是什么

大学 Vibe Coding 课堂的作业系统：学生用 Codex 做作业，**学生端插件采集完整 Codex 会话 + 代码 + 截图**上传；服务器端 **Agent 自动评估**（国内 LLM，A–E 等级 + 维度分 + 证据引用）；**教师浏览器**查看全部数据、复核调分、课堂展示。

```
学生机器                          服务器（Docker 单容器）
┌─────────────────────────┐      ┌──────────────────────────────────┐
│ Codex Plugin / CLI       │      │  FastAPI 单体（单进程+内嵌worker） │
│ vibe-submit (uvx)        │─────►│  submissions/courses/evaluation   │
│ 采集 ~/.codex 会话       │ HTTPS│  review/presentation              │
│ 打包 zip+manifest 上传   │      │  SQLite + 文件系统存储            │
└─────────────────────────┘      └──────┬───────────────────────────┘
                                        │ OpenAI 兼容 API
                                        ▼
                                 DeepSeek（国内 LLM）
```

**技术栈**：Python ≥3.10 / FastAPI / SQLAlchemy 2.x + SQLite / Jinja2 服务端渲染 / uv+uvx 分发 / MCP (FastMCP) / Docker。

**仓库布局**：

```
server/        FastAPI 服务器（app/ + tests/，88 测试）
client/        学生端 vibe-submit（vibe_submit/ + tests/，75 测试）
spikes/        原型验证产物与 RESULTS.md（P0–P8 实测结论）
docs/superpowers/specs/   设计 spec（唯一权威设计文档）
docs/superpowers/plans/   实施计划（P0 spikes、P2 服务器、P1/P3/P4-lite）
docs/superpowers/plans/   另有 P2 完整版 2026-07-19-p2-server-core.md
.superpowers/sdd/progress.md  执行台账（各任务完成记录与 Minor 清单）
DEPLOY.md      Docker 部署文档
```

---

## 2. 已完成（全部经过测试/真实验证）

### 2.1 设计 & 验证

- ✅ **spec 定稿**（`docs/superpowers/specs/2026-07-17-...-design.md`）：四轮评审修订 + spike 结论回写（§11）。
- ✅ **P0 原型验证**（9 项，证据在 `spikes/RESULTS.md`）：Codex 插件机制全部实测（见 §4 硬事实）。

### 2.2 服务器（server/，88 测试全绿）

- ✅ 数据模型全表：teachers/courses/groups/students(+submit_token_hash)/assignments/submissions/**submission_attempts**(不可变)/evaluations(append-only)/group_evaluations(generation)/grade_overrides(stale)/eval_jobs。
- ✅ 教师认证：pbkdf2 密码哈希、签名 cookie session、`vibe-server create-teacher` CLI。
- ✅ 课程/花名册：CSV 导入（自动建组、生成 `vs_` token 只存哈希、明文一次性导出）、token 重置。
- ✅ 作业：rubric 权重和=100 校验、8 位作业码、公开 meta（含 min_client_version/supported_manifest_versions）。
- ✅ 上传 API：Bearer 认证、版本协商（426 CLIENT_OUTDATED）、**ZIP 安全校验**（穿越/绝对路径/符号链接/重复/限额/压缩比/manifest 集合+SHA256 回查/安全解压）、force 覆盖产生新 attempt、eval_job 入队。
- ✅ **评估 Agent**：rollout 解析（逐行容错）→ 硬指标 → 证据包（单 pass 120k 截断）→ LLM（OpenAI 兼容，429/5xx 退避）→ pydantic 校验 + **证据回查**（session_id/turn 必须存在）→ append-only 落库。**超长 quote 系统截断 + flags 透明记录**（真实模型鲁棒性）。
- ✅ **应用内 worker**：单进程 asyncio 循环、原子认领、≤3 次尝试 + attempts*60s 退避、失败隔离（小组评估失败不影响个人）、小组齐套自动评估（generation+1）、截止后缺员补评（注明缺员）。
- ✅ 教师端页面：**课程仪表盘**（首页）/登录/总览板（小组×成员矩阵、进度轮询、stale 标记）/提交详情（等级/维度/证据/feedback/flags/调分/会话时间线/代码查看/截图）/课堂展示（方向键翻页、防泄漏净化）/CSV 导出。
- ✅ **Docker**：`server/Dockerfile` + 根 `docker-compose.yml` + `server/.env.example` + `DEPLOY.md`，容器实测（建号/登录/健康检查）。

### 2.3 学生端（client/，75 测试全绿）

- ✅ 核心：会话筛选（cwd 匹配 + 容错）、项目收集（denylist/排除目录/限额/不跟随链接）、打包（zip+manifest+SHA256）。
- ✅ 上传客户端：Bearer、multipart（manifest 普通字段+file+force）、错误映射 201/401/404/409/422/426、HTTPS 不绕过。
- ✅ outbox 失败重传（按 outbox_id 精确）、全局/项目配置（服务器地址变更需确认）。
- ✅ CLI：`submit --code [--yes] [--force]` / `retry` / `doctor`（/health 探活）/ `bootstrap`（装 uv→注册 marketplace→配置→自检，幂等；镜像只注入子进程环境）。
- ✅ **MCP server**：5 工具（get_assignment_meta/preview_submission/submit_homework/retry_submission/get_submission_status），preview_id 绑定 project_root+指纹+1h 过期，confirmed/force_confirmed 代码层强制，禁 stdio input()。

### 2.4 真实端到端（2026-07-19 实测，非 mock）

- ✅ 真实 Codex 会话 → CLI 提交 ×2 名学生 → **DeepSeek 真实评分**（甲 A→重交 B、乙 A）→ 小组 gen1 A→gen2 B → 教师调分 → 重交 stale 回退 → 总览板/详情/展示/导出全通。
- ✅ E2E 修掉 4 个真 bug（上传路径契约、manifest 字段形式、quote 超长、httpx 运行时依赖）。

---

## 3. 当前怎么跑起来（演示/开发）

```powershell
# 服务器（开发模式，热数据在 server/.env）
cd server
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
# 教师端: http://127.0.0.1:8765/  (admin / teacher123，演示数据已含双学生双评估)

# Docker（生产形态）
cp server/.env.example server/.env   # 填 LLM key
docker compose up -d --build
docker compose exec server vibe-server create-teacher <用户名> <姓名>

# 测试（Windows 本机必须 --basetemp，全局 Temp 有权限问题）
cd server;  ./.venv/Scripts/python.exe -m pytest tests/ -q --basetemp=.pytest_tmp
cd client;  ./.venv/Scripts/python.exe -m pytest tests/ -q --basetemp=.pytest_tmp

# 学生提交（演示）
VIBE_SUBMIT_HOME=E:/vibe-demo-home <client>/.venv/Scripts/vibe-submit.exe submit --code <作业码> --yes
```

---

## 4. 已验证的硬事实（不要重新验证，也不要臆改）

来自 `spikes/RESULTS.md`（2026-07-19，Codex CLI 0.144.6 / uv 0.11.9 / Windows 11）：

1. **插件 .mcp.json 能直接启动 MCP**：`{"command":"uvx","args":["--from","vibe-submit==X.Y.Z","vibe-submit-mcp"]}` 实测通过；**`env` 字段文档未列但实测支持**（用于镜像注入）。
2. **Marketplace 必须仓库根布局**：`.agents/plugins/marketplace.json` 在仓库根；`marketplace add` **不支持子目录**；`--sparse` 需双路径 `.agents/plugins` + `plugins`。
3. **桌面端与 CLI 共享 `~/.codex` 配置**；桌面端插件目录**看不到自定义 marketplace 插件** → 无 CLI 环境无法经桌面 UI 安装，bootstrap 直接写 `config.toml [marketplaces.*]`（追加文本方式对复杂配置安全，已实测）。
4. **VS Code Codex 扩展不支持插件**，但读 `config.toml [mcp_servers]`（兼容路径，实测 pong）。
5. **仓库级 marketplace 无自动发现**（CLI 层），只走显式 add。
6. **Windows 沙箱助手缺失**（0.144.6）：所有沙箱模式 shell 命令失败，**MCP 不受影响**；属平台问题，写课程 FAQ。
7. `uvx --from pkg==ver script` 钉版隔离可靠；镜像用子进程 `UV_INDEX_URL`（不动全局配置）。
8. 教师端 starlette 的 `TemplateResponse` 必须用**旧签名** `(request, name, context)`（新签名会炸 unhashable dict）。

---

## 5. 未完成 — 生产级路线图（按优先级）

### P0 学生端分发闭环（没它学生装不上）

1. **vibe-submit 发布 PyPI**（v0.1.0； twine/uv publish；发布后 `uvx --from vibe-submit==0.1.0 vibe-submit-mcp` 即可用）。
2. **插件 marketplace 正式装配**：把 `JasonLuo365/vibe-course-marketplace` 仓库里的 spike 插件换成正式版（.mcp.json 钉真实版本、SKILL.md 提交引导文案、assets 图标）；建立 stable 分支 + SemVer tag + 版本映射表运营（spec §3.3/§9）。
3. **MCP 路径真实联调**：插件真机安装，对话"提交作业"走 preview→confirm→submit 全流程。
4. **bootstrap.ps1 填课程参数**（marketplace URL + 服务器地址）+ 课程 README。

### P1 生产部署

5. **HTTPS 反代**（Caddy 最简；DEPLOY.md 有示例段）。
6. **备份**：SQLite + data/ 定期拷贝（cron/计划任务脚本）。
7. **域名 + 租赁服务器上线**（现为单机演示）。

### P2 上线前补验（spec §11 遗留）

8. 干净 Windows 用户/VM 装机全流程。
9. Gitee 托管 marketplace 兼容性（国内课堂重要）。
10. 无 CLI 环境手装缓存兜底（设计上可行，未实测）。

### P3 功能补全（12h 冲刺砍掉项）

11. 建课程/花名册/作业的**网页表单**（现仅 API；教师自助化需要）。
12. **map-reduce** 大提交评估（现单 pass 120k 截断；spec §5 设计在案）。
13. 课堂展示的 AI 迭代亮点提炼质量（现为 rationale 截句）。
14. 学生反馈可见性（现仅教师端；spec YAGNI 暂无学生门户）。

### P4 生产化加固

15. **Alembic 迁移**（现 create_all；改表即丢数据风险）。
16. **golden set** 评估质量回归（真实感提交 + 期望等级区间，手动跑调 prompt）。
17. worker 崩溃恢复巡检（stale running 重置已具备，加日志/告警）。
18. 限流 X-Forwarded-For（反代后真实 IP）。
19. 日志规范（服务器结构化日志已有基础，补请求级日志）。
20. VL 模型看截图评分（spec 留有扩展口）。

### 已知 Minor（台账 .superpowers/sdd/progress.md 有完整记录）

- Group 表无 (course_id,name) 唯一约束；token 碰撞无重试；cli.py SessionLocal 未 close + 重名裸 IntegrityError；roster 服务层自提交事务；manifest.submitted_at 未落库；同步解压（大包阻塞请求）；单人小组也触发小组评估。

---

## 6. 关键设计决策（改动前先理解为什么）

- **append-only 评估历史**：每次提交=新 attempt，每次评估=新行；教师调分锚在 (assignment,student/group)，重交后旧调分自动 **stale**（板面回退 AI 等级 + [基于旧提交] 标记）。**不要改成覆盖式**。
- **证据回查**：LLM 输出的 evidence 必须 session_id 存在 + turn 在界内，否则重试；**超长 quote 截断+flag**（不是拒绝）——真实 DeepSeek 反复超长，拒绝重试会被打死。
- **单进程 worker**：禁止 `--workers >1`（会重复消费 eval_jobs）；横向扩展路径 = 抽 Worker + 队列（spec §2 演进路径）。
- **时间一律 naive UTC**（`app.utils.utcnow()`），aware datetime 入库前 astimezone 转换。
- **学生身份只认 Bearer token**；manifest 学号仅展示，不一致直接 422 STUDENT_MISMATCH。
- **客户端确认纪律**：preview_id + confirmed/force_confirmed 代码层强制；MCP 禁 input()；服务器地址变更必须显式确认；HTTPS 证书错误不可绕过。
