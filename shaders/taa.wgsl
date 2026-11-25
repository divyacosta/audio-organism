// Temporal anti-aliasing: the scene is ray marched with a different sub-pixel offset every frame (see neon3d.wgsl), and each new frame is blended
// with the history after clamping the history to the colours around the pixel (so what changed does not leave a ghost). Over a few frames the
// edges get the quality of many samples per pixel. w = how much of the history stays (0 right after a cut).
struct T { w: f32, pad0: f32, pad1: f32, pad2: f32 };
@group(0) @binding(0) var cur: texture_2d<f32>;
@group(0) @binding(1) var hist: texture_2d<f32>;
@group(0) @binding(2) var samp: sampler;
@group(0) @binding(3) var<uniform> t: T;

struct VOut { @builtin(position) pos: vec4<f32>, @location(0) uv: vec2<f32> };

@vertex
fn vs(@builtin(vertex_index) i: u32) -> VOut {
  var q = array<vec2<f32>, 3>(vec2<f32>(-1.0, -1.0), vec2<f32>(3.0, -1.0), vec2<f32>(-1.0, 3.0));
  var o: VOut;
  o.pos = vec4<f32>(q[i], 0.0, 1.0);
  o.uv = vec2<f32>(q[i].x * 0.5 + 0.5, 0.5 - q[i].y * 0.5);
  return o;
}

@fragment
fn fs(in: VOut) -> @location(0) vec4<f32> {
  let texel = 1.0 / vec2<f32>(textureDimensions(cur));
  let c = textureSample(cur, samp, in.uv);
  var mn = c;
  var mx = c;
  for (var y = -1; y <= 1; y = y + 1) {
    for (var x = -1; x <= 1; x = x + 1) {
      let s = textureSample(cur, samp, in.uv + vec2<f32>(f32(x), f32(y)) * texel);
      mn = min(mn, s);
      mx = max(mx, s);
    }
  }
  let h = clamp(textureSample(hist, samp, in.uv), mn, mx);
  return mix(c, h, clamp(t.w, 0.0, 0.95));
}
