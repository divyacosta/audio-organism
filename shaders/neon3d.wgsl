// Neon 3D scene by ray marching (WGSL, runs on Vulkan and Direct3D 12 through wgpu).
//
// Structure is deliberately split so the ray source can change later:
//   map()      scene description: procedural neon tubes (1 scene)
//   march()    one ray through the scene, accumulating neon glow
//   trace()    ray tree: primary ray + glossy-floor reflections (bounces)
// Replacing march()/trace() with a hardware ray query later does not touch the generators.

struct U {
  res: vec2<f32>, time: f32, travel: f32,
  fov: f32, bass: f32, mid: f32, high: f32,
  kick: f32, snare: f32, hat: f32, build: f32,
  drop: f32, explode: f32, collapse: f32, complexity: f32,
  gain: f32, fade: f32, gen: u32, steps: u32,
  bounces: u32, flags: u32, quality: u32, prof: u32,   // prof = scene profile: 0 Facetas, 1 Tunel, 2 Catedral, 3 Impacto, 4 Palco
        // flags: bit0 anime (toon) shading, bit1 ray traced lighting, bit2 edge anti-aliasing
                                                          // quality: shadow | occlusion << 4 | reflection << 8, each 0..3
  seed: vec4<f32>,
  cam: vec4<f32>,          // yaw, pitch, distance, unused
  pal0: vec4<f32>, pal1: vec4<f32>, pal2: vec4<f32>,
  lay: array<vec4<f32>, 12>,     // per layer: universe id, kaleidoscope cut (see fold2), unused x2
  upal: array<vec4<f32>, 9>,    // 3 universes x (face, side, edge highlight)
  geo: vec4<f32>,               // Facetas, per frame (CPU): stretch x, stretch y, layer count, scale
  prm0: vec4<f32>,              // panel half size x/y, layer offset x/y (scene profile)
  prm1: vec4<f32>,              // panel thickness, rectangles only (profile), unused x2
  trig: array<vec4<f32>, 12>,   // per layer: cos / sin of the in-plane rotation, cos / sin of the tilt
  szs: array<vec4<f32>, 12>,    // per layer: size scale (decay x funnel wave), offset scale (funnel), unused x2
  shp: array<vec4<f32>, 12>,    // per layer: shape A, shape B, morph A -> B (0..1), unused. Shape ids: see sdSolid
  mat: vec4<f32>,               // the shader preset's three numbers (1.0 = as the shader always looked), unused
};
@group(0) @binding(0) var<uniform> u: U;

struct VOut { @builtin(position) pos: vec4<f32>, @location(0) uv: vec2<f32> };

@vertex
fn vs(@builtin(vertex_index) i: u32) -> VOut {
  var p = array<vec2<f32>, 3>(vec2<f32>(-1.0, -1.0), vec2<f32>(3.0, -1.0), vec2<f32>(-1.0, 3.0));
  var o: VOut;
  o.pos = vec4<f32>(p[i], 0.0, 1.0);
  o.uv = p[i] * 0.5 + vec2<f32>(0.5);
  return o;
}

fn hash31(p: vec3<f32>) -> f32 {
  var q = fract(p * 0.1031);
  q = q + dot(q, q.zyx + 31.32);
  return fract((q.x + q.y) * q.z);
}

fn vnoise(p: vec3<f32>) -> f32 {
  let i = floor(p);
  let f = fract(p);
  let w = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash31(i), hash31(i + vec3<f32>(1.0, 0.0, 0.0)), w.x), mix(hash31(i + vec3<f32>(0.0, 1.0, 0.0)), hash31(i + vec3<f32>(1.0, 1.0, 0.0)), w.x), w.y),
             mix(mix(hash31(i + vec3<f32>(0.0, 0.0, 1.0)), hash31(i + vec3<f32>(1.0, 0.0, 1.0)), w.x), mix(hash31(i + vec3<f32>(0.0, 1.0, 1.0)), hash31(i + vec3<f32>(1.0, 1.0, 1.0)), w.x), w.y), w.z);
}

fn fmod(x: f32, m: f32) -> f32 { return x - m * floor(x / m); }

// ---------------------------------------------------------------- scene 0: Facetas (solid mirrored panels, perspective camera)
// Thin slabs folded through a kaleidoscope with mirror symmetry on both screen axes, flat shaded: broad faces take the
// theme's face colour, the long edge catches a white highlight, the short edge takes the side colour.
// The camera is ORTHOGRAPHIC: parallel rays, so there is no perspective foreshortening; depth only shows through
// the shading of the tilted panels and the slow rotation.
// pal0 = face, pal1 = side, pal2 = edge highlight (the director rotates red / blue / white themes).

// Fast kaleidoscope fold: the polynomial atan2 replaces the built-in one; the point is folded to the nearest sector centre and mirrored.
fn fatan2(y: f32, x: f32) -> f32 {
  let ax = abs(x);
  let ay = abs(y);
  let mx = max(ax, ay);
  let a = min(ax, ay) / max(mx, 1e-9);
  let s = a * a;
  var r = ((-0.0464964749 * s + 0.15931422) * s - 0.327622764) * s * a + a;
  if (ay > ax) { r = 1.57079637 - r; }
  if (x < 0.0) { r = 3.14159274 - r; }
  if (y < 0.0) { r = -r; }
  return r;
}

