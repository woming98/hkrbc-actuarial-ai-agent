# Security and privacy

## Demonstration threat model

Protect against one signed-in demonstration role reading another classification, prompt text in documents affecting application control flow, accidental external inference and raw personal information entering the audit log. The host operator, Python interpreter, SQLite file owner and administrators are trusted. There is one local demonstration workspace, not separate enterprise tenants.

| Operation | Analyst | Reviewer | Administrator |
|---|---|---|---|
| Public evidence / calculations / own reports | Yes | Yes | Yes |
| Internal evidence | No | Yes | Yes |
| Restricted evidence | No | No | Yes |
| Ingest document versions | No | No | Yes |
| Read own audit | Yes | Yes | Yes |
| Read all audit / other users' reports | No | Yes | Yes |
| Request external commentary | No | Conditional | Conditional |

The UI is not a security boundary. `AgentService` verifies an HMAC-signed one-hour session for every method. Forging a role in a token fails verification. SQLite retrieval includes a classification predicate before any payload is loaded or embedded; output is checked again. Reports require ownership or reviewer/admin permission. Logging out clears displayed results. Credentials can be replaced using environment variables; default demo credentials are intentionally public and offer no enterprise security.

## External processing

Default configuration produces deterministic local answers and never invokes a model API. An optional Ollama model must be explicitly configured at a loopback HTTP endpoint. HTTP redirects and environment proxies are disabled for model transport, so local transport does not silently move to an external URL. The application does not install/download models or fall back to a remote provider.

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

Audit events store demo username/role, UTC timestamp, document IDs and versions, fixed calculation versions, controlled validation statuses, provider, counts, error category and UUID report identifier. Audit keys and values are allowlisted. Raw prompts, exception messages, uploaded files, model outputs, credentials and personal data are not logged. Failed retrieval/calculation attempts produce categorical events only. SQLite contains curated evidence, synthetic report results and audit metadata; report results intentionally include synthetic calculation inputs for traceability.

The database is plaintext, local, single-workspace and **not tamper-proof**. There is no encryption at rest, remote backup, immutable retention, SSO, rate limiting, tenant isolation or certified DLP. Protect host files and avoid shared exposure. Stop the app before removing `runtime/` to reset all local demonstration state; resetting also destroys audit history. Reports copied to `reports/` remain separate files. Production retention and deletion policy must be designed separately.

## Verification

Tests cover cross-role SQL retrieval, second-filter defense, forged/expired tokens, report ownership, PII audit rejection, atomic invalid ingestion, injection quarantine, synthetic-only input checks, malformed CSV, default offline routing, external approval bypass attempts, nonpublic/sensitive external blocking, loopback restrictions, redirect refusal and response filtering. Passing these examples establishes prototype behavior, not a security certification or complete adversarial evaluation.
