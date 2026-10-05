// Gamepad input for the pilot page (provisional, payload DD-0004).
//
// Responsibilities: read a standard-mapping gamepad (Xbox layout) through the
// Gamepad API and build an in/quest payload with the same fields as
// quest/input.js, so the hub mapping is unchanged; detect the E-STOP gesture
// (both sticks pressed); return the view-control inputs.
// Non-responsibilities: sending (pilot.js), mapping to commands (hub).
//
// Standard mapping: buttons 0 A, 1 B, 2 X, 3 Y, 4 LB, 5 RB, 6 LT, 7 RT,
// 8 Back/View, 9 Start/Menu, 10 L3, 11 R3, 12-15 D-pad up/down/left/right;
// axes 0/1 left stick, 2/3 right stick (up is y < 0).

const value = (gp, i) => gp.buttons[i]?.value ?? 0;
const pressed = (gp, i) => Boolean(gp.buttons[i]?.pressed);
const axis = (gp, i) => {
  const v = gp.axes[i] ?? 0;
  return Number.isFinite(v) ? v : 0;
};

export function findGamepad() {
  const pads = [...(navigator.getGamepads?.() ?? [])].filter((p) => p && p.connected);
  return pads.find((p) => p.mapping === 'standard') ?? pads[0] ?? null;
}

// Returns { hands, estop, view } for one gamepad snapshot.
// The right stick is the view (X yaw, Y pitch, 2026-10-05); the stage
// front/back moves to the D-pad up/down and is sent as the right stick Y with
// X = 0, so the hub mapping is unchanged.
export function readGamepad(gp) {
  const hands = {
    left: {
      axes: [axis(gp, 0), axis(gp, 1)],
      trigger: value(gp, 6), grip: value(gp, 4), thumb: pressed(gp, 10),
      x: pressed(gp, 2), y: pressed(gp, 3), pose: null,
    },
    right: {
      axes: [0, (pressed(gp, 13) ? 1 : 0) - (pressed(gp, 12) ? 1 : 0)],
      trigger: value(gp, 7), grip: value(gp, 5), thumb: pressed(gp, 11),
      a: pressed(gp, 0), b: pressed(gp, 1), pose: null,
    },
  };
  return {
    hands,
    estop: pressed(gp, 10) && pressed(gp, 11),
    view: {
      yaw: axis(gp, 2),
      pitch: -axis(gp, 3), // stick up (y < 0) looks up
      reset: pressed(gp, 8),
    },
  };
}