fn radialFold(p: vec2<f32>, mode: i32) -> vec2<f32> {
  var n = 6.0;
  if (mode == 3) { n = 8.0; } else if (mode == 4) { n = 5.0; } else if (mode == 7) { n = 12.0; }
  let sec = 6.2831853 / n;
  let a0 = fatan2(p.y, p.x);
  let a = a0 - sec * floor(a0 / sec + 0.5);                                     // angle from the nearest sector centre, in [-sec/2, sec/2]
  return length(p) * vec2<f32>(cos(a), abs(sin(a)));
}

// Kaleidoscope cuts, one per universe: 0 mirror x+y, 1 lateral, 2/3/4 radial 6/8/5 sectors, 5 diagonal, 6 vertical mirror
fn fold2(p: vec2<f32>, mode: i32) -> vec2<f32> {
  if (mode == 1) { return vec2<f32>(abs(p.x), p.y); }
  if (mode == 6) { return vec2<f32>(p.x, abs(p.y)); }
  if ((mode >= 2 && mode <= 4) || mode == 7) { return radialFold(p, mode); }
  if (mode == 5) {
    let q = abs(p);
    return vec2<f32>(max(q.x, q.y), min(q.x, q.y));
  }
  return abs(p);
}

// x: distance, y: slab index, z: face class (0 broad face, 1 long edge, 2 short edge)
// position inside the facet that was hit last (-1..1 on both axes): the holographic style paints gradients and lines in it
var<private> g_loc_p: vec2<f32> = vec2<f32>(0.0);
var<private> g_edge: bool = false;                                       // the pixel's ray touched a silhouette: MSAA takes extra samples there
fn loc_last() -> vec2<f32> { return g_loc_p; }


// ---------------------------------------------------------------- solids: the shapes a layer can take instead of the thin panel
// ids: 0 panel, 1 sphere, 2 cube, 3 cylinder, 4 cone, 5 square pyramid, 6 hexagonal pyramid, 7 triangular prism, 8 hexagonal prism,
// 9 torus, 10 ring, 11 octahedron, 12 dodecahedron, 13 icosahedron, 14 half sphere, 15 truncated cone, 16 cuboid, 17 pentagrammic prism,
// 18 buckyball. Every function returns (distance, face class): 0 flat face, 1 edge, 3 round surface (the shader finds its rim from the normal).
// The polyhedra are intersections of planes, so the distance is a bound that never overshoots: safe for ray marching.
const TAU: f32 = 6.2831853;
var<private> N_ICO: array<vec3<f32>, 12> = array<vec3<f32>, 12>(
  vec3<f32>(0.0, 0.5257, 0.8507), vec3<f32>(0.0, 0.5257, -0.8507), vec3<f32>(0.0, -0.5257, 0.8507), vec3<f32>(0.0, -0.5257, -0.8507),
  vec3<f32>(0.5257, 0.8507, 0.0), vec3<f32>(0.5257, -0.8507, 0.0), vec3<f32>(-0.5257, 0.8507, 0.0), vec3<f32>(-0.5257, -0.8507, 0.0),
  vec3<f32>(0.8507, 0.0, 0.5257), vec3<f32>(0.8507, 0.0, -0.5257), vec3<f32>(-0.8507, 0.0, 0.5257), vec3<f32>(-0.8507, 0.0, -0.5257));
var<private> N_DOD: array<vec3<f32>, 20> = array<vec3<f32>, 20>(
  vec3<f32>(0.5774, 0.5774, 0.5774), vec3<f32>(0.5774, 0.5774, -0.5774), vec3<f32>(0.5774, -0.5774, 0.5774), vec3<f32>(0.5774, -0.5774, -0.5774),
  vec3<f32>(-0.5774, 0.5774, 0.5774), vec3<f32>(-0.5774, 0.5774, -0.5774), vec3<f32>(-0.5774, -0.5774, 0.5774), vec3<f32>(-0.5774, -0.5774, -0.5774),
  vec3<f32>(0.0, 0.3568, 0.9342), vec3<f32>(0.0, 0.3568, -0.9342), vec3<f32>(0.0, -0.3568, 0.9342), vec3<f32>(0.0, -0.3568, -0.9342),
  vec3<f32>(0.3568, 0.9342, 0.0), vec3<f32>(0.3568, -0.9342, 0.0), vec3<f32>(-0.3568, 0.9342, 0.0), vec3<f32>(-0.3568, -0.9342, 0.0),
  vec3<f32>(0.9342, 0.0, 0.3568), vec3<f32>(0.9342, 0.0, -0.3568), vec3<f32>(-0.9342, 0.0, 0.3568), vec3<f32>(-0.9342, 0.0, -0.3568));

// keeps the two largest plane distances: x = largest (the distance), y = second (close to x means "near an edge")
fn top2(m: vec2<f32>, v: f32) -> vec2<f32> {
  if (v > m.x) { return vec2<f32>(v, m.x); }
  return vec2<f32>(m.x, max(m.y, v));
}

fn edgeFc(m: vec2<f32>, w: f32) -> f32 { return select(0.0, 1.0, m.x - m.y < w); }

fn sdBox(p: vec3<f32>, b: vec3<f32>, w: f32) -> vec2<f32> {
  let q = abs(p) - b;
  let d = length(max(q, vec3<f32>(0.0))) + min(max(q.x, max(q.y, q.z)), 0.0);
  let m1 = max(q.x, max(q.y, q.z));
  let m3 = min(q.x, min(q.y, q.z));
  let m2 = q.x + q.y + q.z - m1 - m3;
  return vec2<f32>(d, select(0.0, 1.0, m2 > -w));
}

