// FXAA (fast approximate anti-aliasing) as a last pass over the finished picture: it finds edges by brightness and blends along them.
// Cheap (5 to 9 texture reads per pixel, no geometry) and it also softens edges that came from shading, not only silhouettes.
// fin0 = brightness, contrast, saturation, gamma; fin1 = warmth (-1 cool .. 1 warm), vignette, dither on, mirror (0 none, 1 horizontal, 2 vertical, 3 both); fin2 = zoom, target aspect (0 = the window's), style (0 normal, 1 flat, 2 lines, 3 pixels), pixel size in screen pixels
// ov0 = the box of the Sobreposição (x, y, width, height, 0..1 from the top left); ov1.x = its opacity (0: none)
struct F { texel: vec2<f32>, pad: vec2<f32>, fin0: vec4<f32>, fin1: vec4<f32>, fin2: vec4<f32>, ov0: vec4<f32>, ov1: vec4<f32> };
@group(0) @binding(0) var src: texture_2d<f32>;
@group(0) @binding(1) var samp: sampler;
@group(0) @binding(2) var<uniform> f: F;
@group(0) @binding(3) var ovt: texture_2d<f32>;

struct VOut { @builtin(position) pos: vec4<f32>, @location(0) uv: vec2<f32> };

@vertex
fn vs(@builtin(vertex_index) i: u32) -> VOut {
  var q = array<vec2<f32>, 3>(vec2<f32>(-1.0, -1.0), vec2<f32>(3.0, -1.0), vec2<f32>(-1.0, 3.0));
  var o: VOut;
  o.pos = vec4<f32>(q[i], 0.0, 1.0);
  o.uv = vec2<f32>(q[i].x * 0.5 + 0.5, 0.5 - q[i].y * 0.5);
  return o;
}

fn lum(c: vec3<f32>) -> f32 { return dot(c, vec3<f32>(0.299, 0.587, 0.114)); }

fn aa(uv: vec2<f32>) -> vec4<f32> {
  let t = f.texel;
  let cM = textureSample(src, samp, uv).rgb;
  if (f.pad.x < 0.5) { return vec4<f32>(cM, 1.0); }               // filter off: this pass only copies (used for the preview thumbnail)
  let lNW = lum(textureSample(src, samp, uv + vec2<f32>(-t.x, -t.y)).rgb);
  let lNE = lum(textureSample(src, samp, uv + vec2<f32>(t.x, -t.y)).rgb);
  let lSW = lum(textureSample(src, samp, uv + vec2<f32>(-t.x, t.y)).rgb);
  let lSE = lum(textureSample(src, samp, uv + vec2<f32>(t.x, t.y)).rgb);
  let lM = lum(cM);
  let lMin = min(lM, min(min(lNW, lNE), min(lSW, lSE)));
  let lMax = max(lM, max(max(lNW, lNE), max(lSW, lSE)));
  if (lMax - lMin < max(0.03, lMax * 0.12)) { return vec4<f32>(cM, 1.0); }       // flat area: leave it alone
  var dir = vec2<f32>(-((lNW + lNE) - (lSW + lSE)), (lNW + lSW) - (lNE + lSE));
  let reduce = max((lNW + lNE + lSW + lSE) * 0.25 * 0.125, 1.0 / 128.0);
  let rcp = 1.0 / (min(abs(dir.x), abs(dir.y)) + reduce);
  dir = clamp(dir * rcp, vec2<f32>(-8.0), vec2<f32>(8.0)) * t;
  let a = 0.5 * (textureSample(src, samp, uv + dir * (1.0 / 3.0 - 0.5)).rgb + textureSample(src, samp, uv + dir * (2.0 / 3.0 - 0.5)).rgb);
  let b = a * 0.5 + 0.25 * (textureSample(src, samp, uv + dir * -0.5).rgb + textureSample(src, samp, uv + dir * 0.5).rgb);
  let lB = lum(b);
  if (lB < lMin || lB > lMax) { return vec4<f32>(a, 1.0); }
  return vec4<f32>(b, 1.0);
}

fn hash2(p: vec2<f32>) -> f32 { return fract(sin(dot(p, vec2<f32>(127.1, 311.7))) * 43758.5453); }

