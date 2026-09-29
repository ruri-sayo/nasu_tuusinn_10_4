// Quest controller input (DD-0014, payload DD-0004).
//
// Responsibilities: read XR input sources (xr-standard gamepad + grip pose in
// local-floor) inside the XR frame loop, send in/quest at 30 Hz, and send
// in/estop when both thumbsticks are pressed (at most once per second).
// Non-responsibilities: mapping to commands (done by the hub).
// Side Effects: sends WebSocket messages.

const SEND_INTERVAL_MS = 1000 / 30;
const ESTOP_INTERVAL_MS = 1000;

function emptyHand(side) {
  const hand = { axes: [0, 0], trigger: 0, grip: 0, thumb: false, pose: null };
  if (side === 'left') Object.assign(hand, { x: false, y: false });
  else Object.assign(hand, { a: false, b: false });
  return hand;
}

function readHand(source, frame, space, side) {
  const hand = emptyHand(side);
  const gp = source.gamepad;
  if (gp) {
    const b = (i) => gp.buttons[i];
    hand.trigger = b(0)?.value ?? 0;
    hand.grip = b(1)?.value ?? 0;
    hand.thumb = Boolean(b(3)?.pressed);
    // xr-standard: thumbstick is axes[2], axes[3]
    hand.axes = gp.axes.length >= 4 ? [gp.axes[2], gp.axes[3]] : [gp.axes[0] ?? 0, gp.axes[1] ?? 0];
    if (side === 'left') { hand.x = Boolean(b(4)?.pressed); hand.y = Boolean(b(5)?.pressed); }
    else { hand.a = Boolean(b(4)?.pressed); hand.b = Boolean(b(5)?.pressed); }
  }
  if (source.gripSpace && space) {
    const pose = frame.getPose(source.gripSpace, space);
    if (pose) {
      const { position: p, orientation: q } = pose.transform;
      hand.pose = { p: [p.x, p.y, p.z], q: [q.x, q.y, q.z, q.w] };
    }
  }
  return hand;
}

export function createInput(sig, { onEstop } = {}) {
  let lastSent = 0;
  let lastEstop = -Infinity;

  return function onFrame(frame, space, time) {
    const hands = { left: emptyHand('left'), right: emptyHand('right') };
    for (const source of frame.session.inputSources) {
      if (source.handedness === 'left' || source.handedness === 'right') {
        hands[source.handedness] = readHand(source, frame, space, source.handedness);
      }
    }
    if (hands.left.thumb && hands.right.thumb && time - lastEstop >= ESTOP_INTERVAL_MS) {
      lastEstop = time;
      sig.sendEnv('in/estop', { reason: 'quest both thumbsticks' });
      if (onEstop) onEstop();
    }
    if (time - lastSent >= SEND_INTERVAL_MS) {
      lastSent = time;
      sig.sendEnv('in/quest', hands);
    }
  };
}
