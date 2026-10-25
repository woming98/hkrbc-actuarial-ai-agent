"""Service probes and checks that the diagnostic detects boundary regressions."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import urllib.request

import pytest

from hkrbc_agent.routing import ModelRouter
from hkrbc_agent.security import AuthService, Principal, Role
from hkrbc_agent.service import AgentService


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("adversarial_eval", PROJECT / "evaluation/adversarial_eval.py")
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)
MANIFEST = evaluation.load_cases(evaluation.DEFAULT_CASES)
CASES = {case["case_id"]: case for case in MANIFEST["cases"]}


@pytest.fixture(scope="module")
def measured():
    return evaluation.evaluate()


@pytest.mark.parametrize("case_id", list(CASES))
def test_fixed_signed_service_outcomes(measured, case_id):
    result = next(row for row in measured["cases"] if row["case_id"] == case_id)
    failed = {name: value for name, value in result["checks"].items() if not value["passed"]}
    assert result["passed"], failed


def test_artifact_identifies_exact_sources_and_records_no_network(measured):
    assert measured["passed"]
    assert measured["source_stable_during_run"]
    assert measured["case_manifest_sha256"] == evaluation.digest(evaluation.DEFAULT_CASES)
    assert measured["source_sha256"] == evaluation.source_hashes()
    assert measured["summary"]["cases"] == len(CASES)
    assert measured["summary"]["network_attempts"] == 0
    assert measured["summary"]["in_memory_transport_attempts"] == 1
    assert {"privacy", "injection", "sessions", "authorization", "routing", "lifecycle", "reports", "claim_scope"} <= set(measured["summary"]["categories"])
    artifact = json.dumps(measured, ensure_ascii=False)
    assert evaluation.FAKE_KEY not in artifact
    for case in CASES.values():
        if case.get("query"):
            assert case["query"] not in artifact
        for marker in case.get("remember", []):
            assert marker not in artifact
    assert "not a security certificate" in measured["purpose"]


def test_probe_detects_forged_session_acceptance(monkeypatch):
    original = AuthService.resolve
    def faulty_resolve(self, token):
        try:
            return original(self, token)
        except PermissionError:
            return Principal("analyst", Role.ANALYST)
    monkeypatch.setattr(AuthService, "resolve", faulty_resolve)
    result = evaluation.run_case(CASES["session-tamper-signature"], MANIFEST["universal_expectations"])
    assert result["passed"] is False
    assert result["observations"]["outcome"] == "returned"
    assert result["checks"]["outcome"]["passed"] is False
    assert result["observations"]["network_attempts"] == 0


def test_probe_detects_truthy_approval_regression_before_network(monkeypatch):
    original = ModelRouter.summarize
    def faulty_approval(self, principal, query, hits, *, mode="local", approved=False):
        return original(self, principal, query, hits, mode=mode, approved=bool(approved))
    monkeypatch.setattr(ModelRouter, "summarize", faulty_approval)
    result = evaluation.run_case(CASES["external-truthy-approval"], MANIFEST["universal_expectations"])
    assert result["passed"] is False
    assert result["observations"]["error_type"] == "TransportBlocked"
    assert result["observations"]["transport_attempts"] == 1
    assert result["observations"]["network_attempts"] == 0


def test_probe_detects_prompt_storage_without_copying_prompt_to_artifact(monkeypatch):
    original = AgentService.ask
    def faulty_storage(self, token, query, **kwargs):
        result = original(self, token, query, **kwargs)
        with self.store.connect() as db:
            # Deliberately simulate a persistence regression outside Store.audit
            # so the independent database scan, rather than an allowlist, catches it.
            db.execute("INSERT INTO audit(timestamp,actor,role,event,details) VALUES(?,?,?,?,?)",
                ("synthetic", "analyst", Role.ANALYST.value, "synthetic_storage_bug", json.dumps({"query": query})))
        return result
    monkeypatch.setattr(AgentService, "ask", faulty_storage)
    case = CASES["local-redaction-no-persistence"]
    result = evaluation.run_case(case, MANIFEST["universal_expectations"])
    assert result["passed"] is False
    assert result["observations"]["raw_prompt_persisted"] is True
    assert result["observations"]["raw_sensitive_fixture_persisted"] is True
    artifact = json.dumps(result)
    assert case["query"] not in artifact
    assert case["remember"][0] not in artifact


def test_network_tripwire_counts_and_fails_attempts(monkeypatch):
    def faulty_summarize(*args, **kwargs):
        urllib.request.urlopen("https://example.invalid/never-contact")
        raise AssertionError("Network guard did not stop execution")
    monkeypatch.setattr(ModelRouter, "summarize", faulty_summarize)
    result = evaluation.run_case(CASES["local-default"], MANIFEST["universal_expectations"])
    assert result["passed"] is False
    assert result["observations"]["error_type"] == "NetworkBlocked"
    assert result["observations"]["network_attempts"] == 1
    assert result["checks"]["network_attempts"]["passed"] is False


@pytest.mark.parametrize("mutation", ["duplicate", "missing_safety", "wrong_safety_type", "unknown_probe"])
def test_invalid_manifest_fails_closed(tmp_path, mutation):
    manifest = json.loads(evaluation.DEFAULT_CASES.read_text(encoding="utf-8"))
    if mutation == "duplicate":
        manifest["cases"].append(manifest["cases"][0])
    elif mutation == "missing_safety":
        manifest["universal_expectations"].pop("network_attempts")
    elif mutation == "wrong_safety_type":
        manifest["universal_expectations"]["network_attempts"] = False
    else:
        manifest["cases"][0]["probe"] = "execute-user-command"
    path = tmp_path / "invalid-cases.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        evaluation.evaluate(cases_path=path)


def test_unknown_case_selection_fails_instead_of_empty_success():
    with pytest.raises(ValueError):
        evaluation.evaluate(case_ids={"not-an-authored-case"})


@pytest.mark.parametrize("passed,expected_code", [(True, 0), (False, 1)])
def test_cli_nonzero_when_any_check_fails(tmp_path, monkeypatch, passed, expected_code):
    result = {"passed": passed, "source_stable_during_run": True, "summary": {"failed_cases": int(not passed)}}
    monkeypatch.setattr(evaluation, "evaluate", lambda **kwargs: result)
    path = tmp_path / "result.json"
    assert evaluation.main(["--output", str(path)]) == expected_code
    assert json.loads(path.read_text(encoding="utf-8")) == result


def test_source_changes_during_execution_prevent_success(monkeypatch):
    calls = iter([{"core": "before"}, {"core": "after"}])
    monkeypatch.setattr(evaluation, "source_hashes", lambda: next(calls))
    monkeypatch.setattr(evaluation, "run_case", lambda case, universal: {
        "case_id": case["case_id"], "category": case["category"], "passed": True,
        "observations": {"network_attempts": 0, "transport_attempts": 0}})
    result = evaluation.evaluate(case_ids={"local-default"})
    assert result["source_stable_during_run"] is False
    assert result["passed"] is False
