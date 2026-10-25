"""Unsupported detail cannot hide behind a supported announcement request."""
from pathlib import Path

import pytest

from hkrbc_agent.retrieval import Hit, Retriever, evidence_answer, requested_claims, rule_identifiers
from hkrbc_agent.routing import ModelRouter, ModelSettings
from hkrbc_agent.security import DEMO_PASSWORDS
from hkrbc_agent.service import AgentService
from hkrbc_agent.security import Principal, Role
from hkrbc_agent.store import Document, Store


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("query,missing", [
    ("Summarize the 2026 announcement and calculate the matching adjustment formula.", {"matching_adjustment.formula"}),
    ("Calculate the matching-adjustment formula under the 2026 review.", {"matching_adjustment.formula"}),
    ("先概述2026年公告，再計算匹配調整公式。", {"matching_adjustment.formula"}),
    ("Which assets qualify for matching adjustment in the 2026 announcement?", {"matching_adjustment.eligibility"}),
    ("Give matching-adjustment eligibility and its formula alongside the announcement.", {"matching_adjustment.formula", "matching_adjustment.eligibility"}),
    ("What matching adjustment applies in 2026?", {"matching_adjustment.formula"}),
])
def test_unsupported_compound_claim_abstains_before_optional_generation(tmp_path, query, missing):
    def no_transport(*args, **kwargs):
        pytest.fail("Unsupported scope must not invoke optional model generation")

    service = AgentService(tmp_path / "compound.sqlite", router=ModelRouter(
        ModelSettings(local_model="synthetic-never-called"), transport=no_transport))
    admin = service.sign_in("admin", DEMO_PASSWORDS["admin"])
    service.seed(admin, ROOT / "data/documents/regulatory_seed.json")
    analyst = service.sign_in("analyst", DEMO_PASSWORDS["analyst"])
    result = service.ask(analyst, query)
    assert result["status"] == "insufficient_evidence"
    assert missing.issubset(result["evidence_scope"]["missing_claim_tags"])
    assert result["provider"] == "local-extractive"
    assert result["commentary"] is None


def test_announcement_only_question_still_has_supported_background(tmp_path):
    service = AgentService(tmp_path / "mention.sqlite", router=ModelRouter(ModelSettings()))
    admin = service.sign_in("admin", DEMO_PASSWORDS["admin"])
    service.seed(admin, ROOT / "data/documents/regulatory_seed.json")
    analyst = service.sign_in("analyst", DEMO_PASSWORDS["analyst"])
    result = service.ask(analyst, "Does the 2026 announcement mention matching-adjustment changes?")
    assert result["status"] == "evidence_found"
    assert any(item["document_id"] == "HKRBC-2026-AMENDMENTS" for item in result["citations"])


def test_tvog_proxy_and_numerical_calculation_have_distinct_scope():
    assert requested_claims("Describe the original TVOG proxy methodology") == {
        "liability.tvog_methodology", "liability.tvog_proxy"}
    assert requested_claims("Calculate a numerical TVOG value using the proxy") == {
        "liability.tvog_methodology", "liability.tvog_proxy", "liability.tvog_calculation"}
    assert "capital.pca_calculation" in requested_claims("Give the PCA calculation formula")


def test_future_topic_needs_its_own_narrow_coverage():
    assert requested_claims("What are the scheduled 2026 crypto stresses?") == {"capital.crypto_stress"}
    assert requested_claims("What future CCA bounds are scheduled?") == {"capital.equity_cca_bounds"}
    assert requested_claims("Compare the original PCA aggregation matrix and its scheduled replacement.") == {"capital.correlation_matrix"}


