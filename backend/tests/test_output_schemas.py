def test_submit_domain_findings_has_required_fields():
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL
    schema = SUBMIT_DOMAIN_FINDINGS_TOOL["input_schema"]
    assert schema["type"] == "object"
    required = schema["required"]
    assert "anomalies" in required
    assert "ruled_out" in required
    assert "confidence" in required
    # anomalies items must have severity enum
    anomaly_props = schema["properties"]["anomalies"]["items"]["properties"]
    assert "severity" in anomaly_props
    assert anomaly_props["severity"]["enum"] == ["high", "medium", "low"]


def test_submit_causal_analysis_has_required_fields():
    from src.agents.cluster.output_schemas import SUBMIT_CAUSAL_ANALYSIS_TOOL
    schema = SUBMIT_CAUSAL_ANALYSIS_TOOL["input_schema"]
    required = schema["required"]
    assert "causal_chains" in required
    assert "uncorrelated_findings" in required


def test_submit_verdict_has_required_fields():
    from src.agents.cluster.output_schemas import SUBMIT_VERDICT_TOOL
    schema = SUBMIT_VERDICT_TOOL["input_schema"]
    required = schema["required"]
    assert "platform_health" in required
    assert "re_dispatch_needed" in required
    assert "re_dispatch_domains" in required
    health_enum = schema["properties"]["platform_health"]["enum"]
    assert "HEALTHY" in health_enum
    assert "CRITICAL" in health_enum
    assert "UNKNOWN" in health_enum


def test_all_tools_have_name_and_description():
    from src.agents.cluster.output_schemas import (
        SUBMIT_DOMAIN_FINDINGS_TOOL,
        SUBMIT_CAUSAL_ANALYSIS_TOOL,
        SUBMIT_VERDICT_TOOL,
    )
    for tool in [SUBMIT_DOMAIN_FINDINGS_TOOL, SUBMIT_CAUSAL_ANALYSIS_TOOL, SUBMIT_VERDICT_TOOL]:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
