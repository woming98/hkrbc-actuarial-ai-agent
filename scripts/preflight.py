#!/usr/bin/env python3
"""Read-only offline demonstration checks. JSON goes to stdout; nothing is started.

No credentials are authenticated, no database is opened, no model is loaded,
and no network/download or output-file operation is performed. Model checks
inspect manifests and file sizes, not large weight contents or inference.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
MAX_METADATA_BYTES = 5_000_000
SAMPLES = ("opening.csv", "closing.csv", "malformed.csv", "coupon_crossing_opening.csv", "coupon_crossing_closing.csv")
PACKAGES = {"pydantic": "pydantic", "numpy": "numpy", "pandas": "pandas", "streamlit": "streamlit"}


def _dependency_report() -> dict[str, dict[str, Any]]:
    result = {}
    for distribution, module in {**PACKAGES, "sentence-transformers": "sentence_transformers"}.items():
        try:
            version = importlib.metadata.version(distribution)
            available = importlib.util.find_spec(module) is not None
        except (ImportError, ModuleNotFoundError, ValueError, importlib.metadata.PackageNotFoundError):
            version, available = None, False
        result[distribution] = {"installed": available, "version": version,
                                "probe": "distribution_metadata_and_module_spec", "model_imported": False}
    return result


def _read_json(path: Path) -> Any:
    if not path.is_file() or path.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError("Metadata file missing or oversized")
    return json.loads(path.read_text(encoding="utf-8"))


def _application_entry(root: Path) -> dict[str, bool]:
    if not (root / "app.py").is_file():
        raise ValueError("Missing application")
    return {"available": True}


def _source_metadata(root: Path) -> dict[str, Any]:
    from hkrbc_agent.store import Document

    directory = root / "data" / "documents"
    register = _read_json(directory / "source_register.json")
    seed = [Document.model_validate(item) for item in _read_json(directory / "regulatory_seed.json")]
    supplement = [Document.model_validate(item) for item in _read_json(directory / "verified_supplement.json")]
    if not seed or not supplement or register.get("current_consolidated_verified") is not False:
        raise ValueError("Source scope metadata invalid")
    seed_hash = hashlib.sha256((directory / "regulatory_seed.json").read_bytes()).hexdigest()
    if seed_hash != register["original_seed_unchanged_sha256"]:
        raise ValueError("Seed fingerprint mismatch")
    if len(supplement) != register["supplement_record_count"]:
        raise ValueError("Supplement count mismatch")
    all_references = [document.reference for document in seed + supplement]
    if len(set(all_references)) != len(all_references):
        raise ValueError("Duplicate source versions")
    sources = {source["source_sha256"]: source for source in register["sources"]
               if source.get("source_sha256") and source.get("access_status") == "downloaded_primary_pdf"}
    verification = {item["document_id"]: item for item in register["section_verification"]}
    if len(verification) != len(register["section_verification"]):
        raise ValueError("Duplicate section provenance")
    for document in supplement:
        source = sources[document.source_sha256]
        section = verification[document.document_id]
        if (document.current_consolidated_verified or not document.source_checked_at or
                document.source_checked_at.isoformat() != source["retrieval_date"] or
                str(document.url) != source["requested_url"] or
                document.source_page not in source["inspected_pdf_pages"] or
                document.source_page not in source["visually_checked_pdf_pages"] or
                section["source_id"] != source["source_id"] or
                document.source_page not in section["pdf_pages"] or
                hashlib.sha256(document.text.encode()).hexdigest() != section["paraphrase_sha256"]):
            raise ValueError("Supplement provenance mismatch")
        if not re.fullmatch(r"[a-f0-9]{64}", document.source_sha256 or ""):
            raise ValueError("Invalid source hash")
    return {"seed_records": len(seed), "supplement_records": len(supplement),
            "registered_downloaded_pdfs": len(sources), "seed_sha256": seed_hash,
            "supplement_sha256": hashlib.sha256((directory / "verified_supplement.json").read_bytes()).hexdigest(),
            "register_sha256": hashlib.sha256((directory / "source_register.json").read_bytes()).hexdigest(),
            "current_consolidated_verified": False, "source_pdf_bytes_checked": False,
            "scope": "schema_and_distributed_metadata_consistency_only"}


def _sample_assets(root: Path) -> dict[str, Any]:
    from hkrbc_agent.attribution import attribute_movement
    from hkrbc_agent.portfolio import ValidationError, load_portfolio_csv

    directory = root / "data" / "portfolios"
    for name in SAMPLES:
        if not (directory / name).is_file():
            raise ValueError("Required synthetic sample missing")
    opening, closing = (load_portfolio_csv(directory / name) for name in ("opening.csv", "closing.csv"))
    normal = attribute_movement(opening, closing)
    if normal["status"] != "complete" or not normal["validation"]["passed"]:
        raise ValueError("Working synthetic movement is not complete")
    try:
        load_portfolio_csv(directory / "malformed.csv")
    except ValidationError:
        duplicate_blocked = True
    else:
        duplicate_blocked = False
    coupon = attribute_movement(*(load_portfolio_csv(directory / name) for name in ("coupon_crossing_opening.csv", "coupon_crossing_closing.csv")))
    coupon_blocked = (coupon["status"] == "blocked" and coupon["unexplained_residual"] is None and
                      any(check["name"] == "cashflow_bridge_supported" and not check["passed"] for check in coupon["validation"]["checks"]))
    if not duplicate_blocked or not coupon_blocked:
        raise ValueError("Negative demonstration no longer blocks")
    return {"required_samples": len(SAMPLES), "working_movement_complete": True,
            "duplicate_upload_blocked": True, "coupon_settlement_bridge_blocked": True,
            "sha256": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in SAMPLES}}


def _report_assets(root: Path) -> dict[str, Any]:
    path = root / "reports" / "example-actuarial-report.json"
    report = _read_json(path)
    markdown_path = path.with_suffix(".md")
    markdown = markdown_path.read_text(encoding="utf-8")
    bridge = report.get("factor_bridge", {})
    values = [report.get("capital_movement"), report.get("opening", {}).get("aggregate_capital"),
              report.get("closing", {}).get("aggregate_capital"), bridge.get("date_ageing"), bridge.get("unexplained_residual")]
    values += list(bridge.get("factor_attribution", {}).values())
    if (any(type(value) not in (int, float) or not math.isfinite(value) for value in values) or
            report.get("status") != "complete" or not report.get("validation", {}).get("passed") or
            bridge.get("status") != "complete" or not bridge.get("validation", {}).get("passed") or
            set(bridge.get("factor_attribution", {})) != {"holdings_and_equity_value", "risk_free_yield", "credit_spread"} or
            "Counterfactual factor bridge" not in markdown or "Not a regulatory capital return" not in markdown):
        raise ValueError("Example report incomplete or missing scope labels")
    if (abs(report["closing"]["aggregate_capital"] - report["opening"]["aggregate_capital"] - report["capital_movement"]) > .01 or
            abs(bridge["date_ageing"] + math.fsum(bridge["factor_attribution"].values()) - report["capital_movement"]) > .01 or
            abs(bridge["unexplained_residual"]) > .01):
        raise ValueError("Example report does not reconcile")
    return {"json_available": True, "markdown_available": True,
            "json_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "preview_images_available": sum((root / "reports" / name).is_file() for name in ("app-preview.jpg", "factor-bridge-preview.jpg"))}


def _model_state(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"present": False, "metadata_ready": False,
                              "weight_content_hashes_checked": False, "model_loaded": False}
    try:
        from hkrbc_agent.embeddings import REVIEWED_MODELS

        result["present"] = path.is_dir()
        if not result["present"]:
            result["state"] = "not_present"
            return result
        manifest_path = path / "provision_manifest.json"
        if path.is_symlink() or manifest_path.is_symlink():
            raise ValueError("Symlinked metadata")
        manifest = _read_json(manifest_path)
        reviewed = REVIEWED_MODELS.get((manifest.get("model_id"), manifest.get("revision")))
        fingerprint = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if not reviewed or fingerprint != reviewed["manifest_sha256"]:
            raise ValueError("Unreviewed manifest")
        files = manifest["files"]
        if not isinstance(files, dict) or not files:
            raise ValueError("Missing inventory")
        root = path.resolve()
        for name, entry in files.items():
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name:
                raise ValueError("Invalid inventory path")
            source = path / name
            if (source.is_symlink() or not source.resolve().is_relative_to(root) or not source.is_file() or
                    type(entry["bytes"]) is not int or source.stat().st_size != entry["bytes"]):
                raise ValueError("Missing or changed-size model file")
        disk_files = {str(item.relative_to(path)) for item in path.rglob("*") if item.is_file()}
        if disk_files != set(files) | {"provision_manifest.json"} or any(item.is_symlink() for item in path.rglob("*")):
            raise ValueError("Unreviewed model inventory")
        result.update(state="manifest_and_sizes_ready", metadata_ready=True, model_id=manifest["model_id"],
                      revision=manifest["revision"], manifest_sha256=fingerprint,
                      manifest_file_count=len(files), manifest_bytes=sum(entry["bytes"] for entry in files.values()))
    except Exception:
        result["state"] = "invalid_manifest_or_inventory"
    return result


def _configuration(environment: Mapping[str, str]) -> tuple[dict[str, Any], list[str], bool]:
    from hkrbc_agent.security import DEMO_PASSWORDS

    external = environment.get("HKRBC_EXTERNAL_ENABLED", "false").strip().lower()
    backend = environment.get("HKRBC_RETRIEVAL_BACKEND", "bm25").strip().lower()
    local_model = bool(environment.get("HKRBC_LOCAL_MODEL", "").strip())
    local_endpoint_ok = True
    if local_model:
        try:
            endpoint = urlsplit(environment.get("HKRBC_OLLAMA_URL", "http://127.0.0.1:11434/api/generate"))
            local_endpoint_ok = (endpoint.scheme == "http" and endpoint.hostname in {"localhost", "127.0.0.1", "::1"}
                                 and not endpoint.username and not endpoint.password)
        except ValueError:
            local_endpoint_ok = False
    public_accounts = sum(not environment.get(f"HKRBC_{username.upper()}_PASSWORD", "") or
                          environment[f"HKRBC_{username.upper()}_PASSWORD"] == password
                          for username, password in DEMO_PASSWORDS.items())
    settings = {"external_processing_disabled": external == "false", "external_enable_flag_valid": external in {"true", "false"},
                "external_credentials_present": bool(environment.get("OPENAI_API_KEY", "")),
                "local_llm_configured": local_model, "local_llm_endpoint_loopback": local_endpoint_ok,
                "retrieval_backend_valid": backend in {"bm25", "hash", "dense", "hybrid"},
                "default_bm25_selected": backend == "bm25", "semantic_retrieval_requested": backend in {"dense", "hybrid"},
                "embedding_path_configured": bool(environment.get("HKRBC_EMBEDDING_MODEL_PATH", "").strip()),
                "public_demo_password_account_count": public_accounts, "production_identity_provider": False,
                "environment_values_printed": False}
    warnings = []
    if public_accounts:
        warnings.append("Public demo credentials remain active; this is not production authentication and must not be exposed publicly.")
    if settings["external_credentials_present"]:
        warnings.append("External credentials are present in the environment; preflight never uses or prints them.")
    if local_model:
        warnings.append("A local LLM is configured; preflight does not contact it or verify that it is running.")
    if backend != "bm25":
        warnings.append("The interview's default BM25 configuration is not selected; observed behavior may differ.")
    valid = settings["external_processing_disabled"] and settings["external_enable_flag_valid"] and settings["retrieval_backend_valid"] and local_endpoint_ok
    return settings, warnings, bool(valid)


def run_preflight(root: Path = ROOT, *, environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    environment = os.environ if environment is None else environment
    checks = []
    metadata: dict[str, Any] = {}

    def check(name: str, operation, *, required: bool = True):
        try:
            details = operation()
            checks.append({"name": name, "required": required, "passed": True})
            metadata[name] = details
        except Exception as exc:
            # Error messages can contain paths, environment values or invalid
            # document contents. Return a controlled category, never raw details.
            checks.append({"name": name, "required": required, "passed": False, "error_type": type(exc).__name__})

    python_ok = sys.version_info >= (3, 11)
    checks.append({"name": "python_version", "required": True, "passed": python_ok})
    metadata["python"] = {"version": ".".join(map(str, sys.version_info[:3])), "minimum": "3.11", "bytecode_writes_disabled": True}
    dependencies = _dependency_report()
    metadata["packages"] = dependencies
    checks.append({"name": "required_packages", "required": True,
                   "passed": all(dependencies[name]["installed"] for name in PACKAGES)})
    check("application_entry", lambda: _application_entry(root))
    check("source_metadata", lambda: _source_metadata(root))
    check("synthetic_samples", lambda: _sample_assets(root))
    check("example_report", lambda: _report_assets(root))
    config, warnings, config_ok = _configuration(environment)
    metadata["configuration"] = config
    checks.append({"name": "offline_configuration", "required": True, "passed": config_ok})
    if config["semantic_retrieval_requested"]:
        configured = environment.get("HKRBC_EMBEDDING_MODEL_PATH", "").strip()
        model = _model_state(Path(configured).expanduser()) if configured else {"state": "not_configured", "metadata_ready": False, "model_loaded": False, "weight_content_hashes_checked": False}
        metadata["configured_embedding_snapshot"] = model
        checks.append({"name": "configured_semantic_model_metadata", "required": True,
                       "passed": model["metadata_ready"] and dependencies["sentence-transformers"]["installed"]})
    metadata["optional_local_snapshots"] = {name: _model_state(root / "runtime" / "models" / name)
                                            for name in ("all-MiniLM-L6-v2", "paraphrase-multilingual-MiniLM-L12-v2")}
    passed = all(item["passed"] for item in checks if item["required"])
    return {"schema_version": "1.0", "project": "hkrbc-actuarial-ai-agent", "status": "ready" if passed else "blocked",
            "required_checks_passed": passed, "checks": checks, "metadata": metadata, "warnings": warnings,
            "limits": ["Read-only offline readiness checks; no database, authentication, model inference, model download, network or server start.",
                       "Package availability is inspected through distribution metadata/module specs; this does not prove every optional binary import works.",
                       "Source checks validate distributed metadata consistency, not legal currency, publisher authenticity or rights to redistribute source PDFs.",
                       "Embedding checks inspect the approved manifest and inventory/sizes only; the actual loader must still verify all weight SHA-256 values before use.",
                       "No port health or live-server check is attempted. Public demo identities are unsuitable for shared production use."]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Project directory to inspect; never modified")
    arguments = parser.parse_args(argv)
    result = run_preflight(arguments.root)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["required_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
