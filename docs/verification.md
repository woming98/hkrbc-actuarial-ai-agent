# Verification record

Verified locally on 2026-10-24 (Asia/Shanghai). No upstream repositories were modified. Initial verification used a separate local Git repository before any remote was configured; GitHub upload is a subsequent, explicitly authorized step. No public application deployment, paid model calls or model downloads were made.

## Actual executions

| Check | Observed result |
|---|---|
| `python -m pytest -q` | **258 passed in 8.69s** |
| Final HTML-chart UI/integration regression run | **18 passed in 5.70s** |
| `python evaluation/run.py` | **C offline fixture checks: 8/8; A: not_run; B: not_run** |
| `python scripts/run_demo.py --output-dir runtime/demo-artifacts` | Local cited answer; sample movement complete; malformed file blocked; seeded scenario checks passed; report/audit generated |
| `python -m compileall -q src app.py evaluation scripts` | Completed without syntax errors |
| Wheel build and local virtual-environment install, no dependency downloads | Succeeded with normal `pip install --no-build-isolation --no-deps .` |
| Live Streamlit on `127.0.0.1:8501` | Started; actual browser login, authorized source response and synthetic capital workflow checked |

The tests include analytical numerical references, independent Cholesky aggregation, finite differences for duration/DV01, exact Shapley telescoping, invalid assumptions/files, reproducible scenarios, signed sessions, role filters, prompt injection, external-routing/DLP gates, metadata-only audit, atomic version ingestion, temporal evidence, report ownership, malformed provider responses and Streamlit interaction flows. These test counts are not performance benchmarks or certification.

The AppTest suite covers invalid login, all four pages, synthetic analysis/report/scenarios, sign-out clearing data, declaration invalidation, external approval, malformed-input exceptions retained on the Validation Dashboard, and a large movement blocking completion. Integration tests also check an invalid session clears stale UI state. Real model transports are replaced with explicit local test doubles; offline evaluation installs a transport that fails if called.

## Tested environment

| Component | Version |
|---|---|
| Python | 3.13.12 |
| Platform | macOS 13.3 ARM64 |
| Streamlit | 1.45.1 |
| Pydantic | 2.9.2 |
| NumPy | 2.3.4 |
| pandas | 2.3.3 |
| pytest | 8.3.4 |
| SQLite | 3.51.2 |

The project-local `.venv` inherits the existing Anaconda packages; this is not a clean dependency-install test. The initial editable build failed because the installed setuptools encoded the Chinese workspace path as ASCII. A normal wheel build/install succeeded; the documented commands therefore use a normal install. Dependency ranges are declared, not claimed to be a fully locked or universally tested matrix.

The host's optional PyArrow native import fails due to an existing libprotobuf/libabsl mismatch. The UI detects this and uses escaped HTML tables and HTML bar charts. A live browser check also caught Streamlit's sanitizer removing an initial SVG fallback; the delivered fallback uses supported HTML elements and the Shapley chart was checked visually. [The actual browser screenshot](../reports/app-preview.jpg) shows the synthetic capital results. Healthy environments can use Streamlit's normal interactive tables/charts. No global package or native library was changed.

## Measured fixture outputs

The bundled portfolios (2025-12-31 and 2026-09-30) produce:

```text
Opening illustrative capital: HKD 20,224,927.84
Closing illustrative capital: HKD 22,615,906.43
Capital movement:            HKD  2,390,978.59
Rate Shapley:                HKD   -113,353.33
Credit Shapley:              HKD   -144,084.41
Equity Shapley:              HKD  2,648,416.33
Unexplained residual:        HKD          0.00
```

Rounding the displayed module allocations can produce a one-cent sum difference; unrounded calculations reconcile within tolerance. Outputs are illustrative asset stresses, not prescribed capital or a solvency assessment.

## Remaining unverified work

- Real Ollama/LLM model quality, availability and end-to-end compatibility; live OpenAI credentials, account access, billing, model compatibility and vendor retention.
- Formal same-LLM A/B/C comparison; only local C fixture behavior is measured. External result-file scoring exists but contains no invented observations.
- Current consolidated Cap.41R text, complete amendment history, later notices and precise operative calibrations; some source excerpts were verified through official search-index text because direct PDFs could not be retrieved.
- Docker build/run, clean installs on other platforms/Python versions, production hosting, real authentication/tenant isolation, encrypted storage, immutable audit and enterprise DLP.
- Liabilities, regulatory capital resources, prescribed risk factors/aggregation, matching adjustment and full HK RBC compliance.

The optional Chat Completions body was checked against [official OpenAI documentation](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create); tests confirm its storage flag, output bound and failure handling without making any API request. API schema review does not establish real provider behavior or retention guarantees.
