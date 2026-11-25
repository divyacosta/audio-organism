// One effect layer of the stack, as a pass over the finished picture: 1 chromatic aberration, 2 edge blur, 3 lens flare, 4 film grain.
// The layer's blend mode and opacity decide how its result is put over the picture below it. Reads the picture (src) and, for the flare, the bloom levels.
struct P { a: vec4<f32>, b: vec4<f32>, c: vec4<f32>, d: vec4<f32> };
// a: kind, opacity, blend (0 normal, 1 add, 2 screen, 3 overlay), amount (after the music and the fade) ; b: p1..p4 of the kind ; c: p5, p6, bloom, time ; d: aspect, width, height, 0
@group(0) @binding(0) var src: texture_2d<f32>;
@group(0) @binding(1) var samp: sampler;
@group(0) @binding(2) var<uniform> u: P;
@group(0) @binding(3) var b2: texture_2d<f32>;
@group(0) @binding(4) var b3: texture_2d<f32>;
@group(0) @binding(5) var b4: texture_2d<f32>;

struct VOut { @builtin(position) pos: vec4<f32>, @location(0) uv: vec2<f32> };

@vertex
fn vs(@builtin(vertex_index) i: u32) -> VOut {
  var q = array<vec2<f32>, 3>(vec2<f32>(-1.0, -1.0), vec2<f32>(3.0, -1.0), vec2<f32>(-1.0, 3.0));
  var o: VOut;
  o.pos = vec4<f32>(q[i], 0.0, 1.0);
  o.uv = vec2<f32>(q[i].x * 0.5 + 0.5, 0.5 - q[i].y * 0.5);
  return o;
}

fn ihash(p: vec2<i32>, seed: i32) -> f32 {                           // integer hash: no sin(), so no patterns however large the coordinates
  var h = u32(p.x) * 374761393u + u32(p.y) * 668265263u + u32(seed) * 2246822519u;
  h = (h ^ (h >> 13u)) * 1274126177u;
  h = h ^ (h >> 16u);
  return f32(h & 16777215u) / 16777215.0;
}

// Grain at a given size (in output pixels): value noise, smoothly interpolated, so a coarse grain is soft clumps and not a block of pixels
fn grain1(px: vec2<f32>, size: f32, seed: i32, chan: i32, soft: f32) -> f32 {
  let q = px / (size * (1.0 + soft * 1.5));
  let i = vec2<i32>(floor(q));
  let f = fract(q);
  let w = f * f * (3.0 - 2.0 * f);
  let s2 = seed * 3 + chan * 7919;
  let a = ihash(i, s2);
  let b = ihash(i + vec2<i32>(1, 0), s2);
  let c = ihash(i + vec2<i32>(0, 1), s2);
  let d = ihash(i + vec2<i32>(1, 1), s2);
  let smooth_n = mix(mix(a, b, w.x), mix(c, d, w.x), w.y);
  let fine = ihash(vec2<i32>(floor(px)), s2 + 101);
  return mix(fine, smooth_n, clamp(select(0.0, 0.7, size > 1.01) + soft * 0.9, 0.0, 1.0)) - 0.5;
}

fn blendmix(s: vec3<f32>, e: vec3<f32>, mode: i32, op: f32) -> vec3<f32> {
  var r = e;
  if (mode == 1) { r = s + max(e - s, vec3<f32>(0.0)); }
  else if (mode == 2) { r = vec3<f32>(1.0) - (vec3<f32>(1.0) - s) * (vec3<f32>(1.0) - e); }
  else if (mode == 3) { r = select(vec3<f32>(1.0) - 2.0 * (vec3<f32>(1.0) - s) * (vec3<f32>(1.0) - e), 2.0 * s * e, s < vec3<f32>(0.5)); }
  return mix(s, clamp(r, vec3<f32>(0.0), vec3<f32>(1.0)), clamp(op, 0.0, 1.0));
}

