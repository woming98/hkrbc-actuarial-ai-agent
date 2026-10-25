"""Local-first Streamlit interface for the HK RBC research prototype."""
from __future__ import annotations

import hashlib
from html import escape
import json
import os
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from hkrbc_agent.reporting import render_report
from hkrbc_agent.security import DEMO_PASSWORDS, Role
from hkrbc_agent.service import AgentService
from hkrbc_agent.store import Document


PAGES = ("Regulatory Assistant", "Capital Analysis", "Validation Dashboard", "Governance & Audit")
RESULT_KEYS = ("analysis_result", "scenario_result", "saved_report", "report_markdown", "input_error")
QUESTION_EXAMPLES = {
    "Commencement / 實施日期": "When did the HK RBC regime commence?",
    "Original tier caps / 原有資本上限": "原有第7條對 Limited Tier 1 與 Tier 2 的上限是甚麼？",
    "Scheduled amendment / 未來修訂": "What crypto stress is scheduled by the 2026 amendment?",
    "Current-law evidence gap / 現行法規證據不足": "What is the current prescribed correlation matrix?",
    "Compound evidence gap / 複合問題證據不足": "Summarize the 2026 announcement and calculate the matching adjustment formula.",
}


@st.cache_resource(show_spinner=False)
def interactive_tables_available() -> bool:
    """Keep the workbench usable if a host's optional Arrow binary is broken."""
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        return False
    return True


def show_table(frame: pd.DataFrame) -> None:
    if interactive_tables_available():
        st.dataframe(frame, hide_index=True, use_container_width=True)
    else:
        # All cell content is escaped before this generated HTML reaches the UI.
        preview = frame.head(200)
        formatters = {}
        for column in preview:
            if pd.api.types.is_float_dtype(preview[column]):
                precision = 6 if any(term in str(column).lower() for term in ("shift", "return", "duration", "yield", "coupon")) else 2
                formatters[column] = lambda value, precision=precision: f"{value:,.{precision}f}"
        st.markdown('<div style="overflow:auto;max-height:480px">' + preview.to_html(index=False, escape=True, border=0, classes="workbench-table", formatters=formatters, na_rep="—") + '</div>', unsafe_allow_html=True)
        if len(frame) > len(preview):
            st.caption(f"Showing {len(preview)} of {len(frame)} rows.")


def movement_chart(attribution: dict[str, float]) -> None:
    if interactive_tables_available():
        frame = pd.DataFrame({"Module": list(attribution), "Movement (HKD)": list(attribution.values())}).set_index("Module")
        st.bar_chart(frame, color="#187D8D", use_container_width=True)
        return
    scale = max((abs(value) for value in attribution.values()), default=1) or 1
    elements = ['<div role="img" aria-label="Shapley movement by module in HKD" style="padding:18px;background:white;border-radius:8px;border:1px solid #dce4ee">']
    for module, value in attribution.items():
        width = abs(value) / scale * 48
        position = "left:50%" if value >= 0 else "right:50%"
        color = "#187D8D" if value >= 0 else "#B24D5A"
        elements.append(f'<div style="display:flex;align-items:center;gap:12px;margin:12px 0;font:14px sans-serif;color:#142d4e"><span style="width:55px">{escape(module.title())}</span><div style="flex:1;position:relative;height:26px;background:#f6f8fb"><div style="position:absolute;left:50%;height:100%;border-left:1px solid #aab8c8"></div><div title="HKD {money(value)}" style="position:absolute;{position};width:{width:.3f}%;height:100%;background:{color}"></div></div><span style="width:115px;text-align:right">{money(value)}</span></div>')
    st.html("".join(elements) + "</div>")


def scenario_chart(rows: list[dict]) -> None:
    if interactive_tables_available():
        st.line_chart(pd.DataFrame(rows).set_index("scenario_id")[["pnl"]], color="#187D8D")
        return
    values = [row["pnl"] for row in rows]
    low, high = min(values), max(values)
    span = high - low or 1
    counts = [0] * 12
    for value in values:
        counts[min(11, int((value-low) / span * 12))] += 1
    maximum = max(counts) or 1
    bars = "".join(f'<div title="Bin {index+1}: {count} scenarios" style="flex:1;height:{count/maximum*100:.3f}%;min-height:1px;background:#187D8D"></div>' for index, count in enumerate(counts))
    st.html(f'<div role="img" aria-label="Illustrative scenario P and L histogram" style="padding:18px;background:white;border:1px solid #dce4ee;border-radius:8px;color:#142d4e;font:14px sans-serif"><div>Illustrative scenario P&amp;L distribution · HKD</div><div style="display:flex;align-items:flex-end;gap:4px;height:160px;margin-top:15px">{bars}</div><div style="display:flex;justify-content:space-between;margin-top:10px"><span>{money(low)}</span><span>{money(high)}</span></div></div>')


