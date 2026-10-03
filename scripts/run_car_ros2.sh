#!/usr/bin/env bash
# Start the car media/control stack and the ROS 2 drive path (DD-0021).
#
# Usage: HUB_HOST=<hub>.<tailnet>.ts.net scripts/run_car_ros2.sh
# Side Effects: starts Chromium, network/UDP clients and ROS 2 motor-control processes.
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

CONTROLLER_PID=""
ADAPTER_PID=""
CAR_PID=""

cleanup() {
  trap - EXIT INT TERM
  for child_pid in "${ADAPTER_PID}" "${CONTROLLER_PID}" "${CAR_PID}"; do
    if [[ -n "${child_pid}" ]]; then
      kill "${child_pid}" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

ros2 run joy_motor_controller joy_motor_controller \
  --ros-args -r joy:=/nasura/drive_joy &
CONTROLLER_PID=$!

PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
  /usr/bin/python3 -m nasura_comm.ros2_drive_node &
ADAPTER_PID=$!

"${REPO_ROOT}/scripts/run_car.sh" &
CAR_PID=$!

wait -n "${CONTROLLER_PID}" "${ADAPTER_PID}" "${CAR_PID}"
