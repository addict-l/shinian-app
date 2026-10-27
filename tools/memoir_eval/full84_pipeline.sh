#!/usr/bin/env bash
# v1.1 full-interview test, end to end (docs/prototypes/memoir-v1/handoffs/2026-10-27-full84-codex.md):
#   interview  finish mb2-full84 and mb2-full84-long (simulate/run_full.py --resume; finished work replays at 0 tokens)
#   check      0-token cache check of both runs (all 83 questions must replay identically)
#   book       grounded drafts (GROUNDED_DRAFT_PROMPT) -> book v1.1 (plan thinking on, write/check thinking off,
#              small pictures kept and marked, new facts dropped, chapters under 500 chars become sections)
#   export     book .md/.html, interview record .html, statistics .md/.json into $OUT
#   all        the four in order
#
# Environment: SHINIAN_EVAL_HOME (the unpacked eval-home), SHINIAN_DS_MODE=direct + DEEPSEEK_API_KEY (or the relay),
# SHINIAN_PERSONA_BACKEND=queue|openai (+ OPENAI_API_KEY, OPENAI_PERSONA_MODEL); OUT (default $SHINIAN_EVAL_HOME/../outputs);
# LONG_BOOK=1 also builds drafts + book for the long-answer variant (about 100 more DeepSeek calls).
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${SHINIAN_EVAL_HOME:?set SHINIAN_EVAL_HOME to the unpacked eval-home}"
PID=N-6733a23cd1
RUNS="${SHINIAN_EVAL_RUNS:-$SHINIAN_EVAL_HOME/runs}"
OUT="${OUT:-$SHINIAN_EVAL_HOME/../outputs}"
PY="${PYTHON:-python3}"
BOOK_FLAGS=(--premerge --plan-prompt plan-v3.txt --simplify --ratio 0.7 --check-thinking disabled
            --check-prompt check-v3.txt --fallback match --short-merge 500 --prefix mb2 --variants v1.1=write-v3.txt:disabled)

interview() {
  # both runs at once: each sends one DeepSeek batch at a time; the elder backend serves both
  $PY tools/interview_eval/simulate/run_full.py --people $PID --name mb2-full84 --resume --chains module \
      >> "$RUNS/mb2-full84.log" 2>&1 &
  local a=$!
  $PY tools/interview_eval/simulate/run_full.py --people $PID --name mb2-full84-long --resume --chains module \
      --sim-config docs/prototypes/memoir-v1/sim-config-long.json >> "$RUNS/mb2-full84-long.log" 2>&1 &
  local b=$!
  local rc=0
  wait $a || rc=$?
  wait $b || rc=$?
  tail -n 2 "$RUNS/mb2-full84.log" "$RUNS/mb2-full84-long.log"
  return $rc
}

check() {
  local rc=0
  for r in mb2-full84 mb2-full84-long; do
    $PY tools/interview_eval/simulate/v6_replay.py cache $r > "$RUNS/$r/cache-check.json" || rc=$?
    $PY - "$RUNS/$r/cache-check.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
print(json.dumps({k: d[k] for k in ('run', 'finished_now', 'questions_planned', 'cache_misses_in_saved', 'differences',
                                    'stale_saved', 'persona_models', 'params', 'ok')}, ensure_ascii=False))
EOF
  done
  return $rc
}

need_finished() {
  for r in "$@"; do
    [ -f "$RUNS/$r/sessions/$PID.json" ] || { echo "$r is not finished (no sessions/$PID.json): run the interview step" >&2; exit 2; }
  done
}

book() {
  need_finished mb2-full84
  $PY tools/memoir_eval/inputs.py --full mb2-full84:$PID --run mb2-inputs --prefix mb2
  $PY tools/memoir_eval/book.py --inputs "$RUNS/mb2-inputs/$PID-full84.json" --run mb2-book "${BOOK_FLAGS[@]}"
  if [ "${LONG_BOOK:-0}" = 1 ]; then
    need_finished mb2-full84-long
    $PY tools/memoir_eval/inputs.py --full mb2-full84-long:$PID --run mb2-inputs-long --prefix mb2
    $PY tools/memoir_eval/book.py --inputs "$RUNS/mb2-inputs-long/$PID-full84.json" --run mb2-book-long "${BOOK_FLAGS[@]}"
  fi
}

export_all() {
  need_finished mb2-full84
  mkdir -p "$OUT"
  local b="$RUNS/mb2-book/v1.1/books/$PID-full84"
  cp "$b.md" "$OUT/回忆录样书_${PID}_full84_v1.1.md"
  cp "$b.html" "$OUT/回忆录样书_${PID}_full84_v1.1.html"
  $PY tools/memoir_eval/full84.py html mb2-full84 $PID "$OUT/完整采访记录_${PID}_full84.html"
  $PY tools/memoir_eval/full84.py report mb2-full84 $PID "$OUT/统计_${PID}_full84.md" \
      --handoff "$RUNS/mb2-inputs/$PID-full84.json" --book "$b.json" --json "$OUT/统计_${PID}_full84.json"
  if [ -f "$RUNS/mb2-full84-long/sessions/$PID.json" ]; then
    $PY tools/memoir_eval/full84.py html mb2-full84-long $PID "$OUT/完整采访记录_${PID}_full84-long.html"
    local extra=()
    [ -f "$RUNS/mb2-inputs-long/$PID-full84.json" ] && extra+=(--handoff "$RUNS/mb2-inputs-long/$PID-full84.json")
    [ -f "$RUNS/mb2-book-long/v1.1/books/$PID-full84.json" ] && extra+=(--book "$RUNS/mb2-book-long/v1.1/books/$PID-full84.json")
    $PY tools/memoir_eval/full84.py report mb2-full84-long $PID "$OUT/统计_${PID}_full84-long.md" "${extra[@]}" \
        --json "$OUT/统计_${PID}_full84-long.json"
    local bl="$RUNS/mb2-book-long/v1.1/books/$PID-full84"
    if [ -f "$bl.md" ]; then
      cp "$bl.md" "$OUT/回忆录样书_${PID}_full84-long_v1.1.md"
      cp "$bl.html" "$OUT/回忆录样书_${PID}_full84-long_v1.1.html"
    fi
  fi
  ls -la "$OUT"
}

case "${1:-all}" in
  interview) interview ;;
  check) check ;;
  book) book ;;
  export) export_all ;;
  all) interview && check && book && export_all ;;
  *) echo "usage: $0 interview|check|book|export|all" >&2; exit 2 ;;
esac
