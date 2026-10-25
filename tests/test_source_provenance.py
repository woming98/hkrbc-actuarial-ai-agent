"""Provenance consistency and live retrieval regression tests for the supplement.

These checks do not prove legal currency, source authenticity, semantic entailment
or rights to redistribute. Private official PDFs are not needed or distributed.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from hkrbc_agent.routing import ModelRouter, ModelSettings
from hkrbc_agent.security import DEMO_PASSWORDS
from hkrbc_agent.service import AgentService
from hkrbc_agent.store import Document


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data/documents/regulatory_seed.json"
SUPPLEMENT = ROOT / "data/documents/verified_supplement.json"
REGISTER = ROOT / "data/documents/source_register.json"
CHECKED = date(2026, 10, 25)
ORIGINAL_SEED_SHA256 = "b84c377c10c371a5419a94451f8f650b318bf3b3c1116aca9079dc32a293b3ce"
PDF_HASHES = {
    "cap41r-original-ln62-2024": "ecca2bbe8b256ca821836b18343e7e6ae977da1ad6bc448d2e6e31df979180d3",
    "cap41r-amendment-ln58-2026": "e8999c31776b8af3389a9b9107cec1c8c2a30c8c7bcab3e0cca2616d37f31b06",
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_supplement_records_match_registered_downloads_and_inspected_pages():
    register = read_json(REGISTER)
    documents = [Document.model_validate(record) for record in read_json(SUPPLEMENT)]
    sources = {item["source_sha256"]: item for item in register["sources"]
               if item["access_status"] == "downloaded_primary_pdf"}
    checks = {item["document_id"]: item for item in register["section_verification"]}
    assert len(documents) == register["supplement_record_count"] == 12
    assert len({document.reference for document in documents}) == 12
    assert {source["source_id"]: digest for digest, source in sources.items()} == PDF_HASHES
    assert hashlib.sha256(SEED.read_bytes()).hexdigest() == register["original_seed_unchanged_sha256"] == ORIGINAL_SEED_SHA256
    for document in documents:
        source = sources[document.source_sha256]
        check = checks[document.document_id]
        assert str(document.url) == source["requested_url"]
        assert urlparse(str(document.url)).hostname == "www.legco.gov.hk"
        assert source["content_type"] == "application/pdf"
        assert source["http_status"] == 200
        assert type(document.source_page) is int
        assert 1 <= document.source_page <= source["page_count"]
        assert document.source_page in source["inspected_pdf_pages"]
        assert document.source_page in source["visually_checked_pdf_pages"]
        assert document.source_page == check["pdf_pages"][0]
        assert check["source_id"] == source["source_id"]
        assert check["gazette_locator"] in document.section
        assert document.source_checked_at == document.reviewed_at == CHECKED
        assert source["retrieval_date"] == CHECKED.isoformat()
        assert check["paraphrase_sha256"] == hashlib.sha256(document.text.encode()).hexdigest()
        assert len(check["page_text_sha256"]) == 64
        assert document.source_type == "downloaded_primary_pdf_paraphrase"
        assert document.current_consolidated_verified is False
        assert document.limitations
    baselines = [document for document in documents if document.status == "verified_baseline"]
    future = [document for document in documents if document.status == "future"]
    assert len(baselines) == 8 and len(future) == 4
    assert all(document.effective_from is None for document in baselines)
    assert all(document.source_sha256 == PDF_HASHES["cap41r-original-ln62-2024"] for document in baselines)
    assert all(document.effective_from == date(2026, 12, 31) for document in future)
    assert all(document.effective_from > CHECKED for document in future)
    assert all(document.source_sha256 == PDF_HASHES["cap41r-amendment-ln58-2026"] for document in future)


@pytest.fixture
def live_service(tmp_path, monkeypatch):
    monkeypatch.setenv("HKRBC_RETRIEVAL_BACKEND", "bm25")
    for username in DEMO_PASSWORDS:
        monkeypatch.delenv(f"HKRBC_{username.upper()}_PASSWORD", raising=False)

    def no_transport(*args, **kwargs):
        pytest.fail("Source-provenance tests must not contact any model endpoint")

    service = AgentService(tmp_path / "source-queries.sqlite", router=ModelRouter(ModelSettings(), transport=no_transport))
    admin = service.auth.authenticate("admin", DEMO_PASSWORDS["admin"])
    assert service.ingest(admin, read_json(SEED) + read_json(SUPPLEMENT)) == 25
    analyst = service.sign_in("analyst", DEMO_PASSWORDS["analyst"])
    return service, analyst


def assert_copied_evidence(result, document_id):
    """Assert faithful output/metadata transport, not independently re-prove law."""
    expected = next(record for record in read_json(SUPPLEMENT) if record["document_id"] == document_id)
    citation = next(item for item in result["citations"] if item["document_id"] == document_id)
    for field in ("source_sha256", "source_page", "source_checked_at", "section", "version", "status",
                  "effective_from", "current_consolidated_verified", "claim_tags"):
        assert citation[field] == expected[field]
    assert citation["reference"] in result["answer"]
    assert expected["section"] in result["answer"]
    assert expected["text"] in result["answer"]
    assert expected["limitations"] in result["answer"]
    assert result["provider"] == "local-extractive"
    assert result["commentary"] is None
    assert result["evidence_scope"]["all_sources_current_verified"] is False
    assert "not semantic entailment verification" in result["evidence_scope"]["assessment"]
    assert any("do not prove" in item for item in result["limitations"])
    return citation


@pytest.mark.parametrize("query,document_id,claim", [
    ("What were the original rule 7 Limited Tier 1 and Tier 2 caps?", "cap41r-direct-tier-caps", "capital.tier_limits"),
    ("What method does original rule 19 require for TVOG?", "cap41r-direct-tvog-method", "liability.tvog_methodology"),
    ("When do the 2026 Amendment Rules commence?", "cap41r-amend-direct-commencement", "amendments.2026_commencement"),
    ("When will the 2026 Amendment Rules commence?", "cap41r-amend-direct-commencement", "amendments.2026_commencement"),
])
def test_supplement_answers_natural_questions_with_precise_source_metadata(live_service, query, document_id, claim):
    service, token = live_service
    result = service.ask(token, query)
    assert result["status"] == "evidence_found"
    assert result["citations"][0]["document_id"] == document_id
    citation = assert_copied_evidence(result, document_id)
    assert claim in citation["claim_tags"]
    if claim in result["evidence_scope"]["requested_claim_tags"]:
        assert claim in result["evidence_scope"]["covered_claim_tags"]
    if document_id == "cap41r-amend-direct-commencement":
        assert citation["status"] == "future"
        assert citation["effective_from"] == "2026-12-31"
        assert "future" in result["answer"]


def test_original_and_future_matrices_keep_distinct_dates_versions_and_limitations(live_service):
    service, token = live_service
    result = service.ask(token, "Compare the original Schedule 7 Table 2 PCA correlation matrix with the 2026 amendment.")
    assert result["status"] == "evidence_found"
    assert result["evidence_scope"]["requested_claim_tags"] == ["capital.correlation_matrix"]
    old = assert_copied_evidence(result, "cap41r-direct-pca-matrix")
    future = assert_copied_evidence(result, "cap41r-amend-direct-pca-matrix")
    assert old["source_page"] == 238 and future["source_page"] == 34
    assert old["source_sha256"] != future["source_sha256"]
    assert old["status"] == "verified_baseline" and future["status"] == "future"
    assert old["version"] != future["version"]
    assert old["effective_from"] is None and future["effective_from"] == "2026-12-31"
    assert "25%" in old["text"] and "12.5%" in future["text"]


def test_explicit_future_matrix_query_uses_future_scoped_evidence(live_service):
    service, token = live_service
    result = service.ask(token, "What correlation will 2026 amendment rule 14 set for market and general insurance?")
    assert result["status"] == "evidence_found"
    assert result["evidence_scope"]["future_scope_requested"] is True
    assert "capital.correlation_matrix" in result["evidence_scope"]["covered_claim_tags"]
    citation = assert_copied_evidence(result, "cap41r-amend-direct-pca-matrix")
    assert citation["status"] == "future" and citation["effective_from"] == "2026-12-31"


def test_numeric_tier_caps_do_not_establish_instrument_eligibility_or_current_law(live_service):
    service, token = live_service
    result = service.ask(token, "What are the current tier caps?")
    assert result["status"] == "insufficient_evidence"
    assert result["evidence_scope"]["current_law_requested"] is True
    assert "Insufficient verified evidence" in result["answer"]
    assert_copied_evidence(result, "cap41r-direct-tier-caps")
    result = service.ask(token, "Under original rule 7, which capital instruments are eligible for Tier 2?")
    assert result["status"] == "insufficient_evidence"
    assert "capital.tier_instrument_eligibility" in result["evidence_scope"]["missing_claim_tags"]
    assert_copied_evidence(result, "cap41r-direct-tier-caps")


@pytest.fixture
def verifier():
    spec = importlib.util.spec_from_file_location("source_register_verifier_tests", ROOT / "scripts/verify_source_register.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify


@pytest.fixture
def synthetic_register(tmp_path):
    """Tiny invented cache bytes exercise integrity checks without copying a PDF."""
    root = tmp_path / "fixture"
    directory = root / "data/documents"
    directory.mkdir(parents=True)
    content = b"%PDF-1.7\nSynthetic integrity-test bytes; not legislation.\n%%EOF\n"
    digest = hashlib.sha256(content).hexdigest()
    cache = root / "runtime/source-cache/synthetic.pdf"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(content)
    seed = b"[]\n"
    (directory / "regulatory_seed.json").write_bytes(seed)
    document = deepcopy(read_json(SUPPLEMENT)[0])
    document.update(document_id="synthetic-source", title="Synthetic provenance fixture", section="Fixture section",
                    text="Invented test data, not legal evidence.", url="https://example.test/source.pdf",
                    source_sha256=digest, source_page=1)
    (directory / "verified_supplement.json").write_text(json.dumps([document]))
    register = {"original_seed_unchanged_sha256": hashlib.sha256(seed).hexdigest(), "supplement_record_count": 1,
                "sources": [{"access_status": "downloaded_primary_pdf", "requested_url": document["url"],
                             "source_sha256": digest, "inspected_pdf_pages": [1], "retrieval_date": CHECKED.isoformat(),
                             "cache_path": "runtime/source-cache/synthetic.pdf", "byte_count": len(content)}]}
    (directory / "source_register.json").write_text(json.dumps(register))
    return root, cache


def test_verifier_accepts_matching_cache_and_marks_metadata_only_without_it(verifier, synthetic_register):
    root, cache = synthetic_register
    assert verifier(root, require_cache=True)["cached_pdf_hashes_checked"] == 1
    cache.unlink()
    result = verifier(root)
    assert result["cached_pdf_hashes_checked"] == 0
    assert result["scope"] == "metadata consistency"
    with pytest.raises(ValueError, match="private source cache is absent"):
        verifier(root, require_cache=True)


def test_verifier_rejects_changed_cache_bytes(verifier, synthetic_register):
    root, cache = synthetic_register
    original = cache.read_bytes()
    cache.write_bytes(original.replace(b"Synthetic", b"Tampered!"))
    assert cache.stat().st_size == len(original)
    with pytest.raises(ValueError, match="corrupt or differs"):
        verifier(root, require_cache=True)


def test_verifier_rejects_uninspected_page_and_cache_escape(verifier, synthetic_register):
    root, _ = synthetic_register
    path = root / "data/documents/verified_supplement.json"
    records = read_json(path)
    records[0]["source_page"] = 2
    path.write_text(json.dumps(records))
    with pytest.raises(ValueError, match="not in the inspected"):
        verifier(root)
    records[0]["source_page"] = 1
    path.write_text(json.dumps(records))
    path = root / "data/documents/source_register.json"
    register = read_json(path)
    register["sources"][0]["cache_path"] = "../outside.pdf"
    path.write_text(json.dumps(register))
    with pytest.raises(ValueError, match="escaped the ignored research directory"):
        verifier(root)
