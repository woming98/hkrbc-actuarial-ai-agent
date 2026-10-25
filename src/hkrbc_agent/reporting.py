"""Deterministic report rendering; free-form LLM commentary is never validation."""
from __future__ import annotations

from datetime import datetime, timezone


def render_report(report_id: str, result: dict, *, citations: list[dict] | None = None) -> str:
    citations = citations if citations is not None else result.get("source_references", [])
    start, end = result.get("opening", {}), result.get("closing", {})
    number = lambda value: f"{value:,.2f}"
    lines = ["# HK RBC — Illustrative actuarial movement report", "",
             f"Report ID: `{report_id}`", "",
             f"Generated (UTC): {datetime.now(timezone.utc).isoformat()}", "",
             "**Synthetic data • Educational approximation • Not a regulatory capital return**", "",
             "## Purpose and scope", "",
             "Compare two synthetic asset portfolios using deterministic valuation, illustrative rate, credit and equity stresses, and diversification-aware attribution. This asset-only model does not calculate statutory HK RBC prescribed capital or capital resources.", "",
             "## Deterministic results", "",
             f"Status: **{result['status'].upper()}** · Calculation version: `{result.get('function_version', 'unknown')}`", "",
             f"Valuation dates: {start.get('valuation_date', 'unknown')} → {end.get('valuation_date', 'unknown')}", "",
             "| Measure | HKD |", "|---|---:|",
             f"| Opening illustrative capital | {number(start.get('aggregate_capital', 0))} |",
             f"| Closing illustrative capital | {number(end.get('aggregate_capital', 0))} |",
             f"| Actual capital movement | {number(result.get('capital_movement', 0))} |",
             f"| Explained movement | {number(result.get('explained_movement', 0))} |",
             f"| Unexplained residual | {number(result.get('unexplained_residual', 0))} |", "",
             "| Risk module | Opening | Closing | Standalone change | Shapley allocation |", "|---|---:|---:|---:|---:|"]
    for module in ("rate", "credit", "equity"):
        lines.append(f"| {module.title()} | {number(start.get('module_capital', {}).get(module, 0))} | {number(end.get('module_capital', {}).get(module, 0))} | {number(result.get('module_changes', {}).get(module, 0))} | {number(result.get('shapley_attribution', {}).get(module, 0))} |")
    bridge = result.get("factor_bridge")
    if bridge:
        lines += ["", "## Counterfactual factor bridge", "",
                  f"Bridge status: **{bridge['status'].upper()}**. Date ageing is applied first; the three remaining factor replacements are averaged over all six orderings. This is model attribution, not reconstructed transactions or investment returns.", ""]
        if bridge.get("date_ageing") is not None:
            lines += ["| Factor | Attributed movement (HKD) |", "|---|---:|",
                      f"| Date ageing at opening quotes | {number(bridge['date_ageing'])} |"]
            for factor, value in bridge["factor_attribution"].items():
                lines.append(f"| {factor.replace('_', ' ').title()} | {number(value)} |")
            lines.append(f"| Unexplained factor-bridge residual | {number(bridge['unexplained_residual'])} |")
        else:
            lines.append("Factor attribution could not be completed from the available positions and settlement information.")
        for check in bridge["validation"]["checks"]:
            if not check["passed"]:
                lines.append(f"- Unresolved: {check['details']}")
        lines += ["", "Equity/cash value changes combine quantities, prices and flows. Entry/exit bonds retain their sole observed quote. Unknown coupon/maturity settlement and changed instrument terms block completion under the default policy."]
    lines += ["", "## Risk-module movement allocation", ""]
    for driver in result.get("drivers", []):
        lines.append(f"- {driver['module'].title()}: {driver['description']} Shapley contribution HKD {number(driver['shapley_change_hkd'])}; material: {driver['material']}.")
    lines += ["", "## Validation", "", "| Check | Result | Detail |", "|---|---|---|"]
    for check in result.get("validation", {}).get("checks", []):
        lines.append(f"| {check['name']} | {'PASS' if check['passed'] else 'FAIL'} | {check['details']} |")
    lines += ["",
             "## Methodology and assumptions", "",
             "Bonds use annual maturity-anniversary cashflows discounted at an effective risk-free yield plus credit spread, with actual/365.25 time. Prices are dirty values without accrued-interest or settlement modelling. Rate capital is the larger aggregate portfolio loss under parallel up/down stresses; spread capital and equity capital use fixed illustrative shocks. Cash has no modelled charge.", "",
             "Aggregate capital is sqrt(cᵀRc) using the documented illustrative positive semidefinite correlation matrix. Exact Shapley allocations across the three module replacements reconcile the nonlinear opening-to-closing movement. Attribution depends on this model and does not establish economic causality.", "",
             "## Regulatory references", ""]
    if citations:
        lines.extend(["Contextual references below do not calibrate the illustrative model or establish current compliance.", ""])
        for citation in citations:
            lines.append(f"- [{citation['title']}]({citation['url']}) — {citation['section']}; version `{citation['version']}`; published {citation.get('published_at') or 'unknown'}; reviewed {citation['reviewed_at']}. {citation.get('limitations', '')}")
    else:
        lines.append("No regulatory calibration is asserted. The application maintains separately versioned official evidence links; the stress assumptions and correlation matrix are internal demonstration choices.")
    lines += ["", "## Limitations and review", "",
              "No liabilities, taxes, operational risk, counterparty default model, matching adjustment, currency risk, rating-specific factors, regulatory floors, or full prescribed aggregation are implemented. Coupon conventions and flat curves are simplified. Large movements require actuarial review even where arithmetic reconciliation passes. Failed validation prevents completion. This prototype is not a certified compliance solution.", "",
              "## Audit and calculation records", "", "The local SQLite audit records demo identity, UTC timestamps, tool versions, validation status, provider, document versions accessed and report identifier. It excludes raw prompts and portfolios. Logs are local and are not tamper-proof.", "",
             f"Deterministic calculation ID: `{result.get('report_id', 'unknown')}`. The accompanying JSON export contains every synthetic input, per-asset output, function/version, assumptions, validations and limitations. Use both files for technical review.", ""]
    if result.get("analysis_id"):
        lines += [f"Combined analysis ID: `{result['analysis_id']}` · Workflow version: `{result['analysis_version']}` · Factor bridge ID: `{result['factor_bridge']['report_id']}`.", ""]
    return "\n".join(lines)
