// pilot page (provisional): drive NASURA from a laptop without the Quest.
//
// Responsibilities: connect as the "quest" role (the hub and the car side are
// unchanged), receive S1 (360° video + car audio), show it on the screen with
// a mouse / gamepad controlled view, and send gamepad input as in/quest at
// 30 Hz and in/estop on the E-STOP gesture, button or key.
// Non-responsibilities: E-STOP release (booth page), sending media.
// Side Effects: briefly opens the microphone; opens WebRTC and WebSocket.
//
// Safety: input is sent from requestAnimationFrame only while a gamepad is
// connected, so a hidden tab or an unplugged gamepad stops the input stream
// and the hub's input-loss timeout stops the drive.

import { Signaling } from '../common/signaling.js';
import { createSession } from '../common/rtc.js';
import { startStats, stateColor } from '../common/stats.js';
import { createPanoView } from './pano-view.js';
import { findGamepad, readGamepad } from './gamepad.js';

const SEND_INTERVAL_MS = 1000 / 30;
const ESTOP_INTERVAL_MS = 1000;
const STICK_DEAD_ZONE = 0.15;
const YAW_SPEED = 2.0; // rad/s at full stick
const PITCH_SPEED = 1.0; // rad/s while the D-pad is held

const $ = (id) => document.getElementById(id);

async function releaseMicOnce() {
  // Same mDNS workaround as the quest page (AD-0010).
  try {
    const s = await navigator.mediaDevices.getUserMedia({ audio: true });
    s.getTracks().forEach((t) => t.stop());
  } catch (err) {
    $('error').textContent = `マイク許可が必要です（映像接続のため）: ${err.name}`;
  }
}

function setupMouse(canvas, view) {
  let drag = null;
  canvas.addEventListener('pointerdown', (e) => { drag = { x: e.clientX, y: e.clientY }; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener('pointerup', () => { drag = null; });
  canvas.addEventListener('pointermove', (e) => {
    if (!drag) return;
    // Drag the image: moving right looks left, moving down looks up.
    const k = (view.camera.fov * Math.PI / 180) / canvas.clientHeight;
    view.camera.yaw += (e.clientX - drag.x) * k;
    view.camera.pitch += (e.clientY - drag.y) * k;
    drag = { x: e.clientX, y: e.clientY };
  });
  canvas.addEventListener('wheel', (e) => { e.preventDefault(); view.camera.fov += e.deltaY * 0.05; }, { passive: false });
  canvas.addEventListener('dblclick', () => view.reset());
}

async function main() {
  await releaseMicOnce();
  const cfg = await (await fetch('/config.json')).json();
  const sig = new Signaling('quest');
  const video = $('video');
  const audio = $('audio');

  sig.on('open', () => { $('ws').textContent = '接続'; $('ws').className = 'ok'; });
  sig.on('replaced', () => { document.title = 'replaced'; document.body.insertAdjacentHTML('afterbegin', '<div style="position:fixed;top:0;left:0;right:0;z-index:9;background:#a00;color:#fff;font:20px system-ui;padding:8px">別の画面（Quest または別の pilot）に置き換えられました（この画面は無効）</div>'); });
  sig.on('close', () => { $('ws').textContent = '切断'; $('ws').className = 'bad'; });
  sig.on('env', (msg) => {
    if (msg.env?.topic === 'sys/pilot' && msg.env.payload?.mode) {
      $('error').textContent = msg.env.payload.mode === 'booth' ? 'ブースで操縦中：この画面の操作は無効です（映像は見られます）' : '';
    }
    if (msg.env?.topic === 'sys/camera') {
      // Sub camera is a normal (flat) camera: show the video as is.
      const flat = msg.env.payload?.source === 'sub';
      document.body.classList.toggle('flat', flat);
      $('camera').textContent = flat ? 'サブ' : 'メイン 360°';
    }
    if (msg.env?.topic === 'sys/state') {
      const st = msg.env.payload.state;
      $('car').textContent = st;
      $('car').className = st === 'RUN' ? 'ok' : 'bad';
    }
  });

  const layout = (new URLSearchParams(location.search).get('layout') || 'equirect').toLowerCase();
  const view = createPanoView({ canvas: $('view'), video, layout, yawOffsetDeg: cfg.view?.yaw_offset_deg ?? 0 });
  setupMouse($('view'), view);

  let lastEstop = -Infinity;
  const estop = (reason) => {
    const now = performance.now();
    if (now - lastEstop < ESTOP_INTERVAL_MS) return;
    lastEstop = now;
    sig.sendEnv('in/estop', { reason });
    $('estop').classList.add('flash');
    setTimeout(() => $('estop').classList.remove('flash'), 300);
  };
  $('estop').addEventListener('click', () => estop('pilot button'));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' || e.key === ' ') { e.preventDefault(); estop('pilot key'); }
    else if (e.key === 'r' || e.key === 'R') view.reset();
    else if (e.key === 'f' || e.key === 'F') {
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
      else document.documentElement.requestFullscreen().catch(() => {});
    }
  });

  // The click is the user gesture that unlocks audio playback.
  $('start').addEventListener('click', () => {
    video.play().catch(() => {});
    audio.play().catch(() => {});
    $('start').remove();
  });

  let lastSent = 0;
  let lastFrame = performance.now();
  function frame(time) {
    requestAnimationFrame(frame);
    const dt = Math.min((time - lastFrame) / 1000, 0.1);
    lastFrame = time;
    const gp = findGamepad();
    if (gp) {
      const inp = readGamepad(gp);
      $('pad').textContent = gp.id.slice(0, 40);
      $('pad').className = document.hasFocus() ? 'ok' : 'bad';
      if (inp.estop) estop('pilot both sticks');
      if (time - lastSent >= SEND_INTERVAL_MS) {
        lastSent = time;
        sig.sendEnv('in/quest', inp.hands);
      }
      if (Math.abs(inp.view.yaw) > STICK_DEAD_ZONE) view.camera.yaw -= inp.view.yaw * YAW_SPEED * dt;
      view.camera.pitch += inp.view.pitch * PITCH_SPEED * dt;
      if (inp.view.reset) view.reset();
    } else {
      $('pad').textContent = '未接続（ボタンを押すと認識）';
      $('pad').className = 'bad';
    }
    $('focus').hidden = document.hasFocus();
    view.render();
  }
  requestAnimationFrame(frame);

  // Relay mode: the 360° video comes from the booth on S4 (same stream as S1).
  const session = cfg.S1_route === 'relay' ? 'S4' : 'S1';
  const s1 = createSession({
    session, role: 'quest', media: cfg.S1, sig,
    onTrack: (stream) => {
      if (video.srcObject !== stream) video.srcObject = stream;
      if (audio.srcObject !== stream) audio.srcObject = stream;
      video.play().catch(() => {});
      audio.play().catch(() => {});
    },
    onState: (s) => {
      $('s1').textContent = s;
      $('s1').style.color = stateColor(s);
    },
  });
  startStats({ sig, session, role: 'quest', getPc: () => s1.pc });
}

main().catch((err) => { $('error').textContent = String(err); });
