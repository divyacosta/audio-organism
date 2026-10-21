// Final composite: scene + bloom, soft clip, then the white flash as a Difference layer.
struct C { bloom: f32, flash: f32, exposure: f32, levels: f32, bg: vec4<f32>, misc: vec4<f32>, duoA: vec4<f32>, duoB: vec4<f32>,
           lgt: vec4<f32>, lca: vec4<f32>, lcb: vec4<f32>, lau: vec4<f32> };      // background lights: lgt = style, intensity, speed, blank scene; lca / lcb = colours (+ bass / kick); lau = mid, high, beat, aspect      // duoA / duoB.rgb = the two colours of the duotone, duoA.w = duotone on       // misc.x = VHS / CRT, misc.y = time      // levels = bloom levels rendered, 0..4      // bg.rgb = background colour, bg.w = fade/gain factor
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

fn hash2(p: vec2<f32>) -> f32 { return fract(sin(dot(p, vec2<f32>(127.1, 311.7))) * 43758.5453); }

// The background lights: soft coloured light behind the picture, moving with time and answering the music. 0 none, 1 aurora, 2 beams, 3 pulses.
fn lights(uv: vec2<f32>) -> vec3<f32> {
  let style = i32(c.lgt.x + 0.5);
  if (style <= 0) { return vec3<f32>(0.0); }
  let p = vec2<f32>((uv.x - 0.5) * 2.0 * c.lau.w, (0.5 - uv.y) * 2.0);
  let t = c.misc.y * c.lgt.z;
  let bass = c.lca.w;
  let kick = c.lcb.w;
  let mid = c.lau.x;
  let beat = c.lau.z;
  var v = 0.0;
  var m = 0.0;
  if (style == 1) {
    let w1 = sin(p.x * 1.6 + t * 0.55 + sin(p.y * 1.3 - t * 0.35) * 1.4);
    let w2 = sin(p.x * 2.9 - t * 0.4 + p.y * 1.1 + sin(t * 0.21) * 2.0);
    let band = smoothstep(0.0, 1.0, 0.5 + 0.5 * w1) * (0.5 + 0.5 * w2);
    let fall = exp(-pow(p.y - 0.25 * w1, 2.0) * 0.8);
    v = band * fall * (0.55 + 0.9 * bass + 0.5 * kick);
    m = 0.5 + 0.5 * sin(p.y * 1.4 + t * 0.3 + w2);
  } else if (style == 2) {
    let r = length(p);
    let a = atan2(p.y, p.x);
    let beam = pow(max(0.0, sin(a * 7.0 + t * 0.8 + sin(t * 0.3) * 2.0)), 6.0 + 10.0 * (1.0 - clamp(mid, 0.0, 1.0)));
    let beam2 = pow(max(0.0, sin(a * 10.0 - t * 0.6)), 10.0);
    v = (beam + 0.6 * beam2) * exp(-r * 0.55) * (0.5 + 1.2 * mid + 0.9 * kick);
    m = 0.5 + 0.5 * sin(a * 2.0 + t * 0.4);
  } else {
    let r = length(p);
    var acc = 0.0;
    for (var k = 0; k < 3; k = k + 1) {
      let ph = fract(beat * 0.5 + f32(k) * 0.3333);
      acc = acc + exp(-pow((r - ph * 3.0) * 5.0, 2.0)) * (1.0 - ph);
    }
    v = acc * (0.6 + 1.2 * kick + 0.4 * bass) + exp(-r * r * 2.5) * kick * 0.8;
    m = clamp(r * 0.4, 0.0, 1.0);
  }
  let colr = mix(c.lca.rgb, c.lcb.rgb, clamp(m, 0.0, 1.0));
  let g = (hash2(uv * 1000.0 + vec2<f32>(t, 0.0)) - 0.5) * 0.012;                     // a little grain keeps the gradients from banding
  return max(colr * v * c.lgt.y + vec3<f32>(g * step(0.001, v)), vec3<f32>(0.0));
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
  let lmask = select(1.0 - clamp(sc4.a, 0.0, 1.0), 1.0, c.lgt.w > 0.5);                       // lights only where the picture does not cover (all of it in a scene with nothing)
  col = min(col + lights(uv) * lmask, vec3<f32>(1.0));
  if (c.duoA.w > 0.5) {                                             // DUOTOM: the whole picture in two colours, by brightness
    // The brightness comes from the HDR scene itself, before exposure and bloom, so the glow slider (which brightens everything) cannot flatten
    // it into a single colour. A little local contrast (scene brightness against its own blur) keeps the detail when the frame is bright.
    let w = vec3<f32>(0.30, 0.59, 0.11);
    let lumH = dot(base, w) * (c.bg.w + 1e-3) / (c.bg.w + 1e-3);
    let blurL = dot(textureSample(b3, samp, in.uv).rgb, w) * step(2.5, c.levels) + dot(base, w) * (1.0 - step(2.5, c.levels));
    let t = clamp((clamp(smoothstep(0.03, 0.90, lumH) + 0.7 * (lumH - blurL), 0.0, 1.0) - 0.5) * c.misc.w + 0.5, 0.0, 1.0);      // misc.w: contrast of the two colours
    col = mix(c.duoA.rgb, c.duoB.rgb, t);
    col = min(col + (1.0 - clamp(sc4.a, 0.0, 1.0)) * c.duoA.rgb * 0.0, vec3<f32>(1.0));
  }
  col = abs(col - vec3<f32>(clamp(c.flash, 0.0, 1.0)));          // white flash = Difference layer over the image
  return vec4<f32>(col, 1.0);
}
