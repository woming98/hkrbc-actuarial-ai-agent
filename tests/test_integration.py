"""End-to-end evidence, report and session isolation checks without inference."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from hkrbc_agent.calculations import FUNCTION_VERSION
from hkrbc_agent.reporting import render_report
from hkrbc_agent.routing import ModelRouter, ModelSettings
from hkrbc_agent.security import AccessDenied, DEMO_PASSWORDS
from hkrbc_agent.service import AgentService
from hkrbc_agent.store import Document


PROJECT = Path(__file__).resolve().parents[1]


def has_session_key(app, key):
    """Use public item access without relying on Streamlit's internal storage."""
    try:
        app.session_state[key]
    except KeyError:
        return False
    return True


@pytest.fixture
def service_and_sessions(tmp_path, monkeypatch):
    for name in DEMO_PASSWORDS:
        monkeypatch.delenv(f"HKRBC_{name.upper()}_PASSWORD", raising=False)
    def forbid_transport(*args, **kwargs):
        pytest.fail("Offline integration attempted model transport")
    service = AgentService(tmp_path / "integration.sqlite3",
        router=ModelRouter(ModelSettings(), transport=forbid_transport))
    sessions = {name: service.sign_in(name, password) for name, password in DEMO_PASSWORDS.items()}
    return service, sessions


@pytest.fixture
def sample_inputs():
    return tuple((PROJECT / "data/portfolios" / name).read_bytes() for name in ("opening.csv", "closing.csv"))


def section(document_id, classification="public", **overrides):
    payload = dict(
        document_id=document_id, version="2026-10", title="Dated capital requirement",
        section="Dated capital section", url="https://www.ia.org.hk/en/example.html",
        reviewed_at="2026-10-24", status="verified_baseline", classification=classification,
        text=f"Dated capital requirement {classification} evidence is available for background review.",
        provenance="Original reviewed paraphrase.", redistribution="Original synthetic integration fixture.",
        limitations="Fixture for validating evidence boundaries.",
    )
    payload.update(overrides)
    return Document(**payload).model_dump(mode="json")


def test_offline_service_returns_seed_evidence_and_honest_current_law_abstention(service_and_sessions):
    service, sessions = service_and_sessions
    service.seed(sessions["admin"], PROJECT / "data/documents/regulatory_seed.json")
    historical = service.ask(sessions["analyst"], "When did HK RBC commence?")
    assert historical["provider"] == "local-extractive"
    assert historical["commentary"] is None
    assert historical["status"] == "evidence_found"
    assert any(citation["document_id"] == "HKRBC-COMMENCEMENT" for citation in historical["citations"])
    for citation in historical["citations"]:
        assert citation["reference"] == f"{citation['document_id']}@{citation['version']}"
        assert citation["section"] and citation["reviewed_at"] and citation["provenance"]
        assert citation["classification"] == "public"
    current = service.ask(sessions["analyst"], "What are the current capital requirements?")
    assert current["status"] == "insufficient_evidence"
    assert current["provider"] == "local-extractive"
    assert current["commentary"] is None
    assert "Insufficient verified evidence" in current["answer"]


def test_empty_local_corpus_abstains_and_records_only_metadata(service_and_sessions):
    service, sessions = service_and_sessions
    query = "Uncovered qwertyflorin insurance question"
    result = service.ask(sessions["analyst"], query)
    assert result["status"] == "insufficient_evidence"
    assert result["citations"] == []
    assert result["commentary"] is None
    rows = service.audit(sessions["analyst"])
    assert rows[0]["event"] == "retrieval"
    assert rows[0]["details"]["documents"] == []
    assert query not in json.dumps(rows)


def test_signed_service_roles_are_isolated_across_queries_and_registers(service_and_sessions):
    service, sessions = service_and_sessions
    service.ingest(sessions["admin"], [section(name, name) for name in ("public", "internal", "restricted")])
    expected = {"analyst": {"public"}, "reviewer": {"public", "internal"}, "admin": {"public", "internal", "restricted"}}
    for username, classes in expected.items():
        result = service.ask(sessions[username], "dated capital requirement")
        assert {citation["classification"] for citation in result["citations"]} == classes
        assert {record["classification"] for record in service.documents(sessions[username])} == classes
    analyst_events = service.audit(sessions["analyst"])
    assert {event["actor"] for event in analyst_events} == {"analyst"}
    assert all(event["details"].get("documents") in (None, ["public@2026-10"]) for event in analyst_events)


def test_real_sample_report_persists_recomputed_results_and_versioned_metadata(service_and_sessions, sample_inputs):
    service, sessions = service_and_sessions
    report_id, result = service.create_report(sessions["analyst"], *sample_inputs, declared_synthetic=True)
    assert result["status"] == "complete"
    assert result["validation"]["passed"]
    assert result["function_version"] == FUNCTION_VERSION
    normalized_result = json.loads(json.dumps(result, allow_nan=False))
    assert service.report(sessions["analyst"], report_id) == normalized_result
    assert service.report(sessions["reviewer"], report_id) == normalized_result
    for bundle in (result, result["opening"], result["closing"]):
        assert bundle["function_version"] == FUNCTION_VERSION
        assert all(record["version"] == FUNCTION_VERSION for record in bundle["calculations"])
    rows = service.audit(sessions["analyst"])
    assert rows[0]["event"] == "report_created"
    assert rows[0]["details"] == {"report_id": report_id, "validation": "complete"}
    calculation_event = next(row for row in rows if row["event"] == "calculation")
    assert calculation_event["details"]["tools"] == [f"compare_portfolios@{FUNCTION_VERSION}"]
    assert "SYN-BOND-01" not in json.dumps(rows)
    markdown = render_report(report_id, result)
    assert report_id in markdown and FUNCTION_VERSION in markdown
    assert "No regulatory calibration is asserted" in markdown
    assert "Not a regulatory capital return" in markdown


