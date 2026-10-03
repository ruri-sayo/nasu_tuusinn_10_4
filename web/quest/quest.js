// quest page (DD-0014): receive S1 (360° video + car audio), render it in
// WebXR and send controller input.
//
// Responsibilities: grab and release the microphone once (AD-0010 mDNS
// workaround), S1 answerer, audio playback, XR view, input sending.
// Non-responsibilities: sending media (the Quest sends no audio/video).
// Side Effects: briefly opens the microphone; opens WebRTC and WebSocket.

import { Signaling } from '../common/signaling.js';
import { createSession } from '../common/rtc.js';
import { startStats, stateColor } from '../common/stats.js';
import { createXRView } from './xr-view.js';
import { createInput } from './input.js';

const $ = (id) => document.getElementById(id);

async function releaseMicOnce() {
  // Without a media permission Chromium hides host candidates behind mDNS
  // names, and car_media could not reach the Quest over the subnet route.
  try {
    const s = await navigator.mediaDevices.getUserMedia({ audio: true });
    s.getTracks().forEach((t) => t.stop());
  } catch (err) {
    $('error').textContent = `マイク許可が必要です（映像接続のため）: ${err.name}`;
  }
}

async function main() {
  await releaseMicOnce();
  const cfg = await (await fetch('/config.json')).json();
  const sig = new Signaling('quest');
  const video = $('video');
  const audio = $('audio');

  sig.on('open', () => { $('ws').textContent = '接続'; $('ws').className = 'ok'; });
  sig.on('replaced', () => { document.title = 'replaced'; document.body.insertAdjacentHTML('afterbegin', '<div style="position:fixed;top:0;left:0;right:0;z-index:9;background:#a00;color:#fff;font:20px system-ui;padding:8px">別の画面に置き換えられました（この画面は無効）</div>'); });
  sig.on('close', () => { $('ws').textContent = '切断'; $('ws').className = 'bad'; });
  sig.on('env', (msg) => {
    if (msg.env?.topic === 'sys/state') {
      const st = msg.env.payload.state;
      $('car').textContent = st;
      $('car').className = st === 'RUN' ? 'ok' : 'bad';
    }
  });

  const view = createXRView({
    canvas: $('xrCanvas'),
    video,
    button: $('enter'),
    hint: $('hint'),
    onFrame: createInput(sig),
    // ?layout=tb / ?layout=bt for the X4 two-strip frame (see xr-view.js).
    layout: (new URLSearchParams(location.search).get('layout') || 'equirect').toLowerCase(),
  });
  // The Enter VR click is the user gesture that unlocks audio playback.
  $('enter').addEventListener('click', () => {
    video.play().catch(() => {});
    audio.play().catch(() => {});
  });

  const s1 = createSession({
    session: 'S1', role: 'quest', media: cfg.S1, sig,
    onTrack: (stream) => {
      if (video.srcObject !== stream) video.srcObject = stream;
      if (audio.srcObject !== stream) audio.srcObject = stream;
      video.play().catch(() => {});
      audio.play().catch(() => {});
      const ready = () => view.setVideoReady(true);
      if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) ready();
      else video.addEventListener('loadeddata', ready, { once: true });
    },
    onState: (s) => {
      $('s1').textContent = s;
      $('s1').style.color = stateColor(s);
    },
  });
  startStats({ sig, session: 'S1', role: 'quest', getPc: () => s1.pc });
}

main().catch((err) => { $('error').textContent = String(err); });
