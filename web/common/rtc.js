// WebRTC session helper for S1/S2 (DD-0011, AD-0003, AD-0004).
//
// Responsibilities:
//   - Create a fresh RTCPeerConnection per (re)negotiation, without STUN/TURN.
//   - Offerer: add tracks with contentHint and codec preference, then apply
//     maxBitrate / maxFramerate via setParameters once connected.
//   - Trickle ICE through the hub; request a restart on ICE failure or a
//     disconnect lasting 3 s.
//   - Relay (S4): an offerer may start without media (`sendKinds` reserves
//     send slots) and swap the stream later with setStream() (replaceTrack,
//     no renegotiation).
// Non-responsibilities:
//   - Acquiring media (pages do that). Encoding and rate adaptation (browser).
// Side Effects: opens WebRTC connections (network).

const OFFERER = { S1: 'car_media', S2: 'booth', S4: 'booth' };
const DEGRADATION = { motion: 'maintain-framerate', detail: 'maintain-resolution' };

export function createSession({ session, role, stream = null, sendKinds = [], media, sig, onTrack, onState }) {
  const isOfferer = OFFERER[session] === role;
  let pc = null;
  let pending = [];
  let discTimer = null;

  const setState = (state) => { if (onState) onState(state); };

  function close() {
    clearTimeout(discTimer);
    pending = [];
    if (pc) {
      pc.onicecandidate = pc.ontrack = pc.oniceconnectionstatechange = pc.onconnectionstatechange = null;
      pc.close();
    }
    pc = null;
  }

  function requestRestart(reason) {
    console.warn(`${session}: restart requested (${reason})`);
    sig.send('restart_req', { session });
  }

  function newPc() {
    close();
    const conn = new RTCPeerConnection({ iceServers: [] });
    pc = conn;
    conn.onicecandidate = (e) => {
      if (e.candidate) sig.send('signal', { session, data: { candidate: e.candidate.toJSON() } });
    };
    conn.ontrack = (e) => {
      const s = e.streams[0] || new MediaStream([e.track]);
      if (onTrack) onTrack(s, e.track);
    };
    conn.oniceconnectionstatechange = () => {
      if (pc !== conn) return;
      const st = conn.iceConnectionState;
      clearTimeout(discTimer);
      if (st === 'failed') requestRestart('ice failed');
      else if (st === 'disconnected') discTimer = setTimeout(() => requestRestart('disconnected 3 s'), 3000);
    };
    conn.onconnectionstatechange = () => {
      if (pc !== conn) return;
      setState(conn.connectionState);
      if (conn.connectionState === 'connected' && isOfferer) applyParameters(conn);
    };
    setState('connecting');
    return conn;
  }

  // Kind of a send slot, also when its track is not set yet (relay).
  const kindOf = (tr) => tr.sender.track?.kind || tr.receiver.track?.kind;

  async function applyParameters(conn) {
    for (const tr of conn.getTransceivers()) {
      const { sender } = tr;
      const kind = kindOf(tr);
      if (!kind) continue;
      const params = sender.getParameters();
      if (!params.encodings || params.encodings.length === 0) params.encodings = [{}];
      if (kind === 'video') {
        params.encodings[0].maxBitrate = media.max_bitrate;
        params.encodings[0].maxFramerate = media.fps;
        const pref = DEGRADATION[media.content_hint];
        if (pref) params.degradationPreference = pref;
      } else {
        params.encodings[0].maxBitrate = media.audio_max_bitrate;
      }
      try {
        await sender.setParameters(params);
      } catch (err) {
        console.warn(`${session}: setParameters failed`, err);
      }
    }
  }

  function preferCodec(transceiver) {
    if (!media.codec || media.codec === 'auto' || !RTCRtpSender.getCapabilities) return;
    const caps = RTCRtpSender.getCapabilities('video');
    if (!caps || typeof transceiver.setCodecPreferences !== 'function') return;
    const want = `video/${media.codec}`.toLowerCase();
    const first = caps.codecs.filter((c) => c.mimeType.toLowerCase() === want);
    const rest = caps.codecs.filter((c) => c.mimeType.toLowerCase() !== want);
    if (first.length) transceiver.setCodecPreferences([...first, ...rest]);
  }

  async function offer() {
    const conn = newPc();
    const msStream = stream || new MediaStream();
    const kinds = new Set();
    for (const track of stream ? stream.getTracks() : []) {
      if (track.kind === 'video') track.contentHint = media.content_hint;
      const tr = conn.addTransceiver(track, { direction: 'sendonly', streams: [msStream] });
      if (track.kind === 'video') preferCodec(tr);
      kinds.add(track.kind);
    }
    for (const kind of sendKinds) {
      if (kinds.has(kind)) continue;
      const tr = conn.addTransceiver(kind, { direction: 'sendonly', streams: [msStream] });
      if (kind === 'video') preferCodec(tr);
    }
    const desc = await conn.createOffer();
    await conn.setLocalDescription(desc);
    sig.send('signal', { session, data: { sdp: { type: desc.type, sdp: desc.sdp } } });
  }

  async function flush(conn) {
    const list = pending;
    pending = [];
    for (const c of list) {
      try { await conn.addIceCandidate(c); } catch (err) { console.warn('addIceCandidate', err); }
    }
  }

  async function onSignal(msg) {
    if (msg.session !== session || !msg.data) return;
    const data = msg.data;
    try {
      if (data.sdp && data.sdp.type === 'offer' && !isOfferer) {
        const conn = newPc();
        await conn.setRemoteDescription(data.sdp);
        await flush(conn);
        const answer = await conn.createAnswer();
        await conn.setLocalDescription(answer);
        sig.send('signal', { session, data: { sdp: { type: answer.type, sdp: answer.sdp } } });
      } else if (data.sdp && data.sdp.type === 'answer' && isOfferer && pc) {
        await pc.setRemoteDescription(data.sdp);
        await flush(pc);
      } else if (data.candidate) {
        if (!pc || !pc.remoteDescription) pending.push(data.candidate);
        else await pc.addIceCandidate(data.candidate);
      }
    } catch (err) {
      console.error(`${session}: signaling error`, err);
      requestRestart('signaling error');
    }
  }

  sig.on('signal', onSignal);
  sig.on('restart', (msg) => { if (msg.session === session && isOfferer) offer().catch((e) => console.error(e)); });
  sig.on('peer', (msg) => {
    if (msg.session === session && msg.state === 'down') { close(); setState('down'); }
  });

  // If the page set up media after the hub already sent `restart`, ask again.
  if (isOfferer && sig.connected) sig.send('restart_req', { session });

  // Replace the sent media without renegotiation; later offers use it too.
  function setStream(next) {
    stream = next;
    if (!pc) return;
    for (const tr of pc.getTransceivers()) {
      const kind = kindOf(tr);
      const track = next?.getTracks().find((t) => t.kind === kind) || null;
      if (track && kind === 'video') track.contentHint = media.content_hint;
      if (tr.sender.track !== track) tr.sender.replaceTrack(track).catch((e) => console.warn(`${session}: replaceTrack`, e));
    }
  }

  return {
    session,
    get pc() { return pc; },
    close,
    setStream,
  };
}
