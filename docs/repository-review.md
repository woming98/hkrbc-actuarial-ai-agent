# Upstream repository review

Reviewed on **24 October 2026 (Asia/Shanghai)** using the connected GitHub plugin, read-only. This report records the inspected snapshots, useful interfaces, licensing evidence and implementation caveats. It is a source-code review, not an independent actuarial sign-off or a current-law verification. No upstream code, data or HTML was copied into the application; no upstream repository was modified.

## Decision

Build the core calculations independently from mathematical definitions and verified official sources. Treat these repositories as secondary technical references and optional integration targets. In particular, do not label the asset-model's educational charges as prescribed HK RBC capital, and do not infer regulatory compliance from its ESG martingale messages.

There is no complete license file in any of the four reviewed trees. Three repositories have no license declaration in their own README. The fourth README claims MIT but links to an absent `LICENSE` file. A page in `hkrbc-notes` also describes `hkrbc-esg` as MIT, without supplying the license text. These are incomplete, inconsistent licensing signals; retain links and metadata, implement original logic, and avoid vendoring source until the intended license and required notices are established.

## Reproducible snapshots

All repositories were public, unarchived, and used `main` as their default branch when inspected. The full recursive tree response for each had `truncated=false`.

| Repository | Reviewed commit | Commit time (UTC) | Main contents |
|---|---|---|---|
| [hkrbc-notes](https://github.com/woming98/hkrbc-notes) | [`87fcbc34cb9492c407906ea1054e88cb7ff09146`](https://github.com/woming98/hkrbc-notes/commit/87fcbc34cb9492c407906ea1054e88cb7ff09146) | 2026-05-25 16:37:38 | HTML technical notes and workflow reference |
| [hkrbc-esg](https://github.com/woming98/hkrbc-esg) | [`a9d3bf2cdf30464bd9be364e81b093155ef5cb9d`](https://github.com/woming98/hkrbc-esg/commit/a9d3bf2cdf30464bd9be364e81b093155ef5cb9d) | 2026-05-27 11:54:29 | Python economic scenario generation and calibration |
| [hkrbc-asset-model](https://github.com/woming98/hkrbc-asset-model) | [`abaa05c813dfb81d22400ce1ecb0ace74e6dc616`](https://github.com/woming98/hkrbc-asset-model/commit/abaa05c813dfb81d22400ce1ecb0ace74e6dc616) | 2026-05-25 15:57:26 | Python asset analysis, Streamlit dashboard and educational capital stresses |
| [ifrs17-subledger](https://github.com/woming98/ifrs17-subledger) | [`ee03a549edea8173f278c8c14480b4825d5ed631`](https://github.com/woming98/ifrs17-subledger/commit/ee03a549edea8173f278c8c14480b4825d5ed631) | 2026-05-28 15:15:53 | Python IFRS 17 AOC and journal-entry demonstration |

GitHub repository metadata returned `license: null` for every repository. This is GitHub's detection result, not conclusive proof that no rights were granted elsewhere. The evidence below distinguishes explicit declarations from absent files.

## Licensing evidence

| Repository | Evidence at inspected commit | Reuse decision |
|---|---|---|
| hkrbc-notes | [README](https://github.com/woming98/hkrbc-notes/blob/87fcbc34cb9492c407906ea1054e88cb7ff09146/README.md) states study/reference purpose. Tree contains only `.gitignore`, two HTML files, README and Vercel config; no license file. [Workflow HTML](https://github.com/woming98/hkrbc-notes/blob/87fcbc34cb9492c407906ea1054e88cb7ff09146/HKRBC_Workflow.html#L9643) has a personal-study disclaimer. | Use as a cited secondary reference; do not redistribute the HTML or prose as licensed application content. |
| hkrbc-esg | [README](https://github.com/woming98/hkrbc-esg/blob/a9d3bf2cdf30464bd9be364e81b093155ef5cb9d/README.md) calls the project open source and for learning/reference, but does not specify a license. No license file in the full tree. [hkrbc-notes line 1422](https://github.com/woming98/hkrbc-notes/blob/87fcbc34cb9492c407906ea1054e88cb7ff09146/HKRBC_Workflow.html#L1422) calls this ESG project MIT; the corresponding text and notice are absent from the ESG repository. | Preserve metadata and design independent calculations; defer direct source reuse pending clear license evidence. |
| hkrbc-asset-model | [README](https://github.com/woming98/hkrbc-asset-model/blob/abaa05c813dfb81d22400ce1ecb0ace74e6dc616/README.md) has learning/reference and mock-data disclaimers, but no license declaration. No license file in the full tree. | Independent implementation only. |
| ifrs17-subledger | [README](https://github.com/woming98/ifrs17-subledger/blob/ee03a549edea8173f278c8c14480b4825d5ed631/README.md) includes an MIT badge and ends with an MIT copyright declaration. Its linked `LICENSE` is absent from the full tree; metadata detection is null. | There is evidence of MIT intent, but no complete grant/notice artifact was verified. Keep the adapter independent and avoid copying code or fixtures in this version. |

## hkrbc-notes

The [workflow HTML](https://github.com/woming98/hkrbc-notes/blob/87fcbc34cb9492c407906ea1054e88cb7ff09146/HKRBC_Workflow.html) is a broad bilingual technical reference covering EBS, matching adjustment, PCA risk modules, participating funds, ESG, asset share, TVOG, ALM and IFRS 17. It contains narrative explanations, tables, example formulas and scripts for navigation. It is not a packaged calculation engine or a normative rules database.

The README section numbering and the inspected HTML headings are not fully aligned. For example, the README presents ESG/TVOG subsections under section 9, whereas the current HTML has ESG under section 8 and TVOG under section 10. An ingestion pipeline should use the document's actual heading IDs and content hash, rather than relying on README section numbers.

Suitable interface: a source manifest with repository URL, commit, file path, content hash, heading anchor and retrieval date. Retrieve small relevant passages for citation only when authorized; prefer official rules as the authoritative corpus. The HTML's references to Cap. 41R and GL34 are useful leads for official-source verification, not proof that every paraphrase or example is current or exact. There is no standalone test suite or CI configuration in this snapshot.

## hkrbc-esg

### Interfaces and compatibility

Inspected the README, requirements, YAML config, yield-curve implementation, HW1F simulation, martingale diagnostics, scenario exporter, G2++ calibration source and swaption data header. Other model files exist for HW2F, LMM, equity, CIR credit, FX, property and inflation, but were not all audited line by line.

The [requirements](https://github.com/woming98/hkrbc-esg/blob/a9d3bf2cdf30464bd9be364e81b093155ef5cb9d/requirements.txt) require NumPy, SciPy, pandas, PyYAML and matplotlib with lower bounds only. There is no lockfile or packaged distribution metadata in the reviewed tree. Source imports use a top-level `src` package, so an adapter process should isolate its working directory or module search path to avoid collisions with the subledger's own `src` package.

Useful public surfaces:

- [`YieldCurve`](https://github.com/woming98/hkrbc-esg/blob/a9d3bf2cdf30464bd9be364e81b093155ef5cb9d/src/yield_curve.py#L48) accepts maturities and continuous zero rates, and exposes spot rates, discount factors and instantaneous forward rates.
- [`HullWhite1F.simulate`](https://github.com/woming98/hkrbc-esg/blob/a9d3bf2cdf30464bd9be364e81b093155ef5cb9d/src/hw1f.py#L63) accepts scenario count, steps, year fraction, seed, optional external normal draws and an antithetic switch. It returns rate and cumulative discount-factor matrices of shape `(scenarios, steps+1)`.
- [`export_to_csv`](https://github.com/woming98/hkrbc-esg/blob/a9d3bf2cdf30464bd9be364e81b093155ef5cb9d/src/scenario_output.py#L27) exports `scenario`, `time_yr`, `rfr_short`, `disc_factor`, `eq_total_return`, `credit_spread`, `fx_rate`, `prop_return`, `cpi_index`, and `inflation_rate`. Scenario identifiers start at 1; times are years; annual rates are decimals; cumulative indices start near 1.
- [`calibrate_G2`](https://github.com/woming98/hkrbc-esg/blob/a9d3bf2cdf30464bd9be364e81b093155ef5cb9d/src/calibrate.py#L251) consumes a swaption surface with `expiry_yr`, `tenor_yr`, `normal_vol_bps` and optional weights, and returns parameters plus fitted-volatility and convergence diagnostics.

A robust CSV bridge should require unique `(scenario, time_yr)` pairs, a common increasing grid, finite rates, positive discount factors and return indices, explicit currency, valuation date, probability measure, calibration provenance and random seed. The upstream CSV has no schema-version or measure metadata, so provide that in a sidecar manifest rather than guessing.

### Exact versus approximate behavior

1. **Initial curve:** [`yield_curve.py`](https://github.com/woming98/hkrbc-esg/blob/a9d3bf2cdf30464bd9be364e81b093155ef5cb9d/src/yield_curve.py) splines maturity times zero rate with SciPy `CubicSpline(extrapolate=True)`. It does not implement Smith–Wilson or enforce convergence to the configured UFR. The YAML contains UFR/LLP fields, but their presence does not make the spline a prescribed extrapolator. Supply a complete dated official curve within its supported range or explicitly label an independent extrapolation.
2. **HW1F transition versus discounting:** conditional short-rate transitions use the analytical normal transition, but [`simulate`](https://github.com/woming98/hkrbc-esg/blob/a9d3bf2cdf30464bd9be364e81b093155ef5cb9d/src/hw1f.py#L63) accumulates discounts from the rate at the start of each step. The rate transition is exact for that model; the path integral is a time-discretization approximation.
3. **Antithetic edge case:** the internal antithetic branch creates `2 × floor(N/2)` draws. An odd scenario count does not match the allocated `N` paths. Validate counts or implement an independently tested odd-count policy.
4. **Martingale diagnostics:** [`test_bond_martingale`](https://github.com/woming98/hkrbc-esg/blob/a9d3bf2cdf30464bd9be364e81b093155ef5cb9d/src/martingale_test.py#L25) silently skips check tenors beyond the simulation horizon; an empty set of checks can be marked passed. Equity diagnostics restrict the checked horizon and use a fixed error tolerance. These are diagnostic utilities, not regulatory certification. Independent checks should require nonempty coverage and report convergence, timestep error and Monte Carlo uncertainty; antithetic paths should be treated as dependent pairs when estimating uncertainty.
5. **Calibration data:** the [swaption CSV header](https://github.com/woming98/hkrbc-esg/blob/a9d3bf2cdf30464bd9be364e81b093155ef5cb9d/data/swaption_vols_hkd.csv) identifies the surface as approximate 2024 reference values rather than live quotes. The config's spot rates and model parameters also lack a validated market-data observation date.
6. **Regulatory claims:** the README asserts a minimum scenario count, particular UFRs and Rule 19 compliance. Those claims were not independently established by this code review and must not enter an authoritative answer as verified facts. A martingale test alone does not establish market calibration or validate policyholder behavior, management actions, asset credit losses or TVOG liability projections.
7. **Prophet export:** the `.ESC` writer emits a simple text header and three factor columns. Compatibility with a specific Prophet product, version and configured interface was not tested; call this an upstream sample interchange format until round-trip evidence exists.

There is a martingale diagnostic module, but no dedicated test directory, pytest configuration, lockfile or CI workflow in this snapshot. No upstream simulation or calibration was executed for this review.

## hkrbc-asset-model

### Interfaces and compatibility

Inspected README, requirements, bond, curve, portfolio, risk engine, ESG loader and sample holdings headers. The [requirements](https://github.com/woming98/hkrbc-asset-model/blob/abaa05c813dfb81d22400ce1ecb0ace74e6dc616/requirements.txt) use pandas, NumPy, SciPy, Streamlit, Plotly and openpyxl with unpinned lower bounds. No package metadata, lockfile, automated test suite or CI workflow was present.

Useful boundaries are CSV holdings, [`Portfolio.from_csv`](https://github.com/woming98/hkrbc-asset-model/blob/abaa05c813dfb81d22400ce1ecb0ace74e6dc616/core/portfolio.py#L41), and [`ESGLoader`](https://github.com/woming98/hkrbc-asset-model/blob/abaa05c813dfb81d22400ce1ecb0ace74e6dc616/esg_connector/loader.py#L17). Holdings fields include instrument identifier, asset class/type, currency, face amount or shares, coupon/frequency, dates and ratings. The ESG loader requires `scenario`, `time_yr`, `rfr_short`, `disc_factor`, `eq_total_return` and `credit_spread`, matching the ESG export.

A file bridge is preferable to importing this Streamlit application into the analysis agent. Normalize as-of date, amounts, reporting currency, day-count conventions and curve conventions at the boundary. The sample holdings are expressly fictional. The asset model's yield curve uses linearly interpolated rates with flat endpoint extrapolation, while the ESG model uses continuously compounded log-discount splines; their rate objects are not interchangeable.

### Material model limits

The [README](https://github.com/woming98/hkrbc-asset-model/blob/abaa05c813dfb81d22400ce1ecb0ace74e6dc616/README.md) and [`hkrbc_risk.py`](https://github.com/woming98/hkrbc-asset-model/blob/abaa05c813dfb81d22400ce1ecb0ace74e6dc616/core/hkrbc_risk.py) explicitly state that the risk factors approximate Schedule 7. Source inspection confirms:

- Interest-rate capital uses fixed parallel shifts of +200 and −100 basis points on the bond assets; it is not a full prescribed, currency-specific asset-liability stress calculation.
- Spread capital uses market value times modified duration times a rating-based spread shock, rather than full stressed cash-flow repricing.
- Aggregate capital takes the square root of the sum of squared IR, spread, equity and FX amounts, then adds its counterparty proxy. The source explicitly omits prescribed inter-module correlation coefficients.
- Counterparty default uses face amount times an annual PD/LGD proxy; this is an expected-loss-style teaching approximation.
- FX is based on asset currency exposures and hardcoded FX factors. Liability offsets, hedges and a complete balance sheet are absent.
- [`Bond.price`](https://github.com/woming98/hkrbc-asset-model/blob/abaa05c813dfb81d22400ce1ecb0ace74e6dc616/core/bond.py#L118) values a rounded regular coupon count using one tenor yield plus a rating spread, ignores accrued interest and does not use the callable/MWC fields in that main price calculation. MWC is separately displayed through a helper; this is not an option-adjusted callable-bond valuation.
- All non-HKD bond currencies use the USD curve and unknown currency FX falls back to 1.0. Reject unsupported currencies in a validation adapter instead of inheriting these defaults.
- The ESG loader's earned-rate helper hardcodes monthly annualization with a factor of 12 and approximates bond yield as short rate plus constant spread. It is not a dynamic bond total-return or reinvestment model. It also uses pivot tables that can average duplicate keys, so validate uniqueness before loading.

Suitable reuse is the *interface idea*: positions → dated curve/FX inputs → independently valued assets and sensitivity results → clearly marked demonstration stresses. The existing risk-engine output must be labeled educational approximation when cited and must never be reported as a complete official PCA/PCR calculation.

## ifrs17-subledger

### Interfaces and compatibility

Inspected README, requirements, AOC base class, GMM model, journal generator, reconciliation, layered reinsurance helper and actuarial-output headers. PAA/VFA, full disclosures, analytics and the large Streamlit UI exist but were not all fully audited.

The [requirements](https://github.com/woming98/ifrs17-subledger/blob/ee03a549edea8173f278c8c14480b4825d5ed631/requirements.txt) include pandas, PyYAML, openpyxl, Streamlit, Plotly and fpdf2, with lower bounds only. The README targets Python 3.10+. Both this repo and ESG use a generic `src` package; isolate imports/processes. There is no packaged release metadata, lockfile, test directory or CI workflow in the inspected tree.

The useful boundary is a table keyed by cohort, period and currency, with measurement-model identifiers and precomputed balances/movements. The input CSV includes ending PVFCF, RA, CSM and LC, expected cash-flow release, experience variance, CSM amortization, finance charges, assumption changes, FX effects, cession rate and period fraction.

[`MeasurementModel.compute_aoc`](https://github.com/woming98/ifrs17-subledger/blob/ee03a549edea8173f278c8c14480b4825d5ed631/src/models/base.py#L189) takes beginning and ending pandas rows and returns an `AOCResult`. [`reconcile_cohort`](https://github.com/woming98/ifrs17-subledger/blob/ee03a549edea8173f278c8c14480b4825d5ed631/src/reconciliation.py#L25) checks beginning balance plus supplied movements against the ending input. [`generate_journal`](https://github.com/woming98/ifrs17-subledger/blob/ee03a549edea8173f278c8c14480b4825d5ed631/src/subledger.py#L149) produces a paired journal batch. These make a reasonable optional reconciliation-adapter contract.

### Scope and accounting caveats

1. **AOC ingestion, not independent valuation:** the GMM engine primarily reads already calculated balances and movements. Its fallback finance charge is a simple beginning balance times DAIR times period fraction. It does not independently project insurance cash flows, calculate coverage units or derive all required accounting judgments.
2. **Loss-component convention requires independent validation:** the [base class](https://github.com/woming98/ifrs17-subledger/blob/ee03a549edea8173f278c8c14480b4825d5ed631/src/models/base.py#L89) subtracts LC from PVFCF + RA + CSM in its ICL properties. This report records the upstream convention without endorsing it as IFRS 17 measurement. Do not import that formula into RBC liability calculations; validate accounting meaning, component definitions and signs against authoritative IFRS material before any accounting use.
3. **Internal transfers:** `total_movements` excludes the CSM assumption-change transfer, while the waterfall display includes a separate CSM-change row. An independent report must distinguish component transfers from changes in total liability to avoid a misleading waterfall.
4. **Double-entry checks are structural:** each journal addition creates equal debit and credit amounts. A balanced batch therefore does not establish that account mapping, recognition, measurement, tax, currency aggregation or disclosure is correct. Validate those separately, with amounts grouped by currency and period.
5. **Reinsurance approximation:** [`compute_rca_treaties`](https://github.com/woming98/ifrs17-subledger/blob/ee03a549edea8173f278c8c14480b4825d5ed631/src/reinsurance_xl.py#L87) scales gross AOC with precomputed effective cession rates. The documented total-loss assumption is restrictive; variable loss severities and genuine reinsurance measurement need separate cash-flow/model outputs.
6. **RBC and IFRS stay distinct:** PVFCF/RA/CSM/LC and HK RBC CE/TVOG/MOCE are different model concepts. A reconciliation view may explain them side by side, but a field name match or balanced journal does not justify treating them as identical measurements.

The demo data is illustrative. No upstream subledger run, disclosure export or accounting compliance test was executed in this review.

## Application recommendations

1. Keep a source manifest with upstream commit and file URL. Mark material secondary-reference claims as `unverified` until matched to the applicable official source and date.
2. Separate deterministic valuation, stochastic demonstration, validation and evidence retrieval. Every numerical result should carry conventions, units, valuation date, assumptions and a model-version identifier.
3. Offer optional CSV adapters only after strict schema, uniqueness, finiteness, date, currency and completeness checks. Return specific validation errors rather than silently defaulting missing fields or averaging duplicates.
4. Label simplified capital examples and toy TVOG projections explicitly in output. Do not present an educational asset charge as official PCA or a diagnostic pass as compliance certification.
5. Establish independent benchmark cases: fixed cash-flow PV, zero-volatility stochastic limit, HW timestep/convergence checks, curve round trips, nonempty martingale horizons and reconciliation failures. Passing upstream demos is insufficient as an acceptance criterion.
6. If direct source reuse is later desired, first resolve license text/notices at a pinned commit and review the specific imported module. No such dependency is required for the clean-room MVP.

## Review limitations

The connected GitHub plugin provided repository metadata, commit objects, complete recursive trees and selected UTF-8 source files. No browser or shell fallback was necessary. This was read-only static review: external deployment sites, proprietary Prophet import compatibility, current official regulatory parameters, numerical calibration correctness, all UI paths and every module were not verified. Findings about likely edge cases arise from source inspection and are not claims that the upstream authors ran or failed a particular test.
