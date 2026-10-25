"""SQLite metadata, versioned evidence, audit allowlist, and owned reports."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from .security import CLASSIFICATIONS, PERMISSIONS, Principal, require, is_injection, redact


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    document_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    version: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,80}$")
    title: str = Field(min_length=1, max_length=300)
    section: str = Field(min_length=1, max_length=300)
    url: HttpUrl
    published_at: date | None = None
    reviewed_at: date
    effective_from: date | None = None
    effective_to: date | None = None
    status: Literal["verified_baseline", "current_at_review", "future", "superseded", "demo"]
    classification: Literal["public", "internal", "restricted"] = "public"
    kind: Literal["regulatory", "interpretation", "demo"] = "regulatory"
    text: str = Field(min_length=1, max_length=12000)
    provenance: str = Field(min_length=1, max_length=1500)
    redistribution: str = Field(min_length=1, max_length=1500)
    current_consolidated_verified: bool = False
    source_type: str = Field(default="section_record", min_length=1, max_length=100)
    limitations: str = Field(default="", max_length=2000)
    source_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_page: int | None = Field(default=None, ge=1, le=10000, strict=True)
    source_checked_at: date | None = None
    claim_tags: tuple[str, ...] = Field(default=(), max_length=32)

    @field_validator("claim_tags")
    @classmethod
    def validate_claim_tags(cls, tags: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(tags)) != len(tags) or any(not re.fullmatch(r"[a-z][a-z0-9_.]{0,79}", tag) or redact(tag)[1] for tag in tags):
            raise ValueError("Claim tags must be unique controlled identifiers")
        return tags

    @property
    def reference(self) -> str:
        return f"{self.document_id}@{self.version}"


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                  document_id TEXT, version TEXT, classification TEXT, status TEXT,
                  payload TEXT NOT NULL, checksum TEXT NOT NULL, quarantined INTEGER NOT NULL,
                  PRIMARY KEY(document_id, version));
                CREATE TABLE IF NOT EXISTS audit (
                  sequence INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
                  actor TEXT NOT NULL, role TEXT NOT NULL, event TEXT NOT NULL,
                  details TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reports (
                  report_id TEXT PRIMARY KEY, actor TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS document_retirements (
                  document_id TEXT NOT NULL, version TEXT NOT NULL, retired_at TEXT NOT NULL,
                  replacement_id TEXT, replacement_version TEXT,
                  PRIMARY KEY(document_id, version));
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def put_document(self, principal: Principal, document: Document) -> None:
        self.put_documents(principal, [document])

    def put_documents(self, principal: Principal, documents: list[Document]) -> None:
        """Prevalidate and commit one immutable batch atomically."""
        require(principal, "ingest")
        entries = [(document, *self._document_payload(document)) for document in documents]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for document, payload, checksum, quarantine in entries:
                previous = db.execute("SELECT checksum FROM documents WHERE document_id=? AND version=?",
                                      (document.document_id, document.version)).fetchone()
                if previous and previous["checksum"] != checksum:
                    raise ValueError("A document version is immutable; create a new version")
                db.execute("INSERT OR IGNORE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (document.document_id, document.version, document.classification,
                            document.status, payload, checksum, int(quarantine)))
        for document, _, _, quarantine in entries:
            self.audit(principal, "document_ingested", {"documents": [document.reference],
                       "validation": "quarantined" if quarantine else "passed"})

    @staticmethod
    def _document_payload(document: Document) -> tuple[str, str, bool]:
        safe_metadata = " ".join((document.document_id, document.version, document.text, document.title,
                                  document.section, document.provenance, document.redistribution,
                                  document.source_type, document.limitations))
        # Official URLs contain long numeric publication IDs. Scan their email,
        # credential and query components, without interpreting IDs as card data.
        from urllib.parse import urlparse, unquote
        parsed = urlparse(str(document.url))
        if parsed.username or parsed.password or parsed.query or "@" in unquote(str(document.url)):
            raise ValueError("Source URLs must not contain credentials, email addresses or query data")
        if redact(safe_metadata)[1]:
            raise ValueError("PII or secrets detected; redact before ingestion")
        # Adding optional verification metadata must not rewrite old immutable
        # versions when their newly introduced fields are still unset.
        optional_defaults = {"source_sha256": None, "source_page": None,
                             "source_checked_at": None, "claim_tags": ()}
        payload = document.model_dump_json(exclude={key for key, value in optional_defaults.items()
                                                    if getattr(document, key) == value})
        checksum = hashlib.sha256(payload.encode()).hexdigest()
        quarantine = is_injection(safe_metadata)
        return payload, checksum, quarantine

    def visible_documents(self, principal: Principal, *, include_archived: bool = False) -> list[Document]:
        require(principal, "query")
        classes = CLASSIFICATIONS[principal.role]
        markers = ",".join("?" for _ in classes)
        # SQL authorization BEFORE payload loading / vectorisation.
        with self.connect() as db:
            live = "" if include_archived else " AND NOT EXISTS (SELECT 1 FROM document_retirements r WHERE r.document_id=documents.document_id AND r.version=documents.version)"
            rows = db.execute(f"SELECT payload, checksum FROM documents WHERE classification IN ({markers}) AND quarantined=0" + live,
                              classes).fetchall()
        result = []
        for row in rows:
            if hashlib.sha256(row["payload"].encode()).hexdigest() != row["checksum"]:
                continue
            doc = Document.model_validate_json(row["payload"])
            # A second independent policy check protects return values as well.
            if doc.classification not in classes or is_injection(doc.text):
                continue
            if not include_archived and doc.status == "superseded":
                continue
            result.append(doc)
        return result

    def retire_document(self, principal: Principal, document_id: str, version: str,
                        replacement: tuple[str, str] | None = None) -> None:
        """Retire retrieval eligibility while preserving immutable source bytes."""
        require(principal, "ingest")
        if replacement is not None and (not isinstance(replacement, tuple) or len(replacement) != 2):
            raise ValueError("Replacement must identify one document version")
        for value in (document_id, version, *(replacement or ())):
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value) or redact(value)[1]:
                raise ValueError("Invalid document reference")
        if replacement == (document_id, version):
            raise ValueError("A version cannot replace itself")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM documents WHERE document_id=? AND version=?", (document_id, version)).fetchone() is None:
                raise ValueError("Document version does not exist")
            previous = db.execute("SELECT replacement_id,replacement_version FROM document_retirements WHERE document_id=? AND version=?", (document_id, version)).fetchone()
            expected = replacement or (None, None)
            if previous:
                if tuple(previous) != expected:
                    raise ValueError("A retirement decision is immutable; it already records a different replacement")
                return
            if replacement and db.execute("SELECT 1 FROM documents WHERE document_id=? AND version=? AND quarantined=0", replacement).fetchone() is None:
                raise ValueError("Replacement is missing or quarantined")
            if replacement and db.execute("SELECT 1 FROM documents WHERE document_id=? AND version=? AND status='superseded'", replacement).fetchone():
                raise ValueError("Replacement is explicitly superseded")
            if replacement and db.execute("SELECT 1 FROM document_retirements WHERE document_id=? AND version=?", replacement).fetchone():
                raise ValueError("Replacement is itself retired")
            db.execute("INSERT OR IGNORE INTO document_retirements VALUES (?,?,?,?,?)", (
                document_id, version, datetime.now(timezone.utc).isoformat(),
                replacement[0] if replacement else None, replacement[1] if replacement else None))
        self.audit(principal, "document_retired", {"documents": [f"{document_id}@{version}"] +
                   ([f"{replacement[0]}@{replacement[1]}"] if replacement else []), "validation": "passed"})

    def retirement_rows(self, principal: Principal) -> list[dict]:
        require(principal, "query")
        classes = CLASSIFICATIONS[principal.role]
        markers = ",".join("?" for _ in classes)
        with self.connect() as db:
            rows = db.execute(f"SELECT r.document_id,r.version,r.retired_at,r.replacement_id,r.replacement_version,d2.classification AS replacement_classification FROM document_retirements r JOIN documents d ON d.document_id=r.document_id AND d.version=r.version LEFT JOIN documents d2 ON d2.document_id=r.replacement_id AND d2.version=r.replacement_version WHERE d.classification IN ({markers})", classes).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            if item.pop("replacement_classification") not in classes:
                item["replacement_id"] = item["replacement_version"] = None
            result.append(item)
        return result

    def audit(self, principal: Principal, event: str, details: dict) -> None:
        allowed = {"documents", "tools", "validation", "provider", "report_id", "error_type", "count", "retrieval_method"}
        if set(details) - allowed:
            raise ValueError("Audit metadata not on privacy allowlist")
        events = {"sign_in", "document_ingested", "retrieval", "retrieval_blocked", "calculation",
                  "calculation_failed", "scenario_generation", "scenario_failed", "report_created", "document_retired"}
        statuses = {"passed", "quarantined", "complete", "blocked", "failed", "unknown",
                    "evidence_found", "insufficient_evidence"}
        providers = {"none", "local-extractive", "local-ollama", "approved-external-openai", "deterministic-python"}
        if event not in events:
            raise ValueError("Unknown audit event")
        for key, value in details.items():
            if key == "validation" and value not in statuses:
                raise ValueError("Unknown validation status")
            if key == "provider" and value not in providers:
                raise ValueError("Unknown model provider")
            if key == "retrieval_method" and value not in {"bm25+mmr", "hash-legacy", "dense+mmr", "hybrid+mmr", "none", "unspecified"}:
                raise ValueError("Unknown retrieval method")
            if key in {"documents", "tools"}:
                if not isinstance(value, list) or len(value) > 1000 or any(
                    not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,180}", item)
                    or redact(item)[1] for item in value):
                    raise ValueError("Audit references must be controlled identifiers")
            if key == "error_type" and (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", value) or redact(value)[1]):
                raise ValueError("Invalid error category")
            if key == "count" and (type(value) is not int or not 0 <= value <= 100_000):
                raise ValueError("Invalid audit count")
            if key == "report_id":
                try:
                    uuid.UUID(value)
                except (ValueError, TypeError, AttributeError) as exc:
                    raise ValueError("Invalid audit report ID") from exc
        # All values must be controlled IDs, versions, statuses, or counts, never free text.
        with self.connect() as db:
            db.execute("INSERT INTO audit(timestamp,actor,role,event,details) VALUES(?,?,?,?,?)",
                       (datetime.now(timezone.utc).isoformat(), principal.actor_id,
                        principal.role.value, event, json.dumps(details, ensure_ascii=False)))

    def audit_rows(self, principal: Principal, limit: int = 100) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        with self.connect() as db:
            if "audit_all" in PERMISSIONS[principal.role]:
                rows = db.execute("SELECT * FROM audit ORDER BY sequence DESC LIMIT ?", (limit,)).fetchall()
            else:
                require(principal, "audit_own")
                rows = db.execute("SELECT * FROM audit WHERE actor=? ORDER BY sequence DESC LIMIT ?",
                                  (principal.actor_id, limit)).fetchall()
        return [{**dict(row), "details": json.loads(row["details"])} for row in rows]

    def save_report(self, principal: Principal, payload: dict) -> str:
        require(principal, "report")
        report_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO reports VALUES (?, ?, ?)",
                       (report_id, principal.actor_id, json.dumps(payload, ensure_ascii=False, allow_nan=False)))
        self.audit(principal, "report_created", {"report_id": report_id, "validation": payload.get("status", "unknown")})
        return report_id

    def get_report(self, principal: Principal, report_id: str) -> dict:
        require(principal, "report")
        with self.connect() as db:
            row = db.execute("SELECT * FROM reports WHERE report_id=?", (report_id,)).fetchone()
        from .security import AccessDenied, PERMISSIONS
        if row is None or (row["actor"] != principal.actor_id and "audit_all" not in PERMISSIONS[principal.role]):
            raise AccessDenied("Report unavailable for this session")
        return json.loads(row["payload"])
