// booth page (DD-0013): pilot camera/mic on S2, E-STOP UI and monitoring.
//
// Responsibilities: S2 offerer; E-STOP button and Escape key -> in/estop;
// release by two presses within 2 s -> in/estop_release; poll /status at
// 1 Hz and render it; show telemetry pushed by the hub; select the S1 camera
// and send preset (in/camera). With S1_route "relay": S1 answerer (show the
// robot video here) and S4 offerer (re-send the same stream to the quest).
// Pilot mode "booth" (switched with the admin password, in/pilot): this page
// shows the 360° video with a pan/zoom view and sends gamepad input as
// in/quest at 30 Hz, like the pilot page; the hub then ignores the quest.
// Non-responsibilities: SFU-style forwarding without re-encoding (the browser
// re-encodes S4).
// Non-responsibilities: browser dialogs (alert/confirm/prompt are not used).
// Side Effects: captures camera/microphone, opens WebRTC and WebSocket,
// polls /status.

import { Signaling } from '../common/signaling.js';
import { createSession } from '../common/rtc.js';
import { startStats } from '../common/stats.js';
import { createPanoView } from '../pilot/pano-view.js';
import { findGamepad, readGamepad } from '../pilot/gamepad.js';

const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? '-').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const cls = (ok, bad = !ok) => (bad ? 'bad' : ok ? 'ok' : '');

function rows(table, list) {
  $(table).innerHTML = list.map(([k, v, c = '']) => `<tr><th>${esc(k)}</th><td class="${c}">${esc(v)}</td></tr>`).join('');
}

const telemetry = {};
let sig;
let cfg;

function estop() {
  const sent = sig.sendEnv('in/estop', { reason: 'booth button' });
  $('releaseHint').textContent = sent ? 'E-STOP を送信しました' : 'WS 切断中：E-STOP を送信できません（車載は通信途絶で停止します）';
}

let releaseArmedAt = 0;
function release() {
  const now = performance.now();
  if (now - releaseArmedAt <= 2000) {
    releaseArmedAt = 0;
    $('release').classList.remove('armed');
    sig.sendEnv('in/estop_release', {});
    $('releaseHint').textContent = '解除を送信しました';
  } else {
    releaseArmedAt = now;
    $('release').classList.add('armed');
    $('releaseHint').textContent = 'もう一度押すと解除します（2秒以内）';
    setTimeout(() => {
      if (releaseArmedAt && performance.now() - releaseArmedAt > 2000) {
        releaseArmedAt = 0;
        $('release').classList.remove('armed');
        $('releaseHint').textContent = '';
      }
    }, 2100);
  }
}

function render(st) {
  const car = st.control.car_state;
  $('carState').textContent = car ?? '不明';
  $('carState').className = car === 'RUN' ? 'ok' : 'bad';
  $('latched').innerHTML = st.control.latched ? '<span class="bad">（hub で E-STOP ラッチ中）</span>' : '';
  rows('conn', [
    ...Object.entries(st.roles).map(([r, v]) => [r, v ? '接続' : '未接続', cls(v)]),
    ...Object.entries(st.sessions).map(([s, v]) => [s, v ?? '-', v === 'connected' ? 'ok' : 'bad']),
  ]);
  const c = st.control;
  rows('ctrl', [
    ['RTT（最新）', c.rtt_ms === null ? '-' : `${c.rtt_ms} ms`, c.rtt_ms > 200 ? 'warn' : ''],
    ['RTT（EWMA）', c.rtt_ewma_ms === null ? '-' : `${c.rtt_ewma_ms} ms`],
    ['Quest 入力の経過', c.last_input_age_ms === null ? '-' : `${c.last_input_age_ms} ms`, c.last_input_age_ms > 300 ? 'warn' : ''],
  ]);
  const media = [];
  const s1 = st.stats.S1 || {};
  const s2 = st.stats.S2 || {};
  const s1Up = s1.car_media?.send_kbps;
  const budget = st.up_budget_bps / 1000;
  media.push(['S1 上り（car_media 送信）', s1Up === undefined ? '-' : `${s1Up} kbps / 予算 ${budget} kbps`, s1Up > budget ? 'bad' : '']);
  // S1 ends at the booth in relay mode, at the quest in direct mode.
  const relay = cfg.S1_route === 'relay';
  const s1r = relay ? s1.booth : s1.quest;
  media.push(['S1 fps（送信／受信）', `${s1.car_media?.fps ?? '-'} / ${s1r?.fps ?? '-'}`]);
  media.push(['S1 解像度', s1.car_media?.width ? `${s1.car_media.width}×${s1.car_media.height}` : '-']);
  media.push([`S1 受信（${relay ? 'booth' : 'quest'}）`, s1r?.recv_kbps === undefined ? '-' : `${s1r.recv_kbps} kbps, drop ${s1r.frames_dropped ?? '-'}, loss ${s1r.loss_pct ?? '-'} %`]);
  const enc = s1.car_media?.encoder;
  media.push(['S1 エンコーダ（車載）', enc ? `${enc}${s1.car_media.hw_encoder === false ? '（ソフト）' : s1.car_media.hw_encoder ? '（ハード）' : ''} 制約: ${s1.car_media.quality_limit ?? '-'}` : '-', s1.car_media?.quality_limit === 'cpu' ? 'warn' : '']);
  media.push(['S1 ロス（受信側の報告）', s1.car_media?.remote_loss_pct === undefined ? '-' : `${s1.car_media.remote_loss_pct} %`, s1.car_media?.remote_loss_pct > 2 ? 'warn' : '']);
  media.push(['S1 候補', s1r ? `${s1r.local_type ?? '-'} ↔ ${s1r.remote_type ?? '-'}, RTT ${s1r.rtt_ms ?? '-'} ms` : '-']);
  if (relay) {
    const s4 = st.stats.S4 || {};
    media.push(['S4 送信（booth → quest）', s4.booth?.send_kbps === undefined ? '-' : `${s4.booth.send_kbps} kbps ${s4.booth.fps ?? '-'} fps ${s4.booth.width ? `${s4.booth.width}×${s4.booth.height}` : ''} ${s4.booth.encoder ?? ''}`]);
    media.push(['S4 受信（quest）', s4.quest?.recv_kbps === undefined ? '-' : `${s4.quest.recv_kbps} kbps ${s4.quest.fps ?? '-'} fps, drop ${s4.quest.frames_dropped ?? '-'}, loss ${s4.quest.loss_pct ?? '-'} %, RTT ${s4.quest.rtt_ms ?? '-'} ms`]);
  }
  media.push(['S2 送信（booth）', s2.booth?.send_kbps === undefined ? '-' : `${s2.booth.send_kbps} kbps ${s2.booth.fps ?? '-'} fps`, s2.booth?.send_kbps > cfg.S2.max_bitrate / 1000 ? 'bad' : '']);
  media.push(['S2 受信（car_media）', s2.car_media?.recv_kbps === undefined ? '-' : `${s2.car_media.recv_kbps} kbps ${s2.car_media.fps ?? '-'} fps`]);
  rows('media', media);
  Object.assign(telemetry, st.telemetry || {});
  rows('tlm', Object.entries(telemetry).map(([k, v]) => [k, JSON.stringify(v)]));
  rows('dropped', Object.entries(st.dropped).map(([k, v]) => [k, v, 'warn']));
}

