#!/usr/bin/env bash
# Start the car media/control stack and the ROS 2 drive path (DD-0021).
#
# Usage: HUB_HOST=<hub>.<tailnet>.ts.net scripts/run_car_ros2.sh
#   PICO_DEV  serial device of the motor Pico (default: /dev/nasura_pico from
#             scripts/udev/99-nasura-pico.rules, else the only
#             /dev/serial/by-id/*Raspberry_Pi_Pico*). Never guesses /dev/ttyACM*,
#             which can be an SO-101 arm board.
#   NO_AGENT=1  do not start the micro-ROS agent (it is already running).
# Side Effects: starts Chromium, network/UDP clients, the micro-ROS agent (serial
# to the Pico) and ROS 2 motor-control processes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROS_DISTRO_SETUP="${ROS_DISTRO_SETUP:-/opt/ros/humble/setup.bash}"
ROS_WORKSPACE_SETUP="${ROS_WORKSPACE_SETUP:-/home/nasc/roarm_ws_em0/install/setup.bash}"
: "${HUB_HOST:?set HUB_HOST, e.g. hub.example.ts.net}"

for setup_file in "${ROS_DISTRO_SETUP}" "${ROS_WORKSPACE_SETUP}"; do
  if [[ ! -r "${setup_file}" ]]; then
    echo "ROS setup file not found: ${setup_file}" >&2
    exit 1
  fi
done

# shellcheck disable=SC1090
set +u
source "${ROS_DISTRO_SETUP}"
# shellcheck disable=SC1090
source "${ROS_WORKSPACE_SETUP}"
set -u

if ! ros2 pkg executables joy_motor_controller | grep -qx 'joy_motor_controller joy_motor_controller'; then
  echo "joy_motor_controller executable not found" >&2
  exit 1
fi

if [[ "${NO_AGENT:-0}" != "1" ]]; then
  if [[ -z "${PICO_DEV:-}" ]]; then
    if [[ -e /dev/nasura_pico ]]; then
      PICO_DEV=/dev/nasura_pico
    else
      shopt -s nullglob
      picos=(/dev/serial/by-id/*Raspberry_Pi_Pico*)
      shopt -u nullglob
      if (( ${#picos[@]} != 1 )); then
        echo "motor Pico not found uniquely (${#picos[@]} candidates); connect it or set PICO_DEV" >&2
        exit 1
      fi
      PICO_DEV="${picos[0]}"
    fi
  fi
  if [[ ! -e "${PICO_DEV}" ]]; then
    echo "PICO_DEV ${PICO_DEV} does not exist" >&2
    exit 1
  fi
  echo "micro-ROS agent on ${PICO_DEV} -> $(readlink -f "${PICO_DEV}")"
fi

AGENT_PID=""
CONTROLLER_PID=""
ADAPTER_PID=""
CAR_PID=""

cleanup() {
  trap - EXIT INT TERM
  for child_pid in "${ADAPTER_PID}" "${CONTROLLER_PID}" "${AGENT_PID}" "${CAR_PID}"; do
    if [[ -n "${child_pid}" ]]; then
      kill "${child_pid}" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# The Pico firmware tries to reach the agent only for a few seconds after it
# boots and never retries, so a Pico that booted before the agent stays
# unconnected (e.g. after a PC reboot). Replugging (or resetting) the Pico
# fixes it; when the device node is recreated, restart the agent at once so
# the fresh Pico finds it, and its old file descriptor is not left dangling.
agent_loop() {
  local inode now apid=""
  trap '[[ -n "${apid}" ]] && { pkill -TERM -P "${apid}"; kill "${apid}"; } 2>/dev/null; exit 0' TERM
  while true; do
    while [[ ! -e "${PICO_DEV}" ]]; do sleep 0.1; done
    inode="$(stat -Lc %i "${PICO_DEV}" 2>/dev/null || echo none)"
    ros2 run micro_ros_agent micro_ros_agent serial --dev "${PICO_DEV}" &
    apid=$!
    while kill -0 "${apid}" 2>/dev/null; do
      sleep 0.2
      now="$(stat -Lc %i "${PICO_DEV}" 2>/dev/null || echo gone)"
      if [[ "${now}" != "${inode}" ]]; then
        echo "motor Pico re-enumerated; restarting the micro-ROS agent" >&2
        break
      fi
    done
    pkill -TERM -P "${apid}" 2>/dev/null || true
    kill "${apid}" 2>/dev/null || true
    wait "${apid}" 2>/dev/null || true
  done
}

pids=()
if [[ "${NO_AGENT:-0}" != "1" ]]; then
  agent_loop &
  AGENT_PID=$!
  pids+=("${AGENT_PID}")
fi

ros2 run joy_motor_controller joy_motor_controller \
  --ros-args -r joy:=/nasura/drive_joy &
CONTROLLER_PID=$!

PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
  /usr/bin/python3 -m nasura_comm.ros2_drive_node &
ADAPTER_PID=$!

"${REPO_ROOT}/scripts/run_car.sh" &
CAR_PID=$!

wait -n "${pids[@]}" "${CONTROLLER_PID}" "${ADAPTER_PID}" "${CAR_PID}"
