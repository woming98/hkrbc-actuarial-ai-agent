"""Application boundary: session checks, fixed tool dispatch, validation and audit."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from .retrieval import Retriever, evidence_answer, section_chunks
from .routing import ModelRouter
from .security import AuthService, PrivacyError, require, redact, sensitive, validate_text, is_injection
from .store import Document, Store


class AgentService:
    def __init__(self, db_path: str | Path, *, router: ModelRouter | None = None) -> None:
        self.auth = AuthService()
        self.store = Store(db_path)
        self.retriever = Retriever.from_env(self.store)
        self.router = router or ModelRouter()

    def sign_in(self, username: str, password: str) -> str:
        token = self.auth.authenticate(username, password)
        self.store.audit(self.auth.resolve(token), "sign_in", {"validation": "passed"})
        return token

    def ingest(self, token: str, records: list[dict[str, Any]]) -> int:
        principal = self.auth.resolve(token)
        require(principal, "ingest")
        if not isinstance(records, list) or len(records) > 100:
            raise ValueError("Ingest a list of at most 100 section records")
        # Validate the entire batch before writing any record.
        documents = [Document.model_validate(record) for record in records]
        if any(is_injection(document.model_dump_json()) for document in documents):
            raise PrivacyError("Document batch contains embedded instructions; ingestion rejected")
        chunks = [chunk for document in documents for chunk in section_chunks(document)]
        self.store.put_documents(principal, chunks)
        return len(chunks)

    def seed(self, token: str, path: Path) -> int:
        require(self.auth.resolve(token), "ingest")
        return self.ingest(token, json.loads(path.read_text(encoding="utf-8")))

    def ask(self, token: str, query: str, *, mode: str = "local", approved: bool = False) -> dict:
        principal = self.auth.resolve(token)
        require(principal, "query")
        query = validate_text(query)
        clean_query, detected = redact(query)
        try:
            # External gate sees the ORIGINAL prompt, so redaction is not approval.
            hits = self.retriever.search(principal, clean_query)
            result = evidence_answer(clean_query, hits)
            commentary, provider = self.router.summarize(principal, query if mode == "external" else clean_query,
                hits if result["status"] == "evidence_found" else [], mode=mode, approved=approved)
            result["commentary"] = commentary
            result["provider"] = provider
            result["pii_redacted"] = bool(detected)
            if commentary:
                result["limitations"].append("Optional model commentary is unverified; regulatory statements are supported only by the attached source paraphrases.")
            self.store.audit(principal, "retrieval", {"documents": [hit.document.reference for hit in hits],
                "provider": provider, "validation": result["status"], "retrieval_method": result.get("retrieval_method", "unspecified")})
            return result
        except Exception as exc:
            self.store.audit(principal, "retrieval_blocked", {"provider": "none", "error_type": type(exc).__name__, "validation": "blocked"})
            raise

    @staticmethod
    def _synthetic_input(data: bytes | str, declared_synthetic: bool) -> bytes | str:
        if declared_synthetic is not True:
            raise PrivacyError("Confirm the upload contains synthetic data only")
        if not isinstance(data, (bytes, str)):
            raise ValueError("Supply CSV bytes or text, not a filesystem path object")
        text = data.decode("utf-8-sig") if isinstance(data, bytes) else data
        if len(text) > 2_000_000:
            raise ValueError("Portfolio exceeds size limit")
        if "," not in text or "\n" not in text:
            raise ValueError("Supply CSV contents; filesystem path inputs are not accepted")
        # Numeric financial fields resemble telephone/card numbers. Scan free
        # text columns, then let the strict numeric/date schema validate the rest.
        import csv
        import io
        numeric_fields = {"market_value", "face_value", "coupon_rate", "yield_rate", "credit_spread_bps"}
        try:
            reader = csv.DictReader(io.StringIO(text), strict=True)
            free_fields = [str(value) for row in reader for key, value in row.items() if key not in numeric_fields]
        except csv.Error as exc:
            raise ValueError("Malformed CSV") from exc
        if any(sensitive(value) for value in free_fields):
            raise PrivacyError("Sensitive content detected in upload; use synthetic data only")
        return data

    def analyse(self, token: str, opening: bytes | str, closing: bytes | str | None = None,
                *, declared_synthetic: bool = False) -> dict:
        principal = self.auth.resolve(token)
        require(principal, "calculate")
        from .portfolio import load_portfolio_csv
        from .calculations import analyse_portfolio, compare_portfolios, FUNCTION_VERSION
        try:
            start = load_portfolio_csv(self._synthetic_input(opening, declared_synthetic))
            if closing is None:
                result = analyse_portfolio(start)
                tool = "analyse_portfolio"
            else:
                end = load_portfolio_csv(self._synthetic_input(closing, declared_synthetic))
                result = compare_portfolios(start, end)
                from .attribution import attribute_movement
                bridge = attribute_movement(start, end)
                from .attribution import FUNCTION_VERSION as BRIDGE_VERSION
                self.store.audit(principal, "calculation", {"tools": ["attribute_movement@" + BRIDGE_VERSION],
                    "validation": bridge["status"], "provider": "deterministic-python"})
                result["factor_bridge"] = bridge
                result["validation"]["checks"].append({"name": "factor_bridge_validation",
                    "passed": bridge["validation"]["passed"], "severity": "error",
                    "details": "Date-first bridge plus exact holdings/yield/spread Shapley; unknown coupon/maturity settlement blocks attribution."})
                result["validation"]["passed"] = all(check["passed"] for check in result["validation"]["checks"])
                result["status"] = "complete" if result["validation"]["passed"] else "blocked"
                result["analysis_version"] = "0.2.0"
                result["analysis_id"] = "analysis-" + hashlib.sha256(json.dumps({
                    "module_calculation_id": result["report_id"], "factor_bridge_id": bridge["report_id"],
                    "status": result["status"], "analysis_version": result["analysis_version"]}, sort_keys=True).encode()).hexdigest()[:16]
                tool = "compare_portfolios"
            self.store.audit(principal, "calculation", {"tools": [tool + "@" + FUNCTION_VERSION],
                "validation": result.get("status", "unknown"), "provider": "deterministic-python"})
            return result
        except Exception as exc:
            self.store.audit(principal, "calculation_failed", {"tools": ["portfolio_validation@" + FUNCTION_VERSION],
                "error_type": type(exc).__name__, "validation": "failed", "provider": "deterministic-python"})
            raise

    def scenarios(self, token: str, data: bytes | str, *, count: int = 100, seed: int = 42,
                  declared_synthetic: bool = False) -> dict:
        principal = self.auth.resolve(token)
        require(principal, "calculate")
        from .portfolio import load_portfolio_csv
        from .calculations import generate_scenarios, FUNCTION_VERSION
        try:
            portfolio = load_portfolio_csv(self._synthetic_input(data, declared_synthetic))
            result = generate_scenarios(portfolio, count=count, seed=seed)
            self.store.audit(principal, "scenario_generation", {"tools": ["generate_scenarios@" + FUNCTION_VERSION],
                "validation": result.get("status", "unknown"), "provider": "deterministic-python", "count": count})
            return result
        except Exception as exc:
            self.store.audit(principal, "scenario_failed", {"tools": ["generate_scenarios@" + FUNCTION_VERSION],
                "error_type": type(exc).__name__, "validation": "failed"})
            raise

    def create_report(self, token: str, opening: bytes | str, closing: bytes | str,
                      *, declared_synthetic: bool = False) -> tuple[str, dict]:
        # Recalculate from validated inputs. Clients cannot submit arbitrary "passed" reports.
        result = self.analyse(token, opening, closing, declared_synthetic=declared_synthetic)
        principal = self.auth.resolve(token)
        context = [hit for hit in self.retriever.search(principal, "capital adequacy PCA MCA")
                   if hit.document.kind == "regulatory"]
        result["source_references"] = [hit.to_dict() for hit in context]
        self.store.audit(principal, "retrieval", {"documents": [hit.document.reference for hit in context],
                         "provider": "local-extractive", "validation": "evidence_found" if context else "insufficient_evidence"})
        report_id = self.store.save_report(principal, result)
        return report_id, result

    def audit(self, token: str) -> list[dict]:
        return self.store.audit_rows(self.auth.resolve(token))

    def documents(self, token: str, *, include_lifecycle: bool = False) -> list[dict]:
        principal = self.auth.resolve(token)
        if not include_lifecycle:
            return [doc.model_dump(mode="json") for doc in self.store.visible_documents(principal, include_archived=True)]
        retired = {(row["document_id"], row["version"]): row for row in self.store.retirement_rows(principal)}
        result = []
        for doc in self.store.visible_documents(principal, include_archived=True):
            row = doc.model_dump(mode="json")
            retirement = retired.get((doc.document_id, doc.version))
            row["retrieval_state"] = "retired" if retirement else ("archived" if doc.status == "superseded" else "eligible")
            row["retirement"] = retirement
            result.append(row)
        return result

    def retire_document(self, token: str, document_id: str, version: str,
                        *, replacement_reference: str | None = None) -> None:
        principal = self.auth.resolve(token)
        require(principal, "ingest")
        replacement = None
        if replacement_reference:
            parts = replacement_reference.split("@")
            if len(parts) != 2:
                raise ValueError("Replacement reference must use document_id@version")
            replacement = (parts[0], parts[1])
        self.store.retire_document(principal, document_id, version, replacement)

    def report(self, token: str, report_id: str) -> dict:
        return self.store.get_report(self.auth.resolve(token), report_id)
