// WebXR 360° equirectangular viewer (DD-0014).
//
// Ported from the Mac -> Quest test viewer (mac-camera-vr, createWebXR360Renderer).
// It uses raw WebGL, so no three.js / CDN is needed.
//
// Responsibilities: render a <video> as an inside-out sphere in immersive-vr,
// following head pose; expose each XR frame to a callback (controller input).
// Non-responsibilities: stereo/parallax (mono 360° on both eyes), networking.

export function createXRView({ canvas, video, button, hint, onFrame, onSessionChange }) {
  let session = null;
  let gl = null;
  let program = null;
  let texture = null;
  let vertexCount = 0;
  let referenceSpace = null;
  let supported = false;
  let videoReady = false;
  let mvpLocation = null;

  const multiply = (a, b) => {
    const out = new Float32Array(16);
    for (let column = 0; column < 4; column += 1) {
      for (let row = 0; row < 4; row += 1) {
        for (let k = 0; k < 4; k += 1) out[row + column * 4] += a[row + k * 4] * b[k + column * 4];
      }
    }
    return out;
  };

  async function checkSupport() {
    if (!window.isSecureContext) {
      hint.textContent = 'WebXR には HTTPS が必要です。HTTPS の URL を開いてください。';
      button.textContent = 'HTTPS が必要です';
      return;
    }
    if (!navigator.xr) {
      hint.textContent = 'このブラウザは WebXR immersive-vr に対応していません。Quest Browser で開いてください。';
      button.textContent = 'WebXR 非対応';
      return;
    }
    supported = await navigator.xr.isSessionSupported('immersive-vr').catch(() => false);
    hint.textContent = supported
      ? '映像が届いたら「VR で見る」を押してください。'
      : 'immersive-vr を利用できません。Quest Browser の設定を確認してください。';
    updateButton();
  }

  function updateButton() {
    button.disabled = !supported || !videoReady || Boolean(session);
    button.textContent = session ? 'VR 表示中' : (supported && videoReady ? 'VR で見る' : '映像の到着を待っています');
  }

  function compile(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
    return shader;
  }

  function initializeGL() {
    gl = canvas.getContext('webgl', { alpha: false, antialias: true, xrCompatible: true });
    if (!gl) throw new Error('WebGL を初期化できません。');
    const vs = compile(gl.VERTEX_SHADER, 'attribute vec3 p; attribute vec2 uv; uniform mat4 mvp; varying vec2 v; void main(){gl_Position=mvp*vec4(p,1.0);v=uv;}');
    const fs = compile(gl.FRAGMENT_SHADER, 'precision mediump float; uniform sampler2D tex; varying vec2 v; void main(){gl_FragColor=texture2D(tex,vec2(v.x,1.0-v.y));}');
    program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error('WebXR シェーダーを初期化できません。');

    const vertices = [];
    const rows = 64;
    const columns = 128;
    const point = (azimuth, latitude) => [
      -10 * Math.cos(latitude) * Math.sin(azimuth),
      10 * Math.sin(latitude),
      -10 * Math.cos(latitude) * Math.cos(azimuth),
    ];
    for (let y = 0; y < rows; y += 1) {
      const v0 = y / rows;
      const v1 = (y + 1) / rows;
      const lat0 = (v0 - 0.5) * Math.PI;
      const lat1 = (v1 - 0.5) * Math.PI;
      for (let x = 0; x < columns; x += 1) {
        const u0 = x / columns;
        const u1 = (x + 1) / columns;
        const a = point(u0 * Math.PI * 2, lat0);
        const b = point(u1 * Math.PI * 2, lat0);
        const c = point(u1 * Math.PI * 2, lat1);
        const d = point(u0 * Math.PI * 2, lat1);
        vertices.push(...a, u0, v0, ...b, u1, v0, ...c, u1, v1, ...a, u0, v0, ...c, u1, v1, ...d, u0, v1);
      }
    }
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);
    gl.useProgram(program);
    const position = gl.getAttribLocation(program, 'p');
    const uv = gl.getAttribLocation(program, 'uv');
    gl.enableVertexAttribArray(position);
    gl.enableVertexAttribArray(uv);
    gl.vertexAttribPointer(position, 3, gl.FLOAT, false, 20, 0);
    gl.vertexAttribPointer(uv, 2, gl.FLOAT, false, 20, 12);
    vertexCount = vertices.length / 5;
    mvpLocation = gl.getUniformLocation(program, 'mvp');
    texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.disable(gl.CULL_FACE);
    gl.enable(gl.DEPTH_TEST);
  }

  function renderXRFrame(time, frame) {
    const current = frame.session;
    current.requestAnimationFrame(renderXRFrame);
    if (onFrame) {
      try { onFrame(frame, referenceSpace, time); } catch (err) { console.error('onFrame', err); }
    }
    const pose = frame.getViewerPose(referenceSpace);
    if (!pose || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
    const layer = current.renderState.baseLayer;
    gl.bindFramebuffer(gl.FRAMEBUFFER, layer.framebuffer);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.useProgram(program);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video);
    for (const view of pose.views) {
      const vp = layer.getViewport(view);
      gl.viewport(vp.x, vp.y, vp.width, vp.height);
      gl.uniformMatrix4fv(mvpLocation, false, multiply(view.projectionMatrix, view.transform.inverse.matrix));
      gl.drawArrays(gl.TRIANGLES, 0, vertexCount);
    }
  }

  async function enterVR() {
    try {
      session = await navigator.xr.requestSession('immersive-vr', { optionalFeatures: ['local-floor'] });
      if (!gl) initializeGL();
      await gl.makeXRCompatible();
      session.updateRenderState({ baseLayer: new XRWebGLLayer(session, gl) });
      // local-floor is the frame for controller poses (DD-0002); fall back to local.
      referenceSpace = await session.requestReferenceSpace('local-floor')
        .catch(() => session.requestReferenceSpace('local'));
      session.addEventListener('end', () => {
        session = null;
        updateButton();
        if (onSessionChange) onSessionChange(false);
      });
      updateButton();
      if (onSessionChange) onSessionChange(true);
      session.requestAnimationFrame(renderXRFrame);
    } catch (error) {
      session = null;
      updateButton();
      hint.textContent = `VR を開始できませんでした: ${error.message}`;
    }
  }

  button.addEventListener('click', enterVR);
  checkSupport();
  return {
    setVideoReady(ready) { videoReady = ready; updateButton(); },
    end() { session?.end().catch(() => {}); },
  };
}