async function poll() {
  try {
    const res = await fetch('/status', { cache: 'no-store' });
    render(await res.json());
  } catch (err) {
    $('carState').textContent = 'hub 応答なし';
    $('carState').className = 'bad';
  }
}

async function main() {
  cfg = await (await fetch('/config.json')).json();
  sig = new Signaling('booth');
  sig.on('open', () => { $('ws').textContent = 'WS: 接続'; $('ws').className = 'ok'; });
  sig.on('close', (m) => {
    $('ws').textContent = m.replaced ? 'WS: 別の booth 画面に置き換えられました（この画面は無効）' : 'WS: 切断（再接続中）';
    $('ws').className = 'bad';
  });
  sig.on('env', (msg) => {
    const env = msg.env;
    if (env?.topic === 'sys/pilot') onPilot(env.payload || {});
    if (env?.topic === 'sys/camera') {
      const src = env.payload?.source;
      $('camNow').textContent = src === 'sub' ? 'サブ' : 'メイン（360°）';
      $('camMain').disabled = src === 'main';
      $('camSub').disabled = src === 'sub';
      const preset = env.payload?.preset;
      const p = cfg.S1_presets[preset];
      $('presetNow').textContent = p
        ? `${preset === 'full' ? 'フルスペック' : '制限'}（上限 ${(p.max_bitrate / 1e6).toFixed(1)} Mbps、解像度 ÷${p.scale}）`
        : '-';
      $('presetLimited').disabled = preset === 'limited';
      $('presetFull').disabled = preset === 'full';
    }
    if (env && env.topic && !env.topic.startsWith('sys/')) telemetry[env.topic] = env.payload;
  });
  // Provisional (2026-10-04): switch the S1 camera on the car.
  $('camMain').addEventListener('click', () => sig.sendEnv('in/camera', { source: 'main' }));
  $('camSub').addEventListener('click', () => sig.sendEnv('in/camera', { source: 'sub' }));
  $('presetLimited').addEventListener('click', () => sig.sendEnv('in/camera', { preset: 'limited' }));
  $('presetFull').addEventListener('click', () => sig.sendEnv('in/camera', { preset: 'full' }));
  const askPilot = (mode) => {
    sig.sendEnv('in/pilot', { mode, password: $('pilotPass').value });
    $('pilotPass').value = '';
  };
  $('pilotQuest').addEventListener('click', () => askPilot('quest'));
  $('pilotBooth').addEventListener('click', () => askPilot('booth'));

  $('estop').addEventListener('click', estop);
  $('release').addEventListener('click', release);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') estop(); });

  setInterval(poll, 1000);
  poll();

  // Before any await: the S1 offer can arrive as soon as the WebSocket opens,
  // and an answerer that registers late would drop it.
  if (cfg.S1_route === 'relay') startRelay();
  else { $('robotBox').hidden = true; $('pilotSel').hidden = true; } // booth mode needs the relay (S1 here)

  let stream = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: cfg.S2.width }, height: { ideal: cfg.S2.height }, frameRate: { ideal: cfg.S2.fps, max: cfg.S2.fps } },
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    $('preview').srcObject = stream;
  } catch (err) {
    $('error').textContent = `カメラ・マイクを開けません: ${err.name} ${err.message}`;
  }
  const s2 = createSession({ session: 'S2', role: 'booth', stream, media: cfg.S2, sig });
  startStats({ sig, session: 'S2', role: 'booth', getPc: () => s2.pc });
}

