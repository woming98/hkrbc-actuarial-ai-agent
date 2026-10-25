# Second-round verification — 25 October 2026

Version **0.2.0** strengthens the first working prototype with inspected source bytes, measured bilingual retrieval, explicit counterfactual movement drivers and immutable evidence retirement. This record supersedes the outstanding-source/encoder items in the [initial verification snapshot](verification.md), while preserving its historical results. It does not certify production readiness, legal currency or full HK RBC implementation.

## Actual executions

| Check | Observed result |
|---|---|
| `python -m pytest -q` | **374 passed in 14.76s** on the final code |
| Clean GitHub Linux / Python 3.11.17 | **374 passed in 16.81s**; provenance, 8/8 offline fixtures, lexical retrieval diagnostics and demo passed |
| Clean GitHub Linux / Python 3.13.16 | **374 passed in 19.81s**; the same subsequent checks passed |
| `python scripts/verify_source_register.py --require-cache` | 12 supplementary records; both registered primary PDFs matched cached file sizes/SHA; current consolidated verification remains false |
| `python evaluation/run.py` | Offline C fixtures **8/8**; A and B **not_run** |
| English and multilingual `evaluation/retrieval_eval.py --model-path ...` | Both real local encoders loaded on CPU; all four rankers measured on the same 44 diagnostic cases; zero unauthorized hits |
| `python scripts/run_demo.py --output-dir runtime/phase2-demo` | Cited local answer, complete sample factor bridge/report, malformed upload blocked, seeded scenarios passed |
| `python -m pip install --no-build-isolation --no-deps .` | Built and installed application wheel **0.2.0** without dependency downloads |
| `python -m compileall -q src app.py evaluation scripts`; `git diff --check` | Passed |
| Actual local Streamlit browser | Analyst sign-in, Chinese original-rule-7 response and synthetic capital/factor table inspected |
| Pinned public model metadata endpoints | Both exact revision responses and Apache-2.0 declarations checked; no weights re-downloaded for this check |

Tests run without model transport. New numerical checks use 50-digit Decimal references, explicit cashflows, multiple finite-difference step sizes, independent subset-weight Shapley arithmetic and bridge invariants. Source tests check exact provenance metadata and reject missing/tampered/escaped caches. Governance tests cover old-database byte preservation, protected replacement references and retirement persistence. UI tests exercise the retirement callback and register refresh. Model-loader/provisioner tests use tiny invented fixtures; separate real model runs establish that both approved snapshots actually load and encode.

The environment remains the Mac/Anaconda-inheriting Python 3.13.12 environment described in the initial record. It is not a clean install or a cross-platform test. Optional PyArrow is still unavailable due to the host's native-library mismatch; escaped HTML tables/charts were visually inspected. No global package repair was attempted.

