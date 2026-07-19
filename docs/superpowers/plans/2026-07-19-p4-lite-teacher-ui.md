# P4-lite 教师端实施计划（12h 冲刺压缩版）

> 范围：登录页、作业总览板、提交详情、调分、课堂展示模式、CSV 导出。Jinja2 服务端渲染 + 少量原生 JS 轮询，无 HTMX 依赖。

**Goal:** 教师浏览器可用的最小完整界面 + 展示/导出。

**Tech:** jinja2（需加入 pyproject 依赖）、Jinja2Templates、原生 fetch 轮询。模板在 `server/app/templates/`，静态 `server/app/static/`。

## Global Constraints（spec §6 逐字约束）

- 多教师 session（复用 P2 登录 API）；页面路由未登录 → 302 到 `/login`（新 `get_teacher_page` 依赖，区别于 API 的 401）。
- 总览板：小组×成员矩阵（提交状态 + AI 等级 + 最终等级；调过分高亮；stale override 标"基于旧提交"；评估失败标红）；进度自动轮询（`GET /api/assignments/{id}/progress` → {total_submissions, evaluated, failed, queued}）；导出 CSV 链接。
- 详情页 tab：评估（等级/维度小分与依据/feedback/flags/调分表单，显示"AI 原评 X → 最终 Y"）、会话时间线（分会话完整对话 user/assistant/tool 着色 + 硬指标条）、代码（树+只读查看）、截图（画廊）。
- 调分：individual/group 两种 target；最终成绩 = override ?? AI 等级；新 attempt 产生时旧 override 自动 stale=True（需在上传端点补钩子）。
- 展示模式 `/assignments/{id}/present`：一页一组、左右方向键翻页、大字号；组名/成员/最终等级/截图轮播/AI 迭代亮点（取该组最新 GroupEvaluation 的 rationale 前 2-3 句 + contribution_json）/硬指标速览；**不含维度小分与 feedback/flags**。
- CSV 导出 `/assignments/{id}/export.csv`：列 学号,姓名,小组,AI等级,最终等级,各维度分(json),提交状态。

### Task 1: 页面骨架 + 登录页 + 总览板 + 进度 API

**Files:** Modify server/pyproject.toml(+jinja2)、server/app/web/__init__.py、server/app/web/pages.py、server/app/web/board.py、server/app/templates/base.html、login.html、board.html、server/app/static/app.css、Modify server/app/main.py（mount static + pages router）、server/tests/test_web_board.py

**Interfaces:**
- `get_teacher_page(request, db) -> Teacher`（未登录 → 302 /login）
- board.py：`board_data(db, assignment) -> dict`：{assignment, groups:[{group, members:[{student, submission, attempt, evaluation(最新), override, final_grade, cell_status}]}], progress:{...}}；cell_status ∈ none/received/queued/evaluating/evaluated/failed
- `GET /login`（页）、`GET /assignments/{aid}/board`、`GET /api/assignments/{aid}/progress`
- 测试：登录页 200；未登录 board → 302；登录后 board 含小组/成员/等级单元格；progress JSON 字段；无作业 404

### Task 2: 提交详情页 + 调分（含上传端点 stale 钩子）

**Files:** server/app/web/detail.py、server/app/templates/submission.html、Modify server/app/api/submissions.py（新 attempt 时把该 (assignment_id,student_id) / (assignment_id,group_id) 旧 override stale=True）、server/tests/test_web_detail.py

**Interfaces:**
- `GET /submissions/{sid}`：evaluation（当前 attempt 最新一条）+ timelines（parse_rollout 每会话）+ metrics + code 文件列表 + screenshots 列表 + override 历史
- `POST /evaluations/{eid}/override`（form：final_grade A–E, comment）→ upsert GradeOverride(individual, "{assignment_id}:{student_id}")；`POST /group-evaluations/{gid}/override` 同理（group）
- 测试：详情页含等级/维度/依据/会话内容；调分后 board 显示最终等级且 AI 原评仍在；stale 钩子：override 后重交 → override.stale=True

### Task 3: 课堂展示模式 + CSV 导出 + 最终回归

**Files:** server/app/web/present.py、server/app/templates/present.html、server/app/static/present.css、server/tests/test_web_present.py

**Interfaces:**
- `GET /assignments/{aid}/present[?i=0]`：server 渲染全部组的 JSON 嵌入页面 + JS 左右键切换；截图路径经 `/media/extracted/{attempt_id}/...`（新静态挂载点，限 data/extracted 内）
- `GET /assignments/{aid}/export.csv`（text/csv，Content-Disposition attachment）
- 测试：present 页含组名/成员/最终等级/亮点且**不含** feedback/flags 字样；export.csv 行列正确含 AI 与最终等级