@st.cache_resource(show_spinner=False)
def get_service(database: str, seed_digest: str) -> AgentService:
    """Share the server-side service, never a user's session or query results."""
    service = AgentService(database)
    seed = ROOT / "data" / "documents" / "regulatory_seed.json"
    if seed_digest and seed.exists():
        token = service.auth.authenticate("admin", os.getenv("HKRBC_ADMIN_PASSWORD") or DEMO_PASSWORDS["admin"])
        service.seed(token, seed)
        supplement = ROOT / "data" / "documents" / "verified_supplement.json"
        if supplement.exists():
            service.seed(token, supplement)
    return service


def clear_results() -> None:
    for key in RESULT_KEYS:
        st.session_state.pop(key, None)


def load_demo(variant: str = "standard") -> None:
    files = {
        "standard": ("opening.csv", "closing.csv", "Bundled synthetic opening.csv and closing.csv"),
        "coupon_crossing": ("coupon_crossing_opening.csv", "coupon_crossing_closing.csv",
                            "Bundled synthetic coupon-crossing example; settlement is unobserved and the factor bridge requires review."),
    }
    opening, closing, label = files[variant]
    clear_results()
    st.session_state["opening_bytes"] = (ROOT / "data" / "portfolios" / opening).read_bytes()
    st.session_state["closing_bytes"] = (ROOT / "data" / "portfolios" / closing).read_bytes()
    st.session_state["input_label"] = label
    st.session_state["input_source"] = "demo"
    st.session_state["synthetic_confirmed"] = True
    st.session_state["synthetic_declaration"] = True
    st.session_state.pop("opening_upload", None)
    st.session_state.pop("closing_upload", None)


def upload_changed(stage: str) -> None:
    clear_results()
    if st.session_state.get("input_source") == "demo":
        # Selecting an upload starts a new pair; do not silently reuse half a demo.
        st.session_state.pop("opening_bytes", None)
        st.session_state.pop("closing_bytes", None)
    upload = st.session_state.get(f"{stage}_upload")
    st.session_state[f"{stage}_bytes"] = upload.getvalue() if upload is not None else None
    st.session_state["input_label"] = "Uploaded synthetic CSVs"
    st.session_state["input_source"] = "upload"
    st.session_state["synthetic_confirmed"] = False
    st.session_state["synthetic_declaration"] = False


def declaration_changed() -> None:
    st.session_state["synthetic_confirmed"] = st.session_state.get("synthetic_declaration", False)
    if not st.session_state["synthetic_confirmed"]:
        clear_results()


def money(value: float) -> str:
    return f"{value:,.2f}"


def limitations(values: list[str]) -> None:
    with st.expander("Scope, assumptions and limitations"):
        for value in dict.fromkeys(values):
            st.write(f"• {value}")


def validation_rows(result: dict, stage: str = "Movement") -> list[dict]:
    rows = [{"Stage": stage, "Check": item["name"], "Asset": item.get("asset_id", "—"),
             "Result": "PASS" if item["passed"] else "FAIL", "Details": item["details"]}
            for item in result.get("validation", {}).get("checks", [])]
    for key in ("opening", "closing", "factor_bridge"):
        if key in result:
            rows.extend(validation_rows(result[key], key.title()))
    return rows


