# Local deployment and operations

Python 3.11+ is required; implementation was exercised with Python3.13.12. No API key is required. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[dev]'
python -m pytest -q
python scripts/run_demo.py
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

Open http://127.0.0.1:8501 locally. The app seeds the original corpus, verified supplement and synthetic governance examples into `runtime/demo.sqlite`; `HKRBC_DB_PATH` can isolate another local database. Seeding is idempotent for unchanged versions. A changed existing version fails instead of overwriting evidence. See the login panel/README for public demonstration credentials. Password environment overrides must be set before process startup; an empty override uses the documented demo default. This is demonstration authentication, not production IAM.

`.env.example` documents configuration only. The app reads environment variables and **does not automatically load `.env` files**. Set variables in the launching environment. Keep secrets out of shell history, reports and source control. The server normally remains local. Do not expose these public demo accounts to a shared network.

The current workspace also supports a reproducible launch with its already installed environment:

```bash
/opt/anaconda3/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

That absolute interpreter is machine-specific, not a portable dependency. A clean install requires package access; offline operation refers to the installed app, not dependency installation. If an older setuptools editable installer fails on the Chinese workspace path under an ASCII locale, use the normal install above; no editable installation is required. On this machine, the project's `.venv` inherits already installed dependencies from Anaconda to avoid network installation.

## Optional local semantic retrieval

`HKRBC_RETRIEVAL_BACKEND=bm25` is the default and requires no model weights. `hash` retains the earlier lexical baseline. `dense` and `hybrid` additionally require the optional dependency and one of the two reviewed, pinned SentenceTransformers snapshots. An arbitrary local directory or a self-generated manifest is not accepted. These encoders rank evidence; they do not generate answers, calculate capital or verify legal claims. See [retrieval methods and measurements](retrieval-evaluation.md) before changing the default.

Provisioning is a separate, explicit network operation. The application and evaluation runner never download weights. To opt in, from an activated environment:

```bash
python -m pip install '.[semantic]'
# Explicit public-model download; do this only when intended.
python scripts/provision_embedding_model.py --model english
```

The script also accepts `--model multilingual`, selecting `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`; the English option selects `sentence-transformers/all-MiniLM-L6-v2`. It uses fixed reviewed revisions, checks revision identity and expected Apache-2.0 Hub metadata, and permits only HTTPS requests and redirects to `huggingface.co`, `hf.co` or their subdomains, with normal certificate verification. It downloads selected files from that revision and records byte counts and SHA256 values in `provision_manifest.json`.

The default destination is `runtime/models/<model-name>`; `--destination PATH` chooses a different **fresh** directory. Any existing file, directory, empty directory or symlink at the destination is rejected. Files are staged beside the destination, and the completed snapshot is published atomically without overwriting another destination. Failed staging is cleaned up; platforms without the required atomic no-overwrite operation fail explicitly. Existing snapshots are not updated in place.

The script sends requests for public model files and metadata, not user questions, application credentials or portfolios. Package installation and this explicit download require network access; subsequent encoder inference uses local files. The loader's approved snapshot identities are:

| Option | Fixed revision | Reviewed provision-manifest SHA256 |
| --- | --- | --- |
| `english` | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | `41a2225d194e4a3593bec0dfdb05a1665338af6bb785babee45d9b1a8226e6c8` |
| `multilingual` | `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` | `cbc095bff2e8e001896def29f391b420956c63b426b51f7b413073616696a3bf` |

After provisioning, configure a backend and restart the application:

```bash
export HKRBC_RETRIEVAL_BACKEND=hybrid
export HKRBC_EMBEDDING_MODEL_PATH="$PWD/runtime/models/all-MiniLM-L6-v2"
export HF_HUB_DISABLE_TELEMETRY=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
python evaluation/retrieval_eval.py \
  --model-path "$HKRBC_EMBEDDING_MODEL_PATH" \
  --output runtime/retrieval-semantic.json
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

`HKRBC_EMBEDDING_MODEL_PATH` selects the location of an approved snapshot, not permission to load arbitrary weights. Before importing or constructing SentenceTransformers, the adapter requires the exact approved model/revision/manifest identity, complete expected file inventory, every file's size and hash, and the approved built-in Transformer/Pooling module graph, with Normalize for the English snapshot. It rejects symlinks, extra files, Python/pickle payloads and custom model/tokenizer code mappings. The approved architecture/tokenizers are built-in BERT implementations. Missing or self-generated manifests do not suffice.