var<private> C6: array<f32, 6> = array<f32, 6>(1.0, 0.5, -0.5, -1.0, -0.5, 0.5);
var<private> S6: array<f32, 6> = array<f32, 6>(0.0, 0.8660254, 0.8660254, 0.0, -0.8660254, -0.8660254);

// horizontal direction of side k of a pyramid (square rotated 45 degrees, or hexagon): no sin / cos inside the distance function
fn pyrDir(k: i32, n: i32) -> vec2<f32> {
  if (n == 6) { return vec2<f32>(C6[k], S6[k]); }
  return vec2<f32>(select(0.7071068, -0.7071068, k == 1 || k == 2), select(0.7071068, -0.7071068, k >= 2));
}

// direction of side k of a prism (triangle or hexagon, first side facing +z)
fn prismDir(k: i32, n: i32) -> vec2<f32> {
  if (n == 6) { return vec2<f32>(-S6[k], C6[k]); }
  if (k == 0) { return vec2<f32>(0.0, 1.0); }
  return vec2<f32>(select(0.8660254, -0.8660254, k == 1), -0.5);
}

fn sdPyramid(p: vec3<f32>, nsides: i32, s: f32, w: f32) -> vec2<f32> {
  let H = 1.5 * s;
  let b = 0.75 * s;
  var m = vec2<f32>(-p.y - 0.75 * s, -1e5);                           // the base
  for (var k = 0; k < nsides; k++) {
    let dr = pyrDir(k, nsides);
    let nrm = normalize(vec3<f32>(dr.x * H, b, dr.y * H));
    m = top2(m, dot(p, nrm) - 0.75 * s * nrm.y);
  }
  return vec2<f32>(m.x, edgeFc(m, w));
}

fn sdPrism(p: vec3<f32>, nsides: i32, apothem: f32, hh: f32, w: f32) -> vec2<f32> {
  var m = vec2<f32>(abs(p.y) - hh, -1e5);
  for (var k = 0; k < nsides; k++) {
    m = top2(m, dot(p.xz, prismDir(k, nsides)) - apothem);
  }
  return vec2<f32>(m.x, edgeFc(m, w));
}

fn sdStar5(pin: vec2<f32>, r: f32, rf: f32) -> f32 {
  let k1 = vec2<f32>(0.809016994375, -0.587785252292);
  let k2 = vec2<f32>(-k1.x, k1.y);
  var p = vec2<f32>(abs(pin.x), pin.y);
  p = p - 2.0 * max(dot(k1, p), 0.0) * k1;
  p = p - 2.0 * max(dot(k2, p), 0.0) * k2;
  p = vec2<f32>(abs(p.x), p.y - r);
  let ba = rf * vec2<f32>(-k1.y, k1.x) - vec2<f32>(0.0, 1.0);
  let h = clamp(dot(p, ba) / dot(ba, ba), 0.0, r);
  return length(p - ba * h) * sign(p.y * ba.x - p.x * ba.y);
}

fn sdCone(pin: vec3<f32>, r: f32, h: f32) -> f32 {                     // apex at the origin, base at y = -h with radius r
  let q = vec2<f32>(r, -h);
  let wv = vec2<f32>(length(pin.xz), pin.y);
  let a = wv - q * clamp(dot(wv, q) / dot(q, q), 0.0, 1.0);
  let b = wv - q * vec2<f32>(clamp(wv.x / q.x, 0.0, 1.0), 1.0);
  let k = sign(q.y);
  let d = min(dot(a, a), dot(b, b));
  let sg = max(k * (wv.x * q.y - wv.y * q.x), k * (wv.y - q.y));
  return sqrt(d) * sign(sg);
}

fn sdCappedCone(p: vec3<f32>, h: f32, r1: f32, r2: f32) -> f32 {
  let q = vec2<f32>(length(p.xz), p.y);
  let k1 = vec2<f32>(r2, h);
  let k2 = vec2<f32>(r2 - r1, 2.0 * h);
  let ca = vec2<f32>(q.x - min(q.x, select(r2, r1, q.y < 0.0)), abs(q.y) - h);
  let tt = clamp(dot(k1 - q, k2) / dot(k2, k2), 0.0, 1.0);
  let cb = q - k1 + k2 * tt;
  let sg = select(1.0, -1.0, cb.x < 0.0 && ca.y < 0.0);
  return sg * sqrt(min(dot(ca, ca), dot(cb, cb)));
}

