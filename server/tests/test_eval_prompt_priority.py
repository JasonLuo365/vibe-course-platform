from app.eval.prompts import SYSTEM_DEFAULT_RUBRIC, effective_rubric, individual_messages


def test_teacher_prompt_is_authoritative_and_hides_default_rubric():
    messages = individual_messages(
        "submitted evidence",
        {},
        [{"name": "legacy-heavy-dimension", "weight": 100, "description": "strict"}],
        profile="generic_experiment",
        custom_instructions="Teacher requirement: reward sound exploration and evidence.",
    )

    system = messages[0]["content"]
    user = messages[1]["content"]
    assert "Teacher requirement: reward sound exploration and evidence." in system
    assert "legacy-heavy-dimension" not in system
    assert "legacy-heavy-dimension" not in user


def test_legacy_hidden_rubric_uses_current_system_baseline():
    legacy = [
        {"name": "功能完成度", "weight": 40, "description": ""},
        {"name": "成果质量", "weight": 40, "description": ""},
        {"name": "过程与迭代", "weight": 20, "description": ""},
    ]
    assert effective_rubric(legacy) == SYSTEM_DEFAULT_RUBRIC


def test_nonlegacy_teacher_configured_rubric_is_preserved():
    rubric = [{"name": "teacher-defined", "weight": 100, "description": "custom"}]
    assert effective_rubric(rubric) == rubric
