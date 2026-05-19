from app import orchestrator


def test_system_prompt_has_creative_generation_section():
    assert "CREATIVE GENERATION" in orchestrator.SYSTEM_PROMPT


def test_system_prompt_requires_patterns_detected_preamble():
    assert "PATTERNS DETECTED" in orchestrator.SYSTEM_PROMPT


def test_system_prompt_requires_draft_marker():
    assert "DRAFT - NOT PUBLISHED" in orchestrator.SYSTEM_PROMPT


def test_system_prompt_forbids_write_tool_calls():
    assert "NEVER call any ads_create_" in orchestrator.SYSTEM_PROMPT


def test_orchestrator_module_does_not_invoke_write_tools():
    import inspect

    source = inspect.getsource(orchestrator)
    code = source.split("SYSTEM_PROMPT", 1)[0] + source.rsplit('"""', 1)[1]
    for write_tool in (
        "ads_create_ad_set",
        "ads_create_campaign",
        "ads_create_creative",
        "ads_create_ad",
    ):
        assert write_tool not in code, (
            f"{write_tool} found in executable code — must only appear inside the SYSTEM_PROMPT string."
        )
