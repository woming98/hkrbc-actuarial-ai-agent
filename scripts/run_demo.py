#!/usr/bin/env python3
"""Offline demonstration through the authenticated application service."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hkrbc_agent.portfolio import ValidationError
from hkrbc_agent.reporting import render_report
from hkrbc_agent.routing import ModelRouter, ModelSettings
from hkrbc_agent.security import DEMO_PASSWORDS
from hkrbc_agent.service import AgentService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Optional directory for the local SQLite audit, report JSON and Markdown")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="hkrbc-demo-") as temporary:
        directory = args.output_dir or Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        # No model is configured here; env model settings cannot enable transport.
        service = AgentService(directory / "demo.sqlite", router=ModelRouter(ModelSettings()))
        admin = service.sign_in("admin", os.getenv("HKRBC_ADMIN_PASSWORD") or DEMO_PASSWORDS["admin"])
        service.seed(admin, ROOT / "data" / "documents" / "regulatory_seed.json")
        supplement = ROOT / "data" / "documents" / "verified_supplement.json"
        if supplement.exists():
            service.seed(admin, supplement)
        analyst = service.sign_in("analyst", os.getenv("HKRBC_ANALYST_PASSWORD") or DEMO_PASSWORDS["analyst"])
        evidence = service.ask(analyst, "When did the RBC regime commence?")
        opening = (ROOT / "data" / "portfolios" / "opening.csv").read_bytes()
        closing = (ROOT / "data" / "portfolios" / "closing.csv").read_bytes()
        report_id, movement = service.create_report(analyst, opening, closing, declared_synthetic=True)
        try:
            service.analyse(analyst, (ROOT / "data" / "portfolios" / "malformed.csv").read_bytes(), declared_synthetic=True)
            malformed_blocked = False
        except ValidationError:
            malformed_blocked = True
        scenarios = service.scenarios(analyst, opening, count=25, seed=42, declared_synthetic=True)
        summary = {"model_label": movement["model_label"], "provider": evidence["provider"],
                   "regulatory_evidence_status": evidence["status"], "source_references": [item["reference"] for item in evidence["citations"]],
                   "opening_capital_hkd": movement["opening"]["aggregate_capital"],
                   "closing_capital_hkd": movement["closing"]["aggregate_capital"],
                   "capital_movement_hkd": movement["capital_movement"], "shapley_allocation_hkd": movement["shapley_attribution"],
                   "residual_hkd": movement["unexplained_residual"], "validation_passed": movement["validation"]["passed"],
                   "malformed_upload_blocked": malformed_blocked, "scenario_validation_passed": scenarios["validation"]["passed"],
                   "report_id": report_id}
        if args.output_dir:
            (directory / "movement.json").write_text(json.dumps(movement, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            (directory / "movement.md").write_text(render_report(report_id, movement), encoding="utf-8")
            (directory / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2, allow_nan=False))
        if args.output_dir:
            print(f"Local artifacts: {directory.resolve()}")
        return 0 if movement["validation"]["passed"] and malformed_blocked and scenarios["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