def sidebar(service: AgentService):
    with st.sidebar:
        st.markdown("### HK RBC Workbench")
        st.caption("Evidence · Analysis · Review")
        with st.expander("Demonstration credentials"):
            st.caption("Public demo accounts. Server password overrides take precedence.")
            for username, password in DEMO_PASSWORDS.items():
                st.text(f"{username} / {password}")
        token = st.session_state.get("session_token")
        principal = None
        if token:
            try:
                principal = service.auth.resolve(token)
            except PermissionError:
                st.session_state.clear()
                st.warning("Session expired. Sign in again.")
        if principal is None:
            with st.form("login", clear_on_submit=True):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                submitted = st.form_submit_button("Sign in", use_container_width=True)
            if submitted:
                try:
                    new_token = service.sign_in(username.strip(), password)
                    # No results, uploads or approval carry across identities.
                    st.session_state.clear()
                    st.session_state["session_token"] = new_token
                    st.rerun()
                except PermissionError as exc:
                    st.error(str(exc))
            st.caption("Synthetic data only. These shared demo identities are intended for a local prototype.")
            return None, None, None
        identity = (principal.actor_id, principal.role.value)
        if st.session_state.get("active_identity") != identity:
            for key in list(st.session_state):
                if key != "session_token":
                    del st.session_state[key]
            st.session_state["active_identity"] = identity
        st.success(f"{principal.actor_id} · {principal.role.value}")
        if st.button("Sign out", use_container_width=True):
            st.session_state.clear()
            st.rerun()
        page = st.radio("Workspace", PAGES, key="page")
        st.divider()
        st.caption("HKD · local storage · deterministic calculations")
        return token, principal, page


def use_question_example() -> None:
    st.session_state["regulatory_question"] = QUESTION_EXAMPLES[st.session_state["question_example"]]
    st.session_state.pop("query_result", None)


def show_missing_coverage(scope: dict) -> None:
    reasons = []
    if scope.get("current_law_requested") and not scope.get("all_sources_current_verified"):
        reasons.append("The current consolidated rules have not been verified by these sources.")
    labels = {
        "matching_adjustment.formula": "matching-adjustment formula or numerical calculation",
        "matching_adjustment.eligibility": "matching-adjustment eligibility criteria",
        "capital.tier_instrument_eligibility": "eligibility of capital instruments",
        "capital.pca_calculation": "complete prescribed-capital calculation",
        "liability.tvog_calculation": "numerical TVOG calculation",
        "liability.tvog_proxy": "conditions for using a TVOG proxy",
        "capital.crypto_stress": "the requested crypto stress provision",
        "capital.equity_cca_bounds": "the requested countercyclical adjustment bounds",
    }
    for tag in scope.get("missing_claim_tags", []):
        reasons.append("Missing evidence for " + labels.get(tag, tag.rsplit(".", 1)[-1].replace("_", " ")) + ".")
    if scope.get("missing_rule_identifiers"):
        reasons.append("The exact requested provision is missing: " + ", ".join(scope["missing_rule_identifiers"]) + ".")
    if scope.get("missing_evidence_versions"):
        reasons.append("This comparison needs relevant evidence from both the historical baseline and the scheduled amendment.")
    if scope.get("classification_evidence_missing") or scope.get("missing_named_identifiers"):
        reasons.append("The requested source is not available in the evidence authorized for this account.")
    for reason in reasons:
        st.write("• " + reason)