@fragment
fn fs(in: VOut) -> @location(0) vec4<f32> {
  let uv = in.uv;
  let base = textureSample(src, samp, uv).rgb;
  let kind = i32(u.a.x + 0.5);
  let amt = u.a.w;
  let aspect = u.d.x;
  let ctr = uv - vec2<f32>(0.5);
  let rr = length(ctr * vec2<f32>(aspect, 1.0)) * 2.0;
  var e = base;
  if (kind == 1) {                                                  // chromatic aberration: red and blue drift apart (radial, sideways or up and down)
    let dirm = i32(u.b.x + 0.5);
    var v = ctr;
    if (dirm == 1) { v = vec2<f32>(ctr.x, 0.0); } else if (dirm == 2) { v = vec2<f32>(0.0, ctr.y); }
    let k0 = clamp((rr * 0.7 - u.b.y) / max(1.0 - u.b.y, 0.05), 0.0, 1.0);
    let off = v * amt * 0.03 * select(1.0, k0 / max(rr * 0.7, 1e-3), u.b.y > 0.0);
    if (u.b.z > 0.01) {                                             // softened fringes: red and blue averaged over a stretch of offsets
      var rch = 0.0;
      var bch = 0.0;
      for (var k = 0; k < 5; k = k + 1) {
        let s = (f32(k) - 2.0) * 0.5 * u.b.z;
        rch = rch + textureSample(src, samp, uv - off * (1.0 + s)).r;
        bch = bch + textureSample(src, samp, uv + off * (1.0 + s)).b;
      }
      e = vec3<f32>(rch / 5.0, base.g, bch / 5.0);
    } else {
      e = vec3<f32>(textureSample(src, samp, uv - off).r, base.g, textureSample(src, samp, uv + off).b);
    }
  } else if (kind == 2) {                                           // blur at the edges: 12 samples on a spiral, wider the further from the sharp centre
    var q = rr;
    let sh = i32(u.b.y + 0.5);
    if (sh == 1) { q = max(abs(ctr.x * aspect) * 0.866 + abs(ctr.y) * 0.5, abs(ctr.y)) * 2.0; }
    else if (sh == 2) { q = abs(ctr.y) * 2.2; }
    let t = clamp((q - u.b.x) / max(1.0 - u.b.x, 0.05), 0.0, 1.0);
    let rad = amt * 0.02 * t * t;
    var acc = vec3<f32>(0.0);
    for (var k = 0; k < 12; k = k + 1) {
      let a = f32(k) * 2.399963;
      let d = sqrt((f32(k) + 0.5) / 12.0) * rad;
      acc = acc + textureSample(src, samp, uv + vec2<f32>(cos(a) / aspect, sin(a)) * d).rgb;
    }
    e = mix(base, acc / 12.0, clamp(t * 1.4, 0.0, 1.0));
  } else if (kind == 3) {                                           // lens flare: an anamorphic streak along the bright parts and ghosts on the other side
    var streak = vec3<f32>(0.0);
    let step = 0.022 * u.b.x;
    for (var k = -7; k <= 7; k = k + 1) {
      let w = exp(-f32(k * k) / 18.0);
      for (var j = -1; j <= 1; j = j + 1) {
        streak = streak + textureSample(b3, samp, uv + vec2<f32>(f32(k) * step, f32(j) * u.b.w * 0.012)).rgb * (w / 3.0);
      }
    }
    let fc = i32(u.b.y + 0.5);
    var tint = vec3<f32>(0.35, 0.6, 1.0);
    if (fc == 1) { tint = vec3<f32>(1.0, 0.62, 0.28); } else if (fc == 2) { tint = vec3<f32>(0.8, 0.8, 0.8); }
    var ghosts = vec3<f32>(0.0);
    let ng = i32(u.b.z + 0.5);
    for (var g = 0; g < 4; g = g + 1) {
      if (g < ng) {
        let sc = 0.85 - 0.28 * f32(g);
        let gt = mix(vec3<f32>(1.0, 0.7, 0.4), vec3<f32>(0.4, 0.7, 1.0), f32(g % 2));
        let gp = vec2<f32>(0.5) - ctr * sc;
        ghosts = ghosts + mix(textureSample(b2, samp, gp).rgb, textureSample(b4, samp, gp).rgb * 1.6, clamp(u.b.w, 0.0, 1.0)) * gt;
      }
    }
    e = base + (streak * tint * 0.28 + ghosts * 0.35 / max(1.0, sqrt(f32(ng)))) * amt * u.c.z;
  } else if (kind == 4) {                                           // film grain: size in output pixels, where it weighs, grey or coloured, every frame or at 24 per second
    let tq = select(u.c.w, floor(u.c.w * 24.0) / 24.0, u.b.w > 0.5);
    let seed = i32(floor(tq * 60.0)) % 4096;
    let size = max(u.b.x, 1.0);
    let soft = u.c.x;
    let g1 = grain1(in.pos.xy, size, seed, 0, soft) * 2.0;
    var gv = vec3<f32>(g1);
    if (u.b.z > 0.5) { gv = vec3<f32>(g1, grain1(in.pos.xy, size, seed, 1, soft) * 2.0, grain1(in.pos.xy, size, seed, 2, soft) * 2.0); }
    let lum = dot(base, vec3<f32>(0.3, 0.59, 0.11));
    var wgt = 0.35 + 1.3 * lum * (1.0 - lum) * 2.0;
    let wh = i32(u.b.y + 0.5);
    if (wh == 1) { wgt = 1.4 * (1.0 - lum); } else if (wh == 2) { wgt = 1.4 * lum; }
    e = clamp(base + gv * amt * 0.2 * wgt, vec3<f32>(0.0), vec3<f32>(1.0));
  }
  return vec4<f32>(blendmix(base, e, i32(u.a.z + 0.5), u.a.y), 1.0);
}
