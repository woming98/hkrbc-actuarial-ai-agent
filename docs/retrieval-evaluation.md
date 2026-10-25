# Retrieval methods and measured diagnostic evaluation

The default ranker is now bilingual **BM25F with exact rule identifiers and light MMR diversification**. Two actual locally provisioned SentenceTransformers encoders were also loaded and measured. On the small developer-authored set below, the English encoder reduced Chinese retrieval quality; neither dense nor hybrid retrieval replaces BM25 by default.

This is a diagnostic development set, not a blinded or held-out benchmark, a general claim of semantic-search superiority, or an evaluation of legal answer correctness. The set exposed two implementation bugs during development: an overly broad `cap` pattern also matched `capital`, and hyphenated prose did not match its separated words. Both were corrected with general regression tests. Queries and relevance labels were left unchanged.

## Reproduce

From the repository root, using an installed environment:

```bash
# No encoder, model download, or inference API required.
python evaluation/retrieval_eval.py --output runtime/retrieval-lexical.json

# Explicit existing local model directory; never downloads weights.
python evaluation/retrieval_eval.py \
  --model-path runtime/models/all-MiniLM-L6-v2 \
  --output runtime/retrieval-evaluation-english.json
```

Without a successfully loaded explicitly supplied model, dense and hybrid methods are recorded as `not_run`. The application does not silently fall back when a configured semantic backend cannot load. The benchmark can still measure lexical methods while recording the semantic load failure. Model provisioning is a separate, explicit operation described in deployment documentation.

The full measurements are preserved in [retrieval-english.json](../evaluation/results/retrieval-english.json) and [retrieval-multilingual.json](../evaluation/results/retrieval-multilingual.json). The runner records every case's ranked references, scope decision, authorization checks and elapsed time, plus corpus/case/source hashes and encoder revision/manifest metadata. The CLI exits nonzero if any unauthorized record is returned.

## Fixed cases and corpus

[retrieval_cases.json](../evaluation/retrieval_cases.json) contains **44 manually labeled cases**: 24 supported historical/conceptual questions, 12 unsupported requests, 4 current-law requests and 4 role-isolation cases. There are 32 English and 12 Chinese queries. Labels were assigned from the actual source-section records before the first candidate-ranker run. Each case states the expected relevant section IDs, corpus answerability, role, forbidden IDs and a labeling rationale.

The measured corpus is the unchanged original **13-record** seed: ten public source paraphrases and three synthetic access/version fixtures. Ordinary retrieval excludes the superseded fixture; SQL authorization further restricts the records visible to each role. The benchmark covers commencement, three pillars, original applicability, distinct rule 5(1)/5(2)/5(3) provisions, allocated MCA, disclosure tier names, catastrophe own-assessment approval and the 2026 announcement. It includes English paraphrases, traditional/full-width Chinese subrule notation and Chinese domain questions.

Some unsupported/current questions have relevant *background* sections but remain unanswerable. Relevance is therefore labeled separately from claim coverage. For example, a disclosure template can be relevant background for a capital-tier question without establishing eligibility or numeric limits. Some background relevance judgments are broad and debatable; the per-case rationales make them inspectable.

| Snapshot | SHA-256 |
|---|---|
| Original seed | `b84c377c10c371a5419a94451f8f650b318bf3b3c1116aca9079dc32a293b3ce` |
| Case manifest | `5ae358fe4d0aeb44ee2373238e62ef2ee398215af22ca2e0758aa546c46c80ef` |
| Retrieval implementation at measured run | `3a33ba6f6a43d3c8d55867e14e4830f117bf830923b44f476b07f962fad7852f` |
| Encoder adapter at measured run | `054e70aec6a8a6eb23526a9986d2fa9f66ffa713c8186e4f7010b023a420c363` |

