// Visual generators: the pictures a scene can have besides the Mandala. One fragment shader, one kind per picture:
//   2 tunnel · 3 spectrum · 4 fractal · 5 synthwave grid · 6 fluid blobs · 7 galaxy · 8 oscilloscope · 9 logo / text
// The output is HDR like the Mandala's (composite tone maps it); alpha is the coverage, so the background layers show through where it is dark.
struct G {
  a: vec4<f32>,                 // time, aspect, kind, gain (fade * gain of the director)
  b: vec4<f32>,                 // bass, mid, high, kick
  c: vec4<f32>,                 // beat, energy, tension, drop
  d: vec4<f32>,                 // p1, p2, p3 (0..1), logo aspect
  col0: vec4<f32>,
  col1: vec4<f32>,
  bands: array<vec4<f32>, 8>,   // 32 bands of the spectrum, low to high
  wave: array<vec4<f32>, 16>,   // 64 samples of the sound
};
@group(0) @binding(0) var<uniform> g: G;
@group(0) @binding(1) var logo: texture_2d<f32>;
@group(0) @binding(2) var samp: sampler;

struct VOut { @builtin(position) pos: vec4<f32>, @location(0) uv: vec2<f32> };

@vertex
fn vs(@builtin(vertex_index) i: u32) -> VOut {
  var q = array<vec2<f32>, 3>(vec2<f32>(-1.0, -1.0), vec2<f32>(3.0, -1.0), vec2<f32>(-1.0, 3.0));
  var o: VOut;
  o.pos = vec4<f32>(q[i], 0.0, 1.0);
  o.uv = vec2<f32>(q[i].x * 0.5 + 0.5, 0.5 - q[i].y * 0.5);
  return o;
}

const PI: f32 = 3.14159265;

fn hash21(p: vec2<f32>) -> f32 {
  var q = fract(p * vec2<f32>(123.34, 456.21));
  q = q + dot(q, q + 45.32);
  return fract(q.x * q.y);
}

fn vnoise(p: vec2<f32>) -> f32 {
  let i = floor(p);
  let f = fract(p);
  let u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash21(i), hash21(i + vec2<f32>(1.0, 0.0)), u.x), mix(hash21(i + vec2<f32>(0.0, 1.0)), hash21(i + vec2<f32>(1.0, 1.0)), u.x), u.y);
}

fn pal(t: f32) -> vec3<f32> { return mix(g.col0.rgb, g.col1.rgb, 0.5 + 0.5 * sin(t * 6.2831)); }

fn band(i: u32) -> f32 { return g.bands[i >> 2u][i & 3u]; }

// the spectrum at x (0 low .. 1 high), smooth between the bands
fn spec(x: f32) -> f32 {
  let f = clamp(x, 0.0, 0.999) * 31.0;
  let i = u32(floor(f));
  return mix(band(i), band(min(i + 1u, 31u)), fract(f));
}

fn wavef(x: f32) -> f32 {
  let f = clamp(x, 0.0, 0.999) * 63.0;
  let i = u32(floor(f));
  let j = min(i + 1u, 63u);
  return mix(g.wave[i >> 2u][i & 3u], g.wave[j >> 2u][j & 3u], fract(f));
}

fn rot(a: f32) -> mat2x2<f32> { let c = cos(a); let s = sin(a); return mat2x2<f32>(c, s, -s, c); }

// ---- 2: tunnel. Rings and panels flying at you; the kick pushes it, the bass opens it.
fn tunnel(p0: vec2<f32>, t: f32) -> vec3<f32> {
  let sides = floor(3.0 + g.d.x * 9.0);
  let spd = 0.4 + g.d.y * 2.2;
  let twist = (g.d.z - 0.5) * 2.0;
  var p = p0 * rot(t * 0.15 * twist + g.c.x * 0.02);
  let r = max(length(p), 0.001);
  let a = atan2(p.y, p.x);
  let z = 0.95 / r + t * spd + g.b.w * 0.35;
  let ring = 1.0 - smoothstep(0.0, 0.07 + g.b.x * 0.06, abs(fract(z * 0.5) - 0.5));
  let panel = 1.0 - smoothstep(0.0, 0.025, abs(fract(a * sides / (2.0 * PI) + z * 0.05 * twist) - 0.5));
  let fog = exp(-0.25 / r) * smoothstep(0.0, 0.3, r);
  let col = pal(z * 0.06 + t * 0.03);
  let ln = (ring * (0.9 + g.b.w * 1.4) + panel * 0.7) * fog;
  return col * ln * (1.2 + g.c.y) + pal(z * 0.06 + 0.5) * exp(-r * r * 2.0) * 0.08 * (1.0 + g.b.x);
}

