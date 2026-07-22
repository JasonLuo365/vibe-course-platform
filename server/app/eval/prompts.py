import json
from typing import Any

from .artifacts import VisualEvidence

PROMPT_VERSION = "v5"

# These are the reusable, teacher-facing evaluation prompt templates.  Keep
# their ids stable because each assignment stores the selected id.
PROMPT_PROFILE_LABELS = {
    "generic_experiment": "通用实验作业",
    "team_experiment": "小组实验项目",
    "team_vibe_coding": "小组 Vibe Coding 成果作业",
    "coding_project": "编程项目",
    "research_report": "研究报告",
    "learning_reflection": "学习反思",
}


_PROFILE_INSTRUCTIONS = {
    "generic_experiment": (
        "这是实验项目的通用占位评价档案。当前没有额外的实验题目规则；"
        "优先核验实验目标、过程证据、结果、分析与反思。"
    ),
    "team_experiment": (
        "这是小组实验项目的通用占位评价档案。除成果外，重点核验成员分工、"
        "协作过程和个人贡献证据。"
    ),
    "team_vibe_coding": (
        "这是小组 Vibe Coding 成果作业。必须先依据小组最终提交的项目成果评分："
        "功能达成、可运行/可演示性、界面与交互、完成度、细节、最终报告和交付质量是首要依据。"
        "成品优秀时，可以得到高分；不得因聊天记录简短或提示词不复杂而扣分。"
        "只有成品存在明显不足、运行/交付无法验证，或个人贡献无法归因时，才深入分析"
        "成员与 Codex 的聊天记录，以诊断原因、确认个人贡献并给出修改建议。"
        "聊天记录用于问题诊断和个人归因，不能完全补偿缺失的核心功能。"
        "小组评价与个人评价独立输出：小组评价最终作品；个人评价只评价可验证的个人贡献，"
        "不得把小组总分平均或复制给成员。无论成果好坏，反馈都必须包含具体亮点、问题和下一步修改建议。"
    ),
    "coding_project": "这是编程项目评价档案。重点核验功能、可运行性、代码质量和迭代过程。",
    "research_report": "这是研究报告评价档案。重点核验论证、证据、概念理解和方法说明。",
    "learning_reflection": "这是学习反思评价档案。重点核验过程证据、问题定位、修改行为和反思深度。",
}


def _profile_instruction(profile: str, custom_instructions: str) -> str:
    base = _PROFILE_INSTRUCTIONS.get(
        profile,
        f"这是预留的评价档案“{profile}”。尚未填写该档案的专属规则，请按通用证据原则评分。",
    )
    if custom_instructions:
        return f"{base}\n\n[本作业/实验的教师专属规则]\n{custom_instructions}"
    return base

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
        criteria = item.get("description") or item.get("criteria", "")
        lines.append(f"- {name}（权重 {weight}%）：{criteria}")
    return "\n".join(lines)


def _system_prompt(
    rubric: list[dict], profile: str, custom_instructions: str, *, has_sessions: bool
) -> str:
    if has_sessions:
        evidence_rules = (
            "2. 每条 evidence 必须给出 session_id、turn 序号和原文 quote；\n"
            "3. quote 必须是原始 rollout 中的真实片段，禁止编造；\n"
            "4. 【硬性要求】每条 quote 最多 200 个字符（约两三句话）。"
            "只截取最关键的一小段原文，宁可更短也不得超过 200 字符；"
            "超过 200 字符的 quote 会被系统自动拒收并导致整份评估作废；\n"
            "5. 若发现无法对应到原始记录的引用、超长的 quote 或无法验证的声明，"
            "请在 flags 中明确标注「真实性风险」。\n"
        )
    else:
        evidence_rules = (
            "2. 本次没有可用的 rollout 会话记录。只能基于代码、最终报告节选和指标"
            "评价最终成果，不得臆测学生的交互过程或个人提示词能力；\n"
            "3. evidence 必须返回空数组 []。不得把文件名、目录名或 manifest.json "
            "当作 session_id，也不得生成 turn 或 quote；\n"
            "4. 请在 flags 中标注「无过程会话记录，仅按成果评估」。\n"
        )
    return (
        "你是大学 Vibe Coding 课程的助教评审。"
        "你只基于提供的证据（rollout 会话记录、代码与最终报告节选、指标）进行评分，不得臆测任何未给出的信息。\n"
        "评分纪律：\n"
        "1. 每条评分结论必须能被证据支持；\n"
        + evidence_rules
        + "\n"
        "评分维度与权重：\n"
        f"{_format_rubric(rubric)}\n\n"
        "本次评价档案：\n"
        f"{_profile_instruction(profile, custom_instructions)}\n\n"
        "输出必须是合法 JSON，严格符合以下 schema（不要包含 markdown 代码块）：\n"
        f"{json.dumps(_INDIVIDUAL_SCHEMA, ensure_ascii=False, indent=2)}\n"
    )


