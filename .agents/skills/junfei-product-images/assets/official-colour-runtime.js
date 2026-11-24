// NativeCurves.js
var IDENTITY_CURVE = Object.freeze([[0, 0], [255, 255]]);
var clamp = (x) => Math.min(255, Math.max(0, x));
function normalizeCurve(points) {
  if (!Array.isArray(points) || points.length < 2 || points.length > 256) throw new RangeError("Expected 2..256 control points");
  const normalized = points.map((p) => {
    if (!Array.isArray(p) || p.length !== 2 || p.some((x) => typeof x !== "number" || !Number.isFinite(x) || x < 0 || x > 255)) throw new RangeError("Expected finite [x,y] control points in 0..255");
    return p.map(Math.fround);
  });
  for (let i = 1; i < normalized.length; i++) if (normalized[i][0] <= normalized[i - 1][0]) throw new RangeError("Control-point x coordinates must remain strictly increasing after float32 conversion");
  if (Math.trunc(normalized.at(-1)[0]) <= Math.trunc(normalized[0][0])) throw new RangeError("Control-point range must span at least one integer sample");
  return normalized;
}
function nativeCompatibleCurveDoubles(points) {
  const curve = normalizeCurve(points), n = curve.length;
  const xs = curve.map((p) => p[0]), ys = curve.map((p) => p[1]);
  const first = Math.trunc(xs[0]), last = Math.trunc(xs[n - 1]);
  const out = new Float64Array(256);
  if (n === 2) {
    const y0 = Math.trunc(ys[0]), y1 = Math.trunc(ys[1]), slope = (y1 - y0) / (last - first);
    for (let i = 0; i < 256; i++) out[i] = i < first ? y0 : i >= last ? y1 : clamp(slope * (i - first) + y0);
    return out;
  }
  const a = new Float64Array(n), b = new Float64Array(n), c = new Float64Array(n), rhs = new Float64Array(n);
  b[0] = b[n - 1] = 1;
  for (let i = 1; i < n - 1; i++) {
    const left = xs[i] - xs[i - 1], right = xs[i + 1] - xs[i];
    a[i] = left;
    b[i] = 2 * (left + right);
    c[i] = right;
    rhs[i] = 6 * ((ys[i + 1] - ys[i]) / right - (ys[i] - ys[i - 1]) / left);
  }
  for (let i = 1; i < n; i++) {
    const scale = a[i] / b[i - 1];
    b[i] -= scale * c[i - 1];
    rhs[i] -= scale * rhs[i - 1];
  }
  const second = new Float64Array(n);
  second[n - 1] = rhs[n - 1] / b[n - 1];
  for (let i = n - 2; i >= 0; i--) second[i] = (rhs[i] - c[i] * second[i + 1]) / b[i];
  for (let i = 0; i < 256; i++) {
    if (i < first) {
      out[i] = Math.trunc(ys[0]);
      continue;
    }
    if (i >= last) {
      out[i] = Math.trunc(ys[n - 1]);
      continue;
    }
    const x = i - first;
    let segment = 0;
    while (segment < n - 2 && x > xs[segment + 1]) segment++;
    const h = xs[segment + 1] - xs[segment], left = (xs[segment + 1] - x) / h, right = (x - xs[segment]) / h;
    const value = left * ys[segment] + right * ys[segment + 1] + ((left * left * left - left) * second[segment] + (right * right * right - right) * second[segment + 1]) * h * h / 6;
    out[i] = clamp(value);
  }
  return out;
}
function nativeCompatibleCurves(entry = {}) {
  const master = nativeCompatibleCurveDoubles(entry.RGB ?? IDENTITY_CURVE);
  const channels = ["R", "G", "B"].map((name) => {
    const channel = nativeCompatibleCurveDoubles(entry[name] ?? IDENTITY_CURVE), bytes = new Uint8Array(256);
    for (let i = 0; i < 256; i++) bytes[i] = Math.trunc(Math.fround(master[Math.trunc(Math.fround(channel[i]))]));
    return bytes;
  });
  const rgba = new Uint8Array(3072);
  for (let c = 0; c < 3; c++) for (let i = 0; i < 256; i++) rgba.set([channels[c][i], channels[c][i], channels[c][i], 255], c * 1024 + i * 4);
  return { channels, rgba };
}

