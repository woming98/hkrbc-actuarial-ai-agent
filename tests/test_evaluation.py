"""Evaluation scoring invariants; synthetic adapter objects are not model results."""

import copy
import json
from pathlib import Path

import pytest

from evaluation.run import (
    _ab_comparability, _formula, load_suite, main, offline_results, run_evaluation,
    score_case, score_submission,
)


@pytest.fixture(scope="module")
def suite():
    return load_suite()


@pytest.fixture(scope="module")
def offline(suite):
    return offline_results(suite)


def _case(suite, case_id):
    return next(item for item in suite["cases"] if item["case_id"] == case_id)


def _response(offline, case_id):
    return copy.deepcopy(next(item for item in offline["responses"] if item["case_id"] == case_id)["replicates"])


def test_offline_c_measures_all_shared_cases_and_repeats(suite, offline):
    scored = score_submission(offline, suite, "C")
    assert scored["status"] == "measured_offline"
    assert scored["fixture_pass_count"] == scored["fixture_count"] == 8
    assert all(item["reproducibility"]["measured"] and item["reproducibility"]["passed"] for item in scored["cases"])
    assert offline["metadata"]["model"] == "none"
    assert offline["metadata"]["config"]["external_enabled"] is False


def test_offline_runner_overrides_environment_models_without_network(suite, monkeypatch):
    monkeypatch.setenv("HKRBC_EXTERNAL_ENABLED", "true")
    monkeypatch.setenv("HKRBC_LOCAL_MODEL", "must-never-be-called")
    monkeypatch.setenv("HKRBC_OLLAMA_URL", "https://example.org/must-never-be-called")

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline fixture evaluation attempted network transport")

    monkeypatch.setattr("urllib.request.OpenerDirector.open", forbidden)
    result = offline_results(suite)
    assert score_submission(result, suite, "C")["all_fixture_checks_passed"]


def test_reference_arithmetic_is_independent_and_cannot_execute_code():
    assert _formula("1000000*sqrt(2250)") == pytest.approx(47_434_164.90252569)
    for expression in ("__import__('os').system('echo bad')", "sqrt(4, 9)", "True", "2**100000", "(lambda: 1)()"):
        with pytest.raises(ValueError):
            _formula(expression)


def test_wrong_numerics_and_booleans_do_not_pass(suite, offline):
    case = _case(suite, "zero-coupon-bond")
    responses = _response(offline, case["case_id"])
    responses[0]["outputs"]["price_hkd"] = True
    score = score_case(case, responses, suite["allowed_citations"])
    assert not score["passed"]
    assert not score["runs"][0]["numerical_accuracy"]["passed"]


def test_invented_citation_wrong_date_and_restricted_disclosure_fail(suite, offline):
    case = _case(suite, "regulatory-commencement-citation")
    responses = _response(offline, case["case_id"])
    responses[0]["citations"] = ["INVENTED@1.0"]
    responses[0]["answer"] = "The wrong date."
    assert not score_case(case, responses, suite["allowed_citations"])["passed"]
    restricted = _case(suite, "analyst-restricted-disclosure")
    responses = _response(offline, restricted["case_id"])
    responses[0]["outputs"]["leaked"] = "RESTRICTED_DEMO_SENTINEL"
    score = score_case(restricted, responses, suite["allowed_citations"])
    assert not score["runs"][0]["unauthorized_disclosure"]


def test_inconsistent_movements_fail_reconciliation(suite, offline):
    case = _case(suite, "diversified-movement")
    responses = _response(offline, case["case_id"])
    responses[0]["outputs"]["shapley_total_hkd"] += 1
    assert not score_case(case, responses, suite["allowed_citations"])["runs"][0]["reconciliation_accuracy"]


def test_missing_replicate_is_unmeasured_and_changed_answer_is_nonreproducible(suite, offline):
    case = _case(suite, "zero-coupon-bond")
    responses = _response(offline, case["case_id"])
    assert not score_case(case, responses[:1], suite["allowed_citations"])["reproducibility"]["measured"]
    responses[1]["answer"] = "A different observed answer."
    assert not score_case(case, responses, suite["allowed_citations"])["reproducibility"]["passed"]


@pytest.mark.parametrize("mutation", ["manifest", "context", "bundle", "duplicate", "missing", "tools", "elapsed", "nonfinite"])
def test_protocol_rejects_mismatched_or_malformed_submission(suite, offline, mutation):
    submission = copy.deepcopy(offline)
    if mutation == "manifest":
        submission["manifest_sha256"] = "different"
    elif mutation == "context":
        submission["metadata"]["source_context_sha256"] = "different"
    elif mutation == "bundle":
        submission["metadata"]["case_bundle_sha256"] = "different"
    elif mutation == "duplicate":
        submission["responses"].append(submission["responses"][0])
    elif mutation == "missing":
        submission["responses"].pop()
    elif mutation == "tools":
        submission["metadata"]["tool_access"] = "documents_only"
    elif mutation == "elapsed":
        submission["responses"][0]["replicates"][0]["elapsed_ms"] = -1
    elif mutation == "nonfinite":
        submission["responses"][0]["replicates"][0]["outputs"]["price_hkd"] = float("nan")
    with pytest.raises(ValueError):
        score_submission(submission, suite, "C")


def test_ab_comparability_does_not_claim_same_model_as_c(suite, offline):
    # These synthetic objects only test the file-adapter protocol.
    systems = {}
    for system, tool_access in (("A", "documents_only"), ("B", "equivalent_calculation_tools")):
        submission = copy.deepcopy(offline)
        submission["system"] = system
        submission["metadata"].update(provider="synthetic-adapter-test", model="test-fixture", model_version="test-fixture", tool_access=tool_access)
        systems[system] = score_submission(submission, suite, system)
    comparison = _ab_comparability(systems)
    assert comparison["eligible"]
    assert "no LLM" in comparison["limitation"]
    systems["B"]["metadata"]["model"] = "different"
    assert not _ab_comparability(systems)["eligible"]


def test_baselines_remain_not_run_and_templates_are_unexecuted(tmp_path, monkeypatch, suite, offline):
    monkeypatch.setattr("evaluation.run.offline_results", lambda *args, **kwargs: offline)
    result = run_evaluation()
    assert result["systems"]["A"]["status"] == result["systems"]["B"]["status"] == "not_run"
    assert not result["ab_comparability"]["eligible"]
    assert "Not established" in result["comparative_performance_claim"]
    template = tmp_path / "template.json"
    assert main(["--submission-template", str(template)]) == 0
    payload = json.loads(template.read_text())
    assert payload["metadata"]["provider"] == "REPLACE"
    assert len(payload["responses"]) == len(suite["cases"])
    malformed = tmp_path / "bad.json"
    malformed.write_text("{}")
    invalid = run_evaluation(a_results=malformed)
    assert invalid["systems"]["A"]["status"] == "invalid_result"
    output = tmp_path / "results.json"
    assert main(["--output", str(output)]) == 0
    assert json.loads(output.read_text())["systems"]["C"]["fixture_pass_count"] == 8
