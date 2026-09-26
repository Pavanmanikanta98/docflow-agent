#!/usr/bin/env bash
# Runs a long-lived, checkpointed evaluation module and restarts it
# automatically if it exits non-zero (a dropped connection, a transient
# proxy blip, a container hiccup). Safe to use because these modules
# checkpoint their own progress (see run_ocr_eval.py's
# evals/results/.ocr_eval_checkpoint.json and run_judge_eval.py's
# evals/results/.judge_eval_checkpoint.json): a restart only replays
# whatever hadn't succeeded yet, never redoes finished work.
#
# This does not survive the whole container being killed and not
# restarted at all - only re-run this script after a restart if nothing
# else already relaunched it.
#
# Usage:
#   scripts/run_eval_resilient.sh backend.tests.evaluation.run_ocr_eval
#   scripts/run_eval_resilient.sh backend.tests.evaluation.run_ocr_eval /tmp/ocr_eval.log
set -uo pipefail

MODULE="${1:?Usage: run_eval_resilient.sh <python.module.path> [log_file]}"
LOG_FILE="${2:-/tmp/$(basename "$MODULE").log}"
MAX_CONSECUTIVE_CRASHES=10
RETRY_DELAY_SECONDS=10

crashes=0
while true; do
  echo "$(date -Iseconds) starting $MODULE" >> "$LOG_FILE"
  uv run python -m "$MODULE" >> "$LOG_FILE" 2>&1
  exit_code=$?

  if [ "$exit_code" -eq 0 ]; then
    echo "$(date -Iseconds) $MODULE finished successfully" >> "$LOG_FILE"
    exit 0
  fi

  crashes=$((crashes + 1))
  echo "$(date -Iseconds) $MODULE exited $exit_code (crash $crashes/$MAX_CONSECUTIVE_CRASHES)" >> "$LOG_FILE"
  if [ "$crashes" -ge "$MAX_CONSECUTIVE_CRASHES" ]; then
    echo "$(date -Iseconds) too many consecutive crashes, giving up - check $LOG_FILE" >> "$LOG_FILE"
    exit 1
  fi
  sleep "$RETRY_DELAY_SECONDS"
done