@pytest.mark.parametrize("query,expected", [
    ("rule 85A(1)(a)", {"rule:85a(1)(a)"}),
    ("第７（ｂ）條", {"rule:7(b)"}),
    ("rule7(a)-(c)", {"rule:7(a)", "rule:7(b)", "rule:7(c)"}),
    ("rule19(4)–(5)", {"rule:19(4)", "rule:19(5)"}),
    ("rules3–4", {"rule:3", "rule:4"}),
    ("rule5(1) and (3)", {"rule:5(1)", "rule:5(3)"}),
    ("rule5(1) to (3)", {"rule:5(1)", "rule:5(2)", "rule:5(3)"}),
    ("rules5 and99", {"rule:5", "rule:99"}),
    ("rule5(1)(a)(ii)", {"rule:5(1)(a)(ii)"}),
    ("rule1234 and rule5AB", {"rule:1234", "rule:5ab"}),
    ("第5條第1至3款", {"rule:5(1)", "rule:5(2)", "rule:5(3)"}),
])
def test_legal_identifier_preserves_suffixes_and_source_ranges(query, expected):
    assert rule_identifiers(query) == expected


def supplement(identifier):
    import json
    return Document.model_validate(next(row for row in json.loads(
        (ROOT / "data/documents/verified_supplement.json").read_text()) if row["document_id"] == identifier))


def test_an_unseen_letter_rule_does_not_match_its_neighbor(tmp_path):
    store = Store(tmp_path / "letters.sqlite")
    admin, analyst = Principal("admin", Role.ADMIN), Principal("analyst", Role.ANALYST)
    store.put_document(admin, supplement("cap41r-amend-direct-crypto-stress"))
    retriever = Retriever(store)
    assert retriever.search(analyst, "scheduled rule85A(1)(a) crypto stress")
    assert retriever.search(analyst, "scheduled rule85B(1)(a) crypto stress") == []
    assert retriever.search(analyst, "scheduled rule85A(1)(b) crypto stress") == []


def test_abbreviated_extra_clause_cannot_disappear_from_coverage(tmp_path):
    source = supplement("cap41r-direct-application").model_copy(update={
        "document_id": "synthetic-first-clause", "section": "rule5(1)",
        "text": "Synthetic capital method for the first clause only.", "claim_tags": ()})
    store = Store(tmp_path / "abbreviated.sqlite")
    admin, analyst = Principal("admin", Role.ADMIN), Principal("analyst", Role.ANALYST)
    store.put_document(admin, source)
    retriever = Retriever(store)
    for query in ("Explain synthetic capital rule5(1) and (3).", "Explain rule5(1) to (3).", "Explain synthetic capital rules5 and99."):
        result = evidence_answer(query, retriever.search(analyst, query))
        assert result["status"] == "insufficient_evidence"
        assert result["evidence_scope"]["missing_rule_identifiers"]


def test_historical_and_scheduled_comparison_needs_both_relevant_versions():
    old = supplement("cap41r-direct-pca-matrix")
    future = supplement("cap41r-amend-direct-pca-matrix")
    commencement = supplement("cap41r-amend-direct-commencement")
    query = "Compare the original 2024 correlation matrix and the scheduled 2026 amendment."
    partial = evidence_answer(query, [Hit(future, 1), Hit(commencement, .5)])
    assert partial["status"] == "insufficient_evidence"
    assert partial["evidence_scope"]["missing_evidence_versions"] == ["historical_baseline"]
    assert evidence_answer(query, [Hit(old, 1), Hit(future, 1)])["status"] == "evidence_found"


def test_chinese_years_and_embedded_acronyms_preserve_scope():
    future = supplement("cap41r-amend-direct-crypto-stress")
    result = evidence_answer("2026年將生效的加密資產壓力是多少？", [Hit(future, 1)])
    assert result["status"] == "evidence_found"
    assert result["evidence_scope"]["future_scope_requested"]
    assert "liability.tvog_calculation" in requested_claims("原有TVOG模型需要哪些校準參數？")
    assert "capital.tier_instrument_eligibility" in requested_claims("二級的上限和合格工具條件是什麼？")


def test_current_estimate_term_does_not_hide_real_current_law_demand():
    source = supplement("cap41r-direct-tvog-proxy")
    technical = evidence_answer("Explain the original TVOG deterministic current estimate proxy.", [Hit(source, 1)])
    assert technical["status"] == "evidence_found"
    assert not technical["evidence_scope"]["current_law_requested"]
    current = evidence_answer("Explain the current rule for the TVOG deterministic current estimate proxy.", [Hit(source, 1)])
    assert current["status"] == "insufficient_evidence"
    assert current["evidence_scope"]["current_law_requested"]
