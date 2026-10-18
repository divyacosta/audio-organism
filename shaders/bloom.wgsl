// Bloom chain passes: fs_down (4-tap box + threshold) and fs_blur (separable gaussian).
struct P { step: vec2<f32>, thresh: f32, pad: f32 };
@group(0) @binding(0) var tex: texture_2d<f32>;
@group(0) @binding(1) var samp: sampler;
@group(0) @binding(2) var<uniform> p: P;

struct VOut { @builtin(position) pos: vec4<f32>, @location(0) uv: vec2<f32> };

@vertex
fn vs(@builtin(vertex_index) i: u32) -> VOut {
  var q = array<vec2<f32>, 3>(vec2<f32>(-1.0, -1.0), vec2<f32>(3.0, -1.0), vec2<f32>(-1.0, 3.0));
  var o: VOut;
  o.pos = vec4<f32>(q[i], 0.0, 1.0);
  o.uv = vec2<f32>(q[i].x * 0.5 + 0.5, 0.5 - q[i].y * 0.5);     // texture space: v = 0 at the top
  return o;
}

@fragment
fn fs_down(in: VOut) -> @location(0) vec4<f32> {
  var s = textureSample(tex, samp, in.uv + p.step * vec2<f32>(-0.5, -0.5)).rgb
        + textureSample(tex, samp, in.uv + p.step * vec2<f32>(0.5, -0.5)).rgb
        + textureSample(tex, samp, in.uv + p.step * vec2<f32>(-0.5, 0.5)).rgb
        + textureSample(tex, samp, in.uv + p.step * vec2<f32>(0.5, 0.5)).rgb;
  s = max(s * 0.25 - vec3<f32>(p.thresh), vec3<f32>(0.0));
  return vec4<f32>(s, 1.0);
}

@fragment
fn fs_blur(in: VOut) -> @location(0) vec4<f32> {
  var s = textureSample(tex, samp, in.uv).rgb * 0.227027;
  s += (textureSample(tex, samp, in.uv + p.step * 1.3846).rgb + textureSample(tex, samp, in.uv - p.step * 1.3846).rgb) * 0.3162162;
  s += (textureSample(tex, samp, in.uv + p.step * 3.2308).rgb + textureSample(tex, samp, in.uv - p.step * 3.2308).rgb) * 0.0702703;
  return vec4<f32>(s, 1.0);
}
