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
    // alternate panels: rectangle / triangle (apex up)
    let dBottom = -p.y - h.y;
    var dSide = abs(p.x) - h.x;
    if ((i % 2) == 1 && !onlyRects) {
      let len = length(vec2<f32>(h.y * 2.0, h.x));
      dSide = (abs(p.x) * 2.0 * h.y + p.y * h.x - h.x * h.y) / len;
    }
    let dTop = select(p.y - h.y, -1e5, (i % 2) == 1 && !onlyRects);
    var d2 = max(max(dBottom, dTop), dSide);
    if ((u.prof == 4u && ((i % 2) == 0)) || u.prof == 5u) {      // Palco: rounded rectangles; Estrela: fully rounded sticks
      let rr = min(h.x, h.y) * select(0.55, 0.96, u.prof == 5u);
      let qx = abs(p.x) - h.x + rr;
      let qy = abs(p.y) - h.y + rr;
      d2 = length(max(vec2<f32>(qx, qy), vec2<f32>(0.0))) + min(max(qx, qy), 0.0) - rr;
    }
    let dz = abs(p.z) - thick * zs;
    let d = max(d2, dz);
    if (d < best.x) {
      var fc = 0.0;
      if (dz < d2) { fc = select(2.0, 1.0, max(dBottom, dTop) > dSide); }
      best = vec3<f32>(d, fi, fc);
      g_loc_p = clamp(vec2<f32>(p.x / h.x, p.y / h.y), vec2<f32>(-1.0), vec2<f32>(1.0));
    }
  }
  return best;
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
fn layerCol(id: f32, fc: f32) -> vec3<f32> {
  let li = i32(id + 0.5);
  let k = i32(u.lay[li].x + 0.5) * 3;
  let v = i32(u.lay[li].w + 0.5);
  let cf = u.upal[k + (v % 3)].xyz;
  let cs = u.upal[k + ((1 + v) % 3)].xyz;
  let ce = u.upal[k + ((2 + v) % 3)].xyz;
  if (fc > 1.5) { return cs; }
  if (fc > 0.5) { return mix(ce, cf, 0.12); }
  return cf;
}

// RAY TRACING (software, on the GPU): secondary rays through the same scene as the camera rays
fn softShadow(o: vec3<f32>, L: vec3<f32>) -> f32 {
  var res = 1.0;
  var t = 0.02;
  let q = qShadow();
  let ns = select(select(select(0, 6, q == 1u), 10, q == 2u), 16, q >= 3u);
  for (var i = 0; i < 16; i++) {
    if (i >= ns) { break; }
    let h = mapFacetL(o + L * t, 6).x;
    res = min(res, 10.0 * h / t);
    t += clamp(h, 0.015, 0.3);
    if (res < 0.01 || t > 4.0) { break; }
  }
  return clamp(res, 0.0, 1.0);
}

fn envColor(r: vec3<f32>) -> vec3<f32> {                       // dark studio with one soft light box
  let L = normalize(LIGHT);
  return u.pal2.xyz * 0.12 * smoothstep(0.55, 0.95, dot(r, L)) + u.pal0.xyz * 0.025 * (0.5 + 0.5 * r.y);
}

fn reflectColor(o: vec3<f32>, r: vec3<f32>) -> vec3<f32> {
  var t = 0.02;
  let q = qRefl();
  let nr = select(select(select(0, 8, q == 1u), 14, q == 2u), 22, q >= 3u);
  for (var i = 0; i < 22; i++) {
    if (i >= nr) { break; }
    let m = mapFacetL(o + r * t, 6);
    if (m.x < 0.004 + 0.003 * t) { return layerCol(m.y, m.z) * 0.6; }          // the panel seen in the mirror: colour bleeding
    t += max(m.x * 0.9, 0.012);
    if (t > 5.0) { break; }
  }
  return envColor(r);
}