fn sdSolid(id: i32, p: vec3<f32>, s: f32) -> vec2<f32> {
  let w = 0.07 * s;
  if (id == 1) { return vec2<f32>(length(p) - 0.85 * s, 3.0); }
  if (id == 2) { return sdBox(p, vec3<f32>(0.62 * s), w); }
  if (id == 16) { return sdBox(p, vec3<f32>(0.95 * s, 0.55 * s, 0.55 * s), w); }
  if (id == 3) {
    let d2 = vec2<f32>(length(p.xz) - 0.55 * s, abs(p.y) - 0.8 * s);
    let d = min(max(d2.x, d2.y), 0.0) + length(max(d2, vec2<f32>(0.0)));
    var fc = 3.0;
    if (min(d2.x, d2.y) > -w) { fc = 1.0; } else if (d2.y > d2.x) { fc = 0.0; }
    return vec2<f32>(d, fc);
  }
  if (id == 4) { return vec2<f32>(sdCone(p - vec3<f32>(0.0, 0.75 * s, 0.0), 0.7 * s, 1.5 * s), 3.0); }
  if (id == 15) { return vec2<f32>(sdCappedCone(p, 0.7 * s, 0.8 * s, 0.4 * s), 3.0); }
  if (id == 5) { return sdPyramid(p, 4, s, w); }
  if (id == 6) { return sdPyramid(p, 6, s, w); }
  if (id == 7) { return sdPrism(p, 3, 0.45 * s, 0.8 * s, w); }
  if (id == 8) { return sdPrism(p, 6, 0.6 * s, 0.8 * s, w); }
  if (id == 9) {
    let q = vec2<f32>(length(p.xz) - 0.62 * s, p.y);
    return vec2<f32>(length(q) - 0.24 * s, 3.0);
  }
  if (id == 10) {
    let d2 = abs(length(p.xy) - 0.62 * s) - 0.22 * s;
    let dz = abs(p.z) - 0.2 * s;
    let d = length(max(vec2<f32>(d2, dz), vec2<f32>(0.0))) + min(max(d2, dz), 0.0);
    return vec2<f32>(d, select(3.0, 1.0, min(d2, dz) > -w));
  }
  if (id == 11) {
    let a = abs(p);
    let mn = min(a.x, min(a.y, a.z));
    return vec2<f32>((a.x + a.y + a.z - 0.95 * s) * 0.57735, select(0.0, 1.0, 2.0 * mn * 0.57735 < w));
  }
  if (id == 12) {
    var m = vec2<f32>(-1e5, -1e5);
    for (var k = 0; k < 12; k++) { m = top2(m, dot(p, N_ICO[k]) - 0.78 * s); }
    return vec2<f32>(m.x, edgeFc(m, w));
  }
  if (id == 13) {
    var m = vec2<f32>(-1e5, -1e5);
    for (var k = 0; k < 20; k++) { m = top2(m, dot(p, N_DOD[k]) - 0.70 * s); }
    return vec2<f32>(m.x, edgeFc(m, w));
  }
  if (id == 14) {
    let pp = p + vec3<f32>(0.0, 0.3 * s, 0.0);
    let ds = length(pp) - 0.85 * s;
    return vec2<f32>(max(ds, -pp.y), select(3.0, 0.0, -pp.y > ds));
  }
  if (id == 17) {
    let d2 = sdStar5(p.xz, 0.95 * s, 0.5);
    let dy = abs(p.y) - 0.5 * s;
    let d = length(max(vec2<f32>(d2, dy), vec2<f32>(0.0))) + min(max(d2, dy), 0.0);
    return vec2<f32>(d, select(0.0, 1.0, min(d2, dy) > -w));
  }
  if (id == 18) {
    var m = vec2<f32>(-1e5, -1e5);
    for (var k = 0; k < 20; k++) { m = top2(m, dot(p, N_DOD[k]) - 0.78 * s); }
    for (var k = 0; k < 12; k++) { m = top2(m, dot(p, N_ICO[k]) - 0.80 * s); }
    return vec2<f32>(m.x, edgeFc(m, 0.05 * s));
  }
  return vec2<f32>(1e5, 0.0);
}

// the thin panel of the Facetas engine: x = distance, y = face class (0 broad face, 1 long edge, 2 short edge)
fn sdPanel(p: vec3<f32>, i: i32, h: vec2<f32>, zs: f32, thick: f32, onlyRects: bool) -> vec2<f32> {
  // alternate panels: rectangle / triangle (apex up)
  let dBottom = -p.y - h.y;
  var dSide = abs(p.x) - h.x;
  if ((i % 2) == 1 && !onlyRects) {
    let len = length(vec2<f32>(h.y * 2.0, h.x));
    dSide = (abs(p.x) * 2.0 * h.y + p.y * h.x - h.x * h.y) / len;
  }
  let dTop = select(p.y - h.y, -1e5, (i % 2) == 1 && !onlyRects);
  var d2 = max(max(dBottom, dTop), dSide);
  if ((u.prm1.z > 0.5 && u.prm1.z < 1.5 && ((i % 2) == 0)) || u.prm1.z > 1.5) {      // corners: 1 = alternate panels rounded, 2 = all fully rounded
    let rr = min(h.x, h.y) * select(0.55, 0.96, u.prm1.z > 1.5);
    let qx = abs(p.x) - h.x + rr;
    let qy = abs(p.y) - h.y + rr;
    d2 = length(max(vec2<f32>(qx, qy), vec2<f32>(0.0))) + min(max(qx, qy), 0.0) - rr;
  }
  let dz = abs(p.z) - thick * zs;
  var fc = 0.0;
  if (dz < d2) { fc = select(2.0, 1.0, max(dBottom, dTop) > dSide); }
  return vec2<f32>(max(d2, dz), fc);
}

fn sdShape(id: i32, p: vec3<f32>, i: i32, h: vec2<f32>, zs: f32, thick: f32, onlyRects: bool) -> vec2<f32> {
  if (id == 0) { return sdPanel(p, i, h, zs, thick, onlyRects); }
  let s = 0.5 * (min(h.x, h.y) + 0.5 * (h.x + h.y));                       // a solid's size follows its panel
  let db = length(p) - 1.25 * s;                                          // every solid fits in this sphere: far away, its distance is a safe answer
  if (db > 0.35 * s) { return vec2<f32>(db, 3.0); }
  return sdSolid(id, p, s);
}

fn mapFacet(p0: vec3<f32>) -> vec3<f32> { return mapFacetL(p0, 99); }