def regulatory_page(service: AgentService, token: str, principal) -> None:
    st.header("Regulatory Assistant")
    st.write("Search authorized source paraphrases with section, version and date references.")
    external_available = service.router.settings.external_enabled and principal.role in (Role.REVIEWER, Role.ADMIN)
    options = ["Local evidence"] + (["Approved external commentary"] if external_available else [])
    mode_label = st.radio("Processing mode", options, horizontal=True, key="model_mode")
    external = mode_label == "Approved external commentary"
    st.caption("Local extractive retrieval is the default. A configured loopback model may add commentary; calculations always run in Python.")
    with st.expander("Example questions / 示範問題"):
        st.selectbox("Choose an example", list(QUESTION_EXAMPLES), key="question_example")
        st.button("Use example", on_click=use_question_example)
        st.caption("This fills the question only. Review it and select Search evidence to run it.")
    with st.form("regulatory_query", clear_on_submit=True):
        question = st.text_area("Regulatory question", placeholder="When did HK RBC commence? What does original rule 5 say?", key="regulatory_question", height=110)
        approved = st.checkbox("I approve sending this request and public evidence to the configured external API; charges may apply.", value=False) if external else False
        submitted = st.form_submit_button("Search evidence", type="primary")
    if submitted:
        st.session_state.pop("query_result", None)
        try:
            with st.spinner("Checking authorized evidence…"):
                st.session_state["query_result"] = service.ask(token, question, mode="external" if external else "local", approved=approved)
        except (ValueError, PermissionError, OSError, KeyError) as exc:
            st.error(str(exc))
    result = st.session_state.get("query_result")
    if not result:
        st.info("Try a question about commencement, the three pillars, capital thresholds or 2026 amendments.")
        return
    if result["status"] == "insufficient_evidence":
        st.warning("Evidence is incomplete for this question. The background sources do not establish the full requested conclusion.")
        show_missing_coverage(result.get("evidence_scope", {}))
        with st.expander("Retrieved background and limitations"):
            st.write(result["answer"])
    else:
        st.subheader("Retrieved evidence")
        st.write(result["answer"])
    st.caption(f"Status: {result['status']} · Provider: {result['provider']}")
    if result.get("pii_redacted"):
        st.caption("Potential personal data were redacted before local retrieval.")
    st.caption(f"Retrieval: {result.get('retrieval_method', 'legacy-hash')} · Current consolidated law remains a separate evidence check.")
    if result.get("evidence_scope"):
        with st.expander("Question coverage and evidence checks"):
            st.json(result["evidence_scope"])
    if result.get("commentary"):
        with st.expander("Optional model commentary — requires review"):
            st.write(result["commentary"])
    for citation in result["citations"]:
        with st.expander(f"{citation['title']} · {citation['section']}"):
            st.caption(f"{citation['reference']} · {citation['status']} · {citation['classification']}")
            st.write(f"Published: {citation.get('published_at') or 'unknown'} · Reviewed: {citation['reviewed_at']} · Effective from: {citation.get('effective_from') or 'not established'}")
            st.write(citation["provenance"])
            if citation.get("source_sha256"):
                st.caption(f"Source file SHA-256: {citation['source_sha256']} · PDF page: {citation.get('source_page') or 'n/a'} · Checked: {citation.get('source_checked_at')}")
            st.link_button("Open source", citation["url"])
    limitations(result["limitations"])


def render_analysis(result: dict) -> None:
    st.subheader("Capital movement · HKD")
    opening, closing = result["opening"], result["closing"]
    cols = st.columns(4)
    cols[0].metric("Opening illustrative capital", money(opening["aggregate_capital"]))
    cols[1].metric("Closing illustrative capital", money(closing["aggregate_capital"]))
    cols[2].metric("Capital movement", money(result["capital_movement"]))
    cols[3].metric("Unexplained residual", money(result["unexplained_residual"]))
    st.caption(f"{opening['valuation_date']} → {closing['valuation_date']} · Calculation version {result['function_version']}")
    if result["validation"]["passed"]:
        st.success("Deterministic validation passed. Review the assumptions before relying on the analysis.")
    else:
        st.error("Validation blocked completion. Review the failed checks in the Validation Dashboard.")
    movement_chart(result["shapley_attribution"])
    st.caption("Exact Shapley allocation includes diversification across the three illustrative modules. It allocates the model movement; it does not establish economic causality.")
    drivers = pd.DataFrame(result["drivers"]).rename(columns={"module": "Module", "standalone_change_hkd": "Standalone change (HKD)",
        "shapley_change_hkd": "Shapley change (HKD)", "material": "Material", "description": "Interpretation"})
    show_table(drivers)
    bridge = result.get("factor_bridge")
    if bridge:
        st.subheader("Date and input-factor bridge")
        st.caption("Date ageing first, then exact Shapley across holdings/equity value, risk-free yield and credit spread. This is an explicit counterfactual model, not a trade ledger.")
        if bridge.get("date_ageing") is not None:
            rows = [{"Factor": "Date ageing at opening quotes", "Movement (HKD)": bridge["date_ageing"]}]
            rows += [{"Factor": name.replace("_", " ").title(), "Movement (HKD)": value} for name, value in bridge["factor_attribution"].items()]
            rows.append({"Factor": "Unexplained factor-bridge residual", "Movement (HKD)": bridge["unexplained_residual"]})
            show_table(pd.DataFrame(rows))
        if not bridge["validation"]["passed"]:
            st.error("Factor bridge is blocked. Review instrument changes or unobserved coupon/maturity settlement.")
        with st.expander("Factor-bridge definitions, hybrid states and checks"):
            st.json(bridge)
    with st.expander("Portfolio valuation and sensitivities"):
        st.write(f"Opening value: HKD {money(opening['total_market_value'])} · Closing value: HKD {money(closing['total_market_value'])}")
        st.write(f"Closing portfolio DV01: HKD {money(closing['portfolio_dv01'])} per basis point")
        show_table(pd.DataFrame(closing["assets"]).drop(columns=["cashflows", "key_rate_durations"], errors="ignore"))
    limitations(result["limitations"])


