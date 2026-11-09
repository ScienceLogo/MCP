from pathlib import Path

import pytest

from sciencelogo_mcp.helper import HelperError

WORKFLOWS = Path(__file__).parent / "workflows"


def check(helper, name):
    return helper.request("check", entry=str(WORKFLOWS / name / "workflow.rkt"))


def test_valid_workflow_split_over_files(helper):
    result = check(helper, "valid")
    assert result["status"] == "valid"
    assert "No structural issues found." in result["assessment"]["report"]


def test_read_error_reports_message_and_location(helper):
    result = check(helper, "unclosed")
    assert result["status"] == "invalid"
    assert "expected ]" in result["message"]
    assert result["file"].endswith("unclosed/workflow.rkt")
    assert isinstance(result["line"], int)


def test_error_in_included_file_names_that_file(helper):
    result = check(helper, "bad-include")
    assert result["status"] == "invalid"
    assert result["file"].endswith("bad-include/part.rkt")


def test_missing_included_file(helper):
    result = check(helper, "missing-include")
    assert result["status"] == "invalid"
    assert "missing included file missing.rkt" in result["message"]


def test_unknown_operation_is_an_error(helper):
    with pytest.raises(HelperError, match="unknown operation"):
        helper.request("nonexistent")


def test_helper_restarts_after_a_crash(helper):
    check(helper, "valid")
    helper._process.kill()
    helper._process.wait()
    assert check(helper, "valid")["status"] == "valid"
