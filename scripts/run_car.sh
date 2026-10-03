#!/usr/bin/env bash
# Start car_ctrl and the car_media page (Chromium kiosk) on the car PC (DD-0015).
#
# Usage: HUB_HOST=<hub>.<tailnet>.ts.net scripts/run_car.sh
#   FAKE_MEDIA=1  use Chromium fake camera/mic (development without X4)
#   INSECURE_TLS=1  accept a self-signed hub certificate (fallback only)
# Side Effects: starts car_ctrl (network, UDP 127.0.0.1:47001/47002) and Chromium.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${HUB_HOST:?set HUB_HOST, e.g. hub.example.ts.net}"
CHROMIUM="${CHROMIUM:-$(command -v chromium || command -v chromium-browser || command -v google-chrome || true)}"

CAR_EXTRA=()
if [[ "${INSECURE_TLS:-0}" == "1" ]]; then
  CAR_EXTRA+=(--insecure)
fi

uv run python -m nasura_comm.car --hub "wss://${HUB_HOST}/ws" "${CAR_EXTRA[@]}" &
CAR_PID=$!
trap 'kill ${CAR_PID} 2>/dev/null || true' EXIT

if [[ -z "${CHROMIUM}" ]]; then
  echo "Chromium not found; open https://${HUB_HOST}/car/ manually." >&2
  wait "${CAR_PID}"
  exit
fi

EXTRA=()
if [[ "${FAKE_MEDIA:-0}" == "1" ]]; then
  EXTRA+=(--use-fake-device-for-media-stream)
fi
if [[ "${INSECURE_TLS:-0}" == "1" ]]; then
  EXTRA+=(--ignore-certificate-errors)
fi

# --use-fake-ui-for-media-stream only auto-accepts the permission prompt;
# real devices are used unless FAKE_MEDIA=1.
"${CHROMIUM}" --kiosk --autoplay-policy=no-user-gesture-required \
  --use-fake-ui-for-media-stream "${EXTRA[@]}" \
  --user-data-dir="${HOME}/.cache/nasura-car-chromium" \
  "https://${HUB_HOST}/car/"