fn facetShade(p: vec3<f32>, rd: vec3<f32>, id: f32, fc: f32) -> vec3<f32> {
  var g_loc = vec2<f32>(0.0);
  if (styleId() == 2u || styleId() == 1u || styleId() == 3u || styleId() == 5u) { let m0 = mapFacet(p); g_loc = loc_last(); }
  let ui = i32(u.lay[i32(id + 0.5)].x + 0.5) * 3;                  // this layer's universe palette
  let vr = i32(u.lay[i32(id + 0.5)].w + 0.5);                      // colour variant: rotates face / side / edge
  let cFace = u.upal[ui + (vr % 3)].xyz;
  let cSide = u.upal[ui + ((1 + vr) % 3)].xyz;
  var cEdge = u.upal[ui + ((2 + vr) % 3)].xyz;
  var cFaceG = cFace;
  if (u.prof == 3u) {                                               // Impacto: hot-white edges, faces pushed to full saturation
    cEdge = mix(cEdge, vec3<f32>(1.0), 0.45);
    cFaceG = cFace * (1.0 + 0.25 * u.kick);
  }
  if (u.prof == 2u) {                                               // Catedral: the glass shifts colour across the pane, edges glow
    cFaceG = mix(cFace, cSide, 0.5 + 0.5 * sin(p.y * 2.2 + p.x * 1.3 + u.time * 0.25));
    cEdge = cEdge * 1.5;
  }
  let n = facetNormal(p);
  let L = normalize(vec3<f32>(0.35, 0.55, -0.75));
  let lit = 0.35 + 0.65 * abs(dot(n, L));
  let ndv = abs(dot(n, -rd));
  let pump = 1.0 + 0.5 * u.kick + 0.25 * u.bass;
  let sty = styleId();
  if (sty == 1u) {
    // NEON: the facets are nearly black glass; only their outline glows, like tubes of neon bent into the shape of each facet. The thin
    // sides are white-hot lines, and a faint wash of the colour stays inside so the shapes keep their volume.
    let l = g_loc;
    let ring = smoothstep(0.78, 0.93, max(abs(l.x), abs(l.y)));
    let core = smoothstep(0.90, 0.99, max(abs(l.x), abs(l.y)));                  // the hottest line, along the very edge
    var nc = cFace * 0.07 * (0.6 + 0.4 * ndv);
    nc = nc + cFace * 1.15 * ring * (1.0 + 0.7 * u.kick) + mix(cFace, vec3<f32>(1.0), 0.55) * core * 0.45;
    if (fc > 0.5) { nc = mix(cEdge, vec3<f32>(1.0), 0.3) * (1.4 + 0.8 * u.kick); }
    return nc * pump;
  }
  if (sty == 3u) {
    // RAIO X: monochrome blue-white film. Faces are almost clear; what shows is the density where layers pile up, the thin edges and a
    // strong rim, like a radiograph of the panels.
    let l = g_loc;
    let ring = smoothstep(0.70, 0.95, max(abs(l.x), abs(l.y)));
    var xr = vec3<f32>(0.035, 0.085, 0.14) + vec3<f32>(0.30, 0.55, 0.70) * pow(1.0 - ndv, 1.6) * 0.9 + vec3<f32>(0.55, 0.85, 1.0) * ring * 0.55;
    if (fc > 0.5) { xr = vec3<f32>(0.80, 0.96, 1.0) * (1.3 + 0.8 * u.kick); }
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
    var chrome = env * mix(vec3<f32>(1.0), cFace, 0.30);
    if ((u.flags & 2u) != 0u && qRefl() > 0u) { chrome = mix(chrome, reflectColor(p + n * 0.012, rr) * 1.6, 0.45); }
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
    let load = clamp(0.38 + 0.50 * n1 + 0.20 * (n2 - 0.5), 0.0, 1.0);          // how much pigment the paper holds here
    var w = mix(paper, wc, load);
    w = mix(w, wc * 0.55, ring * (0.45 + 0.35 * n1));                           // darker wet edge where the pigment pooled
    w = w * (0.96 + 0.08 * n2);
    return w * (1.0 + 0.15 * u.kick);
  }
  if (sty == 2u) {
    // HOLOGRAMA: every facet is a gradient (face colour -> side colour -> edge colour across the facet) crossed by fine lines that run
    // along it, with a bright outline and a rim of light. The faces are translucent (see facetFrag), so the layers glow through each other.
    let l = g_loc;                                                   // position inside this facet, -1..1 on both axes
    let gt = clamp(0.5 + 0.5 * l.y + 0.15 * sin(u.time * 0.6 + id), 0.0, 1.0);
    var hg = mix(mix(cFace, cSide, smoothstep(0.0, 0.55, gt)), mix(cSide, cEdge, 0.7), smoothstep(0.55, 1.0, gt));
    let lines = smoothstep(0.80, 0.96, abs(fract(l.y * 3.5 + u.time * 0.25 + id * 0.17) * 2.0 - 1.0));     // fine lines across the facet
    let ring = smoothstep(0.80, 0.97, max(abs(l.x), abs(l.y)));                                              // outline of the facet
    var hc = hg * (0.45 + 0.55 * lines) + mix(hg, vec3<f32>(1.0), 0.5) * (0.9 * ring);
    hc = hc + hg * pow(1.0 - ndv, 3.0) * 0.8;                                                                // fresnel rim
    if (fc > 0.5) { hc = mix(hg, vec3<f32>(1.0), 0.5) * (1.7 + 1.0 * u.kick); }                              // the thin sides are bright lines
    return hc * pump;
  }
  if ((u.flags & 2u) != 0u && fc < 0.5) {
    // ray traced shading: soft shadow ray, occlusion probes and one glossy reflection ray (the colour of the panel seen in the mirror)
    let o = p + n * 0.012;
    let ld = normalize(LIGHT);
    let lt = max(dot(n, ld), 0.0);
    var shadow = 1.0;
    if (qShadow() > 0u) { shadow = softShadow(o, ld); }
    var occ = 0.0;
    let qa = qAO();
    let na = select(select(select(0, 2, qa == 1u), 3, qa == 2u), 4, qa >= 3u);
    for (var k = 1; k <= 4; k++) {
      if (k > na) { break; }
      let dk = 0.05 * f32(k);
      occ += (dk - mapFacetL(p + n * dk, 6).x) / f32(1 + k);
    }
    let ao = clamp(1.0 - 1.6 * occ, 0.0, 1.0);
    let rr = reflect(rd, n);
    var refl = envColor(rr);
    if (qRefl() > 0u) { refl = reflectColor(o, rr); }
    let fres = 0.08 + 0.92 * pow(1.0 - clamp(dot(n, -rd), 0.0, 1.0), 5.0);
    let spec = pow(max(dot(rr, ld), 0.0), 40.0) * shadow;
    let cr = cFaceG * (0.30 + 0.85 * lt * shadow) * ao + refl * (0.22 + 0.55 * fres) + vec3<f32>(1.0) * spec * 0.45;
    return cr * pump;
  }
  var c: vec3<f32>;
  if (fc < 0.5) {
    c = cFaceG * (0.55 + 0.6 * lit) * (0.8 + 0.4 * ndv);
  } else if (fc < 1.5) {
    c = mix(cEdge, cFace, 0.12) * (1.1 + 0.9 * u.kick);
  } else {
    c = cSide * (0.7 + 0.5 * lit);
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
  for (var i = 0u; i < u.steps; i++) {
    let m = mapFacet(ro + rd * t);
    let px = px0 * t;
    if (m.x < px) {
      if (m.x > -0.6 * px) { g_edge = true; }
      let alpha = select(select(0.0, 1.0, m.x < 0.3 * px), smoothstep(px, -0.5 * px, m.x), (u.flags & 4u) != 0u);    // edge anti-aliasing (flag)
      var al = alpha;
      if (u.prof == 2u && m.z < 0.5) { al = alpha * 0.40; }               // Catedral: translucent faces
      if (styleId() == 2u && m.z < 0.5) { al = al * 0.36; }              // Holograma: translucent faces
      if (styleId() == 1u && m.z < 0.5) { al = al * 0.55; }              // Neon: dark glass, the outlines behind show through
      if (styleId() == 3u && m.z < 0.5) { al = al * 0.24; }              // Raio X: nearly clear faces
      if (styleId() == 5u && m.z < 0.5) { al = al * 0.82; }              // Aquarela: washes let a little of the layer below through
      // slivers narrower than a pixel only sparkle: measure the width of what was hit with two probes on each screen axis, and let
      // the coverage follow it (a feature w pixels wide covers about w of the pixel)
      if ((u.flags & 4u) != 0u && m.x > -0.6 * px) {
        let ph = ro + rd * t;
        let e = 1.5 * px;
        let qx = mapFacet(ph + right * e).x + mapFacet(ph - right * e).x;
        let qy = mapFacet(ph + up * e).x + mapFacet(ph - up * e).x;
        let wx = select(1.0, clamp((2.0 * e - qx) / px, 0.0, 1.0), qx > 0.0);
        let wy = select(1.0, clamp((2.0 * e - qy) / px, 0.0, 1.0), qy > 0.0);
        al = al * max(min(wx, wy), 0.4);
      }
      acc += T * al * facetShade(ro + rd * t, rd, m.y, m.z);
      T = T * (1.0 - al);
      if (T < 0.02) { break; }
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