def capital_page(service: AgentService, token: str) -> None:
    st.header("Capital Analysis")
    st.write("Compare synthetic opening and closing portfolios and reconcile the illustrative capital movement.")
    st.button("Load synthetic demo portfolios", on_click=load_demo)
    with st.expander("Validation example / 驗證示範"):
        st.caption("A second synthetic pair crosses a coupon date without a settlement ledger. Module arithmetic can reconcile while the factor bridge remains blocked.")
        st.button("Load missing-settlement example", on_click=load_demo, args=("coupon_crossing",))
    cols = st.columns(2)
    for col, stage in zip(cols, ("opening", "closing")):
        with col:
            st.file_uploader(f"{stage.title()} synthetic CSV", type=["csv"], key=f"{stage}_upload", on_change=upload_changed, args=(stage,))
            st.download_button(f"Download {stage} template", (ROOT / "data" / "portfolios" / f"{stage}.csv").read_bytes(), file_name=f"synthetic_{stage}.csv", mime="text/csv")
    st.caption(st.session_state.get("input_label", "Load the synthetic demo or upload two synthetic CSV files. UTF-8, HKD, maximum 2 MB per file."))
    if "synthetic_declaration" not in st.session_state:
        st.session_state["synthetic_declaration"] = st.session_state.get("synthetic_confirmed", False)
    declared = st.checkbox("I confirm these portfolios contain synthetic data only.", key="synthetic_declaration", on_change=declaration_changed)
    opening = st.session_state.get("opening_bytes")
    closing = st.session_state.get("closing_bytes")
    ready = bool(opening and closing and declared)
    if st.button("Run capital analysis", type="primary", disabled=not ready):
        clear_results()
        try:
            with st.spinner("Valuing assets, applying stresses and validating movement…"):
                st.session_state["analysis_result"] = service.analyse(token, opening, closing, declared_synthetic=declared)
        except (ValueError, PermissionError, OSError) as exc:
            st.session_state["input_error"] = {"Stage": "Input", "Check": "input_validation", "Asset": "—", "Result": "FAIL", "Details": str(exc)}
            st.error(str(exc))
    result = st.session_state.get("analysis_result")
    if result:
        render_analysis(result)
        if st.button("Create review report", disabled=not ready or not result["validation"]["passed"]):
            try:
                report_id, report_result = service.create_report(token, opening, closing, declared_synthetic=declared)
                st.session_state["saved_report"] = {"report_id": report_id, "result": report_result}
                st.session_state["report_markdown"] = render_report(report_id, report_result)
            except (ValueError, PermissionError, OSError) as exc:
                st.error(str(exc))
        report = st.session_state.get("saved_report")
        if report:
            st.caption(f"Saved report: {report['report_id']}")
            cols = st.columns(2)
            cols[0].download_button("Download report · Markdown", st.session_state["report_markdown"], file_name=f"hkrbc-{report['report_id']}.md", mime="text/markdown")
            cols[1].download_button("Download report · JSON", json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), file_name=f"hkrbc-{report['report_id']}.json", mime="application/json")
    with st.expander("Illustrative scenarios"):
        st.caption("Seeded independent one-year shocks; demonstration assumptions without regulatory or market calibration.")
        cols = st.columns(2)
        count = cols[0].number_input("Scenario count", min_value=1, max_value=1000, value=100, step=10)
        seed = cols[1].number_input("Random seed", min_value=0, max_value=2**32 - 1, value=42, step=1)
        if st.button("Generate scenarios", disabled=not ready):
            st.session_state.pop("scenario_result", None)
            try:
                st.session_state["scenario_result"] = service.scenarios(token, closing, count=int(count), seed=int(seed), declared_synthetic=declared)
            except (ValueError, PermissionError, OSError) as exc:
                st.error(str(exc))
        scenario_result = st.session_state.get("scenario_result")
        if scenario_result:
            st.caption(f"{scenario_result['count']} scenarios · Seed {scenario_result['seed']} · Status {scenario_result['status']}")
            frame = pd.DataFrame(scenario_result["scenarios"])
            scenario_chart(scenario_result["scenarios"])
            show_table(frame)
            st.download_button("Download scenarios · JSON", json.dumps(scenario_result, indent=2, allow_nan=False), file_name="illustrative-scenarios.json", mime="application/json")


