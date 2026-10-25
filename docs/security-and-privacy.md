# Security and privacy

## Demonstration threat model

Protect against one signed-in demonstration role reading another classification, prompt text in documents affecting application control flow, accidental external inference and raw personal information entering the audit log. The host operator, Python interpreter, SQLite file owner and administrators are trusted. There is one local demonstration workspace, not separate enterprise tenants.

| Operation | Analyst | Reviewer | Administrator |
|---|---|---|---|
| Public evidence / calculations / own reports | Yes | Yes | Yes |
| Internal evidence | No | Yes | Yes |
| Restricted evidence | No | No | Yes |
| Ingest / retire document versions | No | No | Yes |
| Read own audit | Yes | Yes | Yes |
| Read all audit / other users' reports | No | Yes | Yes |
| Request external commentary | No | Conditional | Conditional |

The UI is not a security boundary. `AgentService` verifies an HMAC-signed one-hour session for every method. Forging a role in a token fails verification. SQLite retrieval includes a classification predicate before any payload is loaded or embedded; output is checked again. Reports require ownership or reviewer/admin permission. Logging out or changing identity clears results and input state. Credentials can be replaced using environment variables; default demo credentials are intentionally public and offer no enterprise security. This is not production IAM, tenant isolation or an enterprise approval system.

## Optional local encoder and provisioning boundary

Default `HKRBC_RETRIEVAL_BACKEND=bm25` retrieval requires no pretrained model. Opt-in `dense` and `hybrid` retrieval accept only the two reviewed local model snapshots pinned by model ID, revision and provision-manifest SHA256 in the loader policy. The configured directory is a storage location for one approved snapshot; arbitrary local weights or a self-generated manifest are not supported. The application and benchmark runner do not install dependencies, download weights, fetch missing files or fall back to a hosted embedding service. A requested semantic route fails explicitly when the dependency, files or load checks are unavailable.

`scripts/provision_embedding_model.py` is the separate **explicit opt-in download operation**. It requests public model metadata and selected files from two allowlisted repositories at fixed reviewed revisions, checks revision identity and expected Apache-2.0 model metadata, and records file sizes and hashes in a local manifest. Every request/redirect must use HTTPS on `huggingface.co`, `hf.co` or their subdomains, with ordinary certificate verification. It does not submit questions, portfolio content or application credentials. Provisioning contacts the public model host and therefore has a network footprint; it is not part of offline app inference.

Downloads are staged in a sibling temporary directory and published atomically to a fresh destination after the manifest is complete. Existing destinations, including empty directories and symlinks, are rejected; failed staging is removed. Model files remain under ignored `runtime/models/` by default. An alternative destination must receive equivalent host-file protection. Provisioning completion is not a substitute for the loader's separate reviewed-snapshot validation.

Before importing or constructing SentenceTransformers, the encoder adapter requires an approved model/revision/manifest identity, the exact complete file inventory and matching sizes/hashes. It rejects symlinks, extra files, Python/pickle payloads and custom code mappings in model/tokenizer configuration. Only the reviewed built-in Transformer/Pooling graph, plus Normalize for the English model, is accepted, with built-in BERT architecture/tokenizers. `trust_remote_code=False` alone would not rule out every executable local module graph; these preceding validation checks are part of the boundary.

The adapter forces `HF_HUB_DISABLE_TELEMETRY=1`, `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` before the heavy model imports. It requires safetensors and uses CPU with `local_files_only=True` and `trust_remote_code=False`. Local file hashes establish consistency, not independent authenticity. Trust is anchored by the reviewed manifest identities in application code and normal HTTPS origin verification during provisioning, not a publisher-signed manifest or arbitrary local declarations. An attacker able to modify trusted application code or installed dependencies remains outside this boundary. The flags are application/library controls, not an independently enforced egress firewall.

Authorization and active-version filtering occur before lexical features or semantic vectors are created. The retrieval layer independently filters classification even if a defective store adapter returns unauthorized records. Obvious injected instructions are rejected and potential query PII is redacted before encoding. Document text and vectors are request-local; they are not persisted or shared across identities in a document-vector cache. The loaded model weights may be reused, but an analyst request cannot reuse restricted document vectors from an earlier administrator request.

Both approved snapshots passed actual local loading/inference checks with the offline controls enabled; encoder boundary tests also use spies to check text exposure. Neither result establishes Chinese/domain accuracy, complete DLP or semantic entailment. Token limits can truncate evidence even when the stored character-based chunk is accepted. See [deployment instructions](deployment.md) and [retrieval evaluation limits](retrieval-evaluation.md).

## Evidence versions and retirement

Document payloads remain immutable by `document_id` and `version`. An administrator can record an explicit immutable retirement decision and optional existing successor without rewriting the source payload. Ordinary retrieval excludes retired and explicitly superseded records before encoding. Creating a new version does not automatically deactivate another version; curator review and retirement are separate operations.

