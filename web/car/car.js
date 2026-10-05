// car_media page (DD-0012): sends X4 video + car mic on S1, shows the pilot
// video/audio received on S2 full screen.
//
// Responsibilities: pick the camera by label, open media with S1 limits,
// run S1 (offerer) and S2 (answerer), apply the booth-selected S1 camera and
// send preset (maxBitrate / scaleResolutionDownBy, no renegotiation), show a
// small status HUD ('h' toggles).
// Non-responsibilities: re-encoding or cropping video (browser encoder only).
// Side Effects: captures camera/microphone, opens WebRTC and WebSocket.

import { Signaling } from '../common/signaling.js';
import { createSession } from '../common/rtc.js';
import { startStats, stateColor } from '../common/stats.js';

const $ = (id) => document.getElementById(id);
const showError = (text) => { $('error').textContent = text; };

function setDot(id, state) { $(id).style.background = stateColor(state); }

// Provisional (2026-10-04): booth can switch S1 to a sub camera. Settings come
// from the hub (--sub-*); the label substring can be overridden with ?sub=<label>.
async function openSubCamera(SUB, mainLabel) {
  const devices = await navigator.mediaDevices.enumerateDevices();
  const cams = devices.filter((d) => d.kind === 'videoinput');
  const main = (mainLabel || '').toLowerCase();
  const cam = cams.find((d) => d.label.toLowerCase().includes(SUB.label))
    || cams.find((d) => !main || !d.label.toLowerCase().includes(main));
  if (!cam) throw new Error(`サブカメラ「${SUB.label}」が見つかりません`);
  const s = await navigator.mediaDevices.getUserMedia({
    video: {
      deviceId: { exact: cam.deviceId },
      width: { ideal: SUB.width }, height: { ideal: SUB.height },
      frameRate: { ideal: SUB.fps, max: SUB.fps },
    },
  });
  const track = s.getVideoTracks()[0];
  track.contentHint = 'detail';
  return { track, label: cam.label };
}

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

  const mainTrack = stream?.getVideoTracks()[0] || null;
  const mainInfo = $('camInfo').textContent;
  const SUB = {
    ...cfg.sub,
    label: (new URLSearchParams(location.search).get('sub') || cfg.sub.label).toLowerCase(),
  };
  let camera = 'main';
  let preset = cfg.S1_preset;
  let sub = null;

  // Put the selected camera on the S1 video sender with its own limits.
  async function applyCamera() {
    const sender = s1?.pc?.getSenders().find((x) => x.track?.kind === 'video' || x.track === null);
    if (!sender) return;
    if (camera === 'sub' && !sub) {
      try {
        sub = await openSubCamera(SUB, cfg.S1.device_label);
      } catch (err) {
        showError(String(err.message || err));
        return;
      }
    }
    const track = camera === 'sub' ? sub.track : mainTrack;
    if (track && sender.track !== track) await sender.replaceTrack(track);
    const p = cfg.S1_presets[preset] || cfg.S1_presets.limited;
    const params = sender.getParameters();
    if (!params.encodings || params.encodings.length === 0) params.encodings = [{}];
    if (camera === 'sub') {
      // The sub camera is already small; the preset only caps its bitrate.
      params.encodings[0].maxBitrate = Math.min(SUB.max_bitrate, p.max_bitrate);
      params.encodings[0].maxFramerate = SUB.fps;
      params.encodings[0].scaleResolutionDownBy = 1;
      params.degradationPreference = 'maintain-resolution';
    } else {
      params.encodings[0].maxBitrate = p.max_bitrate;
      params.encodings[0].maxFramerate = cfg.S1.fps;
      params.encodings[0].scaleResolutionDownBy = p.scale;
      params.degradationPreference = 'maintain-framerate';
    }
    try { await sender.setParameters(params); } catch (err) { console.warn('setParameters', err); }
    const mbps = (params.encodings[0].maxBitrate / 1e6).toFixed(1);
    if (camera === 'sub') {
      const st = sub.track.getSettings();
      $('camInfo').textContent = `camera: SUB ${sub.label} ${st.width}×${st.height} @${(st.frameRate || 0).toFixed(0)}fps [${preset} ≤${mbps}Mbps]`;
    } else {
      $('camInfo').textContent = `${mainInfo} [${preset} ÷${p.scale} ≤${mbps}Mbps]`;
    }
  }

  sig.on('env', (msg) => {
    if (msg.env?.topic !== 'sys/camera') return;
    const src = msg.env.payload?.source;
    if (src !== 'main' && src !== 'sub') return;
    camera = src;
    if (cfg.S1_presets[msg.env.payload?.preset]) preset = msg.env.payload.preset;
    applyCamera().catch((e) => showError(String(e)));
  });

  const s1 = createSession({
    session: 'S1', role: 'car_media', stream, media: cfg.S1, sig,
    onState: (s) => {
      setDot('s1Dot', s);
      // rtc.js applies the main limits on connect; re-apply the selection after it.
      if (s === 'connected') setTimeout(() => applyCamera().catch((e) => showError(String(e))), 1000);
    },
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
