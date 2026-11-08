#!/bin/bash -l
# One experiment per array task: line N+1 of $GRID is the config for task N. Submitted by lumi/lumi.sh, which sets
# --account, --partition, --time, --cpus-per-task, --mem, --array and --output.
#SBATCH --job-name=fonecta-kw
#SBATCH --nodes=1
#SBATCH --ntasks=1
set -euo pipefail
: "${LUMI_WORK:?}" "${LUMI_ENV:?}" "${GRID:?}"

export PATH="$LUMI_ENV/bin:$PATH"
export CONNECT_DATA_DIR="$LUMI_WORK/fonecta_data/FONECTA_CONNECT_SUGGESTS_2026"
export MODEL_N_JOBS="${SLURM_CPUS_PER_TASK:-16}"
export OMP_NUM_THREADS="$MODEL_N_JOBS"
cd "$LUMI_WORK/repo"

INDEX="${SLURM_ARRAY_TASK_ID:-0}"
CONFIG=$(sed -n "$((INDEX + 1))p" "$GRID")
if [ -z "$CONFIG" ]; then
  echo "No line $((INDEX + 1)) in $GRID"
  exit 1
fi
NAME=$(python3 -c 'import json, sys; print(json.loads(sys.argv[1])["name"])' "$CONFIG")
echo "task $INDEX on $(hostname), $MODEL_N_JOBS cores: $CONFIG"

# EXTRA_ARGS is either empty or --write (the final run).
python3 model/experiment.py --config "$CONFIG" --run-dir "$LUMI_WORK/runs/$NAME" \
  --out "$LUMI_WORK/results/$NAME.json" ${EXTRA_ARGS:-}

# The feature tables are a few hundred MB per run. Keep the keyword list and scores, drop the rest.
if [ "${KEEP_RUNS:-0}" != 1 ]; then
  rm -rf "$LUMI_WORK/runs/$NAME/var/model"
fi
