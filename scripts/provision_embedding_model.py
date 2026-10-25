#!/usr/bin/env python3
"""Explicitly download reviewed public encoder revisions; never called by the app.

Only the allowlisted Apache-2.0 encoders are supported. No user prompts, tokens
or portfolio data are sent. Only HTTPS Hugging Face hosts may receive redirects.
The destination must not already exist, including an empty directory or symlink.
Files are staged beside it and published atomically only after a complete manifest.
Model files remain in ignored runtime/models/.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODELS = {"english": MODEL_ID,
          "multilingual": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"}
REVIEWED_REVISIONS = {
    MODEL_ID: "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    MODELS["multilingual"]: "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
}
FILES = {"1_Pooling/config.json", "config.json", "config_sentence_transformers.json",
         "model.safetensors", "modules.json", "sentence_bert_config.json",
         "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "vocab.txt",
         "sentencepiece.bpe.model", "README.md", "LICENSE"}
MAX_FILE_BYTES = 600_000_000
MAX_METADATA_BYTES = 5_000_000


def _validate_https_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower()
        allowed = any(hostname == base or hostname.endswith("." + base)
                      for base in ("huggingface.co", "hf.co"))
        if (parsed.scheme != "https" or not allowed or parsed.username is not None or
                parsed.password is not None or parsed.port not in (None, 443)):
            raise ValueError("Model URLs must use HTTPS on an allowlisted Hugging Face host")
    except (TypeError, ValueError) as exc:
        raise ValueError("Model URLs must use HTTPS on an allowlisted Hugging Face host") from exc


class HTTPSOnlyHubRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        target = urljoin(request.full_url, new_url)
        _validate_https_url(target)
        return super().redirect_request(request, fp, code, message, headers, target)


def _open_https(request: Request, *, timeout: int):
    _validate_https_url(request.full_url)
    # Default HTTPSHandler retains normal certificate/hostname verification.
    # The explicit redirect handler checks every redirected URL before a request.
    return build_opener(HTTPSOnlyHubRedirects()).open(request, timeout=timeout)


def _rename_no_replace(source: Path, destination: Path) -> None:
    """Atomic publication without POSIX rename's empty-directory replacement."""
    if os.name == "nt":
        os.rename(source, destination)  # Windows rejects an existing destination.
        return
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin" and hasattr(library, "renamex_np"):
        function = library.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(os.fsencode(source), os.fsencode(destination), 0x00000004)  # RENAME_EXCL
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        function = library.renameat2
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(-100, os.fsencode(source), -100, os.fsencode(destination), 1)  # AT_FDCWD, RENAME_NOREPLACE
    else:
        raise OSError("Atomic no-overwrite model publication is unavailable on this platform")
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def _publish(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Model destination already exists; choose a new directory")
    _rename_no_replace(source, destination)


def provision(destination: Path, model_id: str = MODEL_ID) -> dict:
    if model_id not in MODELS.values():
        raise ValueError("Only reviewed, allowlisted model repositories can be provisioned")
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Model destination already exists; choose a new directory (existing files are never overwritten)")
    revision = REVIEWED_REVISIONS[model_id]
    with _open_https(Request(f"https://huggingface.co/api/models/{model_id}/revision/{revision}",
                            headers={"User-Agent": "hkrbc-local-model-provisioner/1.0"}), timeout=30) as response:
        metadata = response.read(MAX_METADATA_BYTES + 1)
    if len(metadata) > MAX_METADATA_BYTES:
        raise ValueError("Model metadata exceeded the response size limit")
    info = json.loads(metadata)
    if not isinstance(info, dict) or info.get("sha") != revision:
        raise ValueError("Hub metadata does not match the exact reviewed model revision")
    if not isinstance(info.get("cardData"), dict) or info["cardData"].get("license") != "apache-2.0":
        raise ValueError("Model metadata no longer declares the reviewed Apache-2.0 licence")
    siblings = info.get("siblings")
    if not isinstance(siblings, list) or any(not isinstance(item, dict) or not isinstance(item.get("rfilename"), str) for item in siblings):
        raise ValueError("Model metadata does not contain a valid file inventory")
    available = {item["rfilename"] for item in siblings}
    chosen = sorted(FILES & available)
    if not {"model.safetensors", "modules.json", "config.json", "tokenizer.json"} <= set(chosen):
        raise ValueError("The public model snapshot is missing required safe-format files")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent))
    try:
        def download(name: str) -> tuple[str, dict]:
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".part")
            total = 0
            sha = hashlib.sha256()
            try:
                request = Request(f"https://huggingface.co/{model_id}/resolve/{revision}/{name}",
                                  headers={"User-Agent": "hkrbc-local-model-provisioner/1.0"})
                with _open_https(request, timeout=60) as response, temporary.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_FILE_BYTES:
                            raise ValueError("Model file exceeded the download size limit")
                        sha.update(chunk)
                        output.write(chunk)
                os.replace(temporary, path)
                return name, {"bytes": total, "sha256": sha.hexdigest()}
            finally:
                temporary.unlink(missing_ok=True)

        with ThreadPoolExecutor(max_workers=4) as pool:
            manifest = dict(pool.map(download, chosen))
        # Keep keys, insertion order, text, JSON formatting and newline stable:
        # reviewed loader anchors pin existing provision_manifest.json bytes.
        result = {"model_id": model_id, "revision": revision, "license": "apache-2.0",
                  "language": "English" if model_id == MODEL_ID else "Multilingual (model card: 50 languages)",
                  "dimensions": 384, "files": manifest,
                  "source": f"https://huggingface.co/{model_id}",
                  "limitations": ("English encoder; not a validated Chinese or actuarial domain model. Model-card wordpiece truncation applies."
                                  if model_id == MODEL_ID else
                                  "General-purpose pretrained encoder, not a validated actuarial domain model. Model-card wordpiece truncation applies.")}
        (staging / "provision_manifest.json").write_text(json.dumps(result, indent=2) + "\n")
        _publish(staging, destination)
        return result
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=sorted(MODELS), default="english")
    parser.add_argument("--destination", type=Path, help="Fresh destination path; existing files, directories and symlinks are never overwritten")
    args = parser.parse_args()
    model_id = MODELS[args.model]
    destination = args.destination or ROOT / "runtime/models" / model_id.split("/")[-1]
    manifest = provision(destination, model_id)
    print(json.dumps({"model_id": model_id, "revision": manifest["revision"],
                      "files": len(manifest["files"]), "bytes": sum(item["bytes"] for item in manifest["files"].values()),
                      "destination": str(destination.resolve())}, indent=2))


if __name__ == "__main__":
    main()
