// Final composite: scene + bloom, soft clip, then the white flash as a Difference layer.
struct C { bloom: f32, flash: f32, exposure: f32, levels: f32, bg: vec4<f32>, misc: vec4<f32>, duoA: vec4<f32>, duoB: vec4<f32>,
           lgt: vec4<f32>, lca: vec4<f32>, lcb: vec4<f32>, lau: vec4<f32>,
           fxa: vec4<f32>,
           bgl: array<vec4<f32>, 20> };      // fxa.x = tone mapping (0 soft clip, 1 filmic, 2 keeps the hue); bgl = the 4 background layers, 5 vec4 each: (kind 1 gradient / 2 lights, blend, opacity, 0), (type or style, intensity, speed, pulse), colour A, colour B + angle, colour C
// lgt.w = blank scene (nothing drawn); lca / lcb = the colours of the palette lights (+ bass / kick); lau = mid, high, beat, aspect; duoA / duoB.rgb = the two colours of the duotone, duoA.w = duotone on; misc.x = flash mode, misc.y = time; levels = bloom levels rendered, 0..4; bg.rgb = background colour, bg.w = fade / gain factor
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

// The background lights: soft coloured light behind the picture, moving with time and answering the music. 0 none, 1 aurora, 2 beams, 3 pulses, 4 stars, 5 bands.
fn lights(uv: vec2<f32>, style: i32, inten: f32, speed: f32, ca: vec3<f32>, cb: vec3<f32>) -> vec3<f32> {
  if (style <= 0) { return vec3<f32>(0.0); }
  let p = vec2<f32>((uv.x - 0.5) * 2.0 * c.lau.w, (0.5 - uv.y) * 2.0);
  let t = c.misc.y * speed;
  let bass = c.lca.w;
  let kick = c.lcb.w;
  if (style == 7) {
    // one laser beam across the screen: a white-hot thread, a coloured glow around it that thickens with the bass, and a hot point in the middle that
    // flashes on the kick; the beam turns slowly
    let ang = 0.75 + 0.35 * sin(t * 0.07) + 0.08 * sin(t * 0.31);
    let dir = vec2<f32>(cos(ang), sin(ang));
    let along = dot(p, dir);
    let d = abs(p.x * dir.y - p.y * dir.x);
    let w = 0.0035 * (1.0 + 1.5 * bass);
    let core = exp(-d * d / (w * w));
    let glow = 0.018 * (1.0 + bass) / (d + 0.018) * exp(-d * 2.5);
    let ends = smoothstep(2.4, 0.6, abs(along));
    let r = length(p);
    let hot = exp(-r * 7.0) * (0.8 + 2.2 * kick) + 0.012 / (r + 0.012) * (0.4 + kick);
    let flare = exp(-abs(p.y) * 160.0) * exp(-abs(p.x) * 2.5) * (0.3 + kick) * 0.6;   // a thin anamorphic streak through the hot point
    var col = ca * glow * ends * 1.6 + mix(cb, vec3<f32>(1.0, 0.95, 0.85), 0.7) * core * ends * 2.2;
    col = col + mix(ca, vec3<f32>(1.0, 0.9, 0.7), 0.6) * (hot + flare);
    return max(col * inten, vec3<f32>(0.0));
  }
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
  } else if (style == 4) {
    let g = p * 7.0 + vec2<f32>(0.0, t * 0.15);
    let id = floor(g);
    let f = fract(g) - 0.5;
    let h = hash2(id);
    let pos = (vec2<f32>(hash2(id + vec2<f32>(7.1, 1.7)), hash2(id + vec2<f32>(3.3, 9.2))) - 0.5) * 0.6;
    let d = length(f - pos);
    let tw = 0.5 + 0.5 * sin(t * (1.0 + h * 3.0) + h * 40.0);
    v = step(0.55, h) * exp(-d * d * 90.0) * (0.35 + tw) * (0.6 + 1.1 * c.lau.y + 0.8 * kick) * 2.2;
    m = h;
  } else if (style == 5) {
    let y = p.y * 2.6 - t * 0.35 - bass * 0.4;
    let s = 1.0 - smoothstep(0.0, 0.28, abs(fract(y) - 0.5));
    v = s * (0.35 + 0.9 * kick + 0.5 * mid);
    m = fract(y * 0.5);
  } else if (style == 6) {
    // lasers as a show projects them: three projectors throw fans of thin beams that open with the bass, flicker with the highs and light the haze between them
    let q = p * 0.5;
    let open = mix(0.12, 1.25, clamp(0.2 + 0.8 * bass + 0.4 * kick, 0.0, 1.0));
    var acc = 0.0;
    var acc3 = 0.0;
    for (var s = 0; s < 3; s = s + 1) {
      var o = vec2<f32>(-0.75 * c.lau.w / 1.78, -0.5);
      var dir = 0.75 + 0.25 * sin(t * 0.3);
      if (s == 1) { o = vec2<f32>(0.75 * c.lau.w / 1.78, -0.5); dir = 2.39 - 0.25 * sin(t * 0.3); }
      if (s == 2) { o = vec2<f32>(-0.9 * c.lau.w / 1.78, 0.45); dir = -0.35 + 0.3 * sin(t * 0.21); }
      let d = q - o;
      let r = length(d);
      var a = atan2(d.y, d.x) - dir;
      a = a - 6.2831853 * floor((a + 3.14159265) / 6.2831853);
      let fall = exp(-r * 0.9) * (1.0 + 0.6 / (r * 6.0 + 0.3));
      let op_ = select(open, open * 0.8, s == 2);
      var one = smoothstep(op_ * 0.5 + 0.01, op_ * 0.5 - 0.01, abs(a)) * 0.12 * fall;        // the sheet of light in the haze between the outer beams
      for (var i = 0; i < 7; i = i + 1) {
        let k = f32(i) / 6.0 - 0.5;
        let ai = k * op_ + 0.02 * sin(t * 3.0 + f32(i) * 1.7 + f32(s));
        let dd = abs(sin(a - ai)) * r;
        let w = 0.0016 + r * 0.0012;
        let core = w * w / (dd * dd + w * w);
        let fl = 0.75 + 0.25 * sin(t * 9.0 + f32(i * 7 + s * 3)) * c.lau.y;
        one = one + (core * 1.4 + 0.25 * w / (dd + w * 4.0)) * fall * step(0.0, cos(a - ai)) * fl;
      }
      one = one + 0.003 / (r + 0.003) * exp(-r * 5.0);
      acc = acc + one;
      if (s == 2) { acc3 = one; }
    }
    v = acc * (0.6 + 0.8 * kick);
    m = acc3 / max(acc, 1e-4);                                          // the third projector takes the second colour
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
  let colr = mix(ca, cb, clamp(m, 0.0, 1.0));
  let g = (hash2(uv * 1000.0 + vec2<f32>(t, 0.0)) - 0.5) * 0.012;                     // a little grain keeps the gradients from banding
  return max(colr * v * inten + vec3<f32>(g * step(0.001, v)), vec3<f32>(0.0));
}

