// booth page (DD-0013): pilot camera/mic on S2, E-STOP UI and monitoring.
//
// Responsibilities: S2 offerer; E-STOP button and Escape key -> in/estop;
// release by two presses within 2 s -> in/estop_release; poll /status at
// 1 Hz and render it; show telemetry pushed by the hub; select the S1 camera
// and send preset (in/camera).
// Non-responsibilities: browser dialogs (alert/confirm/prompt are not used).
// Side Effects: captures camera/microphone, opens WebRTC and WebSocket,
// polls /status.

import { Signaling } from '../common/signaling.js';
import { createSession } from '../common/rtc.js';
import { startStats } from '../common/stats.js';

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
  media.push(['S1 fps（送信／受信）', `${s1.car_media?.fps ?? '-'} / ${s1.quest?.fps ?? '-'}`]);
  media.push(['S1 解像度', s1.car_media?.width ? `${s1.car_media.width}×${s1.car_media.height}` : '-']);
  media.push(['S1 受信（quest）', s1.quest?.recv_kbps === undefined ? '-' : `${s1.quest.recv_kbps} kbps, drop ${s1.quest.frames_dropped ?? '-'}`]);
  media.push(['S1 候補', s1.quest ? `${s1.quest.local_type ?? '-'} ↔ ${s1.quest.remote_type ?? '-'}, RTT ${s1.quest.rtt_ms ?? '-'} ms` : '-']);
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

  $('estop').addEventListener('click', estop);
  $('release').addEventListener('click', release);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') estop(); });

  setInterval(poll, 1000);
  poll();

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

main().catch((err) => { $('error').textContent = String(err); });