The [initial clean Linux CI run](https://github.com/woming98/hkrbc-actuarial-ai-agent/actions/runs/40153320318) installed successfully but failed 7 tests on each Python version, with 367 passing. Streamlit 1.66.1 removed the AppTest internal `filtered_state` attribute used by those assertions. Tests now use public `app.session_state[key]` reads and catch only `KeyError` for absence; all positive/negative assertions are retained, with no skips or old-version pin. The updated UI/integration tests also passed on local Streamlit 1.45.1 (19/19).

The [subsequent complete CI run](https://github.com/woming98/hkrbc-actuarial-ai-agent/actions/runs/40153525240) passed both clean Linux jobs at application/test commit `384d73233d435767afc4acf02cbd074aa9e4312a`, including every workflow step and evaluation artifact upload. Both jobs installed Streamlit 1.66.1, pandas 2.3.3, Pydantic 2.14.1, PyArrow 26.0.0 and pytest 8.4.2. NumPy was 2.4.6 on Python 3.11 and 2.5.4 on Python 3.13. This establishes those observed combinations, not a locked environment or universal compatibility. Semantic weights/provisioning and generative providers were not run in CI. This final documentation-only follow-up records the observed result without rerunning unchanged application/tests.

## Source evidence

The unchanged original seed is accompanied by **12 short original paraphrases** checked against actual official LegCo-hosted L.N. 62/2024 and L.N. 58/2026 PDFs. The supplement records file SHA-256, one-based PDF page, printed provision, verification date, narrow claim tags and historical/future scope. The [verification record](source-verification-2026-10-25.md) distinguishes actual PDF downloads from 403 responses, configuration HTML and misleading HTML redirects.

The corpus is still incomplete. Every record has `current_consolidated_verified=false`. The 2026 amendment records are future evidence with scheduled commencement on 31 December 2026; they cannot establish the rules operative on the verification date. Raw PDFs, full extracts, rendered source pages and model weights remain in ignored local caches and are not distributed. Hashes do not establish legal currency, semantic entailment or redistribution rights.

## Retrieval measurements and decision

The [44-case diagnostic](retrieval-evaluation.md) has frozen queries, manually reviewed relevance labels, corpus/case/implementation hashes and per-case raw outputs. Both final encoder artifacts match the delivered source hashes. It is a development set used during implementation, not an independent held-out benchmark. Rankers share the same upgraded scope checker.

| Method | Recall@3 | MRR@3 | Answered without a labeled relevant section |
|---|---:|---:|---:|
| Original hash | 0.779 | 0.760 | 1 |
| BM25F + MMR | **0.956** | **0.951** | **0** |
| English dense | 0.691 | 0.657 | 1 |
| English hybrid | 0.926 | 0.863 | 1 |
| Multilingual dense | 0.868 | 0.833 | 2 |
| Multilingual hybrid | 0.926 | 0.892 | 1 |

All methods returned zero unauthorized hits and zero answerable statuses on the 18 authored unsupported/inaccessible/current-law cases. The last column prevents that status-only result from hiding wrong-section retrieval on supported questions. Neither metric establishes sentence-level legal correctness.

**BM25 remains the default.** This is a deliberate deviation from the initial local-embedding-by-default preference: actual bilingual diagnostic results favor the lexical method, which also needs no weight download. Dense/hybrid modes are implemented and measured as explicit local options. This narrow finding is not a universal ranking claim.

Review found that SentenceTransformers can import custom local modules despite `trust_remote_code=False`. The final adapter therefore validates the approved model/revision, application-pinned manifest SHA, every file size/SHA, exact inventory and builtin module/configuration graph **before importing the model library**. It accepts only two reviewed snapshots. Provisioning pins those revisions, constrains HTTPS redirects, refuses existing destinations and publishes a fully staged snapshot without overwriting. Trusted host packages/operators remain outside this boundary; hashes are not publisher signatures. No user prompt, portfolio or credential is sent by provisioning. Actual inference runs used offline controls and local safetensors.

## Movement and lifecycle behavior

The sample still moves from HKD20,224,927.84 to HKD22,615,906.43. Its separate [factor bridge](movement-attribution.md) is:

| Leg | HKD |
|---|---:|
| Date ageing at opening quotes | -924,090.62 |
| Holdings and equity/cash values | 3,165,983.67 |
| Risk-free yields | 277,386.92 |
| Credit spreads | -128,301.37 |
| Unexplained factor residual | 0.00 |

Date ageing is first; subsequent factors use all eight hybrid states and all six replacement orders. This is model attribution, not reconstructed transaction causality. The equity snapshot cannot separate prices, quantities and flows. The new coupon-crossing CSV pair demonstrates a blocked combined analysis despite a zero module-level residual: unknown coupon settlement prevents the default factor bridge. Missing factor values remain `None`, rather than fictitious zeros. Saved blocked review reports retain their blocked status.

Retirement changes retrieval eligibility in a separate immutable table. It preserves original document payload bytes/checksums and historical report references, and filters retired versions before lexical or semantic processing. Successor metadata respects role access. Re-seeding does not reactivate retired versions. The admin form applies retirement before rendering the refreshed register.

See the regenerated [Markdown report](../reports/example-actuarial-report.md), [full JSON records](../reports/example-actuarial-report.json) and [actual factor-table screenshot](../reports/factor-bridge-preview.jpg).

## Remaining work

- Real generative Ollama/OpenAI integration and formal same-LLM A/B/C evaluation remain unrun; no paid API requests were made. Encoder measurements are not LLM evaluations.
- Full current consolidated law, exhaustive amendments, precise prescribed calibrations and insurer-specific decisions remain unverified. Capital is illustrative and asset-only.
- Independent held-out retrieval questions, broader distractor corpora, sentence-level entailment, production-scale indexing and truncation-aware semantic chunking remain necessary for broader claims.
- Docker, production IAM/tenant isolation, encrypted persistence, immutable external audit and enterprise DLP remain outside the verified scope. Clean Linux installs are covered only by the observed CI matrix, not every dependency/platform combination.
- The installed `.github/workflows/verify.yml` runs offline checks on Python 3.11 and 3.13. It does not run model provisioning, paid LLMs or semantic retrieval with actual weights, and it does not establish branch protection.

No public application hosting, source-PDF redistribution or upstream repository modification was performed.
