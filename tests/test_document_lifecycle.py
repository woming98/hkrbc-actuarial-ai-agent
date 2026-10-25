"""Curator retirement changes eligibility without rewriting source payloads."""
import hashlib
import json

import pytest

from hkrbc_agent.security import AccessDenied, DEMO_PASSWORDS, Principal, Role
from hkrbc_agent.service import AgentService
from hkrbc_agent.store import Document, Store


def document(version="1.0", classification="public", **extra):
    return Document(document_id="capital-source", version=version, title="Capital source",
        section="Capital adequacy", url="https://www.ia.org.hk/en/example.html",
        reviewed_at="2026-10-25", status="verified_baseline", classification=classification,
        text="Capital adequacy source for version lifecycle testing.",
        provenance="Synthetic source fixture.", redistribution="Original fixture.", **extra)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "lifecycle.sqlite")


ADMIN = Principal("admin", Role.ADMIN)
ANALYST = Principal("analyst", Role.ANALYST)


def test_retirement_preserves_original_payload_checksum_and_archive(store):
    old, new = document(), document("2.0")
    store.put_documents(ADMIN, [old, new])
    with store.connect() as db:
        before = tuple(db.execute("SELECT payload,checksum FROM documents WHERE version='1.0'").fetchone())
    store.retire_document(ADMIN, old.document_id, old.version, (new.document_id, new.version))
    assert [item.version for item in store.visible_documents(ANALYST)] == ["2.0"]
    assert {item.version for item in store.visible_documents(ANALYST, include_archived=True)} == {"1.0", "2.0"}
    with store.connect() as db:
        after = tuple(db.execute("SELECT payload,checksum FROM documents WHERE version='1.0'").fetchone())
    assert before == after
    store.put_document(ADMIN, old)
    assert [item.version for item in store.visible_documents(ANALYST)] == ["2.0"]


def test_retired_content_is_excluded_before_deserialization(store, monkeypatch):
    store.put_documents(ADMIN, [document(), document("2.0")])
    store.retire_document(ADMIN, "capital-source", "1.0")
    original = Document.model_validate_json
    loaded = []
    def spy(payload, *args, **kwargs):
        loaded.append(json.loads(payload)["version"])
        return original(payload, *args, **kwargs)
    monkeypatch.setattr(Document, "model_validate_json", spy)
    store.visible_documents(ANALYST)
    assert loaded == ["2.0"]


def test_unauthorized_retirement_and_missing_replacement_do_not_modify_eligibility(store):
    store.put_document(ADMIN, document())
    with pytest.raises(AccessDenied):
        store.retire_document(ANALYST, "capital-source", "1.0")
    with pytest.raises(ValueError):
        store.retire_document(ADMIN, "capital-source", "1.0", ("missing", "1.0"))
    assert len(store.visible_documents(ANALYST)) == 1
    assert store.retirement_rows(ADMIN) == []


def test_retirement_metadata_does_not_disclose_restricted_replacement(store):
    store.put_documents(ADMIN, [document(), document("2.0", "restricted")])
    store.retire_document(ADMIN, "capital-source", "1.0", ("capital-source", "2.0"))
    assert store.retirement_rows(ANALYST)[0]["replacement_version"] is None
    assert store.retirement_rows(ADMIN)[0]["replacement_version"] == "2.0"


def test_retirement_is_idempotent_and_decision_cannot_silently_change(store):
    store.put_documents(ADMIN, [document(), document("2.0"), document("3.0")])
    store.retire_document(ADMIN, "capital-source", "1.0", ("capital-source", "2.0"))
    store.retire_document(ADMIN, "capital-source", "1.0", ("capital-source", "2.0"))
    with pytest.raises(ValueError, match="immutable"):
        store.retire_document(ADMIN, "capital-source", "1.0", ("capital-source", "3.0"))
    assert len(store.retirement_rows(ADMIN)) == 1
    with pytest.raises(ValueError):
        store.retire_document(ADMIN, "capital-source", "2.0", ("capital-source", "1.0"))


def test_optional_provenance_fields_do_not_break_legacy_immutable_versions(store):
    doc = document()
    fields = {"source_sha256", "source_page", "source_checked_at", "claim_tags"}
    legacy_payload = doc.model_dump_json(exclude=fields)
    checksum = hashlib.sha256(legacy_payload.encode()).hexdigest()
    with store.connect() as db:
        db.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?)",
                   (doc.document_id, doc.version, "public", doc.status, legacy_payload, checksum, 0))
    store.put_document(ADMIN, doc)
    with store.connect() as db:
        assert db.execute("SELECT payload,checksum FROM documents").fetchone()["checksum"] == checksum


def test_verified_source_metadata_round_trips_and_changes_require_new_version(store):
    doc = document(source_sha256="a" * 64, source_page=4, source_checked_at="2026-10-25",
                   claim_tags=("minimum_capital",))
    store.put_document(ADMIN, doc)
    assert store.visible_documents(ANALYST)[0] == doc
    with pytest.raises(ValueError, match="immutable"):
        store.put_document(ADMIN, doc.model_copy(update={"source_page": 5}))


def test_service_retirement_clears_search_but_preserves_register(tmp_path, monkeypatch):
    for name in DEMO_PASSWORDS:
        monkeypatch.delenv(f"HKRBC_{name.upper()}_PASSWORD", raising=False)
    service = AgentService(tmp_path / "service.sqlite")
    admin = service.sign_in("admin", DEMO_PASSWORDS["admin"])
    analyst = service.sign_in("analyst", DEMO_PASSWORDS["analyst"])
    service.ingest(admin, [document().model_dump(mode="json")])
    with pytest.raises(AccessDenied):
        service.retire_document(analyst, "capital-source", "1.0")
    service.retire_document(admin, "capital-source", "1.0")
    assert service.ask(analyst, "capital adequacy")["status"] == "insufficient_evidence"
    assert service.documents(analyst, include_lifecycle=True)[0]["retrieval_state"] == "retired"
    assert any(row["event"] == "document_retired" for row in service.audit(admin))