// lim = how many fold layers to evaluate. Secondary rays (shadows, occlusion, reflections) use a coarser scene: they are soft and dim
// anyway, so the picture is the same and each ray is much cheaper.
fn mapFacetL(p0: vec3<f32>, lim: i32) -> vec3<f32> {
  var p = p0;                                                           // no global mirror: each universe's cut decides
  // Everything that does not depend on the point is computed once per frame on the CPU (renderer.facet_tables): window stretch, layer
  // count, profile proportions, thickness, and per layer the rotation / tilt (cos, sin), size and offset scales. The distance function
  // runs dozens of times per pixel, so no pow / sin / cos is left inside it except the kaleidoscope fold itself.
  let sx = u.geo.x;
  let sy = u.geo.y;
  let n = i32(u.geo.z);
  let sc = u.geo.w;
  let pSize = u.prm0.xy;
  let pOff = u.prm0.zw;
  let thick = u.prm1.x;
  let onlyRects = u.prm1.y > 0.5;
  var best = vec3<f32>(1e5, 0.0, 0.0);
  let nn = min(n, lim);
  for (var i = 0; i < nn; i++) {
    let fi = f32(i);
    // each layer belongs to a universe: its own kaleidoscope cut and its own rotation, so the large, medium and small layers
    // can come from different universes
    let mode = i32(u.lay[i].y + 0.5);
    let T4 = u.trig[i];
    let S2 = u.szs[i];
    // one-sided cuts only mirror one axis: alternate the offset on the other axis so the layers spread to BOTH sides of it
    // instead of piling up on one half of the screen
    // FUNNEL (u.cam.w = 0..1): the layers converge toward the centre and sink in depth, like looking down a cone, and a size wave runs
    // inward along the layers, so the picture seems to be sucked into the centre
    var off = vec3<f32>(pOff.x * sx, pOff.y * sy, 0.0) * sc * S2.y;
    let flip = select(1.0, -1.0, (i % 2) == 1);
    if (mode == 1) { off.y = off.y * flip; }
    if (mode == 6) { off.x = off.x * flip; }
    off.z = 0.40 + 0.25 * clamp(u.cam.w, 0.0, 1.0);                                              // each layer sits deeper (farther from the camera) than the previous one
    p = vec3<f32>(fold2(p.xy, mode), p.z) - off;
    let a = vec2<f32>(T4.x * p.x - T4.y * p.y, T4.y * p.x + T4.x * p.y);
    p = vec3<f32>(a.x, a.y, p.z);
    let t = vec2<f32>(T4.z * p.y - T4.w * p.z, T4.w * p.y + T4.z * p.z);
    p = vec3<f32>(p.x, t.x, t.y);
    // lay.z = how much of this layer is shown: during a change of universe the old elements shrink away and the new ones grow in
    let zs = u.lay[i].z;
    if (zs < 0.03) { continue; }
    let h = pSize * sc * S2.x * zs;                                         // S2.x = decay x inward-running size wave
    let sh = u.shp[i];
    var r = sdShape(i32(sh.x + 0.5), p, i, h, zs, thick, onlyRects);
    if (sh.z > 0.001) {                                                   // a shape is turning into another one: blend the two distance fields
      let r2 = sdShape(i32(sh.y + 0.5), p, i, h, zs, thick, onlyRects);
      r = vec2<f32>(mix(r.x, r2.x, sh.z), select(r.y, r2.y, sh.z > 0.5));
    }
    if (r.x < best.x) {
      best = vec3<f32>(r.x, fi, r.y);
      g_loc_p = clamp(vec2<f32>(p.x / h.x, p.y / h.y), vec2<f32>(-1.0), vec2<f32>(1.0));
    }
  }
  return best;
}

// the same normal from forward differences: the distance at p itself (d0) is known at a hit, so 3 reads instead of 4
fn facetNormalD(p: vec3<f32>, d0: f32) -> vec3<f32> {
  let e = 0.0012;
  let g = vec3<f32>(mapFacet(p + vec3<f32>(e, 0.0, 0.0)).x - d0, mapFacet(p + vec3<f32>(0.0, e, 0.0)).x - d0, mapFacet(p + vec3<f32>(0.0, 0.0, e)).x - d0);
  let l2 = dot(g, g);
  if (l2 < 1e-14 || l2 != l2) { return vec3<f32>(0.0, 0.0, -1.0); }
  return g * inverseSqrt(l2);
}

fn facetNormal(p: vec3<f32>) -> vec3<f32> {
  let e = vec2<f32>(0.001, -0.001);
  let g = e.xyy * mapFacet(p + e.xyy).x + e.yyx * mapFacet(p + e.yyx).x + e.yxy * mapFacet(p + e.yxy).x + e.xxx * mapFacet(p + e.xxx).x;
  let l2 = dot(g, g);
  if (l2 < 1e-14 || l2 != l2) { return vec3<f32>(0.0, 0.0, -1.0); }      // exactly on a fold seam the gradient cancels out: face the camera, no NaN
  return g * inverseSqrt(l2);
}

const LIGHT: vec3<f32> = vec3<f32>(0.35, 0.55, -0.75);

// material style (flags bits 8..11): 0 = 3D, 1 = neon, 2 = holograma, 3 = raio X, 4 = cromado, 5 = aquarela
fn styleId() -> u32 { return (u.flags >> 8u) & 15u; }
fn qShadow() -> u32 { return u.quality & 15u; }
fn qAO() -> u32 { return (u.quality >> 4u) & 15u; }
fn qRefl() -> u32 { return (u.quality >> 8u) & 15u; }

