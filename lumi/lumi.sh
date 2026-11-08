#!/usr/bin/env bash
# Drive the keyword sweep on LUMI from this laptop. See lumi/README.md.
#
#   lumi/lumi.sh check            test the SSH connection and show the project's allocation
#   lumi/lumi.sh sync             copy the code and the challenge data to LUMI (.env and keys stay here)
#   lumi/lumi.sh setup            build the Python environment on LUMI (once)
#   lumi/lumi.sh smoke            one baseline run on the debug partition, to test the whole path
#   lumi/lumi.sh sweep [small|full]   submit the sweep as a Slurm job array
#   lumi/lumi.sh status           queue state and how many results are in
#   lumi/lumi.sh logs [N]         last N lines of the newest job log (default 40)
#   lumi/lumi.sh fetch            bring the results here and print the leaderboard
#   lumi/lumi.sh final            rebuild the predictions on LUMI with the winning setting
#   lumi/lumi.sh pull             bring the final predictions, model decisions and keyword list into this repo
#   lumi/lumi.sh cancel           cancel this pipeline's queued and running jobs
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(dirname "$HERE")
CONF="${LUMI_CONFIG:-$HERE/config.env}"
if [ ! -f "$CONF" ]; then
  echo "Copy lumi/config.env.example to lumi/config.env and fill in your LUMI username and project."
  exit 1
fi
# shellcheck disable=SC1090
source "$CONF"
[ -d /appl/lumi ] && LUMI_USER=${LUMI_USER:-$USER}
: "${LUMI_USER:?set LUMI_USER in $CONF}" "${LUMI_PROJECT:?set LUMI_PROJECT in $CONF}"
LUMI_HOST=${LUMI_HOST:-lumi.csc.fi}
LUMI_WORK=${LUMI_WORK:-/scratch/$LUMI_PROJECT/$LUMI_USER/fonecta}
LUMI_ENV=${LUMI_ENV:-/projappl/$LUMI_PROJECT/$LUMI_USER/fonecta-env}
DATA_LOCAL=${DATA_LOCAL:-$REPO/../fonecta_data/FONECTA_CONNECT_SUGGESTS_2026}
LUMI_PARTITION=${LUMI_PARTITION:-small}
LUMI_CPUS=${LUMI_CPUS:-16}
LUMI_MEM=${LUMI_MEM:-32G}
LUMI_TIME=${LUMI_TIME:-01:30:00}
LUMI_MAX_PARALLEL=${LUMI_MAX_PARALLEL:-24}
JOB_NAME=fonecta-kw

# One SSH connection is reused for every command, so the key is only unlocked once.
SSH_OPTS=(-o ControlMaster=auto -o "ControlPath=$HOME/.ssh/cm-%r@%h:%p" -o ControlPersist=15m)
if [ -n "${LUMI_SSH_KEY:-}" ]; then
  SSH_OPTS+=(-i "${LUMI_SSH_KEY/#\~/$HOME}")
fi
TARGET="$LUMI_USER@$LUMI_HOST"

# On LUMI itself (for example in the web interface's login-node shell), run commands here instead of over SSH.
if [ -n "${LUMI_LOCAL:-}" ] || [ -d /appl/lumi ]; then
  ON_LUMI=1
  R=""
  remote() { bash -lc "$1"; }
  copy() { rsync -a "$@"; }
else
  ON_LUMI=0
  R="$TARGET:"
  remote() { ssh "${SSH_OPTS[@]}" "$TARGET" "bash -lc $(printf '%q' "$1")"; }
  copy() { rsync -az -e "ssh ${SSH_OPTS[*]}" "$@"; }
fi

# The same folder twice (a clone made right at $LUMI_WORK/repo) needs no copy.
same_dir() { [ -d "$2" ] && [ "$(cd "$1" && pwd -P)" = "$(cd "$2" && pwd -P)" ]; }

sync_code() {
  remote "mkdir -p '$LUMI_WORK/repo' '$LUMI_WORK/fonecta_data/FONECTA_CONNECT_SUGGESTS_2026' '$LUMI_WORK/results' '$LUMI_WORK/logs'"
  if [ "$ON_LUMI" = 1 ] && same_dir "$REPO" "$LUMI_WORK/repo"; then
    echo "Code already in place at $LUMI_WORK/repo"
    return
  fi
  # Secrets never leave this laptop: .env holds the Yext sandbox key, lumi/config.env the LUMI details.
  copy --delete \
    --exclude '.git/' --exclude 'var/' --exclude '.env' --exclude '.env.*' --exclude 'lumi/config.env' \
    --exclude 'lumi/results/' --exclude '__pycache__/' --exclude '.venv/' --exclude '.DS_Store' \
    "$REPO/" "${R}$LUMI_WORK/repo/"
  echo "Code synced to $LUMI_WORK/repo"
}

sync_data() {
  if [ ! -f "$DATA_LOCAL/evaluation/evaluate.py" ]; then
    echo "Can't find the challenge package at $DATA_LOCAL. Set DATA_LOCAL in $CONF."
    exit 1
  fi
  if [ "$ON_LUMI" = 1 ] && same_dir "$DATA_LOCAL" "$LUMI_WORK/fonecta_data/FONECTA_CONNECT_SUGGESTS_2026"; then
    echo "Data already in place"
    return
  fi
  copy --exclude '.DS_Store' "$DATA_LOCAL/" "${R}$LUMI_WORK/fonecta_data/FONECTA_CONNECT_SUGGESTS_2026/"
  echo "Data synced to $LUMI_WORK/fonecta_data (synthetic, CC BY 4.0)"
}

