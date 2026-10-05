// Flat-screen 360° viewer for the pilot page (provisional, no WebXR).
//
// Responsibilities: render a <video> as an inside-out sphere on a normal canvas
// with a perspective camera; yaw / pitch / field of view are set by the caller
// (mouse, gamepad). Same sphere and layout handling as quest/xr-view.js.
// Non-responsibilities: input reading, networking.

const DEG = Math.PI / 180;

function multiply(a, b) {
  const out = new Float32Array(16);
  for (let column = 0; column < 4; column += 1) {
    for (let row = 0; row < 4; row += 1) {
      for (let k = 0; k < 4; k += 1) out[row + column * 4] += a[row + k * 4] * b[k + column * 4];
    }
  }
  return out;
}

function perspective(fovY, aspect, near, far) {
  const f = 1 / Math.tan(fovY / 2);
  return new Float32Array([
    f / aspect, 0, 0, 0,
    0, f, 0, 0,
    0, 0, (far + near) / (near - far), -1,
    0, 0, (2 * far * near) / (near - far), 0,
  ]);
}

function rotX(a) {
  const c = Math.cos(a); const s = Math.sin(a);
  return new Float32Array([1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1]);
}

function rotY(a) {
  const c = Math.cos(a); const s = Math.sin(a);
  return new Float32Array([c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1]);
}

// layout: 'equirect' (default), 'tb' or 'bt' (X4 two-strip frame, see xr-view.js).
// yawOffsetDeg: robot front in the image, degrees right of the image center;
// the initial and reset view looks at it.
export function createPanoView({ canvas, video, layout = 'equirect', yawOffsetDeg = 0 }) {
  const gl = canvas.getContext('webgl', { alpha: false, antialias: true });
  if (!gl) throw new Error('WebGL を初期化できません。');

  const compile = (type, source) => {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
    return shader;
  };
  const vs = compile(gl.VERTEX_SHADER, 'attribute vec3 p; attribute vec2 uv; uniform mat4 mvp; varying vec2 v; void main(){gl_Position=mvp*vec4(p,1.0);v=uv;}');
  const fs = compile(gl.FRAGMENT_SHADER, [
    'precision mediump float; uniform sampler2D tex; uniform float L; varying vec2 v;',
    'void main(){',
    '  vec2 t = vec2(v.x, 1.0 - v.y);',
    '  if (L > 0.5) {',
    '    float u = fract(v.x - 0.25);',
    '    float back = step(0.5, u);',
    '    float strip = L > 1.5 ? 1.0 - back : back;',
    '    t = vec2(fract(u * 2.0), strip * 0.5 + t.y * 0.5);',
    '  }',
    '  gl_FragColor = texture2D(tex, t);',
    '}',
  ].join('\n'));
  const program = gl.createProgram();
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error('シェーダーを初期化できません。');

  const vertices = [];
  const rows = 64;
  const columns = 128;
  // Same orientation as xr-view.js: u = 0.5 straight ahead (-z), u grows to +x.
  const point = (azimuth, latitude) => [
    10 * Math.cos(latitude) * Math.sin(azimuth - Math.PI),
    10 * Math.sin(latitude),
    -10 * Math.cos(latitude) * Math.cos(azimuth - Math.PI),
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
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);
  gl.useProgram(program);
  const position = gl.getAttribLocation(program, 'p');
  const uv = gl.getAttribLocation(program, 'uv');
  gl.enableVertexAttribArray(position);
  gl.enableVertexAttribArray(uv);
  gl.vertexAttribPointer(position, 3, gl.FLOAT, false, 20, 0);
  gl.vertexAttribPointer(uv, 2, gl.FLOAT, false, 20, 12);
  const vertexCount = vertices.length / 5;
  const mvpLocation = gl.getUniformLocation(program, 'mvp');
  gl.uniform1f(gl.getUniformLocation(program, 'L'), { tb: 1, bt: 2 }[layout] || 0);
  const texture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.disable(gl.CULL_FACE);

  // yaw > 0 looks left, pitch > 0 looks up (radians); fov is vertical (degrees).
  const frontYaw = -(Number(yawOffsetDeg) || 0) * DEG;
  const camera = { yaw: frontYaw, pitch: 0, fov: 90 };

  function render() {
    const dpr = window.devicePixelRatio || 1;
    const w = Math.round(canvas.clientWidth * dpr);
    const h = Math.round(canvas.clientHeight * dpr);
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !w || !h) return;
    camera.pitch = Math.max(-85 * DEG, Math.min(85 * DEG, camera.pitch));
    camera.fov = Math.max(30, Math.min(120, camera.fov));
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video);
    const view = multiply(rotX(-camera.pitch), rotY(-camera.yaw));
    gl.uniformMatrix4fv(mvpLocation, false, multiply(perspective(camera.fov * DEG, w / h, 0.1, 100), view));
    gl.drawArrays(gl.TRIANGLES, 0, vertexCount);
  }

  return {
    camera,
    render,
    reset() { camera.yaw = frontYaw; camera.pitch = 0; camera.fov = 90; },
  };
}