// OfficialColour.ts
var VERTEX = "precision highp float;attribute vec4 position;attribute vec4 textureUV;uniform mat4 transformMatrix;varying vec2 textureCoordinate;void main(){gl_Position=transformMatrix*vec4(position.xyz,1.0);textureCoordinate=textureUV.xy;}";
async function load(url) {
  const im = new Image();
  im.src = url;
  await im.decode();
  return im;
}
function pixels(im) {
  const c = document.createElement("canvas");
  c.width = im.naturalWidth;
  c.height = im.naturalHeight;
  const x = c.getContext("2d");
  x.drawImage(im, 0, 0);
  return x.getImageData(0, 0, c.width, c.height);
}
function labLight(r, g, b) {
  const a = [r, g, b].map((v) => {
    v /= 255;
    return v > 0.04045 ? Math.pow((v + 0.055) / 1.055, 2.4) : v / 12.92;
  });
  const y = a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
  return y > 8856e-6 ? 116 * Math.cbrt(y) - 16 : 903.3 * y;
}
function nativeCompatibleStatistics(src, mask) {
  const sum = [0, 0, 0], lights = [];
  let n = 0, covered = 0;
  const stepX = Math.max(1, Math.ceil(src.width * 0.05)), stepY = Math.max(1, Math.ceil(src.height * 0.05));
  for (let y = 0; y < src.height; y += stepY) for (let x = 0; x < src.width; x += stepX) {
    const k = (y * src.width + x) * 4;
    if (mask.data[k] <= 0) continue;
    for (let j = 0; j < 3; j++) sum[j] += src.data[k + j];
    n++;
  }
  for (let k = 0; k < mask.data.length; k += 4) {
    if (mask.data[k] + mask.data[k + 1] + mask.data[k + 2] <= 0) continue;
    lights.push(Math.max(0, Math.min(100, labLight(src.data[k], src.data[k + 1], src.data[k + 2]))));
    covered++;
  }
  if (n < 10 || covered < Math.max(10, src.width * src.height * 5e-3)) throw new Error("\u5546\u54C1\u9009\u533A\u8986\u76D6\u4E0D\u8DB3\uFF0C\u4E0D\u80FD\u636E\u6B64\u8BA1\u7B97\u6362\u8272\u4E3B\u8272");
  lights.sort((a, b) => a - b);
  const percentile = (ratio) => {
    const position = (lights.length - 1) * ratio, lower = Math.floor(position), upper = Math.min(lights.length - 1, lower + 1);
    return lights[lower] * (1 - (position - lower)) + lights[upper] * (position - lower);
  };
  return {
    main: sum.map((v) => v / n),
    low: percentile(0.05),
    high: percentile(0.95),
    samples: n,
    coveragePixels: covered,
    coverageFraction: covered / (src.width * src.height),
    sampling: "linkfox_grid_5percent_positive_mask_v1",
    coverageGate: "local_min10grid_and_0_5percent_pixels"
  };
}
function curveTexture(parameters) {
  const convert = (value) => {
    if (value === void 0 || value === null) return void 0;
    if (!Array.isArray(value)) throw new Error("\u66F2\u7EBF\u63A7\u5236\u70B9\u65E0\u6548");
    return value.map((point) => [point.x, point.y]);
  };
  return nativeCompatibleCurves({
    RGB: convert(parameters.RGBchannel),
    R: convert(parameters.Rchannel),
    G: convert(parameters.Gchannel),
    B: convert(parameters.Bchannel)
  }).rgba;
}
async function sha256(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", new Uint8Array(bytes));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
async function renderOfficialColour(sourceUrl, maskUrl, target, resources, settings = {}, options = {}) {
  const [sourceImage, maskImage] = await Promise.all([load(sourceUrl), load(maskUrl)]);
  const src = pixels(sourceImage), mask = pixels(maskImage);
  if (src.width !== mask.width || src.height !== mask.height) throw new Error("\u9009\u533A\u5FC5\u987B\u4E0E\u539F\u56FE\u5C3A\u5BF8\u4E00\u81F4");
  if (!/^#[0-9a-f]{6}$/i.test(target)) throw new Error("\u76EE\u6807RGB\u989C\u8272\u65E0\u6548");
  const stats = nativeCompatibleStatistics(src, mask), canvas = document.createElement("canvas");
  canvas.width = src.width;
  canvas.height = src.height;
  const gl = canvas.getContext("webgl2", { premultipliedAlpha: false, preserveDrawingBuffer: true, alpha: true });
  if (!gl) throw new Error("\u5F53\u524D\u6D4F\u89C8\u5668\u65E0\u6CD5\u6267\u884C\u5B98\u65B9WebGL\u7740\u8272\u5668\uFF1B\u672A\u7528\u7B80\u5316\u7B97\u6CD5\u5192\u5145");
  const shaders = [], programs = /* @__PURE__ */ new Map(), textures = [], frames = [];
  const compile = (type, text) => {
    const s = gl.createShader(type);
    shaders.push(s);
    gl.shaderSource(s, text);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || "\u7740\u8272\u5668\u7F16\u8BD1\u5931\u8D25");
    return s;
  };
  const texture = (image, width = src.width, height = src.height, raw) => {
    const t = gl.createTexture();
    textures.push(t);
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    if (image) {
      const upload = document.createElement("canvas");
      upload.width = image.naturalWidth;
      upload.height = image.naturalHeight;
      const context = upload.getContext("2d");
      context.translate(0, upload.height);
      context.scale(1, -1);
      context.drawImage(image, 0, 0);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, upload.width, upload.height, 0, gl.RGBA, gl.UNSIGNED_BYTE, upload);
    } else {
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, raw || null);
    }
    return t;
  };
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, 1, -1, -1, 1, -1, 1, 1]), gl.STATIC_DRAW);
  const uvBuffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, uvBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 1, 0, 0, 1, 0, 1, 1]), gl.STATIC_DRAW);
  try {
    const vertex = compile(gl.VERTEX_SHADER, VERTEX), original = texture(sourceImage), originalMask = texture(maskImage);
    const cache = /* @__PURE__ */ new Map();
    let current = originalMask;
    const passes = [];
    for (const filter of resources.config.filters) {
      const originalShader = resources.shaders[filter.fs];
      if (!originalShader) throw new Error("\u7F3A\u5C11\u539F\u59CB\u7740\u8272\u5668 " + filter.fs);
      let program = programs.get(filter.fs);
      if (!program) {
        program = gl.createProgram();
        gl.attachShader(program, vertex);
        gl.attachShader(program, compile(gl.FRAGMENT_SHADER, "precision highp float;\n" + originalShader));
        gl.linkProgram(program);
        if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || "\u7740\u8272\u5668\u94FE\u63A5\u5931\u8D25");
        programs.set(filter.fs, program);
      }
      gl.useProgram(program);
      for (const [name, source] of [["position", buffer], ["textureUV", uvBuffer]]) {
        const loc = gl.getAttribLocation(program, name);
        gl.bindBuffer(gl.ARRAY_BUFFER, source);
        gl.enableVertexAttribArray(loc);
        gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 8, 0);
      }
      gl.uniformMatrix4fv(gl.getUniformLocation(program, "transformMatrix"), false, new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]));
      const values = Object.fromEntries(filter.params.map((p) => [p.key, p.default]));
      Object.assign(values, settings[filter.index] || {});
      if (filter.index === "1" || filter.index === "4") {
        if (settings[filter.index]?.clothingMainColor !== void 0) {
          values.clothingMainColor = settings[filter.index].clothingMainColor;
          values.bSetMainColor = settings[filter.index]?.bSetMainColor ?? 1;
        } else if (settings[filter.index]?.bSetMainColor === void 0) {
          values.bSetMainColor = 1;
          values.clothingMainColor = stats.main;
        }
      }
      if (filter.index === "4") {
        values.targetColor = [1, 3, 5].map((i) => parseInt(target.slice(i, i + 2), 16));
        values.enable = settings[filter.index]?.enable ?? 1;
        values.L_min_orig = settings[filter.index]?.L_min_orig ?? stats.low;
        values.L_max_orig = settings[filter.index]?.L_max_orig ?? (stats.high > stats.low ? stats.high : stats.low + 1);
      }
      for (const parameter of filter.params) {
        const value = values[parameter.key];
        if (typeof value === "number" && (!Number.isFinite(value) || parameter.min !== void 0 && value < parameter.min || parameter.max !== void 0 && value > parameter.max)) throw new Error(parameter.name + "\u8D85\u51FA\u539F\u59CB\u53C2\u6570\u8303\u56F4");
        if (parameter.type === "xyz" && (!Array.isArray(value) || value.length !== 3 || value.some((v) => !Number.isFinite(v) || v < (parameter.min ?? 0) || v > (parameter.max ?? 255)))) throw new Error(parameter.name + "\u5FC5\u987B\u4E3A\u6709\u6548RGB\u6570\u7EC4");
      }
      let second = filter.input2 ? cache.get(filter.input2) : original;
      const third = filter.input3 ? cache.get(filter.input3) : originalMask;
      if (filter.fs === "colorCurves.fs") second = texture(null, 256, 3, curveTexture(values));
      const inputs = [current, second || original, third || originalMask];
      inputs.forEach((t, i) => {
        gl.activeTexture(gl.TEXTURE0 + i);
        gl.bindTexture(gl.TEXTURE_2D, t);
        gl.uniform1i(gl.getUniformLocation(program, "input" + (i + 1)), i);
      });
      values.width = src.width;
      values.height = src.height;
      values.channelForA = 0;
      const count = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS);
      for (let i = 0; i < count; i++) {
        const u = gl.getActiveUniform(program, i);
        const value = values[u.name];
        if (value === void 0 || u.type === gl.SAMPLER_2D) continue;
        const location = gl.getUniformLocation(program, u.name);
        if (u.type === gl.FLOAT_VEC3) gl.uniform3fv(location, value);
        else if (u.type === gl.FLOAT_VEC2) gl.uniform2fv(location, value);
        else if (u.type === gl.INT || u.type === gl.BOOL) gl.uniform1i(location, Number(value));
        else if (u.type === gl.FLOAT) gl.uniform1f(location, Number(value));
      }
      const out = texture(null), frame = gl.createFramebuffer();
      frames.push(frame);
      gl.bindFramebuffer(gl.FRAMEBUFFER, frame);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, out, 0);
      if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) throw new Error("\u5B98\u65B9\u6EE4\u955C\u5E27\u7F13\u51B2\u4E0D\u53EF\u7528");
      inputs.forEach((t, i) => {
        gl.activeTexture(gl.TEXTURE0 + i);
        gl.bindTexture(gl.TEXTURE_2D, t);
      });
      gl.viewport(0, 0, src.width, src.height);
      gl.drawArrays(gl.TRIANGLE_FAN, 0, 4);
      const error = gl.getError();
      if (error !== gl.NO_ERROR) throw new Error("\u5B98\u65B9\u6EE4\u955C\u6267\u884C\u5931\u8D25 " + error);
      current = out;
      cache.set(filter.index, out);
      passes.push({ index: filter.index, fs: filter.fs, params: values });
    }
    const raw = new Uint8Array(src.width * src.height * 4);
    gl.readPixels(0, 0, src.width, src.height, gl.RGBA, gl.UNSIGNED_BYTE, raw);
    if (gl.getError() !== gl.NO_ERROR) throw new Error("\u5B98\u65B9\u6EE4\u955C\u7ED3\u679C\u8BFB\u53D6\u5931\u8D25");
    const data = new Uint8ClampedArray(raw.length), nativeData = new Uint8ClampedArray(raw.length);
    let outside = 0, nativeOutsideChangedPixels = 0;
    for (let y = 0; y < src.height; y++) for (let x = 0; x < src.width; x++) {
      const k = (y * src.width + x) * 4, from = ((src.height - y - 1) * src.width + x) * 4;
      for (let j = 0; j < 4; j++) nativeData[k + j] = raw[from + j];
      if (mask.data[k] === 0 && [0, 1, 2, 3].some((j) => nativeData[k + j] !== src.data[k + j])) nativeOutsideChangedPixels++;
      const restore = options.preserveOutsideSelection === true && mask.data[k] === 0;
      for (let j = 0; j < 4; j++) data[k + j] = restore ? src.data[k + j] : raw[from + j];
      data[k + 3] = src.data[k + 3];
      if (restore) outside++;
    }
    const output = document.createElement("canvas");
    output.width = src.width;
    output.height = src.height;
    output.getContext("2d").putImageData(new ImageData(data, src.width, src.height), 0, 0);
    const blob = await new Promise((resolve, reject) => output.toBlob((b) => b ? resolve(b) : reject(new Error("\u4FDD\u5B58\u5B98\u65B9\u6362\u8272\u7ED3\u679C\u5931\u8D25")), "image/png"));
    const [nativeOutputSHA, outputSHA, outputPngSHA] = await Promise.all([sha256(nativeData), sha256(data), blob.arrayBuffer().then((bytes) => sha256(new Uint8Array(bytes)))]);
    return { blob, receipt: {
      version: resources.version,
      sourceHashes: resources.sourceHashes,
      passes,
      statistics: stats,
      outsideRestoredPixels: outside,
      outsideSelectionPolicy: options.preserveOutsideSelection ? "restore_source_explicit_quality_option" : "native_filter_output",
      boundaryPolicy: options.preserveOutsideSelection ? "preserve_outside_selection_source_rgba" : "native_filter_output",
      nativeOutsideChangedPixels,
      nativeOutputSHA,
      outputSHA,
      outputPngSHA,
      hashPixelOrder: "rgba8_top_to_bottom",
      colourAnchor: {
        source: settings["4"]?.clothingMainColor !== void 0 ? "explicit_sku_override" : "native_statistics",
        main: passes.find((pass) => pass.index === "4")?.params.clothingMainColor,
        low: passes.find((pass) => pass.index === "4")?.params.L_min_orig,
        high: passes.find((pass) => pass.index === "4")?.params.L_max_orig
      },
      renderer: "original-glsl-webgl2-native-quad-v2",
      curveInterpolation: "native_natural_cubic_f32_truncate_v1",
      reportedByClient: true
    } };
  } finally {
    frames.forEach((f) => gl.deleteFramebuffer(f));
    textures.forEach((t) => gl.deleteTexture(t));
    programs.forEach((p) => gl.deleteProgram(p));
    shaders.forEach((s) => gl.deleteShader(s));
    gl.deleteBuffer(buffer);
    gl.deleteBuffer(uvBuffer);
    gl.getExtension("WEBGL_lose_context")?.loseContext();
  }
}
export {
  nativeCompatibleStatistics,
  renderOfficialColour
};
