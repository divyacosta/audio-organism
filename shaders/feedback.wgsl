// Feedback (rastro): the previous picture comes back into the new one, a little zoomed, turned, shifted and with its hue rotated, and fades by
// `decay`. Bright new shapes win over the old (max), so the trails never pile up into white. decay = 0 only copies the new frame.
struct F { decay: f32, zoom: f32, rot: f32, aspect: f32, drift: vec2<f32>, hue: f32, blur: f32 };
@group(0) @binding(0) var cur: texture_2d<f32>;
@group(0) @binding(1) var hist: texture_2d<f32>;
@group(0) @binding(2) var samp: sampler;
@group(0) @binding(3) var<uniform> f: F;

struct VOut { @builtin(position) pos: vec4<f32>, @location(0) uv: vec2<f32> };

@vertex
fn vs(@builtin(vertex_index) i: u32) -> VOut {
  var q = array<vec2<f32>, 3>(vec2<f32>(-1.0, -1.0), vec2<f32>(3.0, -1.0), vec2<f32>(-1.0, 3.0));
  var o: VOut;
  o.pos = vec4<f32>(q[i], 0.0, 1.0);
  o.uv = vec2<f32>(q[i].x * 0.5 + 0.5, 0.5 - q[i].y * 0.5);
  return o;
}

fn hue_rot(c: vec3<f32>, a: f32) -> vec3<f32> {
  let k = vec3<f32>(0.57735);
  let ca = cos(a);
  return c * ca + cross(k, c) * sin(a) + k * dot(k, c) * (1.0 - ca);
}

@fragment
fn fs(in: VOut) -> @location(0) vec4<f32> {
  let c = textureSample(cur, samp, in.uv);
  if (f.decay <= 0.001) { return c; }
  var p = in.uv - vec2<f32>(0.5);
  p.x = p.x * f.aspect;
  let cs = cos(f.rot);
  let sn = sin(f.rot);
  p = vec2<f32>(p.x * cs - p.y * sn, p.x * sn + p.y * cs) / f.zoom;
  p.x = p.x / f.aspect;
  let q = p + vec2<f32>(0.5) + f.drift;
  let inside = step(0.0, q.x) * step(q.x, 1.0) * step(0.0, q.y) * step(q.y, 1.0);
  var h = textureSample(hist, samp, q);
  if (f.blur > 0.01) {                                              // the old picture spreads while it fades: 5 taps, wider with the blur
    let r = f.blur * 0.006;
    h = (h + textureSample(hist, samp, q + vec2<f32>(r / f.aspect, 0.0)) + textureSample(hist, samp, q - vec2<f32>(r / f.aspect, 0.0))
           + textureSample(hist, samp, q + vec2<f32>(0.0, r)) + textureSample(hist, samp, q - vec2<f32>(0.0, r))) * 0.2;
  }
  var rgb = h.rgb;
  if (abs(f.hue) > 1e-5) { rgb = hue_rot(rgb, f.hue); }
  let prev = vec4<f32>(max(rgb, vec3<f32>(0.0)), h.a) * f.decay * inside;
  return vec4<f32>(max(c.rgb, prev.rgb), max(c.a, prev.a));
}