The authorized history/register can still show retired payloads and existing report references. Retirement metadata is classification-filtered; a successor's identifier is hidden from roles that cannot access its classification. Retirement is not deletion, encryption or a guarantee that old exports have been recalled. The SQLite owner can alter the underlying files, so API immutability is not tamper-proof storage.

Verified source bytes and precise page locators do not establish present consolidated law. The original-law baselines and future amendments retain their separate statuses and limitations. The scope checker blocks current-law conclusions when verified-current evidence is absent, and treats explicitly prospective questions separately. Curated claim tags and passage relevance do not prove that every answer is legally entailed or complete. No production regulatory-compliance or current consolidated-law certification is claimed.

## External processing

Default configuration produces deterministic local answers and never invokes a model API. An optional Ollama commentary model must be explicitly configured at a loopback HTTP endpoint. It is separate from the local retrieval encoder. HTTP redirects and environment proxies are disabled for commentary-model transport, so local transport does not silently move to an external URL. The application does not install/download models or fall back to a remote provider; the separate public-model provisioning script requires its own explicit invocation.

External OpenAI calls require all of:

1. `HKRBC_EXTERNAL_ENABLED=true` on the server.
2. A reviewer or administrator signed session.
3. Literal boolean `True` approval for this request.
4. Public classification for every retrieved record.
5. DLP acceptance of original prompt and document text/metadata.
6. Explicit model name and `OPENAI_API_KEY` in the environment.

No live paid calls were made during implementation. Enabling the route does not grant permission to make paid calls on the user's behalf. The transport adapter is tested with in-memory responses; vendor policy, billing, retention and real network behavior are unverified. The demo checkbox is not an enterprise approval or consent-record system.

Only the query and evidence text enter a model request. Metadata and portfolio files are excluded. Output DLP and generated-citation checks fail closed; generated prose remains unverified. Rejecting obvious citation formats is not a proof of semantic factuality.

## Input and content controls

PII patterns cover email, HKID-like strings, Hong Kong telephone-like numbers, long card-like numbers and obvious API-secret assignments. Local queries are redacted before retrieval/local-model use; original sensitive queries cannot pass the external gate. Uploads require an explicit synthetic-only declaration. Strict CSV field types, finite numeric assumptions, unique identifiers, date consistency, schema/row/size limits and price reconciliation protect the calculation boundary. Numeric financial columns are validated as numbers rather than classified as telephone numbers; free-text fields are scanned individually. Synthetic provenance cannot be proven from file contents.

Admin ingestion accepts validated JSON section records. It rejects PII in natural-language metadata, credential/query-bearing source URLs, and obvious injection instructions before chunking. The lower-level document store quarantines injected records, and the retrieval layer rejects them again. Evidence is always data; no retrieved text can invoke application functions or shell commands. Pattern matching is incomplete; obfuscated injection and PII, names, addresses, context-specific confidential facts and multilingual variants may evade it. Use synthetic data exclusively.

## Audit and storage

Audit events store demo username/role, UTC timestamp, document IDs and versions, fixed calculation versions, controlled validation statuses, provider, retrieval method, counts, error category and UUID report identifier. Retirement events record controlled document references. Audit keys and values are allowlisted. Raw prompts, exception messages, uploaded files, model outputs, credentials and personal data are not logged. Failed retrieval/calculation attempts produce categorical events only. SQLite contains curated evidence, retirement records, synthetic report results and audit metadata; report results intentionally include synthetic calculation inputs for traceability.

The database is plaintext, local, single-workspace and **not tamper-proof**. There is no encryption at rest, remote backup, immutable retention, SSO, rate limiting, tenant isolation or certified DLP. Protect host files and avoid shared exposure. Stop the app before removing `runtime/` to reset local demonstration state; that directory can also contain downloaded models, private source snapshots, retirement records and audit history. A database configured elsewhere through `HKRBC_DB_PATH` and reports copied to `reports/` are separate. Production retention and deletion policy must be designed separately.

Private source PDFs, rendered pages and complete snapshots in `runtime/source-cache/` are research-cache artifacts, not licensed public corpus exports. Exclude them from distributed archives and apply the rights restrictions in [the source-verification record](source-verification-2026-10-25.md). Public encoder files have a separate model-license assessment; a manifest's license label does not grant rights to unrelated regulatory source material.

## Verification

Tests cover cross-role SQL retrieval, second-filter defense, forged/expired tokens, report ownership, PII audit rejection, atomic invalid ingestion, injection quarantine, synthetic-only input checks, malformed CSV, default offline routing, external approval bypass attempts, nonpublic/sensitive external blocking, loopback restrictions, redirect refusal and response filtering. Phase 2 adds local-encoder authorization spies, offline/load restrictions, manifest integrity, version retirement, source-provenance consistency and request-scope checks. Passing these examples establishes prototype behavior, not a security certification or complete adversarial evaluation.

`docs/ci/verify.yml` is an inactive verification template stored outside GitHub's workflow directory. Its presence does not mean CI ran, passed or protects a branch. Optional provisioning and actual local encoder inference are separate from that BM25-only template; no live paid-model testing is implied.
