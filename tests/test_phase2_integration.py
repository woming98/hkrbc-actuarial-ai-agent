"""Independent signed-service checks for factor bridges and source governance."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from hkrbc_agent.reporting import render_report
from hkrbc_agent.routing import ModelRouter, ModelSettings
from hkrbc_agent.security import AccessDenied, DEMO_PASSWORDS
from hkrbc_agent.service import AgentService
from hkrbc_agent.store import Document


ROOT = Path(__file__).resolve().parents[1]
HEADER = "asset_id,asset_type,currency,valuation_date,market_value,face_value,coupon_rate,yield_rate,maturity_date,credit_spread_bps\n"


def _service(path, monkeypatch):
    for name in DEMO_PASSWORDS:
        monkeypatch.delenv(f"HKRBC_{name.upper()}_PASSWORD", raising=False)

    def no_transport(*args, **kwargs):
        pytest.fail("Phase-two integration must not invoke any model transport")

    service = AgentService(path, router=ModelRouter(ModelSettings(), transport=no_transport))
    sessions = {username: service.sign_in(username, password) for username, password in DEMO_PASSWORDS.items()}
    return service, sessions


@pytest.fixture
def session_service(tmp_path, monkeypatch):
    return _service(tmp_path / "phase2.sqlite", monkeypatch)


def _document(version="1.0", classification="public", **extra):
    return Document(
        document_id="phase2-capital-source", version=version,
        title="Synthetic capital source", section="Synthetic capital adequacy",
        url="https://www.ia.org.hk/en/synthetic-source.html", reviewed_at="2026-10-25",
        status="verified_baseline", classification=classification,
        text="Synthetic capital adequacy evidence for source lifecycle verification.",
        provenance="Original synthetic integration evidence.", redistribution="Original fixture.",
        **extra,
    )


def _sample_csvs():
    return tuple((ROOT / "data" / "portfolios" / name).read_bytes() for name in ("opening.csv", "closing.csv"))


def _raw_document(service, version):
    with service.store.connect() as database:
        return tuple(database.execute("SELECT payload,checksum FROM documents WHERE document_id=? AND version=?",
                                      ("phase2-capital-source", version)).fetchone())


def test_service_preserves_both_distinct_shapley_bridges_and_validates_total(session_service):
    service, sessions = session_service
    result = service.analyse(sessions["analyst"], *_sample_csvs(), declared_synthetic=True)
    factor = result["factor_bridge"]
    assert result["status"] == factor["status"] == "complete"
    assert result["validation"]["passed"] and factor["validation"]["passed"]
    assert set(result["shapley_attribution"]) == {"rate", "credit", "equity"}
    assert set(factor["factor_attribution"]) == {"holdings_and_equity_value", "risk_free_yield", "credit_spread"}
    assert factor["total_movement"] == result["capital_movement"]
    assert factor["date_ageing"] + sum(factor["factor_attribution"].values()) == pytest.approx(result["capital_movement"], abs=.01)
    assert factor["unexplained_residual"] == pytest.approx(0, abs=.01)
    assert len(factor["states"]) == 8 and len(factor["permutations"]) == 6
    bridge_check = next(check for check in result["validation"]["checks"] if check["name"] == "factor_bridge_validation")
    assert bridge_check["passed"]
    calculation_events = [event for event in service.audit(sessions["analyst"]) if event["event"] == "calculation"]
    assert any("attribute_movement@1.0.0" in event["details"]["tools"] for event in calculation_events)


@pytest.mark.parametrize("reason", ["coupon", "maturity", "changed_coupon"])
def test_unsupported_bridge_blocks_entire_service_result_and_saved_report(session_service, reason):
    service, sessions = session_service
    if reason == "maturity":
        opening = HEADER + "SYN-BOND,bond,HKD,2025-01-01,,100000,0.04,0.03,2025-06-30,100\n"
        closing = HEADER + "SYN-CASH,cash,HKD,2025-08-01,104000,,,,,\n"
        failed_check = "cashflow_bridge_supported"
    elif reason == "coupon":
        opening = HEADER + "SYN-BOND,bond,HKD,2025-01-01,,100000,0.04,0.03,2030-06-30,100\n"
        closing = opening.replace("2025-01-01", "2025-08-01")
        failed_check = "cashflow_bridge_supported"
    else:
        opening = HEADER + "SYN-BOND,bond,HKD,2025-01-01,,100000,0.04,0.03,2030-12-31,100\n"
        closing = opening.replace("2025-01-01", "2025-08-01").replace(",0.04,", ",0.05,")
        failed_check = "instrument_identity"
    report_id, result = service.create_report(sessions["analyst"], opening, closing, declared_synthetic=True)
    assert result["status"] == "blocked" and result["validation"]["passed"] is False
    factor = result["factor_bridge"]
    assert factor["status"] == "blocked" and factor["date_ageing"] is None
    assert factor["explained_movement"] is factor["unexplained_residual"] is None
    assert any(check["name"] == failed_check and not check["passed"] for check in factor["validation"]["checks"])
    assert not next(check for check in result["validation"]["checks"] if check["name"] == "factor_bridge_validation")["passed"]
    stored = service.report(sessions["analyst"], report_id)
    assert stored["status"] == stored["factor_bridge"]["status"] == "blocked"
    markdown = render_report(report_id, stored)
    assert "Status: **BLOCKED**" in markdown and "Bridge status: **BLOCKED**" in markdown
    assert "could not be completed" in markdown
    assert "| Date ageing at opening quotes |" not in markdown
    assert all(event["details"].get("validation") != "complete" for event in service.audit(sessions["analyst"]))


def test_report_factor_rows_reconcile_with_a_defensible_display_rounding_tolerance(session_service):
    service, sessions = session_service
    report_id, result = service.create_report(sessions["analyst"], *_sample_csvs(), declared_synthetic=True)
    markdown = render_report(report_id, result)
    section = markdown.split("## Counterfactual factor bridge", 1)[1].split("## Risk-module movement allocation", 1)[0]
    values = {}
    for line in section.splitlines():
        if line.startswith("| ") and "Attributed movement" not in line:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            values[cells[0]] = Decimal(cells[1].replace(",", ""))
    expected_labels = {"Date ageing at opening quotes", "Holdings And Equity Value", "Risk Free Yield", "Credit Spread", "Unexplained factor-bridge residual"}
    assert set(values) == expected_labels
    displayed_total = sum(values.values())
    actual_displayed = Decimal(f"{result['capital_movement']:.2f}")
    # Five independently rounded values and a rounded total can differ by six
    # half-cents; no artificial residual plug is permissible.
    assert abs(displayed_total - actual_displayed) <= Decimal("0.03")
    assert values["Unexplained factor-bridge residual"] == Decimal("0.00")
    assert "not reconstructed transactions or investment returns" in section
    assert "quantities, prices and flows" in section


def test_legacy_database_migrates_without_rewriting_source_bytes_and_requires_versioned_enrichment(tmp_path, monkeypatch):
    legacy = _document()
    added_fields = {"source_sha256", "source_page", "source_checked_at", "claim_tags"}
    legacy_payload = legacy.model_dump_json(exclude=added_fields)
    legacy_checksum = hashlib.sha256(legacy_payload.encode()).hexdigest()
    database_path = tmp_path / "legacy.sqlite"
    # Construct the old documents-only table before Store initializes retirement
    # metadata. This exercises migration, rather than only a fresh schema.
    with sqlite3.connect(database_path) as database:
        database.execute("CREATE TABLE documents (document_id TEXT,version TEXT,classification TEXT,status TEXT,payload TEXT NOT NULL,checksum TEXT NOT NULL,quarantined INTEGER NOT NULL,PRIMARY KEY(document_id,version))")
        database.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?)", (legacy.document_id, legacy.version, "public", legacy.status, legacy_payload, legacy_checksum, 0))
    service, sessions = _service(database_path, monkeypatch)
    assert _raw_document(service, "1.0") == (legacy_payload, legacy_checksum)
    assert service.ingest(sessions["admin"], [json.loads(legacy_payload)]) == 1
    assert _raw_document(service, "1.0") == (legacy_payload, legacy_checksum)
    enriched = legacy.model_dump(mode="json")
    enriched.update(source_sha256="a" * 64, source_page=4, source_checked_at="2026-10-25", claim_tags=["capital.minimum", "framework.scope"])
    with pytest.raises(ValueError, match="immutable"):
        service.ingest(sessions["admin"], [enriched])
    assert _raw_document(service, "1.0") == (legacy_payload, legacy_checksum)
    enriched["version"] = "1.1"
    service.ingest(sessions["admin"], [enriched])
    service.retire_document(sessions["admin"], legacy.document_id, "1.0", replacement_reference=legacy.document_id + "@1.1")
    evidence = service.ask(sessions["analyst"], "synthetic capital adequacy")
    assert {citation["version"] for citation in evidence["citations"]} == {"1.1"}
    citation = evidence["citations"][0]
    assert citation["source_sha256"] == "a" * 64 and citation["source_page"] == 4
    assert citation["claim_tags"] == ["capital.minimum", "framework.scope"]
    register = {item["version"]: item for item in service.documents(sessions["analyst"], include_lifecycle=True)}
    assert register["1.0"]["retrieval_state"] == "retired"
    assert register["1.0"]["source_sha256"] is None
    assert register["1.1"]["retrieval_state"] == "eligible"
    assert _raw_document(service, "1.0") == (legacy_payload, legacy_checksum)


def test_retirement_is_immutable_through_signed_service_and_cannot_be_undone_by_reingest(session_service):
    service, sessions = session_service
    records = [_document(version).model_dump(mode="json") for version in ("1.0", "2.0", "3.0")]
    service.ingest(sessions["admin"], records)
    before = _raw_document(service, "1.0")
    for role in ("analyst", "reviewer"):
        with pytest.raises(AccessDenied):
            service.retire_document(sessions[role], "phase2-capital-source", "1.0")
    assert service.store.retirement_rows(service.auth.resolve(sessions["admin"])) == []
    service.retire_document(sessions["admin"], "phase2-capital-source", "1.0", replacement_reference="phase2-capital-source@2.0")
    first_decision = service.store.retirement_rows(service.auth.resolve(sessions["admin"]))
    service.retire_document(sessions["admin"], "phase2-capital-source", "1.0", replacement_reference="phase2-capital-source@2.0")
    assert service.store.retirement_rows(service.auth.resolve(sessions["admin"])) == first_decision
    with pytest.raises(ValueError, match="immutable"):
        service.retire_document(sessions["admin"], "phase2-capital-source", "1.0", replacement_reference="phase2-capital-source@3.0")
    service.ingest(sessions["admin"], [records[0]])
    assert _raw_document(service, "1.0") == before
    assert all(citation["version"] != "1.0" for citation in service.ask(sessions["analyst"], "synthetic capital adequacy")["citations"])
    register = {item["version"]: item for item in service.documents(sessions["analyst"], include_lifecycle=True)}
    assert register["1.0"]["retrieval_state"] == "retired"


def test_public_retirement_register_does_not_disclose_protected_successor(session_service):
    service, sessions = session_service
    service.ingest(sessions["admin"], [_document().model_dump(mode="json"), _document("2.0", "restricted").model_dump(mode="json")])
    service.retire_document(sessions["admin"], "phase2-capital-source", "1.0", replacement_reference="phase2-capital-source@2.0")
    for role in ("analyst", "reviewer"):
        register = service.documents(sessions[role], include_lifecycle=True)
        assert len(register) == 1
        assert register[0]["retirement"]["replacement_id"] is None
        assert register[0]["retirement"]["replacement_version"] is None
        assert not service.ask(sessions[role], "synthetic capital adequacy")["citations"]
    admin = service.documents(sessions["admin"], include_lifecycle=True)
    retired = next(item for item in admin if item["version"] == "1.0")
    assert retired["retirement"]["replacement_version"] == "2.0"


def test_retry_of_immutable_retirement_is_idempotent_after_successor_is_later_retired(session_service):
    service, sessions = session_service
    service.ingest(sessions["admin"], [_document(version).model_dump(mode="json") for version in ("1.0", "2.0", "3.0")])
    service.retire_document(sessions["admin"], "phase2-capital-source", "1.0", replacement_reference="phase2-capital-source@2.0")
    service.retire_document(sessions["admin"], "phase2-capital-source", "2.0", replacement_reference="phase2-capital-source@3.0")
    principal = service.auth.resolve(sessions["admin"])
    decisions_before = service.store.retirement_rows(principal)
    audit_before = service.audit(sessions["admin"])
    service.retire_document(sessions["admin"], "phase2-capital-source", "1.0", replacement_reference="phase2-capital-source@2.0")
    assert service.store.retirement_rows(principal) == decisions_before
    assert service.audit(sessions["admin"]) == audit_before
    assert {citation["version"] for citation in service.ask(sessions["analyst"], "synthetic capital adequacy")["citations"]} == {"3.0"}
    with pytest.raises(ValueError, match="immutable"):
        service.retire_document(sessions["admin"], "phase2-capital-source", "1.0", replacement_reference="phase2-capital-source@3.0")
    with pytest.raises(AccessDenied):
        service.retire_document(sessions["analyst"], "phase2-capital-source", "1.0", replacement_reference="phase2-capital-source@2.0")
