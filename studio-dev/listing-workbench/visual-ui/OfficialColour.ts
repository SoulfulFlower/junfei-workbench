// Original GLSL files are loaded intact from the verified bundled catalog.
import { nativeCompatibleCurves } from "./NativeCurves.js";
type Point = { x: number; y: number };
export type Parameter = { key: string; name: string; type: string; min?: number; max?: number; default: unknown };
export type Filter = { index: string; name: string; fs: string; params: Parameter[]; input2?: string; input3?: string };
export type ColourResources = { version: string; config: { filters: Filter[] }; shaders: Record<string, string>; sourceHashes: Record<string, string> };
export type ColourSettings = Record<string, Record<string, unknown>>;
export type ColourRenderOptions = { preserveOutsideSelection?: boolean };
// Original WASM uses an explicit UV buffer and this triangle-fan geometry.
// Preserve its attribute layout rather than computing an equivalent UV field.
const VERTEX = "precision highp float;attribute vec4 position;attribute vec4 textureUV;uniform mat4 transformMatrix;varying vec2 textureCoordinate;void main(){gl_Position=transformMatrix*vec4(position.xyz,1.0);textureCoordinate=textureUV.xy;}";

async function load(url: string) {
  const im = new Image(); im.src = url; await im.decode(); return im;
}
function pixels(im: HTMLImageElement) {
  const c = document.createElement("canvas"); c.width = im.naturalWidth; c.height = im.naturalHeight;
  const x = c.getContext("2d")!; x.drawImage(im, 0, 0); return x.getImageData(0, 0, c.width, c.height);
}
function labLight(r: number, g: number, b: number) {
  const a = [r, g, b].map(v => { v /= 255; return v > .04045 ? Math.pow((v + .055) / 1.055, 2.4) : v / 12.92; });
  const y = a[0] * .2126 + a[1] * .7152 + a[2] * .0722;
  return y > .008856 ? 116 * Math.cbrt(y) - 16 : 903.3 * y;
}
export function nativeCompatibleStatistics(src: ImageData, mask: ImageData) {
  const sum = [0, 0, 0], lights: number[] = []; let n = 0, covered = 0;
  // Original calcMainColor: independent ceil(5%) steps, positive red mask.
  const stepX = Math.max(1, Math.ceil(src.width * .05)), stepY = Math.max(1, Math.ceil(src.height * .05));
  for (let y = 0; y < src.height; y += stepY) for (let x = 0; x < src.width; x += stepX) {
    const k = (y * src.width + x) * 4;
    if (mask.data[k] <= 0) continue;
    for (let j = 0; j < 3; j++) sum[j] += src.data[k + j]; n++;
  }
  // Original calcLMaxMinPercent: every positive RGB-average mask pixel and
  // linearly interpolated 5th/95th percentiles, including soft selection edges.
  for (let k = 0; k < mask.data.length; k += 4) {
    if (mask.data[k] + mask.data[k + 1] + mask.data[k + 2] <= 0) continue;
    lights.push(Math.max(0, Math.min(100, labLight(src.data[k], src.data[k + 1], src.data[k + 2])))); covered++;
  }
  // Explicit local quality gate; this is not claimed as an original LinkFox rule.
  if (n < 10 || covered < Math.max(10, src.width * src.height * .005)) throw new Error("商品选区覆盖不足，不能据此计算换色主色");
  lights.sort((a, b) => a - b);
  const percentile = (ratio: number) => {
    const position = (lights.length - 1) * ratio, lower = Math.floor(position), upper = Math.min(lights.length - 1, lower + 1);
    return lights[lower] * (1 - (position - lower)) + lights[upper] * (position - lower);
  };
  return { main: sum.map(v => v / n), low: percentile(.05), high: percentile(.95), samples: n,
    coveragePixels: covered, coverageFraction: covered / (src.width * src.height), sampling: "linkfox_grid_5percent_positive_mask_v1", coverageGate: "local_min10grid_and_0_5percent_pixels" };
}
function curveTexture(parameters: Record<string, unknown>) {
  const convert = (value: unknown): [number, number][] | undefined => {
    if (value === undefined || value === null) return undefined;
    if (!Array.isArray(value)) throw new Error("曲线控制点无效");
    return value.map((point: Point) => [point.x, point.y]);
  };
  return nativeCompatibleCurves({
    RGB: convert(parameters.RGBchannel), R: convert(parameters.Rchannel),
    G: convert(parameters.Gchannel), B: convert(parameters.Bchannel),
  }).rgba;
}
async function sha256(bytes: Uint8Array | Uint8ClampedArray) {
  const digest = await crypto.subtle.digest("SHA-256", new Uint8Array(bytes));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}
