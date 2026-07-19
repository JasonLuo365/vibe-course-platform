import json

import httpx
import pytest

from app.eval.evaluator import (
    EvalError,
    build_evidence_pack,
    code_digest,
    evaluate_group,
    evaluate_individual,
)
from app.eval.llm import OpenAICompatProvider
from app.eval.metrics import compute_metrics
from app.eval.parser import parse_rollout
from app.eval.prompts import PROMPT_VERSION


def _write_jsonl(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


@pytest.fixture
def rollout_path(tmp_path):
    path = tmp_path / "sess-abc.jsonl"
    lines = [
        {
            "type": "session_meta",
            "payload": {
                "id": "sess-abc",
                "timestamp": "2026-07-19T10:00:00+08:00",
                "cwd": "/workspace",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Implement a todo list"}],
                "timestamp": "2026-07-19T10:01:00+08:00",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "I'll create a FastAPI app."}],
                "timestamp": "2026-07-19T10:02:00+08:00",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "write_file",
                "arguments": '{"path": "src/main.py", "content": "print(1)"}',
                "timestamp": "2026-07-19T10:03:00+08:00",
            },
        },
    ]
    _write_jsonl(path, lines)
    return str(path)


@pytest.fixture
def timelines(rollout_path):
    return [parse_rollout(rollout_path)]


@pytest.fixture
def metrics(timelines):
    return compute_metrics(timelines)


@pytest.fixture
def rubric():
    return [
        {"name": "需求理解", "weight": 30, "criteria": "准确理解作业需求"},
        {"name": "实现质量", "weight": 40, "criteria": "代码可运行、结构清晰"},
        {"name": "迭代能力", "weight": 30, "criteria": "能根据反馈修正"},
    ]


@pytest.fixture
def code_digest_text(tmp_path):
    d = tmp_path / "extracted" / "attempt-1"
    d.mkdir(parents=True)
    (d / "main.py").write_text("def main(): pass\n", encoding="utf-8")
    (d / "README.md").write_text("# Todo\n", encoding="utf-8")
    return code_digest(str(d))


class FakeLLMProvider:
    """Programmable provider for tests: either a queue of response strings or a callable."""

    def __init__(self, responses=None, callable=None):
        self.responses = list(responses) if responses is not None else None
        self._callable = callable
        self.calls = []

    def complete(self, messages, *, json_schema=None, max_tokens=4096):
        self.calls.append(
            {"messages": messages, "json_schema": json_schema, "max_tokens": max_tokens}
        )
        if self._callable is not None:
            return self._callable(messages, json_schema=json_schema, max_tokens=max_tokens)
        if not self.responses:
            raise RuntimeError("FakeLLMProvider response queue exhausted")
        return self.responses.pop(0)


def _valid_individual_json():
    return json.dumps(
        {
            "grade": "B",
            "dimension_scores": [
                {
                    "name": "需求理解",
                    "weight": 30,
                    "score": 85,
                    "rationale": "用户首条请求准确对应了作业目标。",
                },
                {
                    "name": "实现质量",
                    "weight": 40,
                    "score": 78,
                    "rationale": "仅创建了入口文件，结构较简单。",
                },
                {
                    "name": "迭代能力",
                    "weight": 30,
                    "score": 80,
                    "rationale": "未出现报错修正场景。",
                },
            ],
            "evidence": [
                {
                    "session_id": "sess-abc",
                    "turn": 0,
                    "quote": "Implement a todo list",
                }
            ],
            "rationale": "整体完成了基本需求，质量中等。",
            "feedback": ["可以补充更多功能测试", "建议增加错误处理"],
            "flags": [],
        },
        ensure_ascii=False,
    )


def _valid_group_json():
    return json.dumps(
        {
            "grade": "B",
            "dimension_scores": [
                {
                    "name": "协作一致性",
                    "weight": 50,
                    "score": 82,
                    "rationale": "两位成员实现方向一致。",
                },
                {
                    "name": "整体完成度",
                    "weight": 50,
                    "score": 80,
                    "rationale": "整体覆盖需求。",
                },
            ],
            "evidence": [],
            "rationale": "小组整体表现良好。",
            "feedback": ["注意代码风格统一"],
            "flags": ["无真实性风险"],
        },
        ensure_ascii=False,
    )