// ---- 3: spectrum. Bars on a mirrored floor.
fn spectrum(uv: vec2<f32>, t: f32) -> vec3<f32> {
  let horizon = 0.62;
  let n = floor(12.0 + g.d.x * 52.0);
  let mir = g.d.z > 0.5;
  var x = uv.x;
  if (mir) { x = abs(uv.x * 2.0 - 1.0); }
  let idx = floor(x * n);
  let cx = fract(x * n);
  let gap = 0.12 + (1.0 - g.d.x) * 0.1;
  let v = spec((idx + 0.5) / n);
  let h = clamp(v * (0.5 + g.d.y * 1.6) + 0.015, 0.0, 0.62);
  var col = vec3<f32>(0.0);
  let bar = step(gap, cx) * step(cx, 1.0 - gap);
  let col_b = pal(x * 0.8 + t * 0.05);
  if (uv.y < horizon) {
    let y = horizon - uv.y;
    let inside = bar * step(y, h);
    col = col_b * inside * (0.45 + 0.7 * (y / max(h, 0.02))) + col_b * 0.1 * exp(-abs(y - h) * 40.0) * bar;
  } else {
    let y = uv.y - horizon;
    let z = 0.12 / (y + 0.02);
    let gx = abs(fract(uv.x * n * 0.5 + 0.5) - 0.5);
    let gz = abs(fract(z - t * 0.5) - 0.5);
    let grid = (1.0 - smoothstep(0.0, 0.05 * (1.0 + z * 0.4), gx)) + (1.0 - smoothstep(0.0, 0.06, gz));
    let refl = bar * step(y * 1.6, h) * (1.0 - y * 1.6 / max(h, 0.02));
    col = col_b * refl * 0.55 + g.col1.rgb * grid * 0.28 * exp(-y * 2.5);
  }
  return col * (1.0 + g.b.w * 0.5);
}

// ---- 4: fractal. A Julia set that breathes, turns and zooms with the music.
fn fractal(p0: vec2<f32>, t: f32) -> vec3<f32> {
  let iters = i32(24.0 + g.d.x * 56.0);
  let zoom = 1.6 - g.d.y * 0.9 - g.b.w * 0.12;
  var z = (p0 * rot(t * 0.07)) * zoom;
  let wander = 0.05 + g.d.z * 0.35;
  let c = vec2<f32>(-0.745 + sin(t * 0.21) * wander * 0.3 + g.b.x * 0.012, 0.113 + cos(t * 0.17) * wander * 0.3 + g.c.y * 0.01);
  var k = 0.0;
  var m = 0.0;
  for (var i = 0; i < 80; i = i + 1) {
    if (i >= iters) { break; }
    z = vec2<f32>(z.x * z.x - z.y * z.y, 2.0 * z.x * z.y) + c;
    let d = dot(z, z);
    m = max(m, d);
    if (d > 16.0) {
      k = f32(i) - log2(log2(d) * 0.5) + 4.0;
      break;
    }
  }
  if (k <= 0.0) { return g.col0.rgb * 0.06 * (1.0 + sqrt(m)); }
  return pal(k * 0.045 + t * 0.04) * (1.0 - exp(-k * 0.22)) * 1.5 * (1.0 + g.b.w * 0.5);
}

