#!/usr/bin/env bash
# Start both SO-101 followers fed by the remote leaders (provisional, F-003).
#
# Usage: LEADER_HOST=<laptop tailnet name> scripts/run_car_so101_remote.sh --confirm-safe-workspace
#   LEROBOT_PYTHON   LeRobot venv python (default /home/nasc/lebot/lerobot/.venv/bin/python)
#   NASURA_HARDWARE_DIR  hardware checkout (default /home/nasc/hardware)
#   SO101_MAX_RELATIVE_TARGET  degrees per cycle, 0 < x <= 5 (default 5.0)
# If either follower exits, the other is stopped too (DD-0026).
# Side Effects: drives both follower arms; listens on UDP 47110/47111; writes logs/.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${LEADER_HOST:?set LEADER_HOST, e.g. laptop-dynabook}"
if [[ "${1:-}" != "--confirm-safe-workspace" ]]; then
  echo "Confirm attendant at the follower power switch, clear workspace and no load," >&2
  echo "then pass --confirm-safe-workspace." >&2
  exit 2
fi
PY="${LEROBOT_PYTHON:-/home/nasc/lebot/lerobot/.venv/bin/python}"
HW="${NASURA_HARDWARE_DIR:-/home/nasc/hardware}"
MRT="${SO101_MAX_RELATIVE_TARGET:-5.0}"

pids=()
stop_all() {
  for p in "${pids[@]}"; do kill -TERM "$p" 2>/dev/null || true; done
  for _ in $(seq 50); do
    alive=0
    for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && alive=1; done
    [[ $alive == 0 ]] && return
    sleep 0.1
  done
  for p in "${pids[@]}"; do kill -KILL "$p" 2>/dev/null || true; done
}
trap 'stop_all' INT TERM EXIT

for side in left right; do
  "$PY" scripts/so101_follower_sink.py --side "$side" --allow-from "$LEADER_HOST" \
    --hardware-dir "$HW" --max-relative-target "$MRT" --confirm-safe-workspace &
  pids+=($!)
done

# Return as soon as either follower exits; the trap stops the other.
set +e
wait -n "${pids[@]}"
code=$?
echo "a follower exited with code ${code}; stopping the other" >&2
exit "$code"
