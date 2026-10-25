#!/usr/bin/env python3
"""Validate distributed provenance, and optionally check existing private cache.

This script never downloads, republishes or infers currency of legislation.
Hashes identify bytes; they do not prove source authenticity or legal accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from hkrbc_agent.store import Document


def verify(root: Path, *, require_cache: bool = False) -> dict:
    register = json.loads((root / "data/documents/source_register.json").read_text())
    seed = (root / "data/documents/regulatory_seed.json").read_bytes()
    if hashlib.sha256(seed).hexdigest() != register["original_seed_unchanged_sha256"]:
        raise ValueError("Original seed no longer matches its immutable provenance record")
    records = [Document.model_validate(record) for record in json.loads((root / "data/documents/verified_supplement.json").read_text())]
    if len(records) != register["supplement_record_count"] or len({doc.reference for doc in records}) != len(records):
        raise ValueError("Supplement count or unique versions do not match the register")
    sources = {item["source_sha256"]: item for item in register["sources"] if item.get("source_sha256") and item["access_status"] == "downloaded_primary_pdf"}
    cached = 0
    for document in records:
        source = sources.get(document.source_sha256)
        if source is None or str(document.url) != source["requested_url"]:
            raise ValueError("Supplement does not reference an actually downloaded registered PDF")
        if not document.source_page or document.source_page not in source["inspected_pdf_pages"]:
            raise ValueError("Supplement page was not in the inspected source-page register")
        if document.current_consolidated_verified:
            raise ValueError("This register does not establish current consolidated law")
        if document.source_checked_at.isoformat() != source["retrieval_date"]:
            raise ValueError("Source verification date mismatch")
    for source in sources.values():
        path = (root / source["cache_path"]).resolve()
        expected_cache = (root / "runtime/source-cache").resolve()
        if not path.is_relative_to(expected_cache):
            raise ValueError("Source cache path escaped the ignored research directory")
        if path.exists():
            content = path.read_bytes()
            if not content.startswith(b"%PDF-") or len(content) != source["byte_count"] or hashlib.sha256(content).hexdigest() != source["source_sha256"]:
                raise ValueError("Cached PDF is corrupt or differs from the inspected source")
            cached += 1
        elif require_cache:
            raise ValueError("Requested private source cache is absent; metadata alone cannot verify its bytes")
    return {"supplement_records": len(records), "registered_pdf_sources": len(sources), "cached_pdf_hashes_checked": cached,
            "cache_required": require_cache, "current_consolidated_verified": False,
            "scope": "metadata consistency" if not cached else "metadata consistency and available cached-file byte integrity"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-cache", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(ROOT, require_cache=args.require_cache), indent=2))


if __name__ == "__main__":
    main()