// ---- 5: synthwave. Sun, mountains and a grid that runs to the horizon.
fn synth(uv: vec2<f32>, aspect: f32, t: f32) -> vec3<f32> {
  let hz = 0.52;
  let spd = 0.3 + g.d.x * 2.0;
  var col = vec3<f32>(0.0);
  if (uv.y < hz) {
    let sky = clamp((hz - uv.y) / hz, 0.0, 1.0);
    col = mix(g.col0.rgb * 0.55, g.col1.rgb * 0.08, sky);
    let sp = vec2<f32>((uv.x - 0.5) * aspect, uv.y - (hz - 0.2));
    let rs = 0.14 + g.d.y * 0.2 + g.b.w * 0.03;
    let d = length(sp) - rs;
    let sunc = mix(g.col1.rgb, g.col0.rgb, clamp((sp.y / rs) * 0.5 + 0.5, 0.0, 1.0)) * 2.2;
    let slice = step(0.0, sp.y) + (1.0 - step(0.0, sp.y)) * step(0.35, fract(sp.y * 30.0 + t * 0.4));
    col = col + sunc * (1.0 - smoothstep(0.0, 0.012, d)) * slice + g.col0.rgb * exp(-max(d, 0.0) * 9.0) * 0.4;
    let mx = (uv.x - 0.5) * aspect * 3.0;
    let mh = (vnoise(vec2<f32>(mx * 1.5 + 3.0, 0.5)) * 0.7 + vnoise(vec2<f32>(mx * 4.0, 1.5)) * 0.3) * (0.03 + g.d.z * 0.16) * (1.0 + g.b.x * 0.5);
    if (uv.y > hz - mh) { col = g.col1.rgb * 0.04 + g.col1.rgb * 0.5 * exp(-(uv.y - (hz - mh)) * 160.0); }
  } else {
    let y = uv.y - hz;
    let z = 0.35 / (y + 0.003);
    let x = (uv.x - 0.5) * aspect * z * 1.2;
    let gx = abs(fract(x + 0.5) - 0.5);
    let gz = abs(fract(z * 0.5 - t * spd + 0.5) - 0.5);
    let w = 0.012 * z + 0.012;
    let grid = (1.0 - smoothstep(0.0, w, gx)) + (1.0 - smoothstep(0.0, w, gz));
    col = g.col1.rgb * grid * (0.9 + g.b.w * 1.5) * clamp(1.5 - y * 1.8, 0.3, 1.0) + g.col0.rgb * exp(-y * 14.0) * 0.7;
  }
  return col;
}

// ---- 6: fluid. Soft blobs that melt into each other; the spectrum swells them.
fn fluid(p: vec2<f32>, t: f32) -> vec3<f32> {
  let n = 3 + i32(g.d.x * 5.0);
  let spd = 0.25 + g.d.z * 1.3;
  var f = 0.0;
  var cs = vec3<f32>(0.0);
  for (var i = 0; i < 8; i = i + 1) {
    if (i >= n) { break; }
    let fi = f32(i);
    let c = vec2<f32>(sin(t * spd * (0.6 + 0.13 * fi) + fi * 2.1), cos(t * spd * (0.5 + 0.17 * fi) + fi * 3.3)) * vec2<f32>(0.75, 0.55);
    let r = 0.16 + 0.1 * g.d.y + 0.22 * spec((fi + 0.5) / 8.0) + 0.05 * g.b.w;
    let d = length(p - c);
    let v = (r * r) / (d * d + 0.002);
    f = f + v;
    cs = cs + pal(fi * 0.17 + t * 0.03) * v;
  }
  let col = cs / max(f, 0.001);
  let edge = smoothstep(0.85, 1.05, f);
  let rim = exp(-abs(f - 1.0) * 5.0);
  return col * (edge * 0.9 + rim * 0.8) * (1.0 + g.c.y * 0.6) + col * 0.1 * clamp(f, 0.0, 1.0);
}

// ---- 7: galaxy. Spiral arms, a bright core and a field of stars.
fn galaxy(p0: vec2<f32>, t: f32) -> vec3<f32> {
  let arms = floor(2.0 + g.d.x * 3.0);
  let ang = t * (0.05 + g.d.z * 0.5);
  var p = p0 * rot(ang) * (1.0 - g.b.x * 0.04);
  let r = max(length(p), 0.001);
  let a = atan2(p.y, p.x);
  let wind = log(r + 0.05) * 3.2;
  let spiral = pow(0.5 + 0.5 * cos(arms * (a - wind)), 2.5 + g.c.z * 2.0);
  let dust = vnoise(vec2<f32>(a * 3.0 + wind * 2.0, r * 8.0));
  let disk = spiral * exp(-r * 1.6) * (0.55 + 0.9 * dust);
  let core = exp(-r * 7.0) * (1.4 + g.b.x * 1.6 + g.b.w);
  var col = pal(r * 0.5 + 0.1) * (disk * 1.6) + g.col1.rgb * core;
  let cell = floor(p0 * (30.0 + 80.0 * g.d.y) + 7.0);
  let h = hash21(cell);
  let tw = 0.5 + 0.5 * sin(t * (2.0 + h * 5.0) + h * 40.0);
  let sd = length(fract(p0 * (30.0 + 80.0 * g.d.y) + 7.0) - 0.5);
  col = col + vec3<f32>(1.0, 0.95, 0.9) * step(0.93, h) * exp(-sd * sd * 90.0) * (0.4 + tw) * (1.0 + g.b.z * 2.0);
  return col;
}

