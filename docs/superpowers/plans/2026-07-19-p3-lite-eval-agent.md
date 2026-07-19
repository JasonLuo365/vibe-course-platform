# P3-lite 评估 Agent 实施计划（12h 冲刺压缩版）

> 执行方式：subagent-driven，每任务 TDD + 评审。压缩范围：单次评估（无 map-reduce）、缺员小组在 workers 循环内简单补评。

**Goal:** 服务器端评估流水线：rollout 解析 → 硬指标 → 证据包 → LLM（OpenAI 兼容，国内模型）→ 结构化评估落库；应用内单 worker 自动消费 eval_jobs（个人 + 小组）。

**Tech:** 复用 server/ 现有栈；httpx 调 LLM；测试用 FakeLLMProvider，不触真实 API。

## Global Constraints（spec §5 逐字约束）

- 输出 JSON 结构：`grade(A–E)`、`dimension_scores[{name,weight,score,rationale}]`、`evidence[{session_id,turn,quote(≤200字)}]`、`rationale`、`feedback[]`、`flags[]`；pydantic 校验 + 证据回查（session_id/turn 必须存在），不合法自动重试至多 2 次 → failed。
- 评估记录 append-only 关联 attempt；存 `model` + `prompt_version`。
- 状态流转：job queued→running→done/failed；attempt/submission: queued→evaluating→evaluated/failed；失败重试 ≤3 次（退避 attempts*60s）。
- 小组评估触发：组内全部学生当前 attempt 均 evaluated → generation+1 写入 GroupEvaluation；截止后缺员小组也评（rationale 注明缺员名单）。
- 单进程 worker：FastAPI lifespan 内 asyncio 循环（默认 2s 轮询；`VIBE_WORKER_ENABLED=false` 关闭；测试直接调 `run_worker_once`）。
- LLM 配置走 Settings env：`llm_base_url`、`llm_api_key`、`llm_model`（默认 `deepseek-chat`）。
- 证据包单 pass：全文拼接超 `max_chars=120000` 时保头尾截断中部并注明。

### Task 1: rollout 解析器 + 硬指标

**Files:** server/app/eval/__init__.py、server/app/eval/parser.py、server/app/eval/metrics.py、server/tests/test_eval_parser.py

**Interfaces:**
- `Turn = dataclass(kind: str, text: str, ts: str|None)`（kind ∈ user/assistant/tool/other）
- `RolloutTimeline = dataclass(session_id: str, path: str, turns: list[Turn])`
- `parse_rollout(path: str) -> RolloutTimeline`：首行 session_meta 取 id；其后每行容错解析（坏行跳过计数），user 消息→user，assistant→assistant，function_call/tool 调用→tool；无法分类→other；文本提取取 content/input/arguments 中可得字符串（截断 2000 字/turn）
- `compute_metrics(timelines: list[RolloutTimeline]) -> dict`：{sessions, turns, user_turns, duration_min(首末 ts 差,无 ts 则 0), error_fix_cycles(含"error/报错/失败/Traceback"的 tool/user turn 后 3 turn 内有修正类 user turn 的计数), files_touched(tool 文本中路径去重数,启发式)}
- 测试：fixture rollout（真实感多类型行 + 坏行 + 缺 meta）；metrics 数值断言

### Task 2: LLM provider + 提示词 + 评估流水线

**Files:** server/app/eval/llm.py、server/app/eval/prompts.py、server/app/eval/evaluator.py、server/tests/test_eval_pipeline.py

**Interfaces:**
- `class LLMProvider(Protocol): complete(messages: list[dict], *, json_schema: dict|None=None, max_tokens: int=4096) -> str`
- `OpenAICompatProvider(base_url, api_key, model, timeout=120, max_retries=3)`：POST {base}/chat/completions，json response_format（支持时），429/5xx/timeout 指数退避；httpx.Client；transport 可注入测试
- `INDIVIDUAL_SCHEMA: dict`、`GROUP_SCHEMA: dict`
- `build_evidence_pack(timelines, code_digest: str, metrics: dict, max_chars=120000) -> str`（超长按中部截断+注明）
- `code_digest(extract_dir: str, max_files=20, max_chars=8000) -> str`（目录树 + 关键文件节选）
- `evaluate_individual(timelines, code_digest, metrics, rubric: list[dict], provider) -> dict`：组 prompt → complete → json 解析 → pydantic 模型 `EvalOut` 校验 + 证据回查（session_id ∈ timelines, turn < len(turns), quote ≤200）→ 失败带错误说明重试至多 2 次 → 抛 EvalError
- `evaluate_group(member_evals: list[dict], metrics, rubric, provider) -> dict`
- prompts.py：`individual_messages(evidence_pack, metrics, rubric)`、`group_messages(...)`；`PROMPT_VERSION = "v1"`
- 测试：FakeLLMProvider（可编程返回序列）；合法→落字段；首次非法 JSON→重试成功；证据回查失败→重试；超预算截断断言

### Task 3: 应用内 worker + 小组评估 + 状态流转 + e2e

**Files:** server/app/eval/worker.py、server/app/eval/service.py、Modify server/app/config.py（+3 llm 字段 + worker_enabled）、Modify server/app/main.py（lifespan 启动 worker）、server/tests/test_eval_worker.py、server/tests/test_eval_e2e.py

**Interfaces:**
- `run_worker_once(db, provider) -> int`（处理数量）：原子认领先到 queued job（单进程直接事务内 set running+attempts+1）；kind=="individual"→从 attempt.package 对应 data/extracted/{attempt_id} 读 sessions/ 解析+code_digest+metrics→evaluate_individual→写 Evaluation（append-only）→attempt/submission=evaluated，job=done；EvalError→attempt/submission=failed，job 按退避重排或 failed；individual done 后检查小组齐套→evaluate_group→GroupEvaluation(generation=max+1)
- `claim_next_job(db) -> EvalJob|None`；`_group_ready(db, assignment_id, group_id) -> bool`；`missing_members(db, assignment_id, group_id) -> list[Student]`
- deadline 补评：run_worker_once 同时扫描已过 deadline 作业中「有≥1 个 evaluated 成员但无当前代 group eval」的小组→评（rationale 前加"缺员: …"）
- service.py：`evaluate_attempt(db, attempt, provider)`、`evaluate_group_job(db, assignment_id, group_id, provider, missing=[])`
- main.py：lifespan asynccontextmanager，`settings.worker_enabled` 时 `asyncio.create_task(worker_loop())`（循环 sleep 2s 调 run_worker_once，异常吞掉记 log）
- 测试：FakeLLM 下——上传（复用现有测试 helper）→run_worker_once→Evaluation 行+状态 evaluated；LLM 连续失败→3 次后 failed；两成员小组齐套→GroupEvaluation generation=1，新 attempt 重评后 generation=2；缺员补评注明缺员