The adapter also forces all three offline/telemetry flags, requires safetensors weights, and loads on CPU with `local_files_only=True` and `trust_remote_code=False`. Missing dependencies, absent weights, unreviewed content, invalid manifests or load failures stop the configured semantic route; the app neither downloads replacements nor silently switches backends. The evaluation runner can still measure lexical methods while recording semantic loading as `not_run`.

File hashes alone establish consistency, not independent authenticity. The trust basis is the reviewed model/revision/manifest identity pinned in the application policy plus normal HTTPS origin verification during provisioning; these manifest hashes are not publisher signatures. The application code, installed libraries and host operator remain trusted. See [the loader policy](../src/hkrbc_agent/embeddings.py).

Both approved snapshots passed actual local loading and inference checks with the Hugging Face/Transformers offline controls enabled, rather than only mocked. This establishes the observed local execution path, not better bilingual retrieval, actuarial validity or general network-isolation assurance. The measured English model has a 256-wordpiece input limit; character-based sections plus their headings can exceed it. Consult the model metadata and measured results before selecting a model. Weights and runtime measurements remain under ignored `runtime/`; the application does not need them for BM25 operation.

## Optional local commentary model

Run an independently installed Ollama instance with an already provisioned model, set `HKRBC_LOCAL_MODEL` and optionally `HKRBC_OLLAMA_URL` to a loopback HTTP endpoint, then restart. This application does not install Ollama or download weights. Failure yields an explicit error, with no external fallback. This integration is transport-mocked in tests; a real local model was not available for verification.

Ollama commentary and SentenceTransformers retrieval are separate options. The successful local encoder run does not establish that a generative Ollama model was tested.

## Optional external model

Set `HKRBC_EXTERNAL_ENABLED=true`, `HKRBC_OPENAI_MODEL` to an available model, and `OPENAI_API_KEY` via your secret manager, then restart. Reviewer/admin still needs explicit request approval, and only DLP-approved public evidence can be sent. Enabling configuration is not permission for Codex to incur charges. No live external requests were made or verified.

The optional adapter uses the [official Chat Completions request contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), checked on 2026-10-24: model plus messages, `store=false` and a 512-token completion ceiling. It omits sampling temperature to avoid assuming support across configurable models. This is not a zero-retention guarantee or confirmation that a particular account/model supports the endpoint; verify model compatibility and organizational retention policy before enabling it.

## Evidence lifecycle and verification

Administrators can ingest a successor as a new document version and then retire the old `document_id@version` through Governance & Audit. Retirement is an explicit curator decision; the application does not choose the newest version by sorting version strings. The optional successor must already exist and must not be quarantined, superseded or retired. Retirement decisions are immutable through the application API, while the original payload and references in existing reports remain available for authorized historical inspection.

Ordinary retrieval excludes retired and explicitly superseded versions before lexical or semantic processing. The authorized document register retains their history and lifecycle labels. Ingesting a new version alone does not retire another version or certify the replacement as current law. Re-seeding the same source versions does not remove recorded retirements.

The corpus distinguishes original-law baselines from future amendments. Neither source hashes nor retirement establish current consolidated law or regulatory compliance. Validate distributed provenance without downloading sources:

```bash
python scripts/verify_source_register.py
# Optional: additionally require the private, already downloaded PDF cache.
python scripts/verify_source_register.py --require-cache
```

The second command intentionally fails when the private cache is absent. Exclude `runtime/source-cache/` from release archives: it contains research-only source PDFs, snapshots and rendered pages without a public-redistribution licence being asserted. A `.gitignore` rule alone does not control arbitrary archive tools. See [source verification and rights limits](source-verification-2026-10-25.md).

## Local checks and GitHub Actions

Run the tests, provenance verifier and evaluation commands locally before release. The installed [GitHub Actions workflow](../.github/workflows/verify.yml) performs a clean package install on Ubuntu with Python 3.11 and 3.13, then runs tests, provenance metadata checks, deterministic fixtures, lexical retrieval diagnostics and the synthetic demonstration. It uses BM25 and offline model settings without provisioning encoder weights. Dependency installation still needs package access. Only evaluation JSON files are uploaded as CI artifacts; private source caches, model weights and local audit databases are excluded. See [observed verification results](phase2-verification.md); a workflow's presence alone does not mean it passed or protects a branch.

## Container example

```bash
docker build -t hkrbc-actuarial-agent .
docker run --rm -p 127.0.0.1:8501:8501 hkrbc-actuarial-agent
```

The image runs as an unprivileged user. State is ephemeral without an appropriately owned `/app/runtime` volume; exports should be downloaded. Docker instructions are provided but were not executed in this environment. Shared/public deployment additionally needs real authentication, TLS, network controls, encrypted persistence, enterprise DLP, retention, approval records and independent security/regulatory review. No public deployment was performed.
