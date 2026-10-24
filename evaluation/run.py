#!/usr/bin/env python3
"""Run offline fixture checks and score optional, externally produced baselines.

This script makes no model/API requests. A and B are NOT RUN unless result files
are explicitly supplied. It does not pretend local extraction is the same LLM as
an external baseline. See README.md for the response-adapter protocol.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import platform
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from hkrbc_agent.calculations import FUNCTION_VERSION, aggregate_capital, shapley_movement
from hkrbc_agent.portfolio import ValidationError
from hkrbc_agent.routing import ModelRouter, ModelSettings
from hkrbc_agent.security import DEMO_PASSWORDS
from hkrbc_agent.service import AgentService


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load_suite(root: Path = ROOT) -> dict[str, Any]:
    manifest_raw = (root / "evaluation" / "cases.json").read_bytes()
    manifest = json.loads(manifest_raw)
    context_raw = (root / manifest["context_path"]).read_bytes()
    portfolio_files = {name: (root / "data" / "portfolios" / name).read_text(encoding="utf-8")
                       for name in ("opening.csv", "closing.csv", "malformed.csv")}
    manifest["manifest_sha256"] = hashlib.sha256(manifest_raw).hexdigest()
    manifest["source_context_sha256"] = hashlib.sha256(context_raw).hexdigest()
    manifest["case_bundle_sha256"] = digest({"manifest": manifest["manifest_sha256"],
                                            "context": manifest["source_context_sha256"], "portfolios": portfolio_files})
    context = json.loads(context_raw)
    manifest["allowed_citations"] = sorted(f"{item['document_id']}@{item['version']}" for item in context
                                            if item["classification"] == "public" and item["status"] != "superseded")
    return manifest


def _formula(expression: str) -> float:
    """Tiny arithmetic parser for independently documented reference formulas."""
    if not isinstance(expression, str) or len(expression) > 200:
        raise ValueError("Invalid reference formula")
    tree = ast.parse(expression, mode="eval")

    def resolve(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = resolve(node.left), resolve(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            return left / right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sqrt" and len(node.args) == 1 and not node.keywords:
            return math.sqrt(resolve(node.args[0]))
        raise ValueError("Only constants, arithmetic and sqrt are permitted in reference formulas")

    result = resolve(tree.body)
    if not math.isfinite(result):
        raise ValueError("Reference formula is not finite")
    return result


def _numeric_expectations(case: dict[str, Any]) -> dict[str, float]:
    expected = dict(case["expected"].get("numeric", {}))
    expected.update({field: _formula(formula) for field, formula in case["expected"].get("numeric_formulas", {}).items()})
    return expected


def _normalized_response(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict) or not isinstance(response.get("answer"), str):
        raise ValueError("Each replicate requires an answer string")
    if not isinstance(response.get("outputs"), dict):
        raise ValueError("Each replicate requires an outputs object")
    citations = response.get("citations")
    if not isinstance(citations, list) or any(not isinstance(item, str) for item in citations):
        raise ValueError("Each replicate requires citation reference strings")
    elapsed = response.get("elapsed_ms")
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("elapsed_ms must be finite and nonnegative")
    # Also reject non-finite nested output values at the file boundary.
    json.dumps(response["outputs"], allow_nan=False)
    return {"answer": response["answer"], "citations": citations, "outputs": response["outputs"], "elapsed_ms": float(elapsed)}


def score_case(case: dict[str, Any], replicates: list[dict[str, Any]], allowed_citations: list[str]) -> dict[str, Any]:
    if not replicates or len(replicates) > 10:
        raise ValueError("Supply between one and ten replicates per case")
    normalized = [_normalized_response(response) for response in replicates]
    expected = case["expected"]
    numeric_expected = _numeric_expectations(case)
    tolerance = expected.get("absolute_tolerance", 0.01)
    run_scores = []
    for response in normalized:
        outputs, citations = response["outputs"], response["citations"]
        numeric = []
        for field, reference in numeric_expected.items():
            actual = outputs.get(field)
            valid = type(actual) in (int, float) and math.isfinite(actual)
            numeric.append({"field": field, "passed": valid and abs(actual - reference) <= tolerance,
                            "absolute_error": abs(actual - reference) if valid else None, "tolerance": tolerance})
        values_passed = all(type(outputs.get(field)) is type(value) and outputs.get(field) == value
                            for field, value in expected.get("values", {}).items())
        required = expected.get("required_citations", [])
        citation_applicable = bool(citations or required)
        citation_passed = all(reference in allowed_citations for reference in citations) and all(reference in citations for reference in required)
        answer_passed = all(text.lower() in response["answer"].lower() for text in expected.get("answer_contains", []))
        raw = json.dumps({"answer": response["answer"], "outputs": outputs, "citations": citations}, sort_keys=True).lower()
        forbidden = expected.get("forbidden_strings", [])
        disclosure_passed = not any(marker.lower() in raw for marker in forbidden)
        reconciliation = None
        if expected.get("reconciliation"):
            fields = ("opening_capital_hkd", "closing_capital_hkd", "movement_hkd", "shapley_total_hkd", "residual_hkd")
            valid = all(type(outputs.get(field)) in (int, float) and math.isfinite(outputs[field]) for field in fields)
            reconciliation = bool(valid and abs(outputs["closing_capital_hkd"] - outputs["opening_capital_hkd"] - outputs["movement_hkd"]) <= tolerance
                                  and abs(outputs["movement_hkd"] - outputs["shapley_total_hkd"] - outputs["residual_hkd"]) <= tolerance
                                  and abs(outputs["residual_hkd"]) <= tolerance)
        passed = (all(item["passed"] for item in numeric) and values_passed and citation_passed and answer_passed
                  and disclosure_passed and reconciliation is not False)
        run_scores.append({"passed": passed, "numerical_accuracy": {"passed": all(item["passed"] for item in numeric), "checks": numeric} if numeric else None,
                           "citation_reference_validity": {"passed": citation_passed, "supplied_count": len(citations), "required_count": len(required)} if citation_applicable else None,
                           "reconciliation_accuracy": reconciliation, "unauthorized_disclosure": disclosure_passed if forbidden else None,
                           "expected_status_and_fields": values_passed and answer_passed, "elapsed_ms": response["elapsed_ms"]})
    hashes = [digest({key: value for key, value in response.items() if key != "elapsed_ms"}) for response in normalized]
    reproducible = len(set(hashes)) == 1 if len(hashes) >= 2 else None
    return {"case_id": case["case_id"], "passed": all(result["passed"] for result in run_scores) and reproducible is not False,
            "runs": run_scores, "reproducibility": {"measured": len(hashes) >= 2, "passed": reproducible, "response_digests": hashes},
            "mean_elapsed_ms": sum(item["elapsed_ms"] for item in normalized) / len(normalized)}


def _csv(kind: str, *, value: float = 0, valuation: str = "2025-12-31") -> str:
    header = "asset_id,asset_type,currency,valuation_date,market_value,face_value,coupon_rate,yield_rate,maturity_date,credit_spread_bps\n"
    if kind == "bond":
        return header + "SYN-ZERO,bond,HKD,2020-01-01,,1000000,0,0.05,2024-01-01,0\n"
    return header + f"SYN-EQ,equity,HKD,{valuation},{value},,,,,\n"


def _run_case(service: AgentService, token: str, case: dict[str, Any], root: Path) -> dict[str, Any]:
    kind = case["kind"]
    answer, citations = "", []
    if kind == "valuation":
        result = service.analyse(token, _csv("bond"), declared_synthetic=True)
        outputs = {"price_hkd": result["assets"][0]["market_value"], "dv01_hkd_per_bp": result["assets"][0]["dv01"]}
    elif kind == "movement":
        result = service.analyse(token, _csv("equity", value=40_000_000),
                                 _csv("equity", value=50_000_000, valuation="2026-09-30"), declared_synthetic=True)
        outputs = {"opening_capital_hkd": result["opening"]["aggregate_capital"], "closing_capital_hkd": result["closing"]["aggregate_capital"],
                   "movement_hkd": result["capital_movement"], "shapley_total_hkd": sum(result["shapley_attribution"].values()),
                   "residual_hkd": result["unexplained_residual"]}
    elif kind == "aggregation":
        # This isolates the engine's aggregation contract; unlike CSV cases it
        # intentionally does not exercise authentication or the service boundary.
        opening, closing = case["input"]["opening"], case["input"]["closing"]
        start, end = aggregate_capital(opening), aggregate_capital(closing)
        attributed = sum(shapley_movement(opening, closing).values())
        outputs = {"opening_capital_hkd": start, "closing_capital_hkd": end, "movement_hkd": end - start,
                   "shapley_total_hkd": attributed, "residual_hkd": end - start - attributed}
    elif kind == "scenarios":
        params = case["input"]
        data = (root / params["portfolio_path"]).read_bytes()
        first = service.scenarios(token, data, count=params["count"], seed=params["seed"], declared_synthetic=True)
        second = service.scenarios(token, data, count=params["count"], seed=params["seed"], declared_synthetic=True)
        outputs = {"count": len(first["scenarios"]), "finite_outputs": all(math.isfinite(row[key]) for row in first["scenarios"] for key in ("portfolio_value", "pnl")),
                   "identical_outputs": first == second,
                   "pnl_reconciles": all(abs(row["pnl"] - (row["portfolio_value"] - first["base_portfolio_value"])) <= 0.01 for row in first["scenarios"])}
    elif kind == "retrieval":
        result = service.ask(token, case["prompt"])
        answer = result["answer"]
        citations = [item["reference"] for item in result["citations"]]
        outputs = {"answer_status": result["status"]}
    elif kind == "malformed":
        try:
            service.analyse(token, (root / case["input"]["portfolio_path"]).read_bytes(), declared_synthetic=True)
            outputs = {"validation_blocked": False}
        except ValidationError:
            outputs = {"validation_blocked": True}
    else:
        raise ValueError(f"Unknown case kind: {kind}")
    return {"answer": answer, "citations": citations, "outputs": outputs}


def offline_results(suite: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    def no_transport(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("All model transports are forbidden in the offline benchmark")

    with tempfile.TemporaryDirectory(prefix="hkrbc-evaluation-") as temporary:
        # Explicit empty model settings override any local/external env settings.
        service = AgentService(Path(temporary) / "evaluation.sqlite", router=ModelRouter(ModelSettings(), transport=no_transport))
        admin = service.sign_in("admin", os.getenv("HKRBC_ADMIN_PASSWORD") or DEMO_PASSWORDS["admin"])
        service.seed(admin, root / suite["context_path"])
        analyst = service.sign_in("analyst", os.getenv("HKRBC_ANALYST_PASSWORD") or DEMO_PASSWORDS["analyst"])
        responses = []
        for case in suite["cases"]:
            replicates = []
            for _ in range(suite["replicates"]):
                begin = perf_counter()
                response = _run_case(service, analyst, case, root)
                response["elapsed_ms"] = (perf_counter() - begin) * 1000
                replicates.append(response)
            responses.append({"case_id": case["case_id"], "replicates": replicates})
    return {"schema_version": "1.0", "system": "C", "manifest_sha256": suite["manifest_sha256"],
            "metadata": {"provider": "local-extractive-and-deterministic-python", "model": "none", "model_version": "none",
                         "calculation_version": FUNCTION_VERSION, "python_version": platform.python_version(),
                         "config": {"external_enabled": False, "local_model": "", "scenario_seed": 42},
                         "source_context_sha256": suite["source_context_sha256"], "case_bundle_sha256": suite["case_bundle_sha256"],
                         "tool_access": "full_workflow"}, "responses": responses}


def score_submission(submission: dict[str, Any], suite: dict[str, Any], system: str) -> dict[str, Any]:
    if submission.get("schema_version") != "1.0" or submission.get("system") != system:
        raise ValueError("Submission schema_version/system does not match")
    if submission.get("manifest_sha256") != suite["manifest_sha256"]:
        raise ValueError("Submission manifest does not match the identical case manifest")
    metadata = submission.get("metadata")
    if not isinstance(metadata, dict) or any(not isinstance(metadata.get(field), str) or not metadata[field].strip()
                                             for field in ("provider", "model", "model_version", "source_context_sha256", "case_bundle_sha256", "tool_access")):
        raise ValueError("Provider, model, model_version, context/bundle hashes and tool_access metadata are required")
    if not isinstance(metadata.get("config"), dict):
        raise ValueError("Explicit model config metadata is required")
    json.dumps(metadata, allow_nan=False)
    if metadata["source_context_sha256"] != suite["source_context_sha256"] or metadata["case_bundle_sha256"] != suite["case_bundle_sha256"]:
        raise ValueError("Submission source context or input bundle differs")
    expected_tools = {"A": "documents_only", "B": "equivalent_calculation_tools", "C": "full_workflow"}[system]
    if metadata["tool_access"] != expected_tools:
        raise ValueError(f"System {system} must declare tool_access={expected_tools}")
    responses = submission.get("responses")
    if not isinstance(responses, list) or any(not isinstance(item, dict) for item in responses):
        raise ValueError("Submission requires case responses")
    by_id = {item.get("case_id"): item for item in responses}
    required_ids = {case["case_id"] for case in suite["cases"]}
    if len(by_id) != len(responses) or set(by_id) != required_ids:
        raise ValueError("Responses must contain exactly the shared case IDs with no duplicates")
    scored = [score_case(case, by_id[case["case_id"]].get("replicates", []), suite["allowed_citations"]) for case in suite["cases"]]
    return {"status": "measured_offline" if system == "C" else "scored_supplied_results", "metadata": metadata,
            "fixture_pass_count": sum(item["passed"] for item in scored), "fixture_count": len(scored),
            "all_fixture_checks_passed": all(item["passed"] for item in scored), "cases": scored}


def _ab_comparability(systems: dict[str, Any]) -> dict[str, Any]:
    if any(systems[system]["status"] != "scored_supplied_results" for system in ("A", "B")):
        return {"eligible": False, "reason": "A/B result files have not both been supplied and validated."}
    fields = ("provider", "model", "model_version", "config", "source_context_sha256", "case_bundle_sha256")
    mismatches = [field for field in fields if systems["A"]["metadata"][field] != systems["B"]["metadata"][field]]
    return {"eligible": not mismatches, "reason": "Matching declared A/B provider, model, config, context and cases; tool access differs as designed." if not mismatches else "A/B metadata differ: " + ", ".join(mismatches),
            "limitation": "Metadata are self-reported. This does not establish equivalence to C, which uses no LLM offline."}


def run_evaluation(*, a_results: Path | None = None, b_results: Path | None = None, root: Path = ROOT) -> dict[str, Any]:
    suite = load_suite(root)
    systems: dict[str, Any] = {system: {"status": "not_run", "reason": "No baseline model was called and no external result file was supplied."} for system in ("A", "B")}
    for system, path in (("A", a_results), ("B", b_results)):
        if path is not None:
            try:
                systems[system] = score_submission(json.loads(path.read_text(encoding="utf-8")), suite, system)
            except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
                systems[system] = {"status": "invalid_result", "reason": type(exc).__name__ + ": " + str(exc)}
    systems["C"] = score_submission(offline_results(suite, root), suite, "C")
    return {"schema_version": "1.0", "suite_id": suite["suite_id"], "measured_at_utc": datetime.now(timezone.utc).isoformat(),
            "manifest_sha256": suite["manifest_sha256"], "source_context_sha256": suite["source_context_sha256"],
            "case_bundle_sha256": suite["case_bundle_sha256"], "systems": systems, "ab_comparability": _ab_comparability(systems),
            "comparative_performance_claim": "Not established; offline C has no LLM and A/B are not executed by this runner.",
            "limitations": [
                "Eight synthetic fixture tasks are not a representative actuarial or regulatory benchmark.",
                "Citation scoring checks authorized document/version reference identity and the expected date phrase; it does not assess legal entailment, source completeness or current-law accuracy.",
                "Security scoring detects fixed synthetic disclosure markers; passing does not prove resistance to unseen attacks.",
                "Elapsed times are observed local per-case wall time, excluding service creation, sign-in and corpus seeding; supplied baseline timing is self-reported and hardware-uncontrolled.",
                "Reproducibility compares normalized answers, outputs and citation lists, excluding latency. Two repeats do not establish cross-version or cross-platform reproducibility.",
                "The diversified-movement case calls the deterministic engine directly; other numerical cases exercise the service and authorization boundary.",
                "A/B files require matching cases, source context and declared configuration; the adapter neither runs nor verifies their model execution.",
                "Formal same-LLM A/B/C comparison remains pending, including calibration, entailment review and statistically meaningful repeated trials.",
            ]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-results", type=Path, help="Externally generated docs-only result JSON")
    parser.add_argument("--b-results", type=Path, help="Externally generated equivalent-tools result JSON")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "results" / "offline.json")
    parser.add_argument("--submission-template", type=Path, help="Write an unexecuted A adapter template and exit")
    args = parser.parse_args(argv)
    if args.submission_template:
        suite = load_suite()
        template = {"schema_version": "1.0", "system": "A", "manifest_sha256": suite["manifest_sha256"],
                    "metadata": {"provider": "REPLACE", "model": "REPLACE", "model_version": "REPLACE", "config": {"temperature": 0},
                                 "source_context_sha256": suite["source_context_sha256"], "case_bundle_sha256": suite["case_bundle_sha256"], "tool_access": "documents_only"},
                    "responses": [{"case_id": case["case_id"], "replicates": [{"answer": "", "citations": [], "outputs": {}, "elapsed_ms": 0.0}]} for case in suite["cases"]]}
        args.submission_template.parent.mkdir(parents=True, exist_ok=True)
        args.submission_template.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
        print("Wrote an UNEXECUTED adapter template; populate it with actual observed responses and timing.")
        return 0
    result = run_evaluation(a_results=args.a_results, b_results=args.b_results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    measured = result["systems"]["C"]
    print(f"C offline fixture checks: {measured['fixture_pass_count']}/{measured['fixture_count']}; A: {result['systems']['A']['status']}; B: {result['systems']['B']['status']}")
    print(f"Results: {args.output.resolve()}")
    return 0 if measured["all_fixture_checks_passed"] and all(result["systems"][system]["status"] != "invalid_result" for system in ("A", "B")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
