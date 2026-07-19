import json

PROMPT_VERSION = "v1"

_INDIVIDUAL_SCHEMA = {
    "type": "object",
    "properties": {
        "grade": {
            "type": "string",
            "enum": ["A", "B", "C", "D", "E"],
            "description": "总成绩等级，A 最高，E 最低",
        },
        "dimension_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "维度名称"},
                    "weight": {"type": "integer", "description": "权重（0-100）"},
                    "score": {"type": "integer", "description": "得分（0-100）"},
                    "rationale": {"type": "string", "description": "该维度评分依据"},
                },
                "required": ["name", "weight", "score", "rationale"],
            },
            "description": "各维度评分",
        },
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "rollout 会话 id"},
                    "turn": {"type": "integer", "description": "回合序号（从 0 开始）"},
                    "quote": {
                        "type": "string",
                        "maxLength": 200,
                        "description": "不超过 200 字的原文引用",
                    },
                },
                "required": ["session_id", "turn", "quote"],
            },
            "description": "支持评分的具体证据",
        },
        "rationale": {"type": "string", "description": "总体评价 rationale"},
        "feedback": {
            "type": "array",
            "items": {"type": "string"},
            "description": "给学生的反馈建议",
        },
        "flags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "风险提示，如无真实性风险则留空",
        },
    },
    "required": [
        "grade",
        "dimension_scores",
        "evidence",
        "rationale",
        "feedback",
        "flags",
    ],
}

_GROUP_SCHEMA = {
    "type": "object",
    "properties": {
        "grade": {
            "type": "string",
            "enum": ["A", "B", "C", "D", "E"],
            "description": "小组总成绩等级",
        },
        "dimension_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "weight": {"type": "integer"},
                    "score": {"type": "integer"},
                    "rationale": {"type": "string"},
                },
                "required": ["name", "weight", "score", "rationale"],
            },
        },
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "turn": {"type": "integer"},
                    "quote": {"type": "string", "maxLength": 200},
                },
                "required": ["session_id", "turn", "quote"],
            },
        },
        "rationale": {"type": "string"},
        "feedback": {"type": "array", "items": {"type": "string"}},
        "flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "grade",
        "dimension_scores",
        "evidence",
        "rationale",
        "feedback",
        "flags",
    ],
}

INDIVIDUAL_SCHEMA = _INDIVIDUAL_SCHEMA
GROUP_SCHEMA = _GROUP_SCHEMA


def _format_rubric(rubric: list[dict]) -> str:
    lines = []
    for item in rubric:
        name = item.get("name", "未命名维度")
        weight = item.get("weight", 0)
        criteria = item.get("criteria", "")
        lines.append(f"- {name}（权重 {weight}%）：{criteria}")
    return "\n".join(lines)


def _system_prompt(rubric: list[dict]) -> str:
    return (
        "你是大学 Vibe Coding 课程的助教评审。"
        "你只基于提供的证据（rollout 会话记录、代码节选、指标）进行评分，不得臆测任何未给出的信息。\n"
        "评分纪律：\n"
        "1. 每条评分结论必须能被证据支持；\n"
        "2. 每条 evidence 必须给出 session_id、turn 序号和原文 quote；\n"
        "3. quote 必须是原始 rollout 中的真实片段，禁止编造；\n"
        "4. 【硬性要求】每条 quote 最多 200 个字符（约两三句话）。"
        "只截取最关键的一小段原文，宁可更短也不得超过 200 字符；"
        "超过 200 字符的 quote 会被系统自动拒收并导致整份评估作废；\n"
        "5. 若发现无法对应到原始记录的引用、超长的 quote 或无法验证的声明，"
        "请在 flags 中明确标注「真实性风险」。\n\n"
        "评分维度与权重：\n"
        f"{_format_rubric(rubric)}\n\n"
        "输出必须是合法 JSON，严格符合以下 schema（不要包含 markdown 代码块）：\n"
        f"{json.dumps(_INDIVIDUAL_SCHEMA, ensure_ascii=False, indent=2)}\n"
    )


def _group_system_prompt(rubric: list[dict]) -> str:
    return (
        "你是大学 Vibe Coding 课程的助教评审，现在需要对小组作业进行综合评审。"
        "你只基于提供的成员个人评估、指标和证据进行评分，不得臆测。\n"
        "评分纪律：\n"
        "1. 综合结论必须能被成员评估中的证据支持；\n"
        "2. 如引用原始 rollout，必须给出 session_id、turn 序号和不超过 200 字的原文 quote；\n"
        "3. 若发现引用无法对应或无法验证，请在 flags 中标注「真实性风险」。\n\n"
        "评分维度与权重：\n"
        f"{_format_rubric(rubric)}\n\n"
        "输出必须是合法 JSON，严格符合以下 schema（不要包含 markdown 代码块）：\n"
        f"{json.dumps(_GROUP_SCHEMA, ensure_ascii=False, indent=2)}\n"
    )


def individual_messages(
    evidence_pack: str,
    metrics: dict,
    rubric: list[dict],
    *,
    error_note: str | None = None,
) -> list[dict[str, str]]:
    user_content = (
        "请根据以下证据包、指标和评分标准，对学生本次作业进行个人评估。\n\n"
        f"[证据包]\n{evidence_pack}\n\n"
        f"[指标]\n{json.dumps(metrics, ensure_ascii=False, indent=2)}\n\n"
        f"[评分标准]\n{_format_rubric(rubric)}"
    )
    if error_note:
        user_content += f"\n\n[上次输出错误，请修正后重新输出]\n{error_note}"

    return [
        {"role": "system", "content": _system_prompt(rubric)},
        {"role": "user", "content": user_content},
    ]


def group_messages(
    member_evals: list[dict],
    metrics: dict,
    rubric: list[dict],
    *,
    error_note: str | None = None,
) -> list[dict[str, str]]:
    user_content = (
        "请根据以下成员个人评估、指标和评分标准，对小组进行综合评估。\n\n"
        f"[成员评估]\n{json.dumps(member_evals, ensure_ascii=False, indent=2)}\n\n"
        f"[指标]\n{json.dumps(metrics, ensure_ascii=False, indent=2)}\n\n"
        f"[评分标准]\n{_format_rubric(rubric)}"
    )
    if error_note:
        user_content += f"\n\n[上次输出错误，请修正后重新输出]\n{error_note}"

    return [
        {"role": "system", "content": _group_system_prompt(rubric)},
        {"role": "user", "content": user_content},
    ]

