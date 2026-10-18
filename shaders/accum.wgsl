// Motion blur by temporal accumulation: the new frame is blended with the (already blurred) previous one, in HDR, so bright
// moving shapes leave a smooth trail. k = how much of the previous frame stays (0 = no blur), computed from the frame time on the CPU.
struct A { k: f32, pad0: f32, pad1: f32, pad2: f32 };
@group(0) @binding(0) var cur: texture_2d<f32>;
@group(0) @binding(1) var hist: texture_2d<f32>;
@group(0) @binding(2) var samp: sampler;
@group(0) @binding(3) var<uniform> a: A;

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
  let c = textureSample(cur, samp, in.uv);
  let h = textureSample(hist, samp, in.uv);
  return mix(c, h, clamp(a.k, 0.0, 0.97));
}