// lay.w = colour variant of the layer (0..2): the face / side / edge colours of its universe rotate one place per variant. The director
// bumps the variant of a few layers on the beat, so some elements change colour with the BPM.
// colour of the universe palette for variant w (a float: between two whole numbers the colours blend smoothly, which is how a colour
// turns into the next one instead of cutting): j = 0 face, 1 side, 2 edge
fn upalv(k: i32, w: f32, j: i32) -> vec3<f32> {
  let fl = floor(w);
  let f = w - fl;
  let v0 = i32(fl);
  let a = u.upal[k + ((v0 + j) % 3)].xyz;
  let b = u.upal[k + ((v0 + 1 + j) % 3)].xyz;
  return mix(a, b, f * f * (3.0 - 2.0 * f));
}

fn layerCol(id: f32, fc: f32) -> vec3<f32> {
  let li = i32(id + 0.5);
  let k = i32(u.lay[li].x + 0.5) * 3;
  let v = u.lay[li].w;
  let cf = upalv(k, v, 0);
  let cs = upalv(k, v, 1);
  let ce = upalv(k, v, 2);
  if (fc > 1.5) { return cs; }
  if (fc > 0.5) { return mix(ce, cf, 0.12); }
  return cf;
}

fn facetShade(p: vec3<f32>, rd: vec3<f32>, id: f32, fc_in: f32, strong: bool, d0: f32) -> vec3<f32> {      // strong = the ray is still mostly unattenuated: worth the ray-traced extras
  var fc = fc_in;
  let n = facetNormalD(p, d0);
  if (fc > 2.5) {                                                   // a round solid: its rim (silhouette) plays the part of the edge
    fc = select(0.0, 1.0, abs(dot(n, rd)) < 0.30);
  }
  var g_loc = vec2<f32>(0.0);
  if (styleId() == 2u || styleId() == 1u || styleId() == 3u || styleId() == 5u) { let m0 = mapFacet(p); g_loc = loc_last(); }
  let ui = i32(u.lay[i32(id + 0.5)].x + 0.5) * 3;                  // this layer's universe palette
  let vr = u.lay[i32(id + 0.5)].w;                                 // colour variant: rotates face / side / edge (float: blends between)
  let cFace = upalv(ui, vr, 0);
  let cSide = upalv(ui, vr, 1);
  var cEdge = upalv(ui, vr, 2);
  var cFaceG = cFace;
  if (u.prof == 3u) {                                               // Impacto: hot-white edges, faces pushed to full saturation
    cEdge = mix(cEdge, vec3<f32>(1.0), 0.45);
    cFaceG = cFace * (1.0 + 0.25 * u.kick);
  }
  if (u.prof == 2u) {                                               // Catedral: the glass shifts colour across the pane, edges glow
    cFaceG = mix(cFace, cSide, 0.5 + 0.5 * sin(p.y * 2.2 + p.x * 1.3 + u.time * 0.25));
    cEdge = cEdge * 1.5;
  }
  let L = normalize(vec3<f32>(0.35, 0.55, -0.75));
  let lit = 0.35 + 0.65 * abs(dot(n, L));
  let ndv = abs(dot(n, -rd));
  let pump = 1.0 + 0.5 * u.kick + 0.25 * u.bass;
  let sty = styleId();
  if (sty == 1u) {
    // NEON: the facets are nearly black glass; only their outline glows, like tubes of neon bent into the shape of each facet. The thin
    // sides are white-hot lines, and a faint wash of the colour stays inside so the shapes keep their volume.
    let l = g_loc;
    let ring = smoothstep(0.93 - 0.15 * u.mat.y, 0.93, max(abs(l.x), abs(l.y)));      // mat.y: width of the glowing outline
    let core = smoothstep(0.90, 0.99, max(abs(l.x), abs(l.y)));                  // the hottest line, along the very edge
    var nc = cFace * 0.07 * (0.6 + 0.4 * ndv);
    nc = nc + (cFace * 1.15 * ring * (1.0 + 0.7 * u.kick) + mix(cFace, vec3<f32>(1.0), 0.55) * core * 0.45) * u.mat.x;      // mat.x: glow
    if (fc > 0.5) { nc = mix(cEdge, vec3<f32>(1.0), 0.3) * (1.4 + 0.8 * u.kick) * u.mat.x; }
    return nc * pump;
  }
  if (sty == 3u) {
    // RAIO X: monochrome blue-white film. Faces are almost clear; what shows is the density where layers pile up, the thin edges and a
    // strong rim, like a radiograph of the panels.
    let l = g_loc;
    let ring = smoothstep(0.70, 0.95, max(abs(l.x), abs(l.y)));
    var xr = vec3<f32>(0.035, 0.085, 0.14) + vec3<f32>(0.30, 0.55, 0.70) * pow(1.0 - ndv, 1.6 / max(u.mat.y, 0.2)) * 0.9 + vec3<f32>(0.55, 0.85, 1.0) * ring * 0.55 * u.mat.x;
    if (fc > 0.5) { xr = vec3<f32>(0.80, 0.96, 1.0) * (1.3 + 0.8 * u.kick) * u.mat.x; }
    return xr * pump;
  }
  if (sty == 4u) {
    // CROMADO: polished chrome. The environment is a dark studio with streaks and soft boxes tinted by the palette; the panel colour only
    // tints the metal. With ray tracing on, the panels also mirror each other.
    let rr = reflect(rd, n);
    let sky = 0.5 + 0.5 * rr.y;
    var env = mix(vec3<f32>(0.02, 0.025, 0.04), vec3<f32>(0.75, 0.82, 0.95), smoothstep(0.35, 0.95, sky));
    env = env + cFace * 1.4 * pow(max(0.0, sin(rr.x * 4.0 + rr.y * 2.0 + u.time * 0.2)), 12.0);
    env = env + cSide * 1.1 * pow(max(0.0, sin(rr.x * 2.3 - rr.z * 3.1 - u.time * 0.15)), 16.0);
    env = env + vec3<f32>(1.0) * smoothstep(0.88, 0.96, dot(rr, normalize(vec3<f32>(0.35, 0.55, -0.75)))) * 1.4;
    env = env * u.mat.x;                                              // mat.x: how bright the studio reflection is
    var chrome = env * mix(vec3<f32>(1.0), cFace, clamp(0.30 * u.mat.y, 0.0, 1.0));       // mat.y: how much the scene colour tints the metal
    let fr = 0.55 + 0.45 * pow(1.0 - ndv, 3.0);
    if (fc > 0.5) { chrome = chrome * 0.6 + cEdge * 0.6; }
    return chrome * fr * (1.0 + 0.25 * u.kick) * pump;
  }
  if (sty == 5u) {
    // AQUARELA: pigment on paper. Colour thins out and pools with a soft noise, the facet edges collect a darker, wetter line, and a fine
    // grain breaks up the flat areas. (The background becomes paper.)
    let l = g_loc;
    let ring = smoothstep(0.62, 0.97, max(abs(l.x), abs(l.y)));
    let n1 = vnoise(p * 3.1 + vec3<f32>(id * 1.7, u.time * 0.05, 0.0));
    let n2 = vnoise(p * 11.0 + vec3<f32>(0.0, id, 3.3));
    let paper = vec3<f32>(0.97, 0.95, 0.91);
    var wc = cFace;
    if (fc > 1.5) { wc = cSide; } else if (fc > 0.5) { wc = mix(cEdge, cFace, 0.4); }
    let load = clamp((0.38 + 0.50 * n1 + 0.20 * (n2 - 0.5)) * u.mat.x, 0.0, 1.0);          // how much pigment the paper holds here (mat.x: more or less)
    var w = mix(paper, wc, load);
    w = mix(w, wc * 0.55, ring * (0.45 + 0.35 * n1));                           // darker wet edge where the pigment pooled
    w = w * (1.0 - 0.04 * u.mat.y + 0.08 * u.mat.y * n2);                       // mat.y: grain
    return w * (1.0 + 0.15 * u.kick);
  }
  if (sty == 2u) {
    // HOLOGRAMA: every facet is a gradient (face colour -> side colour -> edge colour across the facet) crossed by fine lines that run
    // along it, with a bright outline and a rim of light. The faces are translucent (see facetFrag), so the layers glow through each other.
    let l = g_loc;                                                   // position inside this facet, -1..1 on both axes
    let gt = clamp(0.5 + 0.5 * l.y + 0.15 * sin(u.time * 0.6 + id), 0.0, 1.0);
    var hg = mix(mix(cFace, cSide, smoothstep(0.0, 0.55, gt)), mix(cSide, cEdge, 0.7), smoothstep(0.55, 1.0, gt));
    let lines = smoothstep(0.80, 0.96, abs(fract(l.y * 3.5 * u.mat.y + u.time * 0.25 + id * 0.17) * 2.0 - 1.0));     // fine lines across the facet
    let ring = smoothstep(0.80, 0.97, max(abs(l.x), abs(l.y)));                                              // outline of the facet
    var hc = hg * (0.45 + 0.55 * lines) + mix(hg, vec3<f32>(1.0), 0.5) * (0.9 * ring);
    hc = hc + hg * pow(1.0 - ndv, 3.0) * 0.8;                                                                // fresnel rim
    if (fc > 0.5) { hc = mix(hg, vec3<f32>(1.0), 0.5) * (1.7 + 1.0 * u.kick); }                              // the thin sides are bright lines
    return hc * pump * u.mat.x;
  }
  var c: vec3<f32>;
  if (fc < 0.5) {
    c = cFaceG * (0.55 + 0.6 * u.mat.y * lit) * (0.8 + 0.4 * ndv) * u.mat.x;
  } else if (fc < 1.5) {
    c = mix(cEdge, cFace, 0.12) * (1.1 + 0.9 * u.kick) * u.mat.x;
  } else {
    c = cSide * (0.7 + 0.5 * u.mat.y * lit) * u.mat.x;
  }
  return c * pump;
}