Additional verified sources are intentionally outside this fixed comparison. Use `--supplement PATH` to inspect augmented-corpus rankings. Unless the case manifest supplies a matching `label_supplement_sha256` and reviewed labels for that corpus, the runner records raw outputs but withholds aggregate quality scores. New sources can make previously unsupported questions answerable, and old relevance labels are not exhaustive for new sections. Do not reuse the numbers below as measurements of an expanded corpus.

## Methods

All four methods use the same role-filtered corpus, queries, result limit of three and **same upgraded answer-scope checker**. Ranker comparison therefore does not attribute scope-classifier improvements to a ranking algorithm.

| Method | Implementation |
|---|---|
| `hash` | Frozen original 512-dimensional feature-hash cosine ranker and original aliases; lexical overlap guard; cosine threshold 0.12. This reproduces the original ranking baseline, with the common current security boundary. |
| `bm25` | BM25F: title weight 2.0, section 2.8, text 1.0; saturation `k1=1.2`, field length normalization `b=0.75`; query terms counted once. Exact primary-section identifier matches receive a fixed boost. |
| `dense` | Cosine similarity from the actual local encoder; minimum cosine 0.20. This threshold is a fixed heuristic, not a calibrated confidence score. |
| `hybrid` | Reciprocal-rank fusion of BM25 and dense ranks with constant 60. This is equal-rank fusion, without a trained reranker or language-dependent weights. |

The upgraded tokenizer normalizes Unicode width, retains English words/numbers, expands a controlled English/Chinese HK RBC vocabulary and emits overlapping Chinese bigrams. It splits ordinary hyphenated prose into component terms while retaining identifiers. It preserves rule 5(1) and rule 5(3) as different tokens, including `第5條第3款` and full-width forms. Explicit rule/subrule requests are restricted to the corresponding primary section; a cross-reference in a different section does not replace the requested provision.

Upgraded modes use MMR with 0.9 relevance weight and 0.1 redundancy weight. Frozen hash features estimate redundancy only; they do not replace BM25/dense relevance. Identical section text is deduplicated. This reduces repeated passages, but it does not establish that every third-ranked passage is relevant. Active document-version retirement is handled by the store, not inferred from a version string in the ranker.

## Measured results

Executed on **25 October 2026, 10:05 Asia/Shanghai** (artifact timestamp `2026-10-25T02:05:26Z`) using CPU. The English model was `sentence-transformers/all-MiniLM-L6-v2`, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, Apache-2.0 according to its reviewed [model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) and local provision manifest. Manifest SHA-256: `41a2225d194e4a3593bec0dfdb05a1665338af6bb785babee45d9b1a8226e6c8`. Actual local encoding returned normalized 384-dimensional vectors. No API inference or model download occurred in the benchmark.

Recall and MRR are macro-averages over the **34 cases with nonempty relevance labels**. Cases without relevant sections are assessed through answerability and authorization checks rather than being counted as automatic recall successes.

| Method | Recall@3 | MRR@3 | Unsupported-corpus answer false positives | Answered with no labeled relevant section | Unauthorized hits | Median query time |
|---|---:|---:|---:|---:|---:|---:|
| Original hash | 0.779 | 0.760 | 0/18 | 1 | 0 | 3.7 ms |
| BM25F + MMR | 0.956 | 0.951 | 0/18 | 0 | 0 | 9.4 ms |
| English dense + MMR | 0.691 | 0.657 | 0/18 | 1 | 0 | 123.0 ms |
| English hybrid + MMR | 0.926 | 0.863 | 0/18 | 1 | 0 | 117.9 ms |

The 18 negative cases comprise unsupported, current-law and inaccessible-source questions. Zero false positives on those authored examples is not a general false-positive bound. In particular, a global answerability status can look correct even when an answerable question retrieves the wrong section. The next table includes retrieval in that assessment.

| Method | Relevant-section answer precision | Relevant-section answer rate among 26 answerable cases | Evidence-supported false positives |
|---|---:|---:|---:|
| Original hash | 0.955 | 0.808 | 1/23 |
| BM25F + MMR | 1.000 | 1.000 | 0/18 |
| English dense + MMR | 0.947 | 0.692 | 1/26 |
| English hybrid + MMR | 0.962 | 0.962 | 1/19 |