def _group_system_prompt(
    rubric: list[dict], profile: str, custom_instructions: str
) -> str:
    return (
        "你是大学 Vibe Coding 课程的助教评审，现在需要对小组作业进行综合评审。"
        "你只基于提供的成员个人评估、指标和证据进行评分，不得臆测。\n"
        "评分纪律：\n"
        "1. 综合结论必须能被成员评估中的证据支持；\n"
        "2. 如引用原始 rollout，必须给出 session_id、turn 序号和不超过 200 字的原文 quote；\n"
        "3. 若发现引用无法对应或无法验证，请在 flags 中标注「真实性风险」。\n\n"
        "评分维度与权重：\n"
        f"{_format_rubric(rubric)}\n\n"
        "本次评价档案：\n"
        f"{_profile_instruction(profile, custom_instructions)}\n\n"
        "输出必须是合法 JSON，严格符合以下 schema（不要包含 markdown 代码块）：\n"
        f"{json.dumps(_GROUP_SCHEMA, ensure_ascii=False, indent=2)}\n"
    )


def individual_messages(
    evidence_pack: str,
    metrics: dict,
    rubric: list[dict],
    *,
    profile: str = "generic_experiment",
    custom_instructions: str = "",
    error_note: str | None = None,
    has_sessions: bool = True,
    visual_evidence: list[VisualEvidence] | None = None,
) -> list[dict[str, Any]]:
    user_content = (
        "请根据以下证据包、指标和评分标准，对学生本次作业进行个人评估。\n\n"
        f"[证据包]\n{evidence_pack}\n\n"
        f"[指标]\n{json.dumps(metrics, ensure_ascii=False, indent=2)}\n\n"
        f"[评分标准]\n{_format_rubric(rubric)}"
    )
    if error_note:
        user_content += f"\n\n[上次输出错误，请修正后重新输出]\n{error_note}"

    content: str | list[dict[str, Any]] = user_content
    if visual_evidence:
        content = [
            {
                "type": "text",
                "text": user_content
                + "\n\n[报告图表证据]\n以下图片来自学生提交的报告或截图。请结合文字审阅图表；看不清或无法核验时必须明确说明，不得猜测。",
            }
        ]
        for index, image in enumerate(visual_evidence, start=1):
            content.append({"type": "text", "text": f"图表 {index}：{image.label}"})
            content.append(
                {"type": "image_url", "image_url": {"url": image.data_url()}}
            )

    return [
        {
            "role": "system",
            "content": _system_prompt(
                rubric, profile, custom_instructions, has_sessions=has_sessions
            ),
        },
        {"role": "user", "content": content},
    ]


def group_messages(
    member_evals: list[dict],
    metrics: dict,
    rubric: list[dict],
    *,
    profile: str = "generic_experiment",
    custom_instructions: str = "",
    project_digest: str = "",
    error_note: str | None = None,
) -> list[dict[str, str]]:
    user_content = (
        "请根据以下成员个人评估、指标和评分标准，对小组进行综合评估。\n\n"
        f"[小组最终项目成果节选]\n{project_digest or '未提供；不得虚构最终项目质量。'}\n\n"
        f"[成员评估]\n{json.dumps(member_evals, ensure_ascii=False, indent=2)}\n\n"
        f"[指标]\n{json.dumps(metrics, ensure_ascii=False, indent=2)}\n\n"
        f"[评分标准]\n{_format_rubric(rubric)}"
    )
    if error_note:
        user_content += f"\n\n[上次输出错误，请修正后重新输出]\n{error_note}"

    return [
        {
            "role": "system",
            "content": _group_system_prompt(rubric, profile, custom_instructions),
        },
        {"role": "user", "content": user_content},
    ]
