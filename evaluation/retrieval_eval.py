"""Reproducible ranker comparison with hand-labeled section relevance.

No model downloads or inference APIs. Optional dense modes need provisioned local
weights. All methods share the same corpus, ACL, cases, and answer-scope checker.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from hkrbc_agent.embeddings import EncoderUnavailable, LocalSentenceTransformerEncoder
from hkrbc_agent.retrieval import RETRIEVAL_VERSION, Retriever, evidence_answer, section_chunks
from hkrbc_agent.security import CLASSIFICATIONS, Principal, Role
from hkrbc_agent.store import Document, Store


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(rows: list[dict], k: int) -> dict:
    relevant = [row for row in rows if row["relevant_count"]]
    unsupported = [row for row in rows if not row["expected_answerable"]]
    supported = [row for row in rows if row["expected_answerable"]]
    unsupported_by_retrieval = [row for row in rows if not (row["expected_answerable"] and row["retrieved_relevant_section"])]
    grounded_answers = sum(row["answerable"] and row["expected_answerable"] and row["retrieved_relevant_section"] for row in rows)
    answered = sum(row["answerable"] for row in rows)
    return {"cases": len(rows), "relevance_labeled_cases": len(relevant),
            f"recall_at_{k}": statistics.mean(row["recall"] for row in relevant) if relevant else None,
            f"mrr_at_{k}": statistics.mean(row["reciprocal_rank"] for row in relevant) if relevant else None,
            "answerability_accuracy": statistics.mean(row["answerable"] == row["expected_answerable"] for row in rows) if rows else None,
            "answerability_false_positives": sum(row["answerable"] for row in unsupported),
            "unanswerable_cases": len(unsupported),
            "answerability_false_positive_rate": sum(row["answerable"] for row in unsupported) / len(unsupported) if unsupported else None,
            "answerability_false_negatives": sum(not row["answerable"] for row in supported),
            "answered_without_relevant_section": sum(row["answerable"] and not row["retrieved_relevant_section"] for row in supported),
            "evidence_supported_false_positives": sum(row["answerable"] for row in unsupported_by_retrieval),
            "evidence_unsupported_cases": len(unsupported_by_retrieval),
            "evidence_supported_false_positive_rate": sum(row["answerable"] for row in unsupported_by_retrieval) / len(unsupported_by_retrieval) if unsupported_by_retrieval else None,
            "relevant_section_answer_precision": grounded_answers / answered if answered else None,
            "relevant_section_answer_rate": grounded_answers / len(supported) if supported else None,
            "answerable_cases": len(supported),
            "unauthorized_retrievals": sum(len(row["unauthorized_document_ids"]) for row in rows),
            "median_query_ms": statistics.median(row["elapsed_ms"] for row in rows) if rows else None}


def evaluate(*, cases_path: Path, corpus_path: Path, model_path: Path | None = None,
             supplement_path: Path | None = None) -> dict:
    manifest = json.loads(cases_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1.0" or not manifest.get("cases"):
        raise ValueError("Unsupported or empty retrieval case manifest")
    corpus_hash = digest(corpus_path)
    if manifest["label_corpus_sha256"] != corpus_hash:
        raise ValueError("The relevance labels do not match this corpus snapshot")
    supplement_hash = digest(supplement_path) if supplement_path else None
    labels_complete = not supplement_path or manifest.get("label_supplement_sha256") == supplement_hash
    records = json.loads(corpus_path.read_text(encoding="utf-8"))
    if supplement_path:
        records += json.loads(supplement_path.read_text(encoding="utf-8"))
    ids = {record["document_id"] for record in records}
    cases = manifest["cases"]
    if len({case["case_id"] for case in cases}) != len(cases):
        raise ValueError("Case identifiers must be unique")
    for case in cases:
        if set(case["relevant_document_ids"]) - ids:
            raise ValueError("A relevance label names a missing source section")
    k = int(manifest.get("k", 3))
    roles = {"analyst": Role.ANALYST, "reviewer": Role.REVIEWER, "admin": Role.ADMIN}
    result = {"schema_version": "1.0", "generated_at": datetime.now(timezone.utc).isoformat(),
        "retrieval_version": RETRIEVAL_VERSION, "case_manifest_sha256": digest(cases_path),
        "retrieval_source_sha256": digest(ROOT / "src/hkrbc_agent/retrieval.py"),
        "encoder_source_sha256": digest(ROOT / "src/hkrbc_agent/embeddings.py"),
        "corpus_sha256": corpus_hash, "supplement_sha256": supplement_hash,
        "corpus_section_records": len(records), "cases": len(cases), "k": k,
        "label_status": "matched" if labels_complete else "not_scored_supplement_labels_incomplete",
        "answerability_evaluator": "Shared claim-tag, identifier and temporal scope checker for every ranker.",
        "methods": {}, "limitations": manifest.get("limitations", []) + [
            "Developer-authored diagnostic set, not an independently blinded or held-out benchmark.",
            "Recall/MRR are section relevance checks, not answer entailment or current-law validation.",
            "Latency includes request-local document encoding; model load time is separate. No shared vector cache.",
            "Additional sources require relabeling before quality metrics can be interpreted."]}
    encoder = None
    if model_path is not None:
        start = time.perf_counter()
        try:
            encoder = LocalSentenceTransformerEncoder(model_path)
            result["encoder"] = {**encoder.metadata, "load_ms": (time.perf_counter() - start) * 1000,
                                 "language_limit": "Model-manifest language is descriptive; Chinese/actuarial validity requires the measured language-specific results, not a model-name assumption."}
        except EncoderUnavailable as exc:
            result["encoder"] = {"status": "not_run", "reason": str(exc)}
    with tempfile.TemporaryDirectory(prefix="hkrbc-retrieval-eval-") as folder:
        store = Store(Path(folder) / "evidence.sqlite3")
        admin = Principal("benchmark-curator", Role.ADMIN)
        documents = [chunk for record in records for chunk in section_chunks(Document.model_validate(record))]
        store.put_documents(admin, documents)
        for backend in ("hash", "bm25", "dense", "hybrid"):
            if backend in {"dense", "hybrid"} and encoder is None:
                result["methods"][backend] = {"status": "not_run", "reason": "No successfully loaded explicitly provisioned local encoder"}
                continue
            retriever = Retriever(store, backend=backend, encoder=encoder)
            rows = []
            for case in cases:
                principal = Principal(case["role"], roles[case["role"]])
                start = time.perf_counter()
                hits = retriever.search(principal, case["query"], limit=k)
                answer = evidence_answer(case["query"], hits)
                elapsed = (time.perf_counter() - start) * 1000
                def source_id(document_id: str) -> str:
                    if document_id in ids:
                        return document_id
                    for record_id in ids:
                        if document_id.startswith(record_id[:68] + "-p"):
                            return record_id
                    return document_id
                retrieved = list(dict.fromkeys(source_id(hit.document.document_id) for hit in hits))
                expected = set(case["relevant_document_ids"])
                first = next((rank for rank, identifier in enumerate(retrieved, 1) if identifier in expected), None)
                forbidden = set(case.get("forbidden_document_ids", []))
                unauthorized = {source_id(hit.document.document_id) for hit in hits
                    if hit.document.classification not in CLASSIFICATIONS[principal.role] or source_id(hit.document.document_id) in forbidden}
                rows.append({"case_id": case["case_id"], "language": case["language"], "group": case["group"],
                    "role": case["role"], "retrieved_document_ids": retrieved,
                    "retrieved_references": [hit.document.reference for hit in hits],
                    "relevant_document_ids": sorted(expected), "relevant_count": len(expected),
                    "retrieved_relevant_section": bool(expected & set(retrieved)),
                    "recall": len(expected & set(retrieved)) / len(expected) if expected else None,
                    "reciprocal_rank": 1 / first if first else 0.0,
                    "expected_answerable": case["expected_answerable"], "answerable": answer["status"] == "evidence_found",
                    "evidence_scope": answer["evidence_scope"], "unauthorized_document_ids": sorted(unauthorized),
                    "elapsed_ms": round(elapsed, 4)})
            summary = metrics(rows, k) if labels_complete else None
            groups = {name: metrics([row for row in rows if row["group"] == name], k) for name in sorted({row["group"] for row in rows})} if labels_complete else None
            languages = {name: metrics([row for row in rows if row["language"] == name], k) for name in sorted({row["language"] for row in rows})} if labels_complete else None
            result["methods"][backend] = {"status": "measured", "summary": summary, "groups": groups, "languages": languages, "cases": rows}
    result["authorization_checks_passed"] = not any(row["unauthorized_document_ids"] for method in result["methods"].values() for row in method.get("cases", []))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT / "evaluation/retrieval_cases.json")
    parser.add_argument("--corpus", type=Path, default=ROOT / "data/documents/regulatory_seed.json")
    parser.add_argument("--supplement", type=Path)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "runtime/retrieval-evaluation.json")
    args = parser.parse_args()
    result = evaluate(cases_path=args.cases, corpus_path=args.corpus, model_path=args.model_path, supplement_path=args.supplement)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"cases": result["cases"], "label_status": result["label_status"],
        "methods": {name: {"status": row["status"], "summary": row.get("summary")} for name, row in result["methods"].items()}}, indent=2))
    if not result["authorization_checks_passed"]:
        raise SystemExit("Unauthorized retrieval detected; benchmark safety checks failed")


if __name__ == "__main__":
    main()