@fragment
fn fs(in: VOut) -> @location(0) vec4<f32> {
  var uv = in.uv;
  let asp = f.texel.y / f.texel.x;                                  // the window's aspect
  var rect = vec2<f32>(1.0, 1.0);                                   // the part of the window the picture fills (bars outside it)
  if (f.fin2.y > 0.0) {
    if (f.fin2.y < asp) { rect.x = f.fin2.y / asp; } else { rect.y = asp / f.fin2.y; }
  }
  let q = (in.uv - vec2<f32>(0.5)) / rect;
  if (abs(q.x) > 0.5 || abs(q.y) > 0.5) { return vec4<f32>(0.0, 0.0, 0.0, 1.0); }
  let m = i32(f.fin1.w + 0.5);
  if (m == 1 || m == 3) { uv.x = 1.0 - uv.x; }
  if (m == 2 || m == 3) { uv.y = 1.0 - uv.y; }
  uv = (uv - vec2<f32>(0.5)) / max(f.fin2.x, 1.0) + vec2<f32>(0.5);
  let sty = i32(f.fin2.z + 0.5);
  if (sty == 3) {                                                   // pixels: every block of the screen takes the colour of its middle, and the colours are few
    let blk = max(f.fin2.w, 2.0) * f.texel;
    uv = (floor(uv / blk) + vec2<f32>(0.5)) * blk;
  }
  var col = aa(uv).rgb;
  if (sty == 1 || sty == 3) {                                       // flat: no soft gradients, a few levels of each colour (pixels use more)
    let lv = select(4.0, 6.0, sty == 3);
    let ll = max(max(col.r, col.g), col.b);
    col = floor(col / max(ll, 1e-3) * lv + 0.5) / lv * floor(ll * lv + 0.5) / lv;
    col = clamp(col * 1.1, vec3<f32>(0.0), vec3<f32>(1.0));
  }
  if (sty == 2) {                                                   // lines: only the edges of the picture, in their own colour, over black
    let t = f.texel * 1.5;
    let c0 = textureSample(src, samp, uv).rgb;
    let gx = lum(textureSample(src, samp, uv + vec2<f32>(t.x, 0.0)).rgb) - lum(textureSample(src, samp, uv - vec2<f32>(t.x, 0.0)).rgb);
    let gy = lum(textureSample(src, samp, uv + vec2<f32>(0.0, t.y)).rgb) - lum(textureSample(src, samp, uv - vec2<f32>(0.0, t.y)).rgb);
    let e = smoothstep(0.03, 0.16, sqrt(gx * gx + gy * gy));
    col = (c0 * 0.9 + vec3<f32>(0.10)) * e * 1.6;
  }
  let l = dot(col, vec3<f32>(0.2126, 0.7152, 0.0722));
  col = mix(vec3<f32>(l), col, f.fin0.z);
  col = (col - vec3<f32>(0.5)) * f.fin0.y + vec3<f32>(0.5);
  col = col * f.fin0.x;
  col = col * vec3<f32>(1.0 + 0.18 * f.fin1.x, 1.0 + 0.04 * f.fin1.x, 1.0 - 0.18 * f.fin1.x);
  col = pow(max(col, vec3<f32>(0.0)), vec3<f32>(1.0 / max(f.fin0.w, 0.1)));
  let r = length(q * 2.0) * 0.7071;                                 // 0 in the middle, 1 in the corners
  col = col * (1.0 - f.fin1.y * smoothstep(0.35, 1.05, r));
  col = col + vec3<f32>((hash2(in.uv / f.texel) - 0.5) * (1.5 / 255.0) * f.fin1.z);
  col = clamp(col, vec3<f32>(0.0), vec3<f32>(1.0));
  let ou = (in.uv - f.ov0.xy) / max(f.ov0.zw, vec2<f32>(1e-4));            // the Sobreposição goes over the finished picture: no style, no colour grade
  let oc = textureSampleLevel(ovt, samp, clamp(ou, vec2<f32>(0.0), vec2<f32>(1.0)), 0.0);
  let inside = select(0.0, 1.0, f.ov1.x > 0.0 && ou.x >= 0.0 && ou.x <= 1.0 && ou.y >= 0.0 && ou.y <= 1.0);
  col = mix(col, oc.rgb, oc.a * f.ov1.x * inside);
  return vec4<f32>(col, 1.0);
}
