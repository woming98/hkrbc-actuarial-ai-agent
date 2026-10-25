"""Offline encoder for two reviewed, pinned local safetensors snapshots.

No downloads, arbitrary model modules, remote code, or document-vector persistence.
The manifest pins below anchor the reviewed local inventory, not a publisher's
signature. Trusted host packages/operators remain outside this threat boundary.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Protocol, Sequence

import numpy as np


class EncoderUnavailable(ValueError):
    """A requested semantic encoder cannot be validated or loaded offline."""


class Encoder(Protocol):
    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


_BASE_GRAPH = [
    {"idx": 0, "name": "0", "path": "", "type": "sentence_transformers.models.Transformer"},
    {"idx": 1, "name": "1", "path": "1_Pooling", "type": "sentence_transformers.models.Pooling"},
]
REVIEWED_MODELS = {
    ("sentence-transformers/all-MiniLM-L6-v2", "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"): {
        "manifest_sha256": "41a2225d194e4a3593bec0dfdb05a1665338af6bb785babee45d9b1a8226e6c8",
        "modules": [*_BASE_GRAPH, {"idx": 2, "name": "2", "path": "2_Normalize", "type": "sentence_transformers.models.Normalize"}],
    },
    ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"): {
        "manifest_sha256": "cbc095bff2e8e001896def29f391b420956c63b426b51f7b413073616696a3bf",
        "modules": _BASE_GRAPH,
    },
}
_CRITICAL_FILES = {"modules.json", "model.safetensors", "config.json", "sentence_bert_config.json",
                   "config_sentence_transformers.json", "tokenizer.json", "tokenizer_config.json", "1_Pooling/config.json"}


def _read_json(path: Path):
    if path.stat().st_size > 10_000_000:
        raise ValueError("Configuration exceeds the reviewed size bound")
    return json.loads(path.read_text(encoding="utf-8"))


def _unsafe_config(value) -> bool:
    if isinstance(value, dict):
        return any(key in {"auto_map", "custom_pipelines", "trust_remote_code"} or _unsafe_config(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_unsafe_config(item) for item in value)
    return False


def _validate_directory(path: Path) -> tuple[dict, str]:
    """Validate graph, paths and authenticated inventory BEFORE model imports.

    SentenceTransformers can import custom local modules even with
    trust_remote_code=False. That flag alone is therefore insufficient.
    """
    try:
        manifest_path = path / "provision_manifest.json"
        if not path.is_dir() or not manifest_path.is_file() or manifest_path.is_symlink():
            raise ValueError("Reviewed provision manifest is required")
        manifest = _read_json(manifest_path)
        reviewed = REVIEWED_MODELS.get((manifest.get("model_id"), manifest.get("revision")))
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if not reviewed or manifest_hash != reviewed["manifest_sha256"]:
            raise ValueError("Model/revision/manifest is not a reviewed snapshot")
        files = manifest.get("files")
        if not isinstance(files, dict) or not _CRITICAL_FILES.issubset(files) or len(files) > 100:
            raise ValueError("Manifest does not cover required model files")
        allowed_dirs = {"1_Pooling", "2_Normalize"}
        for name, expected in files.items():
            relative = PurePosixPath(name)
            if (not isinstance(name, str) or relative.is_absolute() or ".." in relative.parts
                    or "\\" in name or str(relative) != name or relative.suffix.lower() not in {".json", ".md", ".txt", ".model", ".safetensors"}):
                raise ValueError("Unreviewed manifest path or file type")
            if (not isinstance(expected, dict) or set(expected) != {"bytes", "sha256"}
                    or type(expected["bytes"]) is not int or not 0 <= expected["bytes"] <= 2_000_000_000
                    or not isinstance(expected["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", expected["sha256"])):
                raise ValueError("Invalid manifest file identity")
            allowed_dirs.update(str(parent) for parent in relative.parents if str(parent) != ".")
            file_path = path / name
            if not file_path.resolve().is_relative_to(path) or not file_path.is_file() or file_path.is_symlink():
                raise ValueError("Manifest path escapes model directory or is missing")
            checksum = hashlib.sha256()
            with file_path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    checksum.update(block)
            if file_path.stat().st_size != expected["bytes"] or checksum.hexdigest() != expected["sha256"]:
                raise ValueError("Manifest file integrity mismatch")
        actual_files = set()
        for entry in path.rglob("*"):
            relative = str(entry.relative_to(path))
            if entry.is_symlink() or not entry.resolve().is_relative_to(path):
                raise ValueError("Symlinked model entries are not allowed")
            if entry.is_file():
                actual_files.add(relative)
            elif not entry.is_dir() or relative not in allowed_dirs:
                raise ValueError("Unreviewed model directory entry")
        if actual_files != set(files) | {"provision_manifest.json"}:
            raise ValueError("Unmanifested extra model files are not allowed")
        graph = _read_json(path / "modules.json")
        if (not isinstance(graph, list) or graph != reviewed["modules"]
                or any(set(module) != {"idx", "name", "path", "type"} or type(module["idx"]) is not int for module in graph)):
            raise ValueError("Unreviewed executable model module graph")
        for module in graph:
            subpath = module["path"]
            if subpath not in {"", "1_Pooling", "2_Normalize"} or not (path / subpath).resolve().is_relative_to(path):
                raise ValueError("Model module subfolder escapes reviewed directory")
        config = _read_json(path / "config.json")
        tokenizer = _read_json(path / "tokenizer_config.json")
        if config.get("model_type") != "bert" or config.get("architectures") != ["BertModel"]:
            raise ValueError("Only the reviewed builtin BertModel architecture is allowed")
        if tokenizer.get("tokenizer_class") not in {"BertTokenizer", "PreTrainedTokenizerFast"}:
            raise ValueError("Only the reviewed builtin tokenizer classes are allowed")
        for name in ("config.json", "tokenizer_config.json", "sentence_bert_config.json", "config_sentence_transformers.json", "1_Pooling/config.json"):
            if _unsafe_config(_read_json(path / name)):
                raise ValueError("Custom config/tokenizer code mapping is not allowed")
        return manifest, manifest_hash
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        raise EncoderUnavailable("Local encoder reviewed-snapshot, module-graph or integrity validation failed") from exc


class LocalSentenceTransformerEncoder:
    def __init__(self, model_path: str | Path) -> None:
        path = Path(model_path).expanduser().resolve()
        provision, manifest_hash = _validate_directory(path)
        # The opt-in adapter remains offline regardless of launching-shell flags.
        for variable in ("HF_HUB_DISABLE_TELEMETRY", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
            os.environ[variable] = "1"
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(str(path), device="cpu", local_files_only=True,
                trust_remote_code=False, model_kwargs={"use_safetensors": True})
        except Exception as exc:
            raise EncoderUnavailable("Configured semantic encoder could not be loaded offline; no fallback") from exc
        self.model_name = path.name
        self.config_sha256 = hashlib.sha256((path / "modules.json").read_bytes() + (path / "config.json").read_bytes()).hexdigest()
        self.provision_manifest_sha256 = manifest_hash
        self.revision = provision["revision"]
        self.model_language = provision.get("language", "unknown")
        self.model_license = provision.get("license", "unverified")
        self.max_sequence_length = getattr(self._model, "max_seq_length", None)

    @property
    def metadata(self) -> dict:
        return {"model_name": self.model_name, "config_sha256": self.config_sha256,
                "model_language": self.model_language, "model_license": self.model_license,
                "provision_manifest_sha256": self.provision_manifest_sha256, "revision": self.revision,
                "max_sequence_length": self.max_sequence_length, "device": "cpu",
                "local_files_only": True, "trust_remote_code": False, "use_safetensors": True,
                "hf_hub_offline": True, "telemetry_disabled": True, "transformers_offline": True,
                "manifest_integrity_verified": True, "reviewed_builtin_module_graph": True,
                "document_vector_cache": "none"}

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if isinstance(texts, (str, bytes)) or any(not isinstance(text, str) for text in texts):
            raise ValueError("Encoder input must be a sequence of strings")
        if not texts:
            return np.empty((0, 0), dtype=np.float64)
        try:
            vectors = np.asarray(self._model.encode(list(texts), batch_size=32, show_progress_bar=False,
                convert_to_numpy=True, normalize_embeddings=True), dtype=np.float64)
        except Exception as exc:
            raise EncoderUnavailable("Local semantic encoding failed; no remote fallback was attempted") from exc
        if vectors.ndim != 2 or vectors.shape[0] != len(texts) or not vectors.shape[1] or not np.isfinite(vectors).all():
            raise ValueError("Local encoder returned invalid vectors")
        lengths = np.linalg.norm(vectors, axis=1)
        if np.any(lengths <= 0):
            raise ValueError("Local encoder returned zero-length vectors")
        return vectors / lengths[:, None]
