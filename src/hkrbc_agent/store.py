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

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

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
        payload = document.model_dump_json()
        checksum = hashlib.sha256(payload.encode()).hexdigest()
        quarantine = is_injection(safe_metadata)
        return payload, checksum, quarantine

    def visible_documents(self, principal: Principal, *, include_archived: bool = False) -> list[Document]:
        require(principal, "query")
        classes = CLASSIFICATIONS[principal.role]
        markers = ",".join("?" for _ in classes)
        # SQL authorization BEFORE payload loading / vectorisation.
        with self.connect() as db:
            rows = db.execute(f"SELECT payload, checksum FROM documents WHERE classification IN ({markers}) AND quarantined=0",
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

    def audit(self, principal: Principal, event: str, details: dict) -> None:
        allowed = {"documents", "tools", "validation", "provider", "report_id", "error_type", "count"}
        if set(details) - allowed:
            raise ValueError("Audit metadata not on privacy allowlist")
        events = {"sign_in", "document_ingested", "retrieval", "retrieval_blocked", "calculation",
                  "calculation_failed", "scenario_generation", "scenario_failed", "report_created"}
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