def validation_page() -> None:
    st.header("Validation Dashboard")
    st.write("Inspect deterministic input, valuation, aggregation and reconciliation checks separately from narrative interpretation.")
    result = st.session_state.get("analysis_result")
    scenarios = st.session_state.get("scenario_result")
    rows = validation_rows(result) if result else []
    if st.session_state.get("input_error"):
        rows.append(st.session_state["input_error"])
    if scenarios:
        rows.extend(validation_rows(scenarios, "Scenarios"))
    if not rows:
        st.info("Run an analysis or generate scenarios in Capital Analysis to populate the validation checks.")
        return
    failed = [row for row in rows if row["Result"] == "FAIL"]
    cols = st.columns(3)
    cols[0].metric("Checks run", str(len(rows)))
    cols[1].metric("Passed", str(len(rows) - len(failed)))
    cols[2].metric("Failed / review required", str(len(failed)))
    if failed:
        st.error("Completion is blocked. Resolve the exceptions and rerun the analysis.")
    else:
        st.success("All displayed deterministic checks passed. This does not certify regulatory compliance.")
    tabs = st.tabs(["Checks", "Exceptions", "Calculation records"])
    with tabs[0]:
        show_table(pd.DataFrame(rows))
    with tabs[1]:
        if failed:
            show_table(pd.DataFrame(failed))
        else:
            st.write("No deterministic exceptions in the current results.")
    with tabs[2]:
        bundles = [("Movement", result)] if result else []
        if result:
            bundles += [("Opening", result["opening"]), ("Closing", result["closing"])]
            if result.get("factor_bridge"):
                bundles.append(("Factor bridge", result["factor_bridge"]))
        if scenarios:
            bundles.append(("Scenarios", scenarios))
        for stage, bundle in bundles:
            for index, record in enumerate(bundle.get("calculations", []), 1):
                with st.expander(f"{stage} · {record['function']} · {record['version']} · {index}"):
                    st.json(record)


def retire_evidence_version(service: AgentService, token: str) -> None:
    """Apply the form action before the next render reads the document register."""
    try:
        document_id, version = st.session_state["retirement_target"].split("@", 1)
        replacement = st.session_state["retirement_successor"]
        service.retire_document(token, document_id, version,
            replacement_reference=None if replacement == "No replacement" else replacement)
        st.session_state["governance_notice"] = "Version retired from retrieval. Its source payload remains unchanged."
    except (ValueError, PermissionError) as exc:
        st.session_state["governance_error"] = str(exc)


def governance_page(service: AgentService, token: str, principal) -> None:
    st.header("Governance & Audit")
    notice = st.session_state.pop("governance_notice", None)
    if notice:
        st.success(notice)
    error = st.session_state.pop("governance_error", None)
    if error:
        st.error(error)
    st.write("Review versioned evidence and the audit records available to your signed-in role.")
    documents = service.documents(token, include_lifecycle=True)
    audit = service.audit(token)
    cols = st.columns(3)
    cols[0].metric("Visible evidence sections", str(len(documents)))
    cols[1].metric("Visible audit records", str(len(audit)))
    cols[2].metric("Role", principal.role.value)
    tabs = st.tabs(["Document register", "Audit trail", "Administration"])
    with tabs[0]:
        st.caption("Documents are filtered by server-side role permissions. Status and review date are evidence metadata, not a completeness assertion.")
        if documents:
            fields = ["document_id", "version", "title", "section", "status", "retrieval_state", "classification", "published_at", "reviewed_at", "effective_from", "source_page"]
            show_table(pd.DataFrame([{key: document.get(key) for key in fields} for document in documents]))
            for document in documents:
                with st.expander(f"{document['document_id']}@{document['version']} · {document['title']}"):
                    st.write(document["text"])
                    st.caption(document["provenance"])
                    st.caption(document["redistribution"])
                    if document.get("source_sha256"):
                        st.caption(f"Source SHA-256: {document['source_sha256']}")
                    if document.get("retirement"):
                        st.json(document["retirement"])
                    st.link_button("Open source", document["url"])
        else:
            st.info("No evidence sections are visible to this role yet.")
    with tabs[1]:
        st.caption("Analysts see their own audit events. Reviewers and administrators see all demo events. Timestamps use UTC; logs are local and are not tamper-proof.")
        if audit:
            table = [{**row, "details": json.dumps(row["details"], ensure_ascii=False)} for row in audit]
            show_table(pd.DataFrame(table))
        else:
            st.info("No audit events available.")
    with tabs[2]:
        if principal.role != Role.ADMIN:
            st.info("Document ingestion is available to administrators.")
            return
        st.write("Upload a versioned JSON array of at most 100 document sections. Maximum file size: 2 MB.")
        st.download_button("Download document schema", json.dumps(Document.model_json_schema(), indent=2), file_name="document-schema.json", mime="application/json")
        with st.form("ingest_documents", clear_on_submit=True):
            upload = st.file_uploader("Document batch JSON", type=["json"])
            submitted = st.form_submit_button("Ingest document batch")
        if submitted:
            try:
                if upload is None:
                    raise ValueError("Select a JSON batch first")
                raw = upload.getvalue()
                if len(raw) > 2_000_000:
                    raise ValueError("Document batch exceeds 2 MB")
                records = json.loads(raw.decode("utf-8-sig"))
                count = service.ingest(token, records)
                st.session_state["governance_notice"] = f"Ingested {count} versioned sections."
                st.rerun()
            except (ValueError, PermissionError, UnicodeError, OSError) as exc:
                st.error(str(exc))
        st.divider()
        st.subheader("Retire an evidence version")
        st.caption("Retirement excludes an old version before retrieval while preserving its original bytes and existing report references. A replacement is an explicit curator decision.")
        eligible = [f"{doc['document_id']}@{doc['version']}" for doc in documents if doc["retrieval_state"] == "eligible"]
        if eligible:
            with st.form("retire_version"):
                st.selectbox("Version to retire", eligible, key="retirement_target")
                st.selectbox("Replacement version", ["No replacement"] + eligible, key="retirement_successor")
                st.form_submit_button("Retire version", on_click=retire_evidence_version, args=(service, token))


