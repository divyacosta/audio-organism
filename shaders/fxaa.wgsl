// FXAA (fast approximate anti-aliasing) as a last pass over the finished picture: it finds edges by brightness and blends along them.
// Cheap (5 to 9 texture reads per pixel, no geometry) and it also softens edges that came from shading, not only silhouettes.
struct F { texel: vec2<f32>, pad: vec2<f32> };
@group(0) @binding(0) var src: texture_2d<f32>;
@group(0) @binding(1) var samp: sampler;
@group(0) @binding(2) var<uniform> f: F;

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

@fragment
fn fs(in: VOut) -> @location(0) vec4<f32> {
  let uv = in.uv;
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
