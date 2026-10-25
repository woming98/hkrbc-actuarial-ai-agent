"""Joint source labels must not be hidden by an any-relevant-section score."""
import hashlib
import json
from pathlib import Path

import pytest

from evaluation.retrieval_eval import evaluate


def bundle(tmp_path):
    corpus = [dict(document_id=name, version="1.0", title="Synthetic evidence",
        section="Synthetic section", url="https://example.invalid/evidence", reviewed_at="2026-10-25",
        classification="public", status="demo", kind="demo", text=text,
        provenance="Invented evaluation fixture", redistribution="Original synthetic fixture")
        for name, text in [("alpha", "Alpha subject has an invented explanatory sentence."),
                           ("beta", "Beta subject has an invented explanatory sentence.")]]
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(json.dumps(corpus))
    manifest = {"schema_version": "1.0", "k": 1,
        "label_corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        "cases": [{"case_id": "joint", "query": "Alpha", "role": "analyst", "language": "en",
                   "group": "supported", "expected_answerable": True,
                   "relevant_document_ids": ["alpha", "beta"], "required_document_ids": ["alpha", "beta"]}]}
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(manifest))
    return path, corpus_path, manifest


def test_partial_source_match_is_reported_even_with_answerable_status(tmp_path):
    cases, corpus, _ = bundle(tmp_path)
    result = evaluate(cases_path=cases, corpus_path=corpus)
    bm25 = result["methods"]["bm25"]
    row, score = bm25["cases"][0], bm25["summary"]
    assert row["answerable"] and row["retrieved_relevant_section"]
    assert not row["all_required_sections_retrieved"]
    assert row["missing_required_document_ids"] == ["beta"]
    assert score["relevant_section_answer_precision"] == 1
    assert score["all_labeled_components_retrieval_rate"] == 0
    assert score["answered_with_missing_labeled_components"] == 1


def test_required_source_cannot_name_an_unlabeled_component(tmp_path):
    path, corpus, manifest = bundle(tmp_path)
    manifest["cases"][0]["required_document_ids"] = ["unreviewed-source"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Required source components"):
        evaluate(cases_path=path, corpus_path=corpus)


def test_frozen_expanded_corpus_negative_requests_abstain():
    root = Path(__file__).resolve().parents[1]
    cases = root / "evaluation/expanded_retrieval_cases.json"
    assert hashlib.sha256(cases.read_bytes()).hexdigest() == "b9b544c45a64d91d00ba739bce26da61ba271774101537cf71970ced8b6aeb34"
    result = evaluate(cases_path=cases, corpus_path=root / "data/documents/regulatory_seed.json",
                      supplement_path=root / "data/documents/verified_supplement.json")
    assert result["label_status"] == "matched"
    assert result["authorization_checks_passed"]
    for method in ("hash", "bm25"):
        score = result["methods"][method]["summary"]
        assert score["unanswerable_cases"] == 28
        assert score["answerability_false_positives"] == 0
