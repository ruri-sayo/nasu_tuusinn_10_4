"""ROS 2 and UDP runtime for the car-side drive adapter (DD-0017 to DD-0022).

Responsibilities:
    - Bind the local ``out/effective`` UDP interface.
    - Publish safety-judged ``sensor_msgs/msg/Joy`` messages at 20 Hz.
    - Detect competing publishers on the dedicated drive-input topic.

Non-responsibilities:
    - Command decisions, PWM calculation and motor actuation.

Side Effects:
    Binds UDP ``127.0.0.1:47001`` and communicates on the ROS 2 graph.
"""

from __future__ import annotations

import signal
import socket
import time
from types import FrameType
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Joy

from nasura_comm.ros2_drive import DriveInputState

UDP_ADDR = ("127.0.0.1", 47001)
JOY_TOPIC = "/nasura/drive_joy"
PUBLISH_PERIOD_S = 0.05
CONFLICT_CHECK_PERIOD_S = 1.0


def monotonic_ms() -> int:
    """Return monotonic time in milliseconds."""
    return time.monotonic_ns() // 1_000_000


class Ros2DriveAdapter(Node):  # type: ignore[misc]
    """Bridge local effective commands to one isolated ROS 2 Joy topic.

    Lifecycle:
        The constructor binds UDP and creates ROS entities. ``close`` publishes
        neutral input and releases the socket. A conflict remains latched until
        the process restarts.
    """

    def __init__(self) -> None:
        """Bind UDP and start the 20 Hz safety-output timers."""
        super().__init__("ros2_drive_adapter")
        self._state = DriveInputState(timeout_ms=200)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)
        self._socket.bind(UDP_ADDR)
        self._publisher = self.create_publisher(Joy, JOY_TOPIC, 10)
        self._timer = self.create_timer(PUBLISH_PERIOD_S, self._tick)
        self._conflict_timer = self.create_timer(
            CONFLICT_CHECK_PERIOD_S, self._check_publishers
        )
        self._closed = False
        self.get_logger().info(
            f"listening on {UDP_ADDR[0]}:{UDP_ADDR[1]}; publishing {JOY_TOPIC}"
        )

    def _drain_udp(self, now_ms: int) -> None:
        while True:
            try:
                data, _ = self._socket.recvfrom(16 * 1024 + 1)
            except BlockingIOError:
                return
            self._state.accept(data, now_ms)

    def _publish(self, axis_x: float, axis_y: float) -> None:
        message = Joy()
        message.header.stamp = self.get_clock().now().to_msg()
        message.axes = [axis_x, axis_y]
        message.buttons = []
        self._publisher.publish(message)

    def _tick(self) -> None:
        now_ms = monotonic_ms()
        self._drain_udp(now_ms)
        self._publish(*self._state.axes(now_ms))
        transition = self._state.transition(now_ms)
        if transition is not None:
            log = self.get_logger().error if transition == "conflict" else self.get_logger().info
            log(f"drive input state: {transition}")

    def _check_publishers(self) -> None:
        endpoints: list[Any] = self.get_publishers_info_by_topic(JOY_TOPIC)
        others = [endpoint for endpoint in endpoints if endpoint.node_name != self.get_name()]
        if others and not self._state.conflict:
            names = ", ".join(f"{item.node_namespace}/{item.node_name}" for item in others)
            self._state.latch_conflict()
            self.get_logger().error(f"competing drive publisher detected: {names}")

    def close(self) -> None:
        """Publish neutral input and close the UDP socket."""
        if self._closed:
            return
        self._closed = True
        self._timer.cancel()
        self._conflict_timer.cancel()
        self._publish(0.0, 0.0)
        self._socket.close()
        if self._state.dropped:
            self.get_logger().info(f"dropped datagrams: {dict(self._state.dropped)}")


def main(args: list[str] | None = None) -> None:
    """Run the ROS 2 drive adapter until shutdown."""
    stop_requested = False

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        nonlocal stop_requested
        stop_requested = True

    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node: Ros2DriveAdapter | None = None
    previous_sigint = signal.signal(signal.SIGINT, request_stop)
    previous_sigterm = signal.signal(signal.SIGTERM, request_stop)
    try:
        node = Ros2DriveAdapter()
        while rclpy.ok() and not stop_requested:
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        if node is not None:
            node.close()
            rclpy.spin_once(node, timeout_sec=0.05)
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    main()
