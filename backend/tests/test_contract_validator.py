"""JSON-Schema validator wrapper — structured issue list."""

from src.contracts.validator import ValidationIssue, validate_against

SCHEMA = {
    "type": "object",
    "properties": {
        "x": {"type": "string"},
        "n": {"type": "integer"},
    },
    "required": ["x"],
}


def test_valid_payload_returns_empty_list():
    assert validate_against({"x": "ok"}, SCHEMA) == []


def test_missing_required_returns_issue():
    issues = validate_against({}, SCHEMA)
    assert len(issues) == 1
    assert issues[0].path == "$"
    assert "x" in issues[0].message


def test_type_mismatch_returns_issue():
    issues = validate_against({"x": "ok", "n": "not-an-int"}, SCHEMA)
    assert any(i.path == "$.n" for i in issues)


def test_multiple_issues_returned():
    issues = validate_against({"n": "bad"}, SCHEMA)
    # Missing required "x" → path "$"; bad type on "n" → path "$.n"
    assert any(i.path == "$" and "x" in i.message for i in issues)
    assert any(i.path == "$.n" for i in issues)


def test_issue_is_immutable_dataclass():
    issue = ValidationIssue(path="$.a", message="bad")
    # frozen=True — attempting to mutate should raise
    try:
        issue.path = "$.b"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("ValidationIssue should be frozen")
