// Final composite: scene + bloom, soft clip, then the white flash as a Difference layer.
struct C { bloom: f32, flash: f32, exposure: f32, levels: f32, bg: vec4<f32>, misc: vec4<f32>, duoA: vec4<f32>, duoB: vec4<f32> };      // duoA / duoB.rgb = the two colours of the duotone, duoA.w = duotone on       // misc.x = VHS / CRT, misc.y = time      // levels = bloom levels rendered, 0..4      // bg.rgb = background colour, bg.w = fade/gain factor
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
  let uv = in.uv;
  let sc4 = textureSample(scene, samp, uv);
  var base = sc4.rgb;
  if (c.misc.z > 0.0) {                                             // sharpening: unsharp mask on the HDR picture (undoes the softness of a lower render scale)
    let tx = 1.0 / vec2<f32>(textureDimensions(scene));
    let nb = 0.25 * (textureSample(scene, samp, uv + vec2<f32>(tx.x, 0.0)).rgb + textureSample(scene, samp, uv - vec2<f32>(tx.x, 0.0)).rgb
                   + textureSample(scene, samp, uv + vec2<f32>(0.0, tx.y)).rgb + textureSample(scene, samp, uv - vec2<f32>(0.0, tx.y)).rgb);
    base = max(base + (base - nb) * c.misc.z, vec3<f32>(0.0));
  }
  let bl = textureSample(b1, samp, in.uv).rgb * 0.16 * step(0.5, c.levels) + textureSample(b2, samp, in.uv).rgb * 0.20 * step(1.5, c.levels)
         + textureSample(b3, samp, in.uv).rgb * 0.24 * step(2.5, c.levels) + textureSample(b4, samp, in.uv).rgb * 0.28 * step(3.5, c.levels);
  var col = base + bl * c.bloom;
  col = vec3<f32>(1.0) - exp(-col * c.exposure);                 // soft clip, zero stays pure black
  col = min(col + (1.0 - clamp(sc4.a, 0.0, 1.0)) * c.bg.rgb * c.bg.w, vec3<f32>(1.0));        // background behind whatever is not covered
  if (c.duoA.w > 0.5) {                                             // DUOTOM: the whole picture in two colours, by brightness
    // The brightness comes from the HDR scene itself, before exposure and bloom, so the glow slider (which brightens everything) cannot flatten
    // it into a single colour. A little local contrast (scene brightness against its own blur) keeps the detail when the frame is bright.
    let w = vec3<f32>(0.30, 0.59, 0.11);
    let lumH = dot(base, w) * (c.bg.w + 1e-3) / (c.bg.w + 1e-3);
    let blurL = dot(textureSample(b3, samp, in.uv).rgb, w) * step(2.5, c.levels) + dot(base, w) * (1.0 - step(2.5, c.levels));
    let t = clamp(smoothstep(0.03, 0.90, lumH) + 0.7 * (lumH - blurL), 0.0, 1.0);
    col = mix(c.duoA.rgb, c.duoB.rgb, t);
    col = min(col + (1.0 - clamp(sc4.a, 0.0, 1.0)) * c.duoA.rgb * 0.0, vec3<f32>(1.0));
  }
  col = abs(col - vec3<f32>(clamp(c.flash, 0.0, 1.0)));          // white flash = Difference layer over the image
  return vec4<f32>(col, 1.0);
}
