"""Tiny mocked HTTP downloads verify publication; no model files are fetched."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from urllib.request import Request

import pytest

from scripts import provision_embedding_model as provisioner


PAYLOADS = {
    "config.json": b'{"model_type":"bert"}',
    "modules.json": b'[]',
    "tokenizer.json": b'{}',
    "model.safetensors": b"synthetic-not-a-real-model",
    "1_Pooling/config.json": b'{}',
}


def _mock_http(monkeypatch, *, model_id=provisioner.MODEL_ID, revision=None, license="apache-2.0", fail_file=None):
    requests = []
    metadata = {
        "sha": revision or provisioner.REVIEWED_REVISIONS[model_id],
        "cardData": {"license": license},
        "siblings": [{"rfilename": name} for name in PAYLOADS] + [{"rfilename": "unapproved.py"}],
    }

    def open_mock(request, *, timeout):
        requests.append(request.full_url)
        if "/api/models/" in request.full_url:
            return io.BytesIO(json.dumps(metadata).encode())
        revision_token = "/resolve/" + provisioner.REVIEWED_REVISIONS[model_id] + "/"
        assert revision_token in request.full_url
        name = request.full_url.split(revision_token, 1)[1]
        if name == fail_file:
            raise OSError("Synthetic interrupted download")
        return io.BytesIO(PAYLOADS[name])

    monkeypatch.setattr(provisioner, "_open_https", open_mock)
    return requests


@pytest.mark.parametrize("model_id", list(provisioner.MODELS.values()))
def test_pinned_snapshot_is_staged_and_manifest_format_remains_compatible(tmp_path, monkeypatch, model_id):
    requests = _mock_http(monkeypatch, model_id=model_id)
    destination = tmp_path / "model"
    publish = provisioner._publish

    def inspect_staged(source, target):
        assert source.parent == target.parent
        assert not target.exists()
        assert (source / "provision_manifest.json").is_file()
        assert not list(source.rglob("*.part"))
        assert {str(path.relative_to(source)) for path in source.rglob("*") if path.is_file()} == set(PAYLOADS) | {"provision_manifest.json"}
        return publish(source, target)

    monkeypatch.setattr(provisioner, "_publish", inspect_staged)
    result = provisioner.provision(destination, model_id)
    assert requests[0] == f"https://huggingface.co/api/models/{model_id}/revision/{provisioner.REVIEWED_REVISIONS[model_id]}"
    assert all("unapproved.py" not in url for url in requests)
    assert result == {
        "model_id": model_id,
        "revision": provisioner.REVIEWED_REVISIONS[model_id],
        "license": "apache-2.0",
        "language": "English" if model_id == provisioner.MODEL_ID else "Multilingual (model card: 50 languages)",
        "dimensions": 384,
        "files": {name: {"bytes": len(PAYLOADS[name]), "sha256": hashlib.sha256(PAYLOADS[name]).hexdigest()} for name in sorted(PAYLOADS)},
        "source": f"https://huggingface.co/{model_id}",
        "limitations": ("English encoder; not a validated Chinese or actuarial domain model. Model-card wordpiece truncation applies."
                        if model_id == provisioner.MODEL_ID else
                        "General-purpose pretrained encoder, not a validated actuarial domain model. Model-card wordpiece truncation applies."),
    }
    assert (destination / "provision_manifest.json").read_text() == json.dumps(result, indent=2) + "\n"
    assert list(result) == ["model_id", "revision", "license", "language", "dimensions", "files", "source", "limitations"]
    for name, contents in PAYLOADS.items():
        assert (destination / name).read_bytes() == contents
    assert not list(tmp_path.glob(".model.staging-*"))


@pytest.mark.parametrize("existing", ["empty_directory", "nonempty_directory", "file", "dangling_symlink"])
def test_existing_destination_is_rejected_before_any_network(tmp_path, monkeypatch, existing):
    destination = tmp_path / "existing"
    if existing in ("empty_directory", "nonempty_directory"):
        destination.mkdir()
        if existing == "nonempty_directory":
            (destination / "keep.txt").write_text("preserve")
    elif existing == "file":
        destination.write_text("preserve")
    else:
        destination.symlink_to(tmp_path / "missing-target")
    monkeypatch.setattr(provisioner, "_open_https", lambda *args, **kwargs: pytest.fail("Existing destination triggered network"))
    with pytest.raises(FileExistsError, match="already exists"):
        provisioner.provision(destination)
    assert destination.exists() or destination.is_symlink()
    if existing == "nonempty_directory":
        assert (destination / "keep.txt").read_text() == "preserve"


@pytest.mark.parametrize("metadata_problem", ["revision", "license", "oversized", "missing_required"])
def test_unreviewed_or_invalid_metadata_cannot_publish(tmp_path, monkeypatch, metadata_problem):
    metadata = {"sha": provisioner.REVIEWED_REVISIONS[provisioner.MODEL_ID], "cardData": {"license": "apache-2.0"},
                "siblings": [{"rfilename": name} for name in PAYLOADS]}
    if metadata_problem == "revision":
        metadata["sha"] = "f" * 40
    elif metadata_problem == "license":
        metadata["cardData"]["license"] = "unreviewed"
    elif metadata_problem == "oversized":
        monkeypatch.setattr(provisioner, "MAX_METADATA_BYTES", 10)
    else:
        metadata["siblings"] = [{"rfilename": "README.md"}]
    monkeypatch.setattr(provisioner, "_open_https", lambda *args, **kwargs: io.BytesIO(json.dumps(metadata).encode()))
    destination = tmp_path / "unpublished"
    with pytest.raises(ValueError):
        provisioner.provision(destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".unpublished.staging-*"))


def test_unknown_repository_never_reaches_network(tmp_path, monkeypatch):
    monkeypatch.setattr(provisioner, "_open_https", lambda *args, **kwargs: pytest.fail("Unapproved model triggered network"))
    with pytest.raises(ValueError, match="allowlisted"):
        provisioner.provision(tmp_path / "bad", "unapproved/model")


@pytest.mark.parametrize("failure", ["interrupted", "oversized_file"])
def test_download_failure_removes_staging_and_never_exposes_partial_model(tmp_path, monkeypatch, failure):
    _mock_http(monkeypatch, fail_file="model.safetensors" if failure == "interrupted" else None)
    if failure == "oversized_file":
        monkeypatch.setattr(provisioner, "MAX_FILE_BYTES", 3)
    destination = tmp_path / "model"
    with pytest.raises((OSError, ValueError)):
        provisioner.provision(destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".model.staging-*"))


def test_native_atomic_publication_cannot_replace_a_racing_empty_directory(tmp_path, monkeypatch):
    _mock_http(monkeypatch)
    native = provisioner._rename_no_replace
    destination = tmp_path / "model"

    def racing_creator(source, target):
        # A plain POSIX os.rename would silently replace this empty directory.
        target.mkdir()
        native(source, target)

    monkeypatch.setattr(provisioner, "_rename_no_replace", racing_creator)
    with pytest.raises(OSError):
        provisioner.provision(destination)
    assert destination.is_dir() and list(destination.iterdir()) == []
    assert not list(tmp_path.glob(".model.staging-*"))


@pytest.mark.parametrize("target", [
    "http://huggingface.co/model", "https://example.org/model", "https://huggingface.co.evil.example/model",
    "https://evil.example.huggingface.co.evil.example/model", "https://huggingface.co:444/model",
    "https://user:secret@huggingface.co/model", "file:///tmp/model", "https://127.0.0.1/model",
])
def test_redirects_reject_downgrades_credentials_and_other_hosts(target):
    handler = provisioner.HTTPSOnlyHubRedirects()
    with pytest.raises(ValueError, match="HTTPS"):
        handler.redirect_request(Request("https://huggingface.co/start"), None, 302, "Found", {}, target)


@pytest.mark.parametrize("target", [
    "https://huggingface.co/model", "https://cdn-lfs.huggingface.co/model", "https://hf.co/model",
    "https://cas-bridge.xethub.hf.co/model", "https://hf.co:443/model", "/relative-model",
])
def test_only_https_hub_hosts_and_relative_hub_redirects_are_allowed(target):
    handler = provisioner.HTTPSOnlyHubRedirects()
    redirected = handler.redirect_request(Request("https://huggingface.co/start"), None, 302, "Found", {}, target)
    assert redirected.full_url.startswith("https://")


def test_initial_unapproved_url_is_rejected_before_opener_construction(monkeypatch):
    monkeypatch.setattr(provisioner, "build_opener", lambda *args, **kwargs: pytest.fail("Disallowed URL reached opener"))
    with pytest.raises(ValueError, match="HTTPS"):
        provisioner._open_https(Request("https://example.org/model"), timeout=30)