// S1 (car) -> this page -> S4 (quest). The car uplink carries one copy only.
function startRelay() {
  const robot = $('robot');
  const s4 = createSession({ session: 'S4', role: 'booth', sendKinds: ['audio', 'video'], media: cfg.S4, sig,
    onState: (s) => { $('s4State').textContent = s; } });
  const s1 = createSession({
    session: 'S1', role: 'booth', media: cfg.S1, sig,
    onTrack: (s) => {
      if (robot.srcObject !== s) robot.srcObject = s;
      robot.play().catch(() => {});
      s4.setStream(s);
    },
    onState: (s) => { $('s1State').textContent = s; },
  });
  startStats({ sig, session: 'S1', role: 'booth', getPc: () => s1.pc });
  startStats({ sig, session: 'S4', role: 'booth', getPc: () => s4.pc });
  startBoothPilot();
  $('robotAudio').addEventListener('click', () => {
    robot.muted = !robot.muted;
    $('robotAudio').textContent = robot.muted ? '車載音声: 消音中（押すとブースで再生）' : '車載音声: 再生中（押すと消音）';
  });
}

// ---- pilot mode ----------------------------------------------------------

const SEND_INTERVAL_MS = 1000 / 30;
const ESTOP_INTERVAL_MS = 1000;
const STICK_DEAD_ZONE = 0.15;
const YAW_SPEED = 2.0; // rad/s at full stick
const PITCH_SPEED = 1.0; // rad/s while the D-pad is held
let pilotMode = 'quest';

function onPilot(p) {
  if (p.error === 'password') $('pilotHint').textContent = 'パスワードが違います';
  else if (p.error === 'retry') $('pilotHint').textContent = '少し待ってから入力してください';
  else $('pilotHint').textContent = '';
  if (!p.mode) return;
  pilotMode = p.mode;
  const booth = pilotMode === 'booth';
  $('pilotNow').textContent = booth ? 'ブース（Quest の入力は無効）' : 'Quest';
  $('pilotQuest').disabled = !booth;
  $('pilotBooth').disabled = booth;
  $('robot').hidden = booth;
  $('pano').hidden = !booth;
  $('padBox').hidden = !booth;
}

// Pan/zoom 360° view of the robot video and gamepad driving (booth mode).
// Input is sent from requestAnimationFrame only while booth mode is on and a
// gamepad is connected: a hidden window or an unplugged gamepad stops the
// input and the hub's input-loss timeout stops the drive.
function startBoothPilot() {
  const canvas = $('pano');
  const layout = (new URLSearchParams(location.search).get('layout') || 'equirect').toLowerCase();
  const view = createPanoView({ canvas, video: $('robot'), layout, yawOffsetDeg: cfg.view?.yaw_offset_deg ?? 0 });
  let drag = null;
  canvas.addEventListener('pointerdown', (e) => { drag = { x: e.clientX, y: e.clientY }; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener('pointerup', () => { drag = null; });
  canvas.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const k = (view.camera.fov * Math.PI / 180) / canvas.clientHeight;
    view.camera.yaw += (e.clientX - drag.x) * k;
    view.camera.pitch += (e.clientY - drag.y) * k;
    drag = { x: e.clientX, y: e.clientY };
  });
  canvas.addEventListener('wheel', (e) => { e.preventDefault(); view.camera.fov += e.deltaY * 0.05; }, { passive: false });
  canvas.addEventListener('dblclick', () => view.reset());

  let lastSent = 0;
  let lastEstop = -Infinity;
  let lastFrame = performance.now();
  function frame(time) {
    requestAnimationFrame(frame);
    const dt = Math.min((time - lastFrame) / 1000, 0.1);
    lastFrame = time;
    if (pilotMode !== 'booth') return;
    const gp = findGamepad();
    if (gp) {
      const inp = readGamepad(gp);
      $('pad').textContent = gp.id.slice(0, 40);
      $('pad').className = document.hasFocus() ? 'ok' : 'bad';
      if (inp.estop && time - lastEstop >= ESTOP_INTERVAL_MS) {
        lastEstop = time;
        sig.sendEnv('in/estop', { reason: 'booth pilot both sticks' });
      }
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
    $('focusHint').textContent = document.hasFocus() ? '' : '（このウィンドウを選択してください）';
    view.render();
  }
  requestAnimationFrame(frame);
}

main().catch((err) => { $('error').textContent = String(err); });
