// car_media page (DD-0012): sends X4 video + car mic on S1, shows the pilot
// video/audio received on S2 full screen.
//
// Responsibilities: pick the camera by label, open media with S1 limits,
// run S1 (offerer) and S2 (answerer), show a small status HUD ('h' toggles).
// Non-responsibilities: re-encoding or cropping video (browser encoder only).
// Side Effects: captures camera/microphone, opens WebRTC and WebSocket.

import { Signaling } from '../common/signaling.js';
import { createSession } from '../common/rtc.js';
import { startStats, stateColor } from '../common/stats.js';

const $ = (id) => document.getElementById(id);
const showError = (text) => { $('error').textContent = text; };

function setDot(id, state) { $(id).style.background = stateColor(state); }

async function openCamera(s1) {
  // Ask once so that device labels become visible, then release.
  const probe = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
  probe.getTracks().forEach((t) => t.stop());
  const devices = await navigator.mediaDevices.enumerateDevices();
  const label = (s1.device_label || '').toLowerCase();
  const cam = devices.find((d) => d.kind === 'videoinput' && label && d.label.toLowerCase().includes(label));
  if (!cam) showError(`カメラ「${s1.device_label}」が見つかりません。既定カメラで続行します。`);
  const stream = await navigator.mediaDevices.getUserMedia({
    video: {
      ...(cam ? { deviceId: { exact: cam.deviceId } } : {}),
      width: { ideal: s1.width },
      height: { ideal: s1.height },
      frameRate: { ideal: s1.fps, max: s1.fps },
    },
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const st = stream.getVideoTracks()[0]?.getSettings() || {};
  $('camInfo').textContent = `camera: ${cam ? cam.label : 'default'} ${st.width || '?'}×${st.height || '?'} @${st.frameRate ? st.frameRate.toFixed(0) : '?'}fps`;
  if (st.width && st.height && (st.width !== s1.width || st.height !== s1.height)) {
    $('camInfo').style.color = '#fc3';
  }
  return stream;
}

async function main() {
  const cfg = await (await fetch('/config.json')).json();
  let stream = null;
  try {
    stream = await openCamera(cfg.S1);
  } catch (err) {
    showError(`カメラ・マイクを開けません: ${err.name} ${err.message}`);
  }

  const sig = new Signaling('car_media');
  sig.on('open', () => setDot('wsDot', 'connected'));
  sig.on('replaced', () => { document.title = 'replaced'; document.body.insertAdjacentHTML('afterbegin', '<div style="position:fixed;top:0;left:0;right:0;z-index:9;background:#a00;color:#fff;font:20px system-ui;padding:8px">別の画面に置き換えられました（この画面は無効）</div>'); });
  sig.on('close', () => setDot('wsDot', 'down'));

  const s1 = createSession({
    session: 'S1', role: 'car_media', stream, media: cfg.S1, sig,
    onState: (s) => setDot('s1Dot', s),
  });
  const video = $('pilot');
  const s2 = createSession({
    session: 'S2', role: 'car_media', media: cfg.S2, sig,
    onTrack: (s) => {
      if (video.srcObject !== s) video.srcObject = s;
      video.play().catch((e) => showError(`再生できません: ${e.message}`));
    },
    onState: (s) => setDot('s2Dot', s),
  });
  startStats({ sig, session: 'S1', role: 'car_media', getPc: () => s1.pc,
    onSummary: (d) => { $('s1Text').textContent = ` ${d.send_kbps ?? '-'} kbps ${d.fps ?? '-'} fps`; } });
  startStats({ sig, session: 'S2', role: 'car_media', getPc: () => s2.pc,
    onSummary: (d) => { $('s2Text').textContent = ` ${d.recv_kbps ?? '-'} kbps ${d.fps ?? '-'} fps`; } });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'h') $('hud').classList.toggle('hidden');
  });
}

main().catch((err) => showError(String(err)));