fn facetFrag(uv: vec2<f32>) -> vec4<f32> {
  let zoom = u.cam.z * 0.40;                                      // half-height of the view in world units
  let yaw = u.cam.x;
  let pitch = u.cam.y;
  let fwd = normalize(-vec3<f32>(sin(yaw) * cos(pitch), sin(pitch), -cos(yaw) * cos(pitch)));
  let right = normalize(cross(vec3<f32>(0.0, 1.0, 0.0), fwd));
  let up = cross(fwd, right);
  // PERSPECTIVE camera, 90 degree vertical field of view (tan 45 = 1): rays fan out, layers farther away look smaller, and the stack
  // of layers reads as a tunnel. The camera sits D0 in front of the first layer (the framing of the first layer matches the old view)
  // and, when the funnel opens, it travels INTO the stack.
  let fn_ = clamp(u.cam.w, 0.0, 1.0);
  let D0 = zoom;
  let D = D0 * pow(2.0 / u.szs[0].w, 0.6) * (1.0 - 0.55 * fn_);       // dolly with the lens: wide angles move in, tele moves out, so the subject keeps its size                                // camera distance to the first layer plane
  let px0 = u.szs[0].w / u.res.y;                                        // angular size of a pixel at tan(45 deg) = 1
  var ro = fwd * -D;
  let cr = cos(u.szs[0].z); let sr = sin(u.szs[0].z);               // camera roll
  let uvr = vec2<f32>(uv.x * cr - uv.y * sr, uv.x * sr + uv.y * cr);
  var rd = normalize(fwd + (uvr.x * right + uvr.y * up) * u.szs[0].w);
  var acc = vec3<f32>(0.0);
  var T = 1.0;
  var t = 0.05;
  g_edge = false;
  var lastId = -1.0;
  var lastCol = vec3<f32>(0.0);
  for (var i = 0u; i < u.steps; i++) {
    let m = mapFacet(ro + rd * t);
    let px = px0 * t;
    if (m.x < px) {
      if (m.x > -0.6 * px) { g_edge = true; }
      let alpha = select(select(0.0, 1.0, m.x < 0.3 * px), smoothstep(px, -0.5 * px, m.x), (u.flags & 4u) != 0u);    // edge anti-aliasing (flag)
      var al = alpha;
      if (u.prm1.w < 0.999 && (m.z < 0.5 || m.z > 2.5)) { al = alpha * u.prm1.w; }       // glass: the faces are only this opaque
      let face = (m.z < 0.5 || m.z > 2.5);
      if (styleId() == 2u && face) { al = al * clamp(0.36 * u.mat.z, 0.0, 1.0); }       // Holograma: translucent faces (mat.z: how much)
      if (styleId() == 1u && face) { al = al * clamp(0.55 * u.mat.z, 0.0, 1.0); }       // Neon: dark glass, the outlines behind show through
      if (styleId() == 3u && face) { al = al * clamp(0.24 * u.mat.z, 0.0, 1.0); }       // Raio X: nearly clear faces
      if (styleId() == 5u && face) { al = al * clamp(0.82 * u.mat.z, 0.0, 1.0); }       // Aquarela: washes let a little of the layer below through
      if (styleId() == 0u && face && u.mat.z < 0.999) { al = al * u.mat.z; }             // 3D: faces are solid unless asked otherwise
      // slivers narrower than a pixel only sparkle: measure the width of what was hit with two probes on each screen axis, and let
      // the coverage follow it (a feature w pixels wide covers about w of the pixel)
      if ((u.flags & 4u) != 0u && m.x > -0.6 * px && T > 0.9) {
        let ph = ro + rd * t;
        let e = 1.5 * px;
        let qx = mapFacet(ph + right * e).x + mapFacet(ph - right * e).x;
        let qy = mapFacet(ph + up * e).x + mapFacet(ph - up * e).x;
        let wx = select(1.0, clamp((2.0 * e - qx) / px, 0.0, 1.0), qx > 0.0);
        let wy = select(1.0, clamp((2.0 * e - qy) / px, 0.0, 1.0), qy > 0.0);
        al = al * max(min(wx, wy), 0.4);
      }
      // a translucent panel is sampled several times while the ray crosses its thickness: shade it once and reuse the colour for the
      // samples that follow inside the same panel (the shading is the expensive part, the extra samples only build up the opacity)
      var sc: vec3<f32>;
      if (m.y == lastId) { sc = lastCol; } else { sc = facetShade(ro + rd * t, rd, m.y, m.z, T > 0.6, m.x); lastId = m.y; lastCol = sc; }
      acc += T * al * sc;
      T = T * (1.0 - al);
      if (T < 0.02) { break; }
    } else {
      lastId = -1.0;
    }
    t += max(abs(m.x) * 0.9, 0.5 * px);
    if (t > D + u.szs[1].z) { break; }
  }
  if (any(acc != acc) || T != T) { acc = vec3<f32>(0.0); T = 1.0; }  // a NaN pixel would smear into the glow as a white dot
  acc = min(acc, vec3<f32>(12.0));
  return vec4<f32>(acc, 1.0 - T);                                  // alpha = coverage: the background colour is added in composite
}

