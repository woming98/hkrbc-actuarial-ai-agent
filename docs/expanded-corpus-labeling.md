# Expanded-corpus diagnostic labels

[expanded_retrieval_cases.json](../evaluation/expanded_retrieval_cases.json) is a new, fixed diagnostic manifest for the complete original 13-record seed plus the 12-record verified supplement. It contains **64 cases: 32 English and 32 Chinese**, with 36 bounded answerable requests and 28 requests requiring abstention from a complete conclusion. It does not replace or rewrite the original 44-case manifest.

The labels were frozen before candidate evaluation on this new manifest. No ranker, service, evaluator or model was imported or queried during its authoring. The author was a separate development agent labeling from source records and their limitations. That agent had previously curated evidence, implemented UI/provenance checks and observed exploratory prototype queries. This is therefore **developer-authored, independent-agent source labeling**, not blinded human labeling, an unseen holdout or an independent institutional benchmark. Earlier development exposure is disclosed in the manifest.

No expanded-corpus performance measurement is reported here.

## Frozen snapshots

| Artifact | SHA256 |
| --- | --- |
| New 64-case manifest | `b9b544c45a64d91d00ba739bce26da61ba271774101537cf71970ced8b6aeb34` |
| Original 13-record seed | `b84c377c10c371a5419a94451f8f650b318bf3b3c1116aca9079dc32a293b3ce` |
| Verified 12-record supplement | `40d3a0089fbca1548f721dca784833b243ddc0bf7c1d0e5d9a211558f9fc135b` |
| Source register | `d732c937f1cb01687738448e3bc628b090205aa32ec84eec50b41bc1a795c49b` |
| Unchanged original 44-case manifest | `5ae358fe4d0aeb44ee2373238e62ef2ee398215af22ca2e0758aa546c46c80ef` |

The legal/source scope is fixed at **25 October 2026**. Every source identifier is mapped to its version, section, URL, classification, lifecycle status and available PDF hash/page/check date in `section_labels`. Each case also provides the locators of its relevant records. Missing download metadata in an older seed record is left missing; the labels do not invent a checksum or upgrade its verification status.

The source register's PDF locators and checksums identify previously inspected material. They do not independently prove current law, source authenticity, permission to redistribute or legal entailment. No source PDF, rendered page or full source extract is copied into this manifest. See [source verification](source-verification-2026-10-25.md) for access and rights limitations.

## Case composition

| Group | Cases | Answerable | Requires abstention | Scope |
| --- | ---: | ---: | ---: | --- |
| Original supported | 16 | 16 | 0 | Original rules 3, 4, 6, 7, 19 and Schedule 7 Table 2 |
| Future supported | 8 | 8 | 0 | Bounded 2026 commencement, matrix, CCA-mechanism and crypto-component requests |
| Historical comparison | 2 | 2 | 0 | Original versus replacement matrix, with the replacement's scheduled date |
| Legacy supported | 8 | 8 | 0 | Earlier framework, commencement, thresholds, MCA, variation, catastrophe approach, template and fund-purpose records |
| Current law | 8 | 0 | 8 | Present applicability/compliance not established by this corpus |
| Unsupported specificity | 8 | 0 | 8 | Full PCA formula, instrument qualification, TVOG calibration and future notice values |
| Compound missing | 8 | 0 | 8 | A supported component combined with a missing substantive requirement |
| Access/lifecycle | 6 | 2 | 4 | Synthetic role permissions and the superseded ordinary-retrieval fixture |
| **Total** | **64** | **36** | **28** | |

English and Chinese coverage is balanced by count, not by production prevalence. Chinese includes ordinary traditional-Chinese and Cantonese phrasing alongside statutory terminology. Questions were written for the available source concepts and documented gaps; they were not sampled from real actuarial work or confidential user queries.

## Label meanings

`relevant_document_ids` identifies substantive support for at least one requested component, or useful historical/background evidence for an otherwise unanswerable request. A shared word alone is insufficient. An unanswerable current-law question can therefore have relevant original/future background without receiving an answerable label. Unauthorized or ordinary-retrieval-ineligible records are not relevant authorized labels.

`expected_answerable: true` means the authorized frozen records can support a bounded response to the complete substantive request, with the source's original/future and verification caveats preserved. It does not certify general law or an individual insurer's compliance. For example, the original tier-cap question asks for limits, not qualifying instrument terms; the TVOG method question asks for stated characteristics, not a calibrated implementation.

`expected_answerable: false` means a complete requested conclusion cannot be established from the authorized frozen records. The system may still show partial evidence while explicitly identifying the missing scope. It must not turn an answerable sub-question into a claim that the whole request is supported. `missing_requirements` and the per-case rationale explain the gap.

`required_document_ids` records the minimum source components needed together for an answerable case. A relevant corroborating source can be optional. The dated matrix-comparison cases, for example, require the original table, replacement table and commencement provision. The current evaluation runner's “any relevant section” measures do not by themselves establish that all these components were retrieved or that a complete compound answer was supported. Recall over all relevant labels and explicit joint-component review are separate assessments.

`forbidden_document_ids` includes records above the case role's classification and the explicitly superseded synthetic fixture. An administrator can inspect history through an authorized history interface, but these cases concern ordinary retrieval from the frozen corpus. They do not simulate an additional database retirement decision or claim that an archived synthetic method is outdated legislation.

## Important distinctions retained in the labels

- Historical evidence does not establish a present compliance conclusion. Every regulatory record lacks verified-current-consolidated status.
- The future amendment records are prospective relative to the fixed labeling date. A future numerical component can answer an explicitly prospective, narrowly scoped request without being treated as already operative.
- A complete intermodule PCA table does not supply every sub-risk matrix, stress factor, adjustment or full statutory PCA formula.
- Capital-tier limits do not supply instrument qualification criteria. Disclosure field names do not supply either a complete eligibility checklist or capital calibration.
- The TVOG proxy is conditional. Its method record omits simulation count, generator calibration and convergence details. “Deterministic current estimate” in an explicitly historical question is a technical expression, not a request to certify today's law.
- The future CCA record gives a notice-based specification mechanism; it explicitly lacks verified subsequent numerical notice values.
- Compound negative requests retain the supported component's relevance while requiring abstention for the missing component. The gap is not removed by finding one familiar source.

These are source-content judgments authored before the new candidate runs, not labels copied from the scope matcher's output. A rule-based classifier may recognize some phrasings poorly; that is an observed implementation issue if later measured, not grounds to silently relabel the source support.

## Running and interpreting later evaluations

The label author did not execute this command:

```bash
python evaluation/retrieval_eval.py \
  --cases evaluation/expanded_retrieval_cases.json \
  --supplement data/documents/verified_supplement.json \
  --output runtime/expanded-retrieval-lexical.json
```

The manifest pins both corpus files so the runner can detect mismatched expanded-corpus labels. Optional encoder runs must use the same case file, corpus, access rules and scope checker, and must record their actual model revision/configuration. The existing evaluation framework and its limits are described in [retrieval evaluation](retrieval-evaluation.md).

Report retrieval relevance, abstention, unauthorized hits and complete-component coverage separately. No metric here is a proof of sentence-level entailment, present-law accuracy, general security or actuarial competence. The small corpus, authored questions, developer exposure and binary relevance judgments limit generalization. A successful run on these labels is not an independent validation or a controlled comparison of general-purpose language models.

Preserve this frozen snapshot after inspecting candidate results. A genuine source or labeling correction should create a separately versioned manifest and disclose the changed rationale and hashes. Additional difficult cases identified from failures belong in a new diagnostic version; they must not be folded silently into this benchmark and then presented as unseen evidence.