# submit GRID_FILE_ON_LUMI PARTITION TIME [EXTRA_ARGS]
submit() {
  local grid=$1 partition=$2 time=$3 extra=${4:-}
  local count
  count=$(remote "wc -l < '$grid'" | tr -d ' ')
  local job
  job=$(remote "cd '$LUMI_WORK/repo' && sbatch --parsable --account='$LUMI_PROJECT' --partition='$partition' --time='$time' \
    --cpus-per-task='$LUMI_CPUS' --mem='$LUMI_MEM' --array=0-$((count - 1))%$LUMI_MAX_PARALLEL \
    --output='$LUMI_WORK/logs/%x-%A_%a.out' \
    --export=ALL,LUMI_WORK='$LUMI_WORK',LUMI_ENV='$LUMI_ENV',GRID='$grid',EXTRA_ARGS='$extra' lumi/job.sbatch")
  echo "Submitted job $job: $count experiment(s) on $partition, at most $LUMI_MAX_PARALLEL at once."
  echo "Follow it with: lumi/lumi.sh status"
}

cmd=${1:-help}
case "$cmd" in
  check)
    remote "echo \"Connected to \$(hostname) as \$USER\"; lumi-allocations 2>/dev/null | head -20 || true; ls -ld /scratch/$LUMI_PROJECT /projappl/$LUMI_PROJECT"
    ;;
  sync)
    sync_code
    sync_data
    ;;
  setup)
    sync_code
    remote "bash '$LUMI_WORK/repo/lumi/setup_env.sh' '$LUMI_ENV' '$LUMI_WORK/repo/model/requirements.txt'"
    ;;
  smoke)
    python3 "$HERE/grid.py" --size smoke > "$HERE/grid-smoke.jsonl"
    sync_code
    submit "$LUMI_WORK/repo/lumi/grid-smoke.jsonl" debug 00:30:00
    ;;
  sweep)
    size=${2:-small}
    python3 "$HERE/grid.py" --size "$size" > "$HERE/grid.jsonl"
    echo "$(wc -l < "$HERE/grid.jsonl" | tr -d ' ') experiments in the $size grid"
    sync_code
    submit "$LUMI_WORK/repo/lumi/grid.jsonl" "$LUMI_PARTITION" "$LUMI_TIME"
    ;;
  status)
    remote "squeue -u \$USER --name=$JOB_NAME -o '%.18i %.9P %.8T %.10M %.12l %R' | head -40; \
      echo; echo \"\$(ls '$LUMI_WORK/results' 2>/dev/null | grep -c json || true) result file(s) in $LUMI_WORK/results\"; \
      failed=\$(grep -l -E 'Traceback|Error|CANCELLED|oom' '$LUMI_WORK'/logs/*.out 2>/dev/null | head -5); \
      if [ -n \"\$failed\" ]; then echo 'Logs with errors:'; echo \"\$failed\"; fi"
    ;;
  logs)
    remote "f=\$(ls -t '$LUMI_WORK'/logs/*.out 2>/dev/null | head -1); [ -n \"\$f\" ] && { echo \"== \$f\"; tail -n ${2:-40} \"\$f\"; } || echo 'No logs yet'"
    ;;
  fetch)
    mkdir -p "$HERE/results"
    copy "${R}$LUMI_WORK/results/" "$HERE/results/"
    python3 "$HERE/collect.py" "$HERE/results"
    ;;
  final)
    mkdir -p "$HERE/results"
    copy "${R}$LUMI_WORK/results/" "$HERE/results/"
    python3 "$HERE/collect.py" "$HERE/results" --best > "$HERE/final.jsonl"
    echo "Final setting: $(cat "$HERE/final.jsonl")"
    sync_code
    submit "$LUMI_WORK/repo/lumi/final.jsonl" "$LUMI_PARTITION" "$LUMI_TIME" --write
    ;;
  pull)
    copy "${R}$LUMI_WORK/results/final.json" "$HERE/results/final.json"
    copy "${R}$LUMI_WORK/repo/predictions_2026.csv" "$REPO/predictions_2026.csv"
    copy "${R}$LUMI_WORK/repo/connect/model_decisions.json" "$REPO/connect/model_decisions.json"
    if remote "test -f '$LUMI_WORK/repo/model/keywords.json'"; then
      copy "${R}$LUMI_WORK/repo/model/keywords.json" "$REPO/model/keywords.json"
    else
      rm -f "$REPO/model/keywords.json"
    fi
    python3 -c "import json,sys; r=json.load(open(sys.argv[1])); print(r['name'], {k: v['score_0_100'] for k, v in r['summary'].items()})" "$HERE/results/final.json"
    echo "Check the score here with the organisers' scorer:"
    echo "  python3 $DATA_LOCAL/evaluation/evaluate.py --predictions $REPO/predictions_2026.csv"
    ;;
  cancel)
    remote "scancel -u \$USER --name=$JOB_NAME && echo 'Cancelled $JOB_NAME jobs'"
    ;;
  *)
    sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
    ;;
esac
