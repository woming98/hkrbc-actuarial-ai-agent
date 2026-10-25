# Authored service adversarial diagnostics

This fixed diagnostic set checks 36 synthetic service interactions across eight categories. It exercises signed sessions and the application boundary, including ingestion, retrieval, routing, lifecycle decisions and report access. It is a developer-authored regression set, not a security certificate or an independently held-out adversarial benchmark.

Run from the project root:

```sh
python evaluation/adversarial_eval.py --output evaluation/results/adversarial.json
python -m pytest tests/test_adversarial_evaluation.py -q
```

The runner exits with status 1 if any expectation fails, a network attempt occurs, or a measured source file changes during the run. Selected diagnostic cases can be reproduced using repeated `--case-id` arguments. It checks fixed outcomes without making an external model call.

The final tracked result is [evaluation/results/adversarial.json](../evaluation/results/adversarial.json). The final run on 25 October 2026 passed **36/36 cases**, with **zero network attempts**, **one intentional in-memory transport boundary control**, and stable source fingerprints during execution. Its focused suite contains **49 tests** and is included in the passing full suite. The tracked artifact was regenerated after the final core freeze; its recorded source hashes determine which implementation was measured.

## What is exercised

| Category | Cases | Service outcomes checked |
| --- | ---: | --- |
| Privacy | 4 | Local query redaction, sensitive ingestion rejected atomically, original external query checked before redaction, sensitive evidence blocked |
| Injection | 3 | English and Chinese query instructions rejected; instructions beyond a chunk boundary reject the whole ingestion batch |
| Sessions | 4 | Altered role, altered signature, expired signed token and incorrect demonstration password rejected |
| Authorization | 3 | Analyst/public and reviewer/public+internal evidence isolation; nonpublic evidence blocked from external routing |
| Routing | 8 | Local default, server external gate, strict per-request approval, role gate, authorized public boundary control, no-evidence abstention and unknown mode |
| Lifecycle | 3 | Retired version excluded, source bytes/checksum unchanged, analyst retirement denied, private successor reference hidden |
| Reports | 2 | Owner/reviewer access with analyst denial; invalid CSV cannot create a report or complete audit event |
| Claim scope | 9 | Missing compound claims and exact subrules abstain, current compliance request abstains, supported compound/topic controls return evidence |

Case definitions and expected outcomes live in [adversarial_cases.json](../evaluation/adversarial_cases.json). Regulatory-looking statements in the tiny fixture corpus are explicitly synthetic demonstrations. They are not evidence of actual law or actuarial calibration. All cases use the same BM25 service path; no semantic encoder is loaded.

Each case creates a fresh temporary database and service signing secret, then authenticates the public demonstration accounts through `AgentService.sign_in`. A forged token is therefore tested against the real session validator. The service performs all role decisions; the harness does not pass trusted principals into the query or report APIs.

## Network and persistence boundaries

The harness overrides inference settings and uses an obvious fake, in-memory placeholder credential. It replaces model transport with a spy that counts a call and immediately raises `TransportBlocked`. The authorized external positive control must reach that spy exactly once. All rejected cases must reach it zero times. No prompt, header or body is retained by the spy.

Independent socket connect/send, DNS and urllib guards raise before network I/O and count any attempt as a failure. No HTTP server, remote model, paid API, model download or real credential is required. An external provider's behavior is not tested.

After every case, the harness scans all text cells in the evidence, audit, report and retirement tables for the complete submitted queries, deliberately sensitive synthetic markers and issued/tampered session tokens. The expectations require their absence. Synthetic source documents and calculated report snapshots may be stored; raw query strings, the synthetic PII markers and session tokens may not. The temporary database is deleted after inspection.

Results contain case identifiers, categorical outcomes, controlled claim tags, pass/fail checks and source/case SHA256 fingerprints. They omit raw prompts, answers, tokens, credentials, transport payloads and exception messages. Timestamps, session signatures, report UUIDs and temporary paths are not compared or emitted. The cases and semantic expectations are fixed; generated timestamps vary.

## Reproducibility and interpretation

The runner fingerprints its own source plus the exercised service, security, store, router, retrieval, portfolio, calculation and attribution modules. Re-run the diagnostic after changes to those files; a prior result describes only its recorded snapshots. The associated tests also deliberately simulate four regressions—accepting a forged signature, accepting truthy approval, persisting a raw query and attempting urllib access—to verify the probes actually detect those failures.

The first actual run exposed an unsupported compound eligibility request: a sentence naming capital tiers and separately asking which debt instruments qualify was marked `evidence_found` against evidence tagged only for tier limits. Instrument-eligibility coverage was corrected to apply independently of word distance, and the unchanged case passed in the provisional run.

Limits remain substantial. The set does not test enterprise identity integration, production tenant isolation, operating-system compromise, concurrent-session attacks, exhaustive Unicode obfuscation, all prompt-injection forms, every PII format, network behavior of arbitrary third-party extensions, real external model responses or current legal completeness. Claim tags and authored phrase recognition do not prove semantic entailment. Passing 36 fixed probes means these specified paths met their expectations for the recorded code snapshot.
