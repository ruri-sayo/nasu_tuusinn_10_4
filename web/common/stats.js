// Periodic WebRTC stats summary (DD-0011, AD-0009).
//
// Responsibilities:
//   - Every 2 s, summarize getStats() of a session and send it to the hub as
//     {type: "stats", session, data}. Also hand the summary to a callback.
// Non-responsibilities:
//   - Display (pages render as they like).
// Side Effects: sends WebSocket messages.

export function startStats({ sig, session, role, getPc, onSummary, periodMs = 2000 }) {
  let prev = new Map();
  let prevAt = performance.now();

  async function sample() {
    const pc = getPc();
    const now = performance.now();
    const dt = (now - prevAt) / 1000;
    const data = { role, state: pc ? pc.connectionState : 'down' };
    if (pc) {
      const report = await pc.getStats();
      const next = new Map();
      let sendBytes = 0;
      let recvBytes = 0;
      const pairs = [];
      const candidates = new Map();
      report.forEach((s) => {
        if (s.type === 'outbound-rtp' || s.type === 'inbound-rtp') {
          const bytes = s.type === 'outbound-rtp' ? s.bytesSent : s.bytesReceived;
          const last = prev.get(s.id);
          const delta = last === undefined ? 0 : Math.max(0, bytes - last);
          next.set(s.id, bytes);
          if (s.type === 'outbound-rtp') sendBytes += delta; else recvBytes += delta;
          if (s.kind === 'video') {
            data.fps = s.framesPerSecond ?? data.fps;
            if (s.frameWidth) data.width = s.frameWidth;
            if (s.frameHeight) data.height = s.frameHeight;
            if (s.type === 'inbound-rtp') {
              data.frames_dropped = s.framesDropped;
              if (s.jitter !== undefined) data.jitter_ms = Math.round(s.jitter * 1000);
            } else if (s.qualityLimitationReason) {
              data.quality_limit = s.qualityLimitationReason;
            }
          }
        } else if (s.type === 'candidate-pair') {
          pairs.push(s);
        } else if (s.type === 'local-candidate' || s.type === 'remote-candidate') {
          candidates.set(s.id, s);
        } else if (s.type === 'transport' && s.selectedCandidatePairId) {
          data._selected = s.selectedCandidatePairId;
        }
      });
      const pair = pairs.find((p) => p.id === data._selected)
        || pairs.find((p) => p.nominated && p.state === 'succeeded');
      delete data._selected;
      if (pair) {
        if (pair.currentRoundTripTime !== undefined) data.rtt_ms = Math.round(pair.currentRoundTripTime * 1000);
        data.local_type = candidates.get(pair.localCandidateId)?.candidateType;
        data.remote_type = candidates.get(pair.remoteCandidateId)?.candidateType;
      }
      if (dt > 0) {
        data.send_kbps = Math.round((sendBytes * 8) / 1000 / dt);
        data.recv_kbps = Math.round((recvBytes * 8) / 1000 / dt);
      }
      prev = next;
    }
    prevAt = now;
    sig.send('stats', { session, data });
    if (onSummary) onSummary(data);
  }

  const timer = setInterval(() => { sample().catch((e) => console.warn('stats', e)); }, periodMs);
  return () => clearInterval(timer);
}

// Shared styles for small status badges.
export function stateColor(state) {
  if (state === 'connected') return '#3c3';
  if (state === 'connecting' || state === 'new') return '#fc3';
  return '#f44';
}
