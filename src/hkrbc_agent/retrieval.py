"""Section-preserving retrieval with deterministic local feature-hash embeddings.

This exact NumPy index intentionally avoids model downloads. It is lexical, not a
trained semantic embedding model. Authorization occurs before any embedding.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from .security import CLASSIFICATIONS, Principal, is_injection, redact, validate_text
from .store import Document, Store

STOPWORDS = frozenset("the a an is are was were what which when how of for in and to with on hk hong kong insurance please does do me about under requirement requirements".split())
ALIASES = {
    "實施": "commencement", "生效": "commencement", "何時": "commencement",
    "資本": "capital", "風險": "risk", "監管": "regulatory", "支柱": "pillar",
    "披露": "disclosure", "修訂": "amendment", "規則": "rules", "估值": "valuation",
    "自然災害": "catastrophe", "三級": "tier", "資源": "resources",
    "開始": "commencement", "有效": "commencement", "當前": "current",
    "effective": "commencement", "introduced": "commencement", "begin": "commencement",
    "start": "commencement", "implemented": "commencement", "implementation": "commencement",
    "pillars": "pillar", "amendments": "amendment", "tiers": "tier",
}


def tokens(text: str) -> list[str]:
    text = text.lower()
    expanded = text + " " + " ".join(value for key, value in ALIASES.items() if key in text)
    terms = re.findall(r"[a-z]+|\d{4}|[\u4e00-\u9fff]{2,}", expanded)
    return [ALIASES.get(term, term) for term in terms if term not in STOPWORDS]


def embed(text: str, dimensions: int = 512) -> np.ndarray:
    vector = np.zeros(dimensions, dtype=np.float64)
    for term in tokens(text):
        digest = hashlib.blake2b(term.encode(), digest_size=8).digest()
        index = int.from_bytes(digest, "big") % dimensions
        vector[index] += 1.0
    norm = np.linalg.norm(vector)
    return vector / norm if norm else vector


def section_chunks(document: Document, max_chars: int = 1200) -> list[Document]:
    """Input is one named section; never merge text across named sections."""
    if max_chars < 100:
        raise ValueError("Chunk size must be at least 100")
    if len(document.text) <= max_chars:
        return [document]
    pieces: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", document.text):
        # Long paragraphs split on sentence boundaries, then bounded text slices.
        for sentence in re.split(r"(?<=[.!?。])\s+", paragraph):
            for offset in range(0, len(sentence), max_chars):
                part = sentence[offset:offset + max_chars]
                if current and len(current) + len(part) + 1 > max_chars:
                    pieces.append(current)
                    current = ""
                current = (current + " " + part).strip()
    if current:
        pieces.append(current)
    return [document.model_copy(update={"document_id": f"{document.document_id[:68]}-p{index+1}", "text": text})
            for index, text in enumerate(pieces)]


@dataclass(frozen=True)
class Hit:
    document: Document
    score: float

    def to_dict(self) -> dict:
        return {"reference": self.document.reference, "score": round(self.score, 6),
                **self.document.model_dump(mode="json")}


class Retriever:
    def __init__(self, store: Store) -> None:
        self.store = store

    def search(self, principal: Principal, query: str, limit: int = 3) -> list[Hit]:
        query = validate_text(query)
        safe_query, _ = redact(query)
        if is_injection(safe_query):
            return []
        documents = self.store.visible_documents(principal)
        query_terms = set(tokens(safe_query))
        if not query_terms:
            return []
        query_vector = embed(safe_query)
        hits = []
        for document in documents:
            content = document.title + " " + document.section + " " + document.text
            # A lexical guard avoids hash collisions becoming false evidence.
            overlap = query_terms & set(tokens(document.text + " " + document.section))
            score = float(np.dot(query_vector, embed(content)))
            if overlap and math.isfinite(score) and score >= 0.12:
                hits.append(Hit(document, score))
        hits.sort(key=lambda hit: (-hit.score, hit.document.reference))
        # Post-retrieval policy check, independent of index eligibility.
        return [hit for hit in hits if hit.document.classification in CLASSIFICATIONS[principal.role]][:max(1, min(limit, 10))]


def evidence_answer(query: str, hits: list[Hit]) -> dict:
    if not hits:
        return {"status": "insufficient_evidence", "answer": "Insufficient verified evidence in the authorized local corpus. No regulatory conclusion can be made; consult the current official rules and a qualified reviewer.",
                "citations": [], "provider": "local-extractive", "commentary": None,
                "limitations": ["The curated corpus does not cover the full HK RBC framework."]}
    lines = []
    for hit in hits:
        document = hit.document
        label = "Regulatory source paraphrase" if document.kind == "regulatory" else "Internal interpretation / demonstration"
        lines.append(f"{label} [{document.reference}] — {document.status}; section: {document.section}: {document.text}\nSource limitation: {document.limitations or 'See source metadata.'}")
    current_question = bool(re.search(r"\b(current|currently|today|latest|compliant|compliance)\b|現行|當前|最新|合規", query, re.I))
    calibration_question = bool(re.search(r"\b(correlation|calibrat\w*|factor|factors|matching adjustment|calculate.*PCA)\b|相關矩陣|壓力因子|計算.*資本", query, re.I))
    today = datetime.now(ZoneInfo("Asia/Hong_Kong")).date()
    def current_eligible(document: Document) -> bool:
        return (document.current_consolidated_verified and document.kind == "regulatory"
                and document.status not in {"future", "superseded", "demo"}
                and (document.effective_from is None or document.effective_from <= today)
                and (document.effective_to is None or today <= document.effective_to)
                and document.reviewed_at <= today)
    insufficient = (current_question and not all(current_eligible(hit.document) for hit in hits)) or calibration_question
    prefix = "Insufficient verified evidence to establish the requested current requirement or regulatory calibration. The following historical/background sources may assist a reviewer:\n\n" if insufficient else ""
    return {"status": "insufficient_evidence" if insufficient else "evidence_found", "answer": prefix + "\n\n".join(lines),
            "citations": [hit.to_dict() for hit in hits], "provider": "local-extractive", "commentary": None,
            "limitations": ["Retrieved evidence is not a completeness determination or legal advice.",
                            "Dates, sections and versions shown below apply to each source. Review the latest consolidated law before reliance.",
                            "Paraphrases are stored; no generated quotation is presented as law."]}
