# Expanded diagnostics and demonstration — version 0.3.0

Executed on 25 October 2026. This release adds an expanded-corpus retrieval study, offline service adversarial probes, clearer evidence gaps, guided examples and a demonstration preflight. The capital engine remains version 1.0.0 and the factor workflow 0.2.0; the existing numerical assumptions and report snapshots retain those identifiers.

## Measured evidence

| Check | Observed result |
|---|---|
| Full local pytest suite | **476 passed in 24.46s** on the final source snapshot |
| Signed-service adversarial runner | **36/36**, zero network attempts, one intentional in-memory authorized transport control |
| Original 44-case regression | BM25 Recall@3 **0.956**, MRR@3 **0.951**; zero authored-negative false positives/unauthorized hits |
| Expanded full-corpus study | **64 cases**, 25 source records, all four rankers measured with a real local multilingual encoder |
| Read-only preflight | `ready`; required source, sample, report, package and offline-configuration checks passed |
| Local UI | Example prefill did not run a query; compound formula request returned an explicit missing-coverage explanation |

The [36-case artifact](../evaluation/results/adversarial.json), [44-case regression](../evaluation/results/retrieval-original-v0.3.json) and [64-case artifact](../evaluation/results/retrieval-expanded.json) record actual observations and implementation hashes. The adversarial runner verified that its measured source files stayed unchanged during execution. Model inference used the approved local multilingual snapshot and offline controls; no weights were downloaded or paid APIs called in this round.

## Expanded-corpus results

The [new labels](expanded-corpus-labeling.md) were authored by another development agent directly from the immutable source records and frozen **before candidate runs**. The 64-case manifest remains SHA256 `b9b544c45a64d91d00ba739bce26da61ba271774101537cf71970ced8b6aeb34`: 32 English, 32 Chinese; 36 answerable and 28 requiring complete-answer abstention. Earlier developer exposure and subsequent diagnostic-guided fixes are disclosed. This is not a blinded human holdout or independent institutional validation.

The added 12 records make the corpus different from the original 44-case experiment. **Do not compare the two studies' aggregate scores as a before/after improvement percentage.** Recall/MRR below average the 60 cases with nonempty relevance labels.

| Method | Recall@3 | MRR@3 | Unsupported-corpus false positives | Positive-case answerable statuses | All labeled components retrieved |
|---|---:|---:|---:|---:|---:|
| Legacy hash | 0.658 | 0.664 | 0/28 | 28/36 | 27/36 |
| BM25F + MMR | **0.878** | **0.928** | 0/28 | 35/36 | 34/36 |
| Multilingual dense | 0.839 | 0.883 | 0/28 | 35/36 | 34/36 |
| Multilingual hybrid | 0.856 | 0.903 | 0/28 | 35/36 | 34/36 |

Every method returned zero unauthorized hits. BM25 remains the default on these observed corpora. The multilingual model is `paraphrase-multilingual-MiniLM-L12-v2`, revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, manifest SHA `cbc095bff2e8e001896def29f391b420956c63b426b51f7b413073616696a3bf`. Its input limit is 128 wordpieces. No English-encoder measurement on this expanded corpus is asserted.

**Two completeness limitations remain visible.** The Chinese old-versus-future matrix question misses the historical table and is conservatively marked insufficient. The English comparison gets an answerable status but misses the annotator's dedicated commencement record; another returned amendment record contains the scheduled date in its verified metadata. All upgraded methods therefore retrieve every labeled component on 34/36 positive cases, while one emitted answerable status lacks the full labeled source set. The legacy ranker has additional misses. Neither any-relevant-section precision nor an answerable status proves complete source support. The new component metric deliberately exposes this distinction; metadata overlap is not silently used to rewrite frozen labels.

CPU timings were recorded in raw results during other local activity. They are diagnostic wall times, not controlled performance benchmarks. There is no shared vector cache. Semantic ranking, relevance labels and the claim matcher do not establish sentence-level entailment or current legal accuracy.

## Defects found and corrected

- **Compound specificity:** an announcement/year mention could suppress a second matching-adjustment formula or eligibility request. Required detail now survives the announcement context. Debt-instrument eligibility is recognized independently of its word distance from “tier.” Insufficient scope reaches no optional generation transport.
- **Narrow methods versus calculations:** TVOG methodology/proxy coverage does not supply calibration parameters or numerical calculations. CCA notice-based mechanisms do not supply unverified subsequent notice values; HKD denomination does not supply currency-risk stresses.
- **Unicode boundaries and dates:** Chinese-adjacent acronyms, sentinel identifiers and `2026年` preserve their scope. The technical term “deterministic current estimate” does not by itself mean today's law; an actual current-law request still requires verified current evidence.
- **Legal references:** letter rules such as 85A, nested Roman clauses, abbreviated clause lists and bounded ranges remain distinct. The regression cases retain unsupported additional clauses instead of dropping them behind the first referenced clause. Reversed, complex or overly long ranges retain an unresolved identifier rather than silently narrowing the request.
- **Version comparisons:** recognized historical/future claim scopes require relevant evidence from both versions. Unrecognized semantic components remain a limitation of the phrase-based checker, as the component metrics expose.

The unchanged diagnostics were used to find and correct these problems, so the final numbers remain development results. Tests independently pin compound refusal, malformed/missing references, typed specificity, public session behavior and the authored negative set. The original 44 queries and expanded 64 labels were not altered to fit a candidate.

## Demonstration and reproducibility

```bash
python scripts/preflight.py
python -m pytest -q
python evaluation/adversarial_eval.py --output runtime/adversarial.json
python evaluation/retrieval_eval.py \
  --cases evaluation/expanded_retrieval_cases.json \
  --supplement data/documents/verified_supplement.json \
  --output runtime/retrieval-expanded-lexical.json
```

Dense/hybrid require the separately provisioned approved local snapshot. Without one, the runner honestly records those methods as `not_run`. The [interview walkthrough](interview-demo.md) gives a roughly 9½-minute bilingual demonstration using **Example questions**, **Use example**, and **Load missing-settlement example**. Prefill never submits or approves an external request. Loading a new portfolio example clears earlier reports/results; the settlement example disables report completion despite a zero module residual.

Preflight reads local configuration and distributed fixtures without authentication, databases, network, model loading or output files. It emits risk codes/booleans instead of secret values. Its optional model inventory check does not hash large weights or certify inference; the strict actual loader performs that separate validation.

The [actual evidence-gap screenshot](../reports/evidence-gap-preview.jpg) shows the missing-formula explanation and historical/background sources. Local browser verification used a freshly restarted loopback-only Streamlit process with external inference disabled.

## Remaining scope

The application remains an asset-only, educational portfolio prototype. Present consolidated law, complete statutory capital, enterprise IAM/tenant isolation, full DLP, sentence-level legal entailment, real generative provider behavior and the formal same-LLM A/B/C experiment remain unverified. A/B are still `not_run`; local encoders are retrieval models. No public app deployment, upstream repository modification or source-PDF redistribution occurred.

The extended GitHub workflow includes preflight, the authored adversarial runner and lexical expanded-corpus checks. Observed clean-environment results are recorded after that workflow finishes; its existence alone does not establish a passing run or branch protection.
