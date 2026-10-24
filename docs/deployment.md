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

Open http://127.0.0.1:8501 locally. The app seeds the curated corpus and synthetic governance examples into `runtime/demo.sqlite`; `HKRBC_DB_PATH` can isolate another local database. Seeding is idempotent for unchanged versions. A changed existing version fails instead of overwriting evidence. See the login panel/README for public demonstration credentials. Password environment overrides must be set before process startup; an empty override uses the documented demo default.

`.env.example` documents configuration only. The app reads environment variables and **does not automatically load `.env` files**. Set variables in the launching environment. Keep secrets out of shell history, reports and source control. The server normally remains local. Do not expose these public demo accounts to a shared network.

The current workspace also supports a reproducible launch with its already installed environment:

```bash
/opt/anaconda3/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

That absolute interpreter is machine-specific, not a portable dependency. A clean install requires package access; offline operation refers to the installed app, not dependency installation. If an older setuptools editable installer fails on the Chinese workspace path under an ASCII locale, use the normal install above; no editable installation is required. On this machine, the project's `.venv` inherits already installed dependencies from Anaconda to avoid network installation.

## Optional local model

Run an independently installed Ollama instance with an already provisioned model, set `HKRBC_LOCAL_MODEL` and optionally `HKRBC_OLLAMA_URL` to a loopback HTTP endpoint, then restart. This application does not install Ollama or download weights. Failure yields an explicit error, with no external fallback. This integration is transport-mocked in tests; a real local model was not available for verification.

## Optional external model

Set `HKRBC_EXTERNAL_ENABLED=true`, `HKRBC_OPENAI_MODEL` to an available model, and `OPENAI_API_KEY` via your secret manager, then restart. Reviewer/admin still needs explicit request approval, and only DLP-approved public evidence can be sent. Enabling configuration is not permission for Codex to incur charges. No live external requests were made or verified.

The optional adapter uses the [official Chat Completions request contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), checked on 2026-10-24: model plus messages, `store=false` and a 512-token completion ceiling. It omits sampling temperature to avoid assuming support across configurable models. This is not a zero-retention guarantee or confirmation that a particular account/model supports the endpoint; verify model compatibility and organizational retention policy before enabling it.

## Container example

```bash
docker build -t hkrbc-actuarial-agent .
docker run --rm -p 127.0.0.1:8501:8501 hkrbc-actuarial-agent
```

The image runs as an unprivileged user. State is ephemeral without an appropriately owned `/app/runtime` volume; exports should be downloaded. Docker instructions are provided but were not executed in this environment. Shared/public deployment additionally needs real authentication, TLS, network controls, encrypted persistence, enterprise DLP, retention, approval records and independent security/regulatory review. No public deployment was performed.