Here a “relevant-section answer” means the corpus supports the question and at least one hand-labeled relevant section is returned. “Evidence-supported false positive” means `evidence_found` despite either an unsupported corpus question or no retrieved labeled relevant section. The denominators vary because rankers miss different relevant sections. These remain section-label proxies; neither metric checks entailment of every sentence or whether multiple required claims are fully supported.

BM25 ranked the intended section first on all 24 supported development cases. Its remaining recall misses were a current Chinese capital question with two background labels and a weak background label for an unsupported correlation request. That result is narrow: the source set is tiny, the vocabulary was deliberately designed for HK RBC, and the diagnostic cases were used during implementation.

| Method | English Recall@3 / MRR@3 | Chinese Recall@3 / MRR@3 |
|---|---:|---:|
| Original hash | 0.870 / 0.870 | 0.591 / 0.530 |
| BM25F + MMR | 0.957 / 0.957 | 0.955 / 0.939 |
| English dense + MMR | 0.870 / 0.819 | 0.318 / 0.318 |
| English hybrid + MMR | 0.957 / 0.891 | 0.864 / 0.803 |

The English encoder's Chinese misses include commencement, pillars, numbered provisions and catastrophe approval. Equal-weight fusion also missed the labeled Chinese tier-disclosure section while still emitting an answer status. These are reasons to retain BM25 as the default on the current bilingual corpus. The multilingual comparison below uses the identical case labels and corpus; a model name alone is not evidence of better retrieval.

Latency includes authorization, request-local document encoding and ranking, but excludes model load (approximately 6.3 seconds in this run). This was one run on a working machine with other activity, not a controlled speed benchmark. There is deliberately no shared document-vector cache to accelerate semantic modes across identities.

## Measured multilingual comparison