export async function renderOfficialColour(sourceUrl: string, maskUrl: string, target: string, resources: ColourResources, settings: ColourSettings = {}, options: ColourRenderOptions = {}) {
  const [sourceImage, maskImage] = await Promise.all([load(sourceUrl), load(maskUrl)]);
  const src = pixels(sourceImage), mask = pixels(maskImage);
  if (src.width !== mask.width || src.height !== mask.height) throw new Error("选区必须与原图尺寸一致");
  if (!/^#[0-9a-f]{6}$/i.test(target)) throw new Error("目标RGB颜色无效");
  const stats = nativeCompatibleStatistics(src, mask), canvas = document.createElement("canvas");
  canvas.width = src.width; canvas.height = src.height;
  const gl = canvas.getContext("webgl2", { premultipliedAlpha: false, preserveDrawingBuffer: true, alpha: true });
  if (!gl) throw new Error("当前浏览器无法执行官方WebGL着色器；未用简化算法冒充");
  const shaders: WebGLShader[] = [], programs = new Map<string, WebGLProgram>(), textures: WebGLTexture[] = [], frames: WebGLFramebuffer[] = [];
  const compile = (type: number, text: string) => {
    const s = gl.createShader(type)!; shaders.push(s); gl.shaderSource(s, text); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || "着色器编译失败"); return s;
  };
  const texture = (image: HTMLImageElement | null, width = src.width, height = src.height, raw?: Uint8Array) => {
    const t = gl.createTexture()!; textures.push(t); gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    if (image) {
      // Match handleinterfaces-DjND9wxo.js: decode through a 2D canvas, flip
      // there, then upload. Direct JPEG DOM-image upload can quantize RGB
      // differently from this path even with UNPACK_FLIP_Y_WEBGL enabled.
      const upload = document.createElement("canvas"); upload.width = image.naturalWidth; upload.height = image.naturalHeight;
      const context = upload.getContext("2d")!; context.translate(0, upload.height); context.scale(1, -1); context.drawImage(image, 0, 0);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, upload.width, upload.height, 0, gl.RGBA, gl.UNSIGNED_BYTE, upload);
    }
    else { gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, raw || null); }
    return t;
  };
  const buffer = gl.createBuffer()!; gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, 1, -1, -1, 1, -1, 1, 1]), gl.STATIC_DRAW);
  const uvBuffer = gl.createBuffer()!; gl.bindBuffer(gl.ARRAY_BUFFER, uvBuffer); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 1, 0, 0, 1, 0, 1, 1]), gl.STATIC_DRAW);
  try {
    const vertex = compile(gl.VERTEX_SHADER, VERTEX), original = texture(sourceImage), originalMask = texture(maskImage);
    const cache = new Map<string, WebGLTexture>(); let current = originalMask;
    const passes: { index: string; fs: string; params: Record<string, unknown> }[] = [];
    for (const filter of resources.config.filters) {
      const originalShader = resources.shaders[filter.fs]; if (!originalShader) throw new Error("缺少原始着色器 " + filter.fs);
      let program = programs.get(filter.fs);
      if (!program) {
        program = gl.createProgram()!; gl.attachShader(program, vertex);
        gl.attachShader(program, compile(gl.FRAGMENT_SHADER, "precision highp float;\n" + originalShader)); gl.linkProgram(program);
        if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || "着色器链接失败");
        programs.set(filter.fs, program);
      }
      gl.useProgram(program);
      for (const [name, source] of [["position", buffer], ["textureUV", uvBuffer]] as const) {
        const loc = gl.getAttribLocation(program, name); gl.bindBuffer(gl.ARRAY_BUFFER, source); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 8, 0);
      }
      gl.uniformMatrix4fv(gl.getUniformLocation(program, "transformMatrix"), false, new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]));
      const values: Record<string, unknown> = Object.fromEntries(filter.params.map(p => [p.key, p.default]));
      Object.assign(values, settings[filter.index] || {});
      if (filter.index === "1" || filter.index === "4") {
        if (settings[filter.index]?.clothingMainColor !== undefined) {
          values.clothingMainColor = settings[filter.index].clothingMainColor;
          values.bSetMainColor = settings[filter.index]?.bSetMainColor ?? 1;
        } else if (settings[filter.index]?.bSetMainColor === undefined) {
          values.bSetMainColor = 1; values.clothingMainColor = stats.main;
        }
      }
      if (filter.index === "4") {
        values.targetColor = [1, 3, 5].map(i => parseInt(target.slice(i, i + 2), 16));
        values.enable = settings[filter.index]?.enable ?? 1;
        values.L_min_orig = settings[filter.index]?.L_min_orig ?? stats.low;
        values.L_max_orig = settings[filter.index]?.L_max_orig ?? (stats.high > stats.low ? stats.high : stats.low + 1);
      }
      for (const parameter of filter.params) {
        const value = values[parameter.key];
        if (typeof value === "number" && (!Number.isFinite(value) || (parameter.min !== undefined && value < parameter.min) || (parameter.max !== undefined && value > parameter.max))) throw new Error(parameter.name + "超出原始参数范围");
        if (parameter.type === "xyz" && (!Array.isArray(value) || value.length !== 3 || value.some(v => !Number.isFinite(v) || v < (parameter.min ?? 0) || v > (parameter.max ?? 255)))) throw new Error(parameter.name + "必须为有效RGB数组");
      }
      let second = filter.input2 ? cache.get(filter.input2) : original;
      const third = filter.input3 ? cache.get(filter.input3) : originalMask;
      if (filter.fs === "colorCurves.fs") second = texture(null, 256, 3, curveTexture(values));
      const inputs = [current, second || original, third || originalMask];
      inputs.forEach((t, i) => { gl.activeTexture(gl.TEXTURE0 + i); gl.bindTexture(gl.TEXTURE_2D, t); gl.uniform1i(gl.getUniformLocation(program!, "input" + (i + 1)), i); });
      values.width = src.width; values.height = src.height; values.channelForA = 0;
      const count = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS) as number;
      for (let i = 0; i < count; i++) {
        const u = gl.getActiveUniform(program, i)!; const value = values[u.name]; if (value === undefined || u.type === gl.SAMPLER_2D) continue;
        const location = gl.getUniformLocation(program, u.name);
        if (u.type === gl.FLOAT_VEC3) gl.uniform3fv(location, value as number[]);
        else if (u.type === gl.FLOAT_VEC2) gl.uniform2fv(location, value as number[]);
        else if (u.type === gl.INT || u.type === gl.BOOL) gl.uniform1i(location, Number(value));
        else if (u.type === gl.FLOAT) gl.uniform1f(location, Number(value));
      }
      const out = texture(null), frame = gl.createFramebuffer()!; frames.push(frame);
      gl.bindFramebuffer(gl.FRAMEBUFFER, frame); gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, out, 0);
      if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) throw new Error("官方滤镜帧缓冲不可用");
      // Allocating the output texture changes the active unit's binding.
      // Rebind inputs so the FBO is never sampled from itself.
      inputs.forEach((t, i) => { gl.activeTexture(gl.TEXTURE0 + i); gl.bindTexture(gl.TEXTURE_2D, t); });
      gl.viewport(0, 0, src.width, src.height); gl.drawArrays(gl.TRIANGLE_FAN, 0, 4);
      const error = gl.getError(); if (error !== gl.NO_ERROR) throw new Error("官方滤镜执行失败 " + error);
      current = out; cache.set(filter.index, out); passes.push({ index: filter.index, fs: filter.fs, params: values });
    }
    const raw = new Uint8Array(src.width * src.height * 4); gl.readPixels(0, 0, src.width, src.height, gl.RGBA, gl.UNSIGNED_BYTE, raw);
    if (gl.getError() !== gl.NO_ERROR) throw new Error("官方滤镜结果读取失败");
    const data = new Uint8ClampedArray(raw.length), nativeData = new Uint8ClampedArray(raw.length); let outside = 0, nativeOutsideChangedPixels = 0;
    for (let y = 0; y < src.height; y++) for (let x = 0; x < src.width; x++) {
      const k = (y * src.width + x) * 4, from = ((src.height - y - 1) * src.width + x) * 4;
      for (let j = 0; j < 4; j++) nativeData[k + j] = raw[from + j];
      if (mask.data[k] === 0 && [0, 1, 2, 3].some(j => nativeData[k + j] !== src.data[k + j])) nativeOutsideChangedPixels++;
      const restore = options.preserveOutsideSelection === true && mask.data[k] === 0;
      for (let j = 0; j < 4; j++) data[k + j] = restore ? src.data[k + j] : raw[from + j];
      data[k + 3] = src.data[k + 3]; if (restore) outside++;
    }
    const output = document.createElement("canvas"); output.width = src.width; output.height = src.height;
    output.getContext("2d")!.putImageData(new ImageData(data, src.width, src.height), 0, 0);
    const blob = await new Promise<Blob>((resolve, reject) => output.toBlob(b => b ? resolve(b) : reject(new Error("保存官方换色结果失败")), "image/png"));
    const [nativeOutputSHA, outputSHA, outputPngSHA] = await Promise.all([sha256(nativeData), sha256(data), blob.arrayBuffer().then(bytes => sha256(new Uint8Array(bytes)))]);
    return { blob, receipt: { version: resources.version, sourceHashes: resources.sourceHashes, passes, statistics: stats, outsideRestoredPixels: outside,
      outsideSelectionPolicy: options.preserveOutsideSelection ? "restore_source_explicit_quality_option" : "native_filter_output",
      boundaryPolicy: options.preserveOutsideSelection ? "preserve_outside_selection_source_rgba" : "native_filter_output",
      nativeOutsideChangedPixels, nativeOutputSHA, outputSHA, outputPngSHA, hashPixelOrder: "rgba8_top_to_bottom",
      colourAnchor: { source: settings["4"]?.clothingMainColor !== undefined ? "explicit_sku_override" : "native_statistics", main: passes.find(pass => pass.index === "4")?.params.clothingMainColor,
        low: passes.find(pass => pass.index === "4")?.params.L_min_orig, high: passes.find(pass => pass.index === "4")?.params.L_max_orig },
      renderer: "original-glsl-webgl2-native-quad-v2", curveInterpolation: "native_natural_cubic_f32_truncate_v1", reportedByClient: true } };
  } finally {
    frames.forEach(f => gl.deleteFramebuffer(f)); textures.forEach(t => gl.deleteTexture(t)); programs.forEach(p => gl.deleteProgram(p)); shaders.forEach(s => gl.deleteShader(s)); gl.deleteBuffer(buffer); gl.deleteBuffer(uvBuffer);
    gl.getExtension("WEBGL_lose_context")?.loseContext();
  }
}