// The coloured background: a solid colour or a gradient of up to three colours, behind everything the picture does not cover.
fn bgGradL(uv: vec2<f32>, typ: i32, ca: vec3<f32>, cb: vec3<f32>, cc: vec3<f32>, ang: f32, react: f32) -> vec3<f32> {
  if (typ == 0) { return ca * (1.0 + react * c.lcb.w); }
  let p = vec2<f32>((uv.x - 0.5) * 2.0 * c.lau.w, (0.5 - uv.y) * 2.0);
  var t = 0.0;
  if (typ == 2) {
    t = clamp(length(p) / (1.1 * max(c.lau.w, 1.0)), 0.0, 1.0);
  } else {
    let d = vec2<f32>(cos(ang), sin(ang));
    t = clamp(0.5 + dot(p, d) / (2.0 * (abs(d.x) * c.lau.w + abs(d.y))), 0.0, 1.0);
  }
  let col = mix(mix(ca, cb, smoothstep(0.0, 0.5, t)), cc, smoothstep(0.5, 1.0, t));
  return col * (1.0 + react * c.lcb.w);
}

// How a background layer is put over the ones below it: 0 normal, 1 add, 2 screen, 3 overlay; `op` is how much of it comes in
fn blendL(s: vec3<f32>, e: vec3<f32>, mode: i32, op: f32) -> vec3<f32> {
  var r = e;
  if (mode == 1) { r = s + e; }
  else if (mode == 2) { r = vec3<f32>(1.0) - (vec3<f32>(1.0) - min(s, vec3<f32>(1.0))) * (vec3<f32>(1.0) - min(e, vec3<f32>(1.0))); }
  else if (mode == 3) { r = select(vec3<f32>(1.0) - 2.0 * (vec3<f32>(1.0) - s) * (vec3<f32>(1.0) - e), 2.0 * s * e, s < vec3<f32>(0.5)); }
  return mix(s, max(r, vec3<f32>(0.0)), clamp(op, 0.0, 1.0));
}

