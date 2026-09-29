// Signaling client for the hub WebSocket (DD-0011, protocol DD-0008).
//
// Responsibilities:
//   - Connect to /ws on the serving host, announce the role (hello) and
//     reconnect with backoff 1 -> 2 -> 4 -> 5 s (cap).
//   - Dispatch incoming messages by type; send messages and envelopes.
//   - Stop reconnecting when the hub closes with 4001 (another page took
//     over this role), so two pages of one role do not evict each other.
// Non-responsibilities:
//   - WebRTC handling (rtc.js). Retrying sends made while disconnected.
// Side Effects: opens a WebSocket to the hub.

const REPLACED = 4001;

export class Signaling {
  constructor(role) {
    this.role = role;
    this.handlers = new Map();
    this.seq = {};
    this.ws = null;
    this.delay = 1000;
    this.connected = false;
    this.connect();
  }

  get url() {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${scheme}://${location.host}/ws`;
  }

  connect() {
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.onopen = () => {
      this.delay = 1000;
      this.connected = true;
      ws.send(JSON.stringify({ type: 'hello', role: this.role }));
      this.emit('open', {});
    };
    ws.onmessage = (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      if (msg && typeof msg.type === 'string') this.emit(msg.type, msg);
    };
    ws.onclose = (event) => {
      if (this.ws !== ws) return;
      this.connected = false;
      if (event.code === REPLACED) {
        this.emit('replaced', {});
        this.emit('close', { replaced: true });
        return;
      }
      this.emit('close', {});
      setTimeout(() => this.connect(), this.delay);
      this.delay = Math.min(this.delay * 2, 5000);
    };
    ws.onerror = () => ws.close();
  }

  on(type, fn) {
    if (!this.handlers.has(type)) this.handlers.set(type, []);
    this.handlers.get(type).push(fn);
  }

  emit(type, msg) {
    for (const fn of this.handlers.get(type) || []) {
      try { fn(msg); } catch (err) { console.error(`handler for ${type} failed`, err); }
    }
  }

  // Returns false when the socket is not open (the message is dropped).
  send(type, body = {}) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify({ type, ...body }));
    return true;
  }

  // Wrap payload in the common envelope (DD-0001). The hub overwrites src.
  sendEnv(topic, payload) {
    const seq = (this.seq[topic] ?? -1) + 1;
    this.seq[topic] = seq;
    const env = { topic, ver: 1, seq, ts: Date.now(), src: this.role, payload };
    return this.send('env', { env });
  }
}