// ---- 10: accelerator. A beam of light comes down from the top to a focal point and opens there downwards into threads that bend out to both sides,
// with light running along them. p1 how many filaments, p2 how much they bend, p3 how fast the light runs. The bass bends and opens the fan, the highs sharpen the threads,
// the kick lights the focus, the energy speeds the flow.
fn accel(p0: vec2<f32>, t: f32) -> vec3<f32> {
  let f = vec2<f32>(0.0, 0.2);                                         // the beam comes down from the top to the focus and opens downwards
  let q = p0 - f;
  let r = max(length(q), 1e-4);
  let off = abs(q.x);
  let w = 0.005 + 0.006 * g.b.x;
  let beam = smoothstep(-0.03, 0.06, q.y) * ((w * w) / (off * off + w * w) * 1.8 + 0.025 / (off + 0.025) * 0.35);
  var col = mix(g.col1.rgb, vec3<f32>(1.0), 0.45) * beam;
  let a = atan2(q.x, -q.y);                                            // the angle from straight down: the fan opens to both sides
  let k = 0.6 + g.d.y * 2.4 + g.b.x * 1.2;                             // the threads bend outwards the farther they go
  let wob = (vnoise(vec2<f32>(a * 2.5, r * 2.5 - t * 0.6)) - 0.5) * 0.06 * min(r, 1.5);   // the threads wander like lightning or rivers
  let a2 = a / (1.0 + k * r) + wob;
  let spread = 0.8 + 0.3 * g.c.y + 0.2 * g.b.x;
  let inside = exp(-a2 * a2 / (spread * spread) * 2.2) * smoothstep(0.0, 0.35, -q.y + 0.03);
  let speed = 1.5 + g.d.z * 4.0 + g.c.y * 3.0;                       // how fast the light runs out along the threads
  var fil = vec3<f32>(0.0);
  for (var L = 0; L < 4; L = L + 1) {                                  // hair-fine threads, from a few bright ones to many faint ones, with pulses running out
    let dens = (60.0 + g.d.x * 160.0) * pow(2.4, f32(L));
    let u = a2 * dens + f32(L) * 0.37;
    let id = floor(u);
    let hh = hash21(vec2<f32>(id, 3.7 + f32(L) * 11.0));
    let dpx = abs(fract(u) - 0.5) / dens * r;
    let lw = (0.0006 + 0.0006 * r) * (1.0 - 0.3 * g.b.z);
    let line = lw * lw / (dpx * dpx + lw * lw) * (0.3 + 0.7 * hh);
    let ph = fract((r - t * speed * (0.25 + 0.2 * hh)) * (0.6 + hh * 0.6) + hh * 13.0);
    let back = 1.0 - ph;
    let glow = line * (0.12 + 1.2 * exp(-back * 3.0) + 2.5 * exp(-back * 28.0));
    let tint = mix(g.col1.rgb, g.col0.rgb, hh * 0.5);
    fil = fil + mix(tint, vec3<f32>(1.0), 0.3 * exp(-back * 28.0)) * glow * 1.8 * pow(0.38, f32(L));                  // a few bright main branches over many faint ones
  }
  let dd = 700.0;                                                      // the dust: tiny round grains of light running out along the threads
  let cu = vec2<f32>(a2 * dd, r * 140.0 - t * speed * 18.0);
  let cid = floor(cu);
  let cf = fract(cu) - 0.5;
  let ch = hash21(cid + vec2<f32>(17.0, 5.0));
  let off2 = (vec2<f32>(hash21(cid + vec2<f32>(3.1, 9.4)), hash21(cid + vec2<f32>(7.7, 1.3))) - 0.5) * 0.7;
  let dv = (cf - off2) * vec2<f32>(r / dd, 1.0 / 140.0);
  let dust = step(0.8, ch) * exp(-dot(dv, dv) / 0.0000016) * (0.6 + 1.4 * g.b.z);
  fil = fil + mix(g.col1.rgb, vec3<f32>(1.0), 0.6) * dust;
  col = col + fil * exp(-r * 0.5) * inside * 2.2;
  col = col + mix(g.col0.rgb, g.col1.rgb, 0.5) * (0.10 + 0.12 * inside * exp(-r * 0.7) + 0.08 * exp(-abs(q.x) * 6.0) * step(0.0, q.y)) * (0.7 + 0.5 * g.c.y);   // the haze the path runs through
  col = col + mix(g.col1.rgb, vec3<f32>(1.0), 0.6) * (exp(-r * 9.0) * (1.2 + 2.0 * g.b.w) + 0.02 / (r + 0.02) * 0.4);
  return col * (0.85 + 0.5 * g.b.w);
}