def test_report_ownership_is_enforced_with_real_sessions(service_and_sessions, sample_inputs):
    service, sessions = service_and_sessions
    report_id, result = service.create_report(sessions["admin"], *sample_inputs, declared_synthetic=True)
    with pytest.raises(AccessDenied):
        service.report(sessions["analyst"], report_id)
    normalized_result = json.loads(json.dumps(result, allow_nan=False))
    assert service.report(sessions["reviewer"], report_id) == normalized_result
    assert service.report(sessions["admin"], report_id) == normalized_result
    with pytest.raises(AccessDenied):
        service.report(sessions["reviewer"], "not-a-report")


def test_invalid_input_never_creates_a_report_or_success_audit(service_and_sessions, sample_inputs):
    service, sessions = service_and_sessions
    malformed = (PROJECT / "data/portfolios/malformed.csv").read_bytes()
    with pytest.raises(ValueError):
        service.create_report(sessions["analyst"], malformed, sample_inputs[1], declared_synthetic=True)
    with service.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0
    rows = service.audit(sessions["analyst"])
    assert rows[0]["event"] == "calculation_failed"
    assert rows[0]["details"]["validation"] == "failed"
    assert not any(row["event"] == "report_created" for row in rows)
    assert not any(row["details"].get("validation") == "complete" for row in rows)


def test_large_reconciled_movement_stays_blocked_in_service_and_saved_report(service_and_sessions):
    service, sessions = service_and_sessions
    header = "asset_id,asset_type,currency,valuation_date,market_value,face_value,coupon_rate,yield_rate,maturity_date,credit_spread_bps\n"
    opening = header + "SYN-EQ,equity,HKD,2025-12-31,1000000,,,,,\n"
    closing = header + "SYN-EQ,equity,HKD,2026-09-30,10000000,,,,,\n"
    report_id, result = service.create_report(sessions["analyst"], opening, closing, declared_synthetic=True)
    assert result["status"] == "blocked"
    assert result["validation"]["passed"] is False
    assert abs(result["unexplained_residual"]) < 0.01
    assert any(check["name"] == "unexpected_movement_review" and not check["passed"] for check in result["validation"]["checks"])
    assert service.report(sessions["analyst"], report_id)["status"] == "blocked"
    assert all(row["details"].get("validation") != "complete" for row in service.audit(sessions["analyst"]))


def test_report_reference_rendering_keeps_exact_source_section_and_version(service_and_sessions, sample_inputs):
    service, sessions = service_and_sessions
    service.ingest(sessions["admin"], [section("background-source")])
    evidence = service.ask(sessions["analyst"], "dated capital requirement")
    report_id, result = service.create_report(sessions["analyst"], *sample_inputs, declared_synthetic=True)
    markdown = render_report(report_id, result, citations=evidence["citations"])
    source = evidence["citations"][0]
    assert source["section"] in markdown
    assert source["version"] in markdown
    assert source["url"] in markdown
    assert result["function_version"] in markdown


@pytest.mark.parametrize("metadata", [
    {"status": "future"},
    {"status": "current_at_review", "effective_from": "2099-12-31"},
    {"status": "current_at_review", "effective_to": "2000-01-01"},
])
def test_future_or_expired_metadata_cannot_establish_current_requirement_even_with_verified_flag(service_and_sessions, metadata):
    service, sessions = service_and_sessions
    record = section("temporal-source", current_consolidated_verified=True, **metadata)
    service.ingest(sessions["admin"], [record])
    result = service.ask(sessions["analyst"], "current dated capital requirement")
    assert result["status"] == "insufficient_evidence"
    assert result["commentary"] is None


def test_ui_invalid_session_clears_prior_identity_results(tmp_path, monkeypatch):
    monkeypatch.setenv("HKRBC_DB_PATH", str(tmp_path / "invalid-session-ui.sqlite3"))
    monkeypatch.setenv("HKRBC_EXTERNAL_ENABLED", "false")
    monkeypatch.delenv("HKRBC_LOCAL_MODEL", raising=False)
    app = AppTest.from_file(str(PROJECT / "app.py"), default_timeout=15).run()
    assert not app.exception
    app.session_state["session_token"] = "forged.Administrator"
    app.session_state["analysis_result"] = {"private_canary": "prior identity result"}
    app.session_state["query_result"] = {"answer": "prior identity evidence"}
    app.session_state["opening_bytes"] = b"prior identity upload"
    app.run()
    assert not app.exception
    assert not has_session_key(app, "session_token")
    assert not has_session_key(app, "analysis_result")
    assert not has_session_key(app, "query_result")
    assert not has_session_key(app, "opening_bytes")
    assert not any(radio.label == "Workspace" for radio in app.radio)
    assert any("Session expired" in warning.value for warning in app.warning)
