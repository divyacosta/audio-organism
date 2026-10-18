// Final composite: scene + bloom, soft clip, then the white flash as a Difference layer.
struct C { bloom: f32, flash: f32, exposure: f32, levels: f32, bg: vec4<f32> };      // levels = bloom levels rendered, 0..4      // bg.rgb = background colour, bg.w = fade/gain factor
@group(0) @binding(0) var scene: texture_2d<f32>;
@group(0) @binding(1) var b1: texture_2d<f32>;
@group(0) @binding(2) var b2: texture_2d<f32>;
@group(0) @binding(3) var b3: texture_2d<f32>;
@group(0) @binding(4) var b4: texture_2d<f32>;
@group(0) @binding(5) var samp: sampler;
@group(0) @binding(6) var<uniform> c: C;

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
  let sc4 = textureSample(scene, samp, in.uv);
  let base = sc4.rgb;
  let bl = textureSample(b1, samp, in.uv).rgb * 0.16 * step(0.5, c.levels) + textureSample(b2, samp, in.uv).rgb * 0.20 * step(1.5, c.levels)
         + textureSample(b3, samp, in.uv).rgb * 0.24 * step(2.5, c.levels) + textureSample(b4, samp, in.uv).rgb * 0.28 * step(3.5, c.levels);
  var col = base + bl * c.bloom;
  col = vec3<f32>(1.0) - exp(-col * c.exposure);                 // soft clip, zero stays pure black
  col = min(col + (1.0 - clamp(sc4.a, 0.0, 1.0)) * c.bg.rgb * c.bg.w, vec3<f32>(1.0));        // background behind whatever is not covered
  col = abs(col - vec3<f32>(clamp(c.flash, 0.0, 1.0)));          // white flash = Difference layer over the image
  return vec4<f32>(col, 1.0);
}