The same frozen cases were also run with `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, on CPU at `2026-10-25T02:05:46Z`. Its reviewed [model card](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) declares Apache-2.0 and 50 languages; those declarations are not domain validation. Manifest SHA-256 is `cbc095bff2e8e001896def29f391b420956c63b426b51f7b413073616696a3bf`. Actual offline loading took approximately 7.0 seconds and produced normalized 384-dimensional vectors, with a 128-wordpiece input limit.

| Method | Recall@3 | MRR@3 | Chinese Recall@3 / MRR@3 | Answered with no labeled relevant section | Median query time |
|---|---:|---:|---:|---:|---:|
| BM25F + MMR | 0.956 | 0.951 | 0.955 / 0.939 | 0 | 9.3 ms |
| Multilingual dense + MMR | 0.868 | 0.833 | 0.864 / 0.864 | 2 | 366.7 ms |
| Multilingual hybrid + MMR | 0.926 | 0.892 | 0.864 / 0.909 | 1 | 332.8 ms |

The multilingual encoder improved Chinese recall over the English encoder on these cases, while remaining below BM25 overall. Dense and hybrid each reported zero unsupported-corpus false positives and zero unauthorized hits. Their joint evidence-supported false positives were **2/20** and **1/19**, respectively: an apparently correct answerability status still sometimes accompanied the wrong labeled section. Their relevant-section answer precision/rate was 0.923/0.923 and 0.962/0.962. BM25 remains the default. These are two encoder comparisons on a small development set, not proof that lexical search is universally better.

Both final artifacts were regenerated after the strict local-loader hardening described below; their encoder/retrieval source hashes match the delivered code. Timing runs overlapped other local verification activity and are not controlled hardware benchmarks. Rankings and quality scores remained unchanged after the loader gates were added.

## Claim scope and uncertainty

The old unconditional block for words such as `factor` and `matching adjustment` has been replaced by narrower request-scope checks. A question about the *factor-based catastrophe approach* can be answered from an approval/default-method source. A numeric calibration, MA formula, full PCA computation, tier cap or instrument-eligibility question needs the corresponding explicit curated claim tag.

Tags describe narrow section coverage; they are not generated by the encoder. For example, `capital.tier_limits` does not establish `capital.tier_instrument_eligibility`, and `matching_adjustment.announcement` does not supply `matching_adjustment.formula`. A mentioned topic is not promoted to a complete calculation. Scope results list requested, covered and missing tags, missing rule identifiers, temporal eligibility and requested classification.

Current-law questions retain the verification flag, regulatory-kind, future/superseded/demo status, effective interval and review-date checks. A future source cannot satisfy an ordinary present-scope numeric claim. Explicit future/scheduled questions, or a named amendment year matching the source's publication/effective year, may use future tags while preserving the future status. Asking “current” or “today” still prevents that prospective exception.

The request-scope matcher is conservative and incomplete. It is not a trained answerability or entailment model, and it cannot recognize every unsupported specificity, jurisdiction, legal exception or paraphrase. Generic `evidence_found` means authorized passages were retrieved and the implemented scope checks permitted them; it does not mean the corpus completely answers every possible reading of the question.

## Optional semantic operation and privacy

`HKRBC_RETRIEVAL_BACKEND` accepts `bm25` (default), `hash`, `dense` or `hybrid`. Semantic modes additionally require `HKRBC_EMBEDDING_MODEL_PATH` pointing to one of the **two approved pinned snapshots**. Before importing SentenceTransformers, the adapter requires the approved model/revision and application-pinned manifest SHA, validates every file size/SHA and the exact disk inventory, and accepts only the reviewed builtin Transformer/Pooling graph (plus Normalize for the English model). It rejects arbitrary directories, missing manifests, extra executable/pickle files, symlinks, custom module paths, custom configuration mappings and unreviewed architectures/tokenizers. This addresses a concrete library behavior found during review: `trust_remote_code=False` alone does not prevent custom local module loading. The adapter also requires safetensors, uses CPU, `local_files_only=True`, `trust_remote_code=False` and `model_kwargs={"use_safetensors": true}`, and forces `HF_HUB_DISABLE_TELEMETRY=1`, `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` before importing the model stack. Reviewed manifest pins and normal HTTPS origin underpin this supply boundary; hashes are not publisher signatures. Host packages/operators and modification of application code remain trusted. See the explicit, pinned, HTTPS-only fresh-directory provisioning process in deployment instructions.

Document authorization occurs in SQL and is checked independently again **before** tokenization or semantic encoding, including when a defective store adapter returns an unauthorized record. PII query redaction and obvious instruction rejection precede encoding. Vectors/text are not persisted or shared across requests. A later analyst request therefore cannot reuse a restricted document vector generated for an administrator. Tests exercise this boundary with explicit encoder spies.

The measured English model truncates inputs at 256 wordpieces. The existing section chunk limit is 1,200 characters, and concatenated title/section/text can exceed an encoder's token limit; semantic retrieval does not guarantee that a complete chunk was encoded. BM25 sees the whole stored chunk. Other models can have different truncation limits. There is no general multilingual guarantee, production-scale index, ANN search, neural reranker, private cache isolation service, or semantic factuality certification in this implementation.

## Verification and next evidence needed

New tests cover bilingual token units, identifier variants, subrule cross-reference confusion, rare-field relevance, duplicate passages, request-local semantic ACL checks, redaction before encoding, invalid encoder output, explicit opt-in, missing models, mandatory offline/safetensors flags, approved snapshot/manifest/module-graph and exact inventory gates, manifest corruption, claim-scope distinctions and benchmark snapshot validation. Existing retrieval/service/UI integration contracts remain compatible.

Before drawing broader conclusions, collect independently written representative questions, add realistic distractor sections and review graded relevance with a second human. Freeze a held-out set; expand multilingual model comparisons and measure expanded-source runs with fresh labels; inspect sentence-level source support and adversarial answerability separately. The present measurements demonstrate a concrete local ranking improvement on an inspectable diagnostic fixture, with the limits above.
