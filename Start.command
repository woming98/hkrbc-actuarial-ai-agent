#!/bin/zsh
# Local demonstration launcher. External inference remains disabled.
set -eu
task_root="${0:A:h}"
cd "$task_root"
task_python="$task_root/.venv/bin/python"
if [[ ! -x "$task_python" ]]; then
  print 'Create the Python environment using the README before starting.'
  exit 1
fi
export HKRBC_EXTERNAL_ENABLED=false
export HKRBC_LOCAL_MODEL=''
exec "$task_python" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
