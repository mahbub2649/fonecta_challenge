#!/bin/bash -l
# Build the model's Python environment on LUMI. Runs on a login node, called by `lumi/lumi.sh setup`.
#
#   setup_env.sh ENV_DIR REQUIREMENTS_FILE      (FORCE=1 rebuilds an existing one)
#
# First choice is LUMI's container wrapper (tykky): the whole environment is one image file, which Lustre handles
# far better than thousands of small Python files. If the wrapper isn't available, it falls back to a plain venv.
set -euo pipefail
ENV_DIR=${1:?usage: setup_env.sh ENV_DIR REQUIREMENTS_FILE}
REQ=${2:?usage: setup_env.sh ENV_DIR REQUIREMENTS_FILE}

check() {
  "$ENV_DIR/bin/python3" -c "import lightgbm, numpy, pandas, pyarrow, sklearn; print('environment ok: lightgbm', lightgbm.__version__, '| pandas', pandas.__version__)"
}

if [ -x "$ENV_DIR/bin/python3" ] && [ "${FORCE:-0}" != 1 ]; then
  echo "Environment already at $ENV_DIR (FORCE=1 to rebuild)"
  check
  exit 0
fi

rm -rf "$ENV_DIR"
mkdir -p "$(dirname "$ENV_DIR")"
module load LUMI >/dev/null 2>&1 || true
module load cray-python
built=0
if module load lumi-container-wrapper >/dev/null 2>&1; then
  echo "Building with lumi-container-wrapper into $ENV_DIR"
  if pip-containerize new --prefix "$ENV_DIR" "$REQ"; then
    built=1
  else
    echo "Container build failed, falling back to a venv"
    rm -rf "$ENV_DIR"
  fi
fi
if [ "$built" = 0 ]; then
  echo "Building a venv with cray-python into $ENV_DIR"
  python3 -m venv "$ENV_DIR"
  "$ENV_DIR/bin/pip" install --quiet --upgrade pip
  "$ENV_DIR/bin/pip" install --quiet -r "$REQ"
fi
check