fn tonemap(x: vec3<f32>, mode: i32) -> vec3<f32> {
  if (mode == 1) {                                                // filmic (ACES): contrasty highlights that roll off
    return clamp((x * (2.51 * x + vec3<f32>(0.03))) / (x * (2.43 * x + vec3<f32>(0.59)) + vec3<f32>(0.14)), vec3<f32>(0.0), vec3<f32>(1.0));
  }
  if (mode == 2) {                                                // keeps the hue: compresses the brightness, not each channel on its own
    let l = dot(x, vec3<f32>(0.2126, 0.7152, 0.0722));
    let t = l * (1.0 + l / 6.0) / (1.0 + l);
    return clamp(x * (t / max(l, 1e-4)), vec3<f32>(0.0), vec3<f32>(1.0));
  }
  return vec3<f32>(1.0) - exp(-x);                                // the original soft clip, zero stays pure black
}

@fragment
fn fs(in: VOut) -> @location(0) vec4<f32> {
  let uv = in.uv;
  let sc4 = textureSample(scene, samp, uv);
  var base = sc4.rgb;
  let bl = textureSample(b1, samp, in.uv).rgb * 0.16 * step(0.5, c.levels) + textureSample(b2, samp, in.uv).rgb * 0.20 * step(1.5, c.levels)
         + textureSample(b3, samp, in.uv).rgb * 0.24 * step(2.5, c.levels) + textureSample(b4, samp, in.uv).rgb * 0.28 * step(3.5, c.levels);
  var col = base + bl * c.bloom;
  col = tonemap(col * c.exposure, i32(c.fxa.x + 0.5));
  let blank = c.lgt.w > 0.5;
  col = min(col + (1.0 - clamp(sc4.a, 0.0, 1.0)) * c.bg.rgb * c.bg.w, vec3<f32>(1.0));        // the base of the background (the palette's, or black) behind whatever is not covered
  var stack = vec3<f32>(0.0);                                                                 // the background layers, from the bottom to the top
  for (var i = 0; i < 4; i = i + 1) {
    let v0 = c.bgl[i * 5];
    if (v0.x > 0.5) {
      let v1 = c.bgl[i * 5 + 1];
      var lc = vec3<f32>(0.0);
      if (v0.x < 1.5) { lc = bgGradL(uv, i32(v1.x + 0.5), c.bgl[i * 5 + 2].rgb, c.bgl[i * 5 + 3].rgb, c.bgl[i * 5 + 4].rgb, c.bgl[i * 5 + 3].w, v1.w) * v1.y; }
      else { lc = lights(uv, i32(v1.x + 0.5), v1.y, v1.z, c.bgl[i * 5 + 2].rgb, c.bgl[i * 5 + 3].rgb); }
      stack = blendL(stack, lc, i32(v0.y + 0.5), v0.z);
    }
  }
  let lmask = select(1.0 - clamp(sc4.a, 0.0, 1.0), 1.0, blank);                              // layers only where the picture does not cover (all of it in a scene with nothing)
  col = min(col + stack * lmask, vec3<f32>(1.0));
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
  let fl = clamp(c.flash, 0.0, 1.0);
  if (c.misc.x > 0.5) { col = min(col + vec3<f32>(fl), vec3<f32>(1.0)); }          // flash mode 1: a white glow added to the picture
  else { col = abs(col - vec3<f32>(fl)); }                                          // flash mode 0: Difference layer, the picture inverts
  return vec4<f32>(col, 1.0);
}