def main() -> None:
    st.set_page_config(page_title="HK RBC · Actuarial Workbench", page_icon="◈", layout="wide")
    st.markdown("""<style>
        .stApp { background-color: #f6f8fb; }
        [data-testid="stSidebar"] { background-color: #eaf0f6; }
        h1,h2,h3 { color: #142d4e; }
        [data-testid="stMetric"] { background: white; padding: 18px; border-radius: 10px; border: 1px solid #dce4ee; }
        .block-container { padding-top: 2rem; padding-bottom: 3rem; }
        .workbench-table { width:100%; border-collapse:collapse; font-size:0.88rem; background:white; }
        .workbench-table th,.workbench-table td { padding:10px; border-bottom:1px solid #dce4ee; text-align:left; vertical-align:top; }
        .workbench-table th { color:#142d4e; background:#edf2f7; }
        </style>""", unsafe_allow_html=True)
    st.caption("HK RBC / ACTUARIAL RESEARCH & VALIDATION")
    st.title("Actuarial Workbench")
    st.warning("Research prototype · Evidence includes historical baselines; verify the current consolidated rules. Capital figures are illustrative HKD asset stresses, not statutory HK RBC capital.")
    seed = ROOT / "data" / "documents" / "regulatory_seed.json"
    supplement = ROOT / "data" / "documents" / "verified_supplement.json"
    seed_bytes = seed.read_bytes() if seed.exists() else b""
    digest = hashlib.sha256(seed_bytes + (supplement.read_bytes() if supplement.exists() else b"")).hexdigest() if seed_bytes else ""
    database = os.getenv("HKRBC_DB_PATH") or str(ROOT / "runtime" / "demo.sqlite")
    try:
        service = get_service(database, digest)
    except (ValueError, PermissionError, OSError) as exc:
        st.error(f"Could not initialize the local evidence store: {exc}")
        st.stop()
    token, principal, page = sidebar(service)
    if not token:
        st.info("Sign in using a demonstration account to open the workbench.")
        st.write("Use versioned regulatory evidence, compare synthetic portfolios, inspect deterministic validation, and export review reports.")
        st.stop()
    if not digest:
        st.info("The curated regulatory seed is not present; document ingestion is available to an administrator.")
    try:
        if page == "Regulatory Assistant":
            regulatory_page(service, token, principal)
        elif page == "Capital Analysis":
            capital_page(service, token)
        elif page == "Validation Dashboard":
            validation_page()
        elif page == "Governance & Audit":
            governance_page(service, token, principal)
    except (ValueError, PermissionError, OSError) as exc:
        st.error(str(exc))


if __name__ == "__main__":
    main()