// ---- 8: oscilloscope. The sound drawn as a line, a ring or two mirrored lines.
fn scope(uv: vec2<f32>, aspect: f32, t: f32) -> vec3<f32> {
  let mode = i32(g.d.x * 2.999);
  let th = 0.004 + g.d.y * 0.02;
  let gain = 0.25 + g.d.z * 1.4;
  var d = 1.0;
  if (mode == 0) {
    let w = wavef(uv.x) * gain * 0.45;
    d = abs((0.5 - uv.y) - w);
  } else if (mode == 1) {
    let p = vec2<f32>((uv.x - 0.5) * aspect, 0.5 - uv.y);
    let a = atan2(p.y, p.x) / (2.0 * PI) + 0.5;
    let w = wavef(a) * gain * 0.3;
    d = abs(length(p) - (0.28 + w + g.b.x * 0.04));
  } else {
    let w = wavef(uv.x) * gain * 0.3;
    d = min(abs((0.5 - uv.y) - 0.18 - w), abs((0.5 - uv.y) + 0.18 + w));
  }
  let ln = exp(-d * d / (th * th)) * 2.0 + exp(-d * 18.0) * 0.28 * (1.0 + g.b.w);
  let grid = smoothstep(0.492, 0.5, abs(fract(uv.x * 12.0) - 0.5)) * 0.1 + smoothstep(0.49, 0.5, abs(fract(uv.y * 8.0) - 0.5)) * 0.1;
  return pal(uv.x * 0.6 + t * 0.05) * ln + g.col1.rgb * grid;
}

// ---- 9: logo / text. The picture the user gave, in the middle, that breathes with the sound.
fn logo_pic(uv: vec2<f32>, aspect: f32, t: f32) -> vec4<f32> {
  let la = max(g.d.w, 0.1);
  let sz = min((0.12 + g.d.x * 0.45) * (1.0 + g.b.x * 0.10 * g.d.y * 2.0 + g.b.w * 0.14 * g.d.y * 2.0), 0.46 * aspect / la);
  let p = vec2<f32>((uv.x - 0.5) * aspect, uv.y - 0.5);
  let q = vec2<f32>(p.x / (sz * la), p.y / sz) * 0.5 + 0.5;
  var a = 0.0;
  var rgb = vec3<f32>(0.0);
  if (q.x > 0.0 && q.x < 1.0 && q.y > 0.0 && q.y < 1.0) {
    let s = textureSample(logo, samp, q);
    a = s.a;
    rgb = s.rgb;
  }
  var glow = 0.0;
  for (var i = 0; i < 8; i = i + 1) {
    let ang = f32(i) * 0.785398;
    let o = vec2<f32>(cos(ang), sin(ang)) * (0.012 + g.b.x * 0.01) / sz;
    let q2 = q + o * vec2<f32>(1.0 / la, 1.0);
    if (q2.x > 0.0 && q2.x < 1.0 && q2.y > 0.0 && q2.y < 1.0) { glow = glow + textureSample(logo, samp, q2).a; }
  }
  glow = glow / 8.0;
  let tint = pal(uv.y * 0.7 + t * 0.06);
  let base = mix(rgb, tint * dot(rgb, vec3<f32>(0.34)) * 1.4 + tint * a * 0.2, g.d.z);
  let col = base * a * (1.0 + g.c.y * 0.5 + g.b.w * 0.6) + pal(uv.x + 0.3) * glow * (0.4 + g.b.x * 1.2) * (1.0 - a);
  return vec4<f32>(col, max(a, glow));
}

@fragment
fn fs(in: VOut) -> @location(0) vec4<f32> {
  let aspect = g.a.y;
  let t = g.a.x;
  let uv = in.uv;
  let p = vec2<f32>((uv.x - 0.5) * 2.0 * aspect, (0.5 - uv.y) * 2.0);
  let k = i32(g.a.z + 0.5);
  var col = vec3<f32>(0.0);
  if (k == 2) { col = tunnel(p, t); }
  else if (k == 3) { col = spectrum(uv, t); }
  else if (k == 4) { col = fractal(p, t); }
  else if (k == 5) { col = synth(uv, aspect, t); }
  else if (k == 6) { col = fluid(p, t); }
  else if (k == 7) { col = galaxy(p, t); }
  else if (k == 8) { col = scope(uv, aspect, t); }
  else if (k == 10) { col = accel(p, t); }
  else {
    let l = logo_pic(uv, aspect, t);
    return vec4<f32>(l.rgb * g.a.w, clamp(l.a, 0.0, 1.0));
  }
  col = max(col, vec3<f32>(0.0)) * g.a.w;
  return vec4<f32>(col, clamp(max(col.r, max(col.g, col.b)) * 1.6, 0.0, 1.0));
}