@fragment
fn fs(in: VOut) -> @location(0) vec4<f32> {
  let frag = vec2<f32>(in.pos.x, u.res.y - in.pos.y);
  let uv = (frag - 0.5 * u.res) / u.res.y;
  var f = facetFrag(uv);
  // MSAA equivalent: the picture is ray marched, there are no polygons to multisample, so the extra samples (2 / 4 / 8 per pixel) are taken
  // only on pixels whose ray touched a silhouette, which is where polygon MSAA spends them too
  let ms = (u.flags >> 12u) & 7u;
  if (ms > 0u && g_edge) {
    var offs = array<vec2<f32>, 7>(vec2<f32>(0.25, -0.375), vec2<f32>(-0.25, 0.375), vec2<f32>(0.40, 0.15), vec2<f32>(-0.40, -0.15),
                                   vec2<f32>(0.10, 0.45), vec2<f32>(-0.10, -0.45), vec2<f32>(0.45, -0.10));
    let extra = (1u << ms) - 1u;
    for (var k = 0u; k < extra; k++) { f += facetFrag(uv + offs[k] / u.res.y); }
    f = f / f32(extra + 1u);
  }
  return vec4<f32>(f.rgb * u.gain * u.fade, f.a);      // HDR out: tone mapping happens in composite.wgsl
}
