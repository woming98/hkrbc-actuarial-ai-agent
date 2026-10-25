"""Ranking capabilities and offline semantic boundaries, not benchmark snapshots."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from hkrbc_agent.embeddings import EncoderUnavailable, LocalSentenceTransformerEncoder
from hkrbc_agent import embeddings
from hkrbc_agent.retrieval import Hit, Retriever, evidence_answer, rule_identifiers, tokens
from hkrbc_agent.security import Principal, Role
from hkrbc_agent.store import Document, Store


ADMIN = Principal("admin", Role.ADMIN)
ANALYST = Principal("analyst", Role.ANALYST)


def document(identifier="source", **overrides):
    values = dict(document_id=identifier, version="1.0", title="Capital background", section="Source section",
        url="https://www.ia.org.hk/en/example.html", reviewed_at="2026-10-24", status="verified_baseline",
        text="Capital background evidence.", provenance="Synthetic original test source.", redistribution="Original synthetic fixture.")
    values.update(overrides)
    return Document(**values)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "quality.sqlite3")


@pytest.fixture
def reviewed_model(tmp_path, monkeypatch):
    """Synthetic reviewed inventory; production allowlist remains pinned to two models."""
    def make(*, graph=None, config=None, tokenizer=None):
        graph = embeddings._BASE_GRAPH if graph is None else graph
        payloads = {
            "modules.json": json.dumps(graph).encode(), "model.safetensors": b"synthetic-test-only",
            "config.json": json.dumps(config or {"model_type": "bert", "architectures": ["BertModel"]}).encode(),
            "tokenizer_config.json": json.dumps(tokenizer or {"tokenizer_class": "BertTokenizer"}).encode(),
            "tokenizer.json": b"{}", "sentence_bert_config.json": b'{"max_seq_length":256}',
            "config_sentence_transformers.json": b"{}", "1_Pooling/config.json": b"{}",
        }
        for name, payload in payloads.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        manifest = {"model_id": "synthetic/reviewed", "revision": "test-revision",
            "files": {name: {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()} for name, payload in payloads.items()}}
        def anchor():
            manifest_path = tmp_path / "provision_manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            monkeypatch.setattr(embeddings, "REVIEWED_MODELS", {("synthetic/reviewed", "test-revision"): {
                "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "modules": embeddings._BASE_GRAPH}})
        anchor()
        return tmp_path, manifest, anchor
    return make


def test_tokenizer_has_overlapping_chinese_bigrams_and_financial_concepts():
    terms = tokens("保險公司最低資本額")
    assert {"zh:保險", "zh:險公", "zh:公司"}.issubset(terms)
    assert "mca" in terms and "capital" in terms
    assert {"matching", "adjustment"}.issubset(tokens("matching-adjustment"))


@pytest.mark.parametrize("text", ["rule 5 ( 3 )", "第５（３）條", "第5條第3款", "§5(3)"])
def test_exact_subrule_identifier_survives_notation_variants(text):
    assert "rule:5(3)" in rule_identifiers(text)
    assert "rule:5(1)" not in rule_identifiers(text)


def test_exact_subrule_primary_section_beats_cross_reference_in_body(store):
    first = document("first", section="Part2, rule5(1)", text="Capital base thresholds, subject to rule5(3).")
    third = document("third", section="Part2, rule5(3)", text="The minimum amount is one half of the prescribed amount.")
    store.put_documents(ADMIN, [first, third])
    for query in ("Describe rule5(3)", "原第5條第3款的最低金額"):
        hits = Retriever(store).search(ANALYST, query)
        assert [hit.document.document_id for hit in hits] == ["third"]


def test_absent_precise_rule_does_not_substitute_neighboring_rule(store):
    store.put_document(ADMIN, document(section="rule5(1)"))
    assert Retriever(store).search(ANALYST, "rule99(3) capital requirement") == []


def test_bilingual_domain_aliases_retrieve_english_approval_section(store):
    source = document("catastrophe", title="Natural catastrophe own assessment", text="An own-assessment approach needs IA approval.")
    store.put_document(ADMIN, source)
    hits = Retriever(store).search(ANALYST, "天災採用自行評估要先批准嗎？")
    assert hits[0].document == source
    assert hits[0].retrieval_method == "bm25+mmr"


def test_bm25_rare_section_term_is_not_swamped_by_common_capital_words(store):
    source = document("allocated", title="Allocated capital", section="Statutory fund allocation", text="Allocated minimum amounts apply to statutory funds.")
    spam = document("generic", title="Capital", text="capital valuation " * 100)
    store.put_documents(ADMIN, [spam, source])
    assert Retriever(store).search(ANALYST, "statutory fund allocation")[0].document == source


def test_identical_section_versions_do_not_crowd_out_distinct_evidence(store):
    first = document("same-a", text="Capital qualitative governance evidence.")
    second = document("same-b", text=first.text)
    other = document("other", section="Different section", text="Capital governance and risk evidence.")
    store.put_documents(ADMIN, [first, second, other])
    hits = Retriever(store).search(ANALYST, "capital governance", limit=3)
    assert len(hits) == 2
    assert "other" in {hit.document.document_id for hit in hits}


class RecordingEncoder:
    def __init__(self):
        self.calls = []
    def encode(self, texts):
        self.calls.append(list(texts))
        return np.tile([1.0, 0.0], (len(texts), 1))


@pytest.mark.parametrize("backend", ["dense", "hybrid"])
def test_semantic_encoding_cannot_see_unauthorized_documents_or_unredacted_queries(store, backend):
    store.put_documents(ADMIN, [document("public"), document("private", classification="restricted", text="Capital restricted_canary_ZETA evidence.")])
    encoder = RecordingEncoder()
    retriever = Retriever(store, backend=backend, encoder=encoder)
    retriever.search(ANALYST, "capital alice@example.com")
    assert encoder.calls
    assert "alice@example.com" not in str(encoder.calls)
    assert "restricted_canary_ZETA" not in str(encoder.calls)


def test_semantic_requests_do_not_reuse_private_document_vectors(store):
    store.put_documents(ADMIN, [document("public"), document("private", classification="restricted", text="Capital private_canary_ZETA.")])
    encoder = RecordingEncoder()
    retriever = Retriever(store, backend="hybrid", encoder=encoder)
    retriever.search(ADMIN, "capital")
    assert "private_canary_ZETA" in str(encoder.calls[-1])
    retriever.search(ANALYST, "capital")
    assert "private_canary_ZETA" not in str(encoder.calls[-1])


def test_independent_filter_precedes_semantic_encoder_even_with_defective_store(store, monkeypatch):
    encoder = RecordingEncoder()
    monkeypatch.setattr(store, "visible_documents", lambda principal: [document("private", classification="restricted")])
    assert Retriever(store, backend="dense", encoder=encoder).search(ANALYST, "capital") == []
    assert encoder.calls == []


@pytest.mark.parametrize("backend", ["dense", "hybrid"])
def test_missing_opted_in_semantic_encoder_fails_closed(store, backend):
    with pytest.raises(EncoderUnavailable):
        Retriever(store, backend=backend)


def test_invalid_semantic_vectors_do_not_fallback_to_lexical_results(store):
    store.put_document(ADMIN, document())
    encoder = SimpleNamespace(encode=lambda texts: np.full((len(texts), 2), np.nan))
    with pytest.raises(ValueError, match="invalid vector"):
        Retriever(store, backend="hybrid", encoder=encoder).search(ANALYST, "capital")


def test_env_requires_explicit_backend_and_existing_model(store, monkeypatch):
    monkeypatch.setenv("HKRBC_EMBEDDING_MODEL_PATH", "/nonexistent-local-encoder")
    monkeypatch.delenv("HKRBC_RETRIEVAL_BACKEND", raising=False)
    assert Retriever.from_env(store).backend == "bm25"
    monkeypatch.setenv("HKRBC_RETRIEVAL_BACKEND", "dense")
    with pytest.raises(EncoderUnavailable):
        Retriever.from_env(store)
    monkeypatch.setenv("HKRBC_RETRIEVAL_BACKEND", "automatic-remote")
    with pytest.raises(ValueError, match="Unknown"):
        Retriever.from_env(store)


def test_local_encoder_enforces_offline_safetensors_flags_and_normalizes(reviewed_model, monkeypatch):
    model_path, _, _ = reviewed_model()
    captured = []
    class FakeModel:
        max_seq_length = 256
        def encode(self, texts, **kwargs):
            return np.tile([3.0, 4.0], (len(texts), 1))
    def constructor(*args, **kwargs):
        assert all(os.environ[name] == "1" for name in ("HF_HUB_DISABLE_TELEMETRY", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"))
        captured.append((args, kwargs))
        return FakeModel()
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=constructor))
    encoder = LocalSentenceTransformerEncoder(model_path)
    assert captured[0][1]["local_files_only"] is True
    assert captured[0][1]["trust_remote_code"] is False
    assert captured[0][1]["model_kwargs"]["use_safetensors"] is True
    assert np.allclose(encoder.encode(["synthetic"]), [[.6, .8]])
    assert encoder.metadata["document_vector_cache"] == "none"


def test_model_manifest_tampering_is_rejected_before_import(reviewed_model, monkeypatch):
    model_path, _, _ = reviewed_model()
    weights = model_path / "model.safetensors"
    weights.write_bytes(b"tampered")
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: pytest.fail("Tampered weights reached model loader")))
    with pytest.raises(EncoderUnavailable, match="integrity"):
        LocalSentenceTransformerEncoder(model_path)


@pytest.mark.parametrize("type_name,path", [
    ("malicious.LocalModule", ""),
    ("sentence_transformers.models.Transformer", "../outside"),
    ("sentence_transformers.models.Transformer", "/tmp/outside"),
])
def test_custom_or_escaping_module_graph_is_rejected_before_loader(reviewed_model, monkeypatch, type_name, path):
    graph = [dict(embeddings._BASE_GRAPH[0], type=type_name, path=path), embeddings._BASE_GRAPH[1]]
    model_path, _, _ = reviewed_model(graph=graph)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: pytest.fail("Unreviewed graph reached loader")))
    with pytest.raises(EncoderUnavailable, match="module-graph"):
        LocalSentenceTransformerEncoder(model_path)


@pytest.mark.parametrize("filename", ["custom_module.py", "pytorch_model.bin", "hidden.pkl"])
def test_unmanifested_executable_or_pickle_sidecars_are_rejected(reviewed_model, monkeypatch, filename):
    model_path, _, _ = reviewed_model()
    (model_path / filename).write_bytes(b"must never be loaded")
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: pytest.fail("Unmanifested sidecar reached loader")))
    with pytest.raises(EncoderUnavailable):
        LocalSentenceTransformerEncoder(model_path)


def test_incomplete_manifest_is_not_accepted_as_verified_inventory(reviewed_model, monkeypatch):
    model_path, manifest, anchor = reviewed_model()
    del manifest["files"]["config.json"]
    anchor()
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: pytest.fail("Incomplete manifest reached loader")))
    with pytest.raises(EncoderUnavailable):
        LocalSentenceTransformerEncoder(model_path)


def test_custom_tokenizer_mapping_is_rejected_even_with_valid_local_hashes(reviewed_model, monkeypatch):
    model_path, _, _ = reviewed_model(tokenizer={"tokenizer_class": "BertTokenizer", "auto_map": {"AutoTokenizer": "evil.Tokenizer"}})
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: pytest.fail("Custom tokenizer reached loader")))
    with pytest.raises(EncoderUnavailable):
        LocalSentenceTransformerEncoder(model_path)


def test_model_file_symlink_is_rejected(reviewed_model, tmp_path, monkeypatch):
    model_path, _, _ = reviewed_model()
    weights = model_path / "model.safetensors"
    target = model_path.parent / (tmp_path.name + "-external-weights")
    target.write_bytes(weights.read_bytes())
    weights.unlink()
    weights.symlink_to(target)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: pytest.fail("Symlink reached loader")))
    with pytest.raises(EncoderUnavailable):
        LocalSentenceTransformerEncoder(model_path)


def test_unreviewed_manifest_identity_cannot_self_declare_trust(tmp_path, monkeypatch):
    (tmp_path / "provision_manifest.json").write_text(json.dumps({"model_id": "unreviewed/model", "revision": "fake", "files": {}}))
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=lambda *args, **kwargs: pytest.fail("Unreviewed identity reached loader")))
    with pytest.raises(EncoderUnavailable):
        LocalSentenceTransformerEncoder(tmp_path)


def test_factor_based_approach_question_is_answerable_without_numeric_factor_claim():
    source = document(text="The factor-based natural catastrophe approach is the default and own assessment needs approval.")
    assert evidence_answer("Is a factor-based approach the default?", [Hit(source, 1.0)])["status"] == "evidence_found"


def test_numeric_claim_requires_explicit_narrow_source_coverage():
    source = document(text="The disclosure template names the capital tiers.")
    query = "What is the Tier2 capital limit?"
    assert evidence_answer(query, [Hit(source, 1.0)])["status"] == "insufficient_evidence"
    caps = source.model_copy(update={"claim_tags": ("capital.tier_limits",), "text": "The original rule specifies a numeric Tier2 limit."})
    assert evidence_answer(query, [Hit(caps, 1.0)])["status"] == "evidence_found"
    assert evidence_answer("Which instruments are eligible for Tier2 capital?", [Hit(caps, 1.0)])["status"] == "insufficient_evidence"
    assert evidence_answer("Which tiers appear in capital disclosure tables?", [Hit(source, 1.0)])["status"] == "evidence_found"


def test_announcement_mention_does_not_claim_matching_adjustment_formula():
    source = document(text="The 2026 announcement describes matching adjustment changes.")
    assert evidence_answer("Does the2026 announcement mention matching adjustment changes?", [Hit(source, 1.0)])["status"] == "evidence_found"
    assert evidence_answer("What matching adjustment formula applies?", [Hit(source, 1.0)])["status"] == "insufficient_evidence"


def test_future_claim_coverage_requires_explicit_future_scope():
    source = document(status="future", effective_from="2099-12-31", claim_tags=("capital.correlation_matrix",))
    assert evidence_answer("What is the prescribed correlation matrix?", [Hit(source, 1.0)])["status"] == "insufficient_evidence"
    assert evidence_answer("What is the scheduled future correlation matrix?", [Hit(source, 1.0)])["status"] == "evidence_found"
    assert evidence_answer("What is the current correlation matrix?", [Hit(source, 1.0)])["status"] == "insufficient_evidence"
    assert evidence_answer("What does the 2099 amendment set for the correlation matrix?", [Hit(source, 1.0)])["status"] == "evidence_found"


def test_benchmark_refuses_unmatched_labels_and_marks_unprovisioned_dense_not_run(tmp_path):
    from evaluation.retrieval_eval import evaluate
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps([document().model_dump(mode="json")]))
    cases = tmp_path / "cases.json"
    manifest = {"schema_version": "1.0", "label_corpus_sha256": "wrong", "k": 3,
        "cases": [{"case_id": "one", "query": "capital background", "role": "analyst", "language": "en",
                   "group": "supported", "relevant_document_ids": ["source"], "expected_answerable": True}]}
    cases.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="snapshot"):
        evaluate(cases_path=cases, corpus_path=corpus)
    manifest["label_corpus_sha256"] = hashlib.sha256(corpus.read_bytes()).hexdigest()
    cases.write_text(json.dumps(manifest))
    result = evaluate(cases_path=cases, corpus_path=corpus)
    assert result["methods"]["dense"]["status"] == "not_run"
    assert result["methods"]["hybrid"]["status"] == "not_run"
    assert result["methods"]["bm25"]["summary"]["recall_at_3"] == 1
    assert result["authorization_checks_passed"] is True
