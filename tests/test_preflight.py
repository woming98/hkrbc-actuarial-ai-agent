"""Readiness checks must be offline, read-only and free of environment values."""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
from pathlib import Path

import pytest

from scripts import preflight


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project_copy(tmp_path):
    root = tmp_path / "project"
    for relative in ("data/documents", "data/portfolios", "reports"):
        shutil.copytree(ROOT / relative, root / relative)
    shutil.copyfile(ROOT / "app.py", root / "app.py")
    return root


def _check(result, name):
    return next(check for check in result["checks"] if check["name"] == name)


def _inventory(root):
    return {str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


def test_ready_preflight_is_offline_without_authentication_model_load_or_filesystem_writes(project_copy, monkeypatch):
    before = _inventory(project_copy)

    def forbidden(*args, **kwargs):
        pytest.fail("Preflight performed a forbidden side effect")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr("urllib.request.OpenerDirector.open", forbidden)
    monkeypatch.setattr("hkrbc_agent.security.AuthService.authenticate", forbidden)
    monkeypatch.setattr("hkrbc_agent.embeddings.LocalSentenceTransformerEncoder.__init__", forbidden)
    monkeypatch.setattr("sqlite3.connect", forbidden)
    result = preflight.run_preflight(project_copy, environment={})
    assert result["status"] == "ready" and result["required_checks_passed"]
    assert result["metadata"]["source_metadata"]["seed_records"] == 13
    assert result["metadata"]["source_metadata"]["supplement_records"] == 12
    assert result["metadata"]["source_metadata"]["source_pdf_bytes_checked"] is False
    assert result["metadata"]["synthetic_samples"]["coupon_settlement_bridge_blocked"]
    assert result["metadata"]["configuration"]["public_demo_password_account_count"] == 3
    assert any("not production authentication" in warning for warning in result["warnings"])
    assert _inventory(project_copy) == before


@pytest.mark.parametrize("relative", ["app.py", "data/documents/regulatory_seed.json", "data/portfolios/closing.csv", "reports/example-actuarial-report.md"])
def test_missing_required_fixture_blocks_readiness(project_copy, relative):
    (project_copy / relative).unlink()
    result = preflight.run_preflight(project_copy, environment={})
    assert result["status"] == "blocked" and not result["required_checks_passed"]
    assert any(check["required"] and not check["passed"] for check in result["checks"])


@pytest.mark.parametrize("corruption", ["seed_bytes", "supplement_text", "register_page", "report_number", "duplicate_no_longer_bad", "coupon_no_longer_crosses"])
def test_corrupted_or_no_longer_meaningful_fixtures_fail(project_copy, corruption):
    if corruption == "seed_bytes":
        path = project_copy / "data/documents/regulatory_seed.json"
        path.write_text(path.read_text() + "\n")
        expected = "source_metadata"
    elif corruption == "supplement_text":
        path = project_copy / "data/documents/verified_supplement.json"
        content = json.loads(path.read_text())
        content[0]["text"] += " Changed paraphrase."
        path.write_text(json.dumps(content))
        expected = "source_metadata"
    elif corruption == "register_page":
        path = project_copy / "data/documents/source_register.json"
        content = json.loads(path.read_text())
        content["section_verification"][0]["pdf_pages"] = [9999]
        path.write_text(json.dumps(content))
        expected = "source_metadata"
    elif corruption == "report_number":
        path = project_copy / "reports/example-actuarial-report.json"
        content = json.loads(path.read_text())
        content["capital_movement"] += 1
        path.write_text(json.dumps(content))
        expected = "example_report"
    elif corruption == "duplicate_no_longer_bad":
        path = project_copy / "data/portfolios/malformed.csv"
        path.write_bytes((project_copy / "data/portfolios/opening.csv").read_bytes())
        expected = "synthetic_samples"
    else:
        path = project_copy / "data/portfolios/coupon_crossing_closing.csv"
        path.write_bytes((project_copy / "data/portfolios/coupon_crossing_opening.csv").read_bytes())
        expected = "synthetic_samples"
    result = preflight.run_preflight(project_copy, environment={})
    assert not _check(result, expected)["passed"]
    assert result["status"] == "blocked"


@pytest.mark.parametrize("environment", [
    {"HKRBC_EXTERNAL_ENABLED": "true"}, {"HKRBC_EXTERNAL_ENABLED": "invalid"},
    {"HKRBC_RETRIEVAL_BACKEND": "unknown"},
    {"HKRBC_LOCAL_MODEL": "secret-model-name", "HKRBC_OLLAMA_URL": "https://sensitive.example/private"},
    {"HKRBC_LOCAL_MODEL": "secret-model-name", "HKRBC_OLLAMA_URL": "http://person:password@127.0.0.1/private"},
    {"HKRBC_RETRIEVAL_BACKEND": "dense"},
    {"HKRBC_RETRIEVAL_BACKEND": "hybrid", "HKRBC_EMBEDDING_MODEL_PATH": "/missing-private-model-location"},
])
def test_offline_misconfiguration_fails_without_echoing_values(project_copy, environment):
    result = preflight.run_preflight(project_copy, environment=environment)
    assert result["status"] == "blocked"
    rendered = json.dumps(result)
    assert "secret-model-name" not in rendered and "sensitive.example" not in rendered
    assert "person:password" not in rendered and "/missing-private-model-location" not in rendered


def test_sensitive_environment_and_schema_error_values_are_never_printed(project_copy):
    canary = "preflight-secret-canary-value"
    environment = {"OPENAI_API_KEY": canary, "HKRBC_ANALYST_PASSWORD": canary,
                   "HKRBC_REVIEWER_PASSWORD": canary, "HKRBC_ADMIN_PASSWORD": canary}
    result = preflight.run_preflight(project_copy, environment=environment)
    assert result["status"] == "ready"
    assert result["metadata"]["configuration"]["external_credentials_present"]
    assert result["metadata"]["configuration"]["public_demo_password_account_count"] == 0
    assert canary not in json.dumps(result)
    path = project_copy / "data/documents/verified_supplement.json"
    content = json.loads(path.read_text())
    content[0]["status"] = canary
    path.write_text(json.dumps(content))
    failed = preflight.run_preflight(project_copy, environment=environment)
    assert not _check(failed, "source_metadata")["passed"]
    assert canary not in json.dumps(failed)


def test_missing_required_package_blocks_readiness(project_copy, monkeypatch):
    actual = preflight._dependency_report()
    actual["streamlit"] = {"installed": False, "version": None}
    monkeypatch.setattr(preflight, "_dependency_report", lambda: actual)
    result = preflight.run_preflight(project_copy, environment={})
    assert not _check(result, "required_packages")["passed"]


def test_optional_invalid_model_is_nonblocking_for_bm25_but_required_for_semantic_modes(project_copy):
    model = project_copy / "runtime/models/all-MiniLM-L6-v2"
    model.mkdir(parents=True)
    (model / "provision_manifest.json").write_text('{"files": {}}')
    lexical = preflight.run_preflight(project_copy, environment={})
    assert lexical["status"] == "ready"
    optional = lexical["metadata"]["optional_local_snapshots"]["all-MiniLM-L6-v2"]
    assert not optional["metadata_ready"] and optional["state"] == "invalid_manifest_or_inventory"
    semantic = preflight.run_preflight(project_copy, environment={"HKRBC_RETRIEVAL_BACKEND": "dense", "HKRBC_EMBEDDING_MODEL_PATH": str(model)})
    assert semantic["status"] == "blocked"
    assert not _check(semantic, "configured_semantic_model_metadata")["passed"]


def test_model_preflight_explicitly_checks_only_manifest_and_sizes_not_weight_bytes(tmp_path, monkeypatch):
    from hkrbc_agent import embeddings

    path = tmp_path / "model"
    path.mkdir()
    weights = path / "model.safetensors"
    weights.write_bytes(b"same-size-current")
    manifest = {"model_id": "synthetic-reviewed-fixture", "revision": "test",
                "files": {"model.safetensors": {"bytes": len(b"same-size-current"), "sha256": hashlib.sha256(b"different-content").hexdigest()}}}
    metadata = json.dumps(manifest)
    (path / "provision_manifest.json").write_text(metadata)
    monkeypatch.setattr(embeddings, "REVIEWED_MODELS", {("synthetic-reviewed-fixture", "test"): {"manifest_sha256": hashlib.sha256(metadata.encode()).hexdigest()}})
    state = preflight._model_state(path)
    assert state["metadata_ready"]
    assert not state["weight_content_hashes_checked"] and not state["model_loaded"]
    weights.write_bytes(b"changed-size")
    assert not preflight._model_state(path)["metadata_ready"]


def test_cli_emits_json_only_and_nonzero_for_missing_required_assets(project_copy, capsys):
    assert preflight.main(["--root", str(project_copy)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ready"
    (project_copy / "app.py").unlink()
    assert preflight.main(["--root", str(project_copy)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