class TestEvaluateIndividual:
    def test_valid_evaluation_fields(self, timelines, code_digest_text, metrics, rubric):
        provider = FakeLLMProvider(responses=[_valid_individual_json()])
        result = evaluate_individual(timelines, code_digest_text, metrics, rubric, provider)

        assert result["grade"] == "B"
        assert result["prompt_version"] == PROMPT_VERSION
        assert len(result["dimension_scores"]) == 3
        assert result["dimension_scores"][0]["name"] == "需求理解"
        assert result["evidence"][0]["session_id"] == "sess-abc"
        assert result["evidence"][0]["turn"] == 0
        assert len(result["feedback"]) == 2
        assert result["flags"] == []
        assert provider.calls[0]["json_schema"] is not None
        assert len(provider.calls) == 1

    def test_invalid_json_then_valid_retries_ok(self, timelines, code_digest_text, metrics, rubric):
        provider = FakeLLMProvider(
            responses=["this is not json", _valid_individual_json()]
        )
        result = evaluate_individual(timelines, code_digest_text, metrics, rubric, provider)

        assert result["grade"] == "B"
        assert len(provider.calls) == 2
        # The retry should have appended an error note to the user message.
        last_user = _last_user_message(provider.calls[-1]["messages"])
        assert "JSON" in last_user or "json" in last_user

    def test_evidence_backcheck_fail_then_valid_retries_ok(
        self, timelines, code_digest_text, metrics, rubric
    ):
        bad = json.dumps(
            {
                "grade": "A",
                "dimension_scores": [
                    {
                        "name": "需求理解",
                        "weight": 30,
                        "score": 95,
                        "rationale": "引用不存在的回合",
                    }
                ],
                "evidence": [
                    {"session_id": "sess-abc", "turn": 99, "quote": "does not exist"}
                ],
                "rationale": "bad",
                "feedback": [],
                "flags": [],
            },
            ensure_ascii=False,
        )
        provider = FakeLLMProvider(responses=[bad, _valid_individual_json()])
        result = evaluate_individual(timelines, code_digest_text, metrics, rubric, provider)

        assert result["grade"] == "B"
        assert len(provider.calls) == 2
        last_user = _last_user_message(provider.calls[-1]["messages"])
        assert "证据" in last_user or "turn" in last_user

    def test_quote_too_long_then_valid_retries_ok(
        self, timelines, code_digest_text, metrics, rubric
    ):
        bad = json.dumps(
            {
                "grade": "A",
                "dimension_scores": [
                    {
                        "name": "需求理解",
                        "weight": 30,
                        "score": 95,
                        "rationale": "引用超长",
                    }
                ],
                "evidence": [
                    {
                        "session_id": "sess-abc",
                        "turn": 0,
                        "quote": "x" * 201,
                    }
                ],
                "rationale": "bad",
                "feedback": [],
                "flags": [],
            },
            ensure_ascii=False,
        )
        provider = FakeLLMProvider(responses=[bad, _valid_individual_json()])
        result = evaluate_individual(timelines, code_digest_text, metrics, rubric, provider)
        assert result["grade"] == "B"
        assert len(provider.calls) == 2

    def test_all_retries_exhausted_raises_eval_error(
        self, timelines, code_digest_text, metrics, rubric
    ):
        provider = FakeLLMProvider(responses=["bad"] * 3)
        with pytest.raises(EvalError):
            evaluate_individual(timelines, code_digest_text, metrics, rubric, provider)
        assert len(provider.calls) == 3


class TestBuildEvidencePack:
    def test_build_pack_contains_session_and_metrics(self, timelines, metrics):
        pack = build_evidence_pack(timelines, "# code", metrics, max_chars=10000)
        assert "sess-abc" in pack
        assert "sessions" in pack
        assert "# code" in pack

    def test_budget_truncation_keeps_within_limit(self, tmp_path):
        path = tmp_path / "long.jsonl"
        lines = [
            {
                "type": "session_meta",
                "payload": {"id": "long-sess", "timestamp": "2026-07-19T10:00:00Z"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": "x" * 5000,
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "y" * 5000,
                },
            },
        ]
        _write_jsonl(path, lines)
        timelines = [parse_rollout(str(path))]
        metrics = compute_metrics(timelines)
        pack = build_evidence_pack(timelines, "z" * 1000, metrics, max_chars=2000)
        assert len(pack) <= 2000
        assert "截断" in pack


class TestCodeDigest:
    def test_digest_has_tree_and_snippets(self, tmp_path):
        d = tmp_path / "src"
        d.mkdir()
        (d / "main.py").write_text("def main():\n    pass\n", encoding="utf-8")
        (d / "utils.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
        digest = code_digest(str(d), max_files=10, max_chars=2000)
        assert "main.py" in digest
        assert "utils.py" in digest
        assert len(digest) <= 2000


class TestEvaluateGroup:
    def test_valid_group_evaluation(self, rubric, metrics):
        member_eval = json.loads(_valid_individual_json())
        member_eval["prompt_version"] = PROMPT_VERSION
        provider = FakeLLMProvider(responses=[_valid_group_json()])
        result = evaluate_group([member_eval], metrics, rubric, provider)

        assert result["grade"] == "B"
        assert result["prompt_version"] == PROMPT_VERSION
        assert len(result["dimension_scores"]) == 2
        assert "无真实性风险" in result["flags"]


class TestOpenAICompatProvider:
    def test_retries_429_and_5xx_with_backoff(self):
        attempts = []

        def handler(request: httpx.Request):
            attempts.append(request.url.path)
            if len(attempts) < 3:
                return httpx.Response(429, json={"error": "rate limited"})
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "hello"}, "finish_reason": "stop"}
                    ]
                },
            )

        transport = httpx.MockTransport(handler)
        provider = OpenAICompatProvider(
            base_url="http://test",
            api_key="key",
            model="m",
            max_retries=3,
            transport=transport,
        )
        result = provider.complete([{"role": "user", "content": "hi"}])
        assert result == "hello"
        assert len(attempts) == 3


def _last_user_message(messages):
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""
