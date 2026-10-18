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
  bounces: u32, flags: u32, quality: u32, pad2: u32,      // flags: bit0 anime (toon) shading, bit1 ray traced lighting, bit2 edge anti-aliasing
                                                          // quality: shadow | occlusion << 4 | reflection << 8, each 0..3
  seed: vec4<f32>,
  cam: vec4<f32>,          // yaw, pitch, distance, unused
  pal0: vec4<f32>, pal1: vec4<f32>, pal2: vec4<f32>,
  lay: array<vec4<f32>, 12>,     // per layer: universe id, kaleidoscope cut (see fold2), unused x2
  upal: array<vec4<f32>, 9>,    // 3 universes x (face, side, edge highlight)
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

const FLOOR_Y: f32 = -1.65;
const TUBE_R: f32 = 0.020;          // glass tube radius (world units)
const TAU: f32 = 6.2831853;

fn rot(a: f32) -> mat2x2<f32> {
  let c = cos(a);
  let s = sin(a);
  return mat2x2<f32>(c, s, -s, c);
}

fn sdCap(p: vec3<f32>, a: vec3<f32>, b: vec3<f32>, r: f32) -> f32 {
  let pa = p - a;
  let ba = b - a;
  let h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
  return length(pa - ba * h) - r;
}

// capsule distance + position along the segment (0..1): the end caps are shaded differently
fn sdCapH(p: vec3<f32>, a: vec3<f32>, b: vec3<f32>, r: f32) -> vec2<f32> {
  let pa = p - a;
  let ba = b - a;
  let h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
  return vec2<f32>(length(pa - ba * h) - r, h);
}

fn fmod(x: f32, m: f32) -> f32 { return x - m * floor(x / m); }

// ---------------------------------------------------------------- scene 0: Facetas (solid mirrored panels, orthographic view)
// Thin slabs folded through a kaleidoscope with mirror symmetry on both screen axes, flat shaded: broad faces take the
// theme's face colour, the long edge catches a white highlight, the short edge takes the side colour.
// The camera is ORTHOGRAPHIC: parallel rays, so there is no perspective foreshortening; depth only shows through
// the shading of the tilted panels and the slow rotation.
// pal0 = face, pal1 = side, pal2 = edge highlight (the director rotates red / blue / white themes).

// Kaleidoscope cuts, one per universe: 0 mirror x+y, 1 lateral, 2/3/4 radial 6/8/5 sectors, 5 diagonal, 6 vertical mirror
fn fold2(p: vec2<f32>, mode: i32) -> vec2<f32> {
  if (mode == 1) { return vec2<f32>(abs(p.x), p.y); }
  if (mode == 6) { return vec2<f32>(p.x, abs(p.y)); }
  if (mode >= 2 && mode <= 4) {
    let sectors = select(select(6.0, 8.0, mode == 3), 5.0, mode == 4);
    let sec = TAU / sectors;
    let a = abs(fmod(atan2(p.y, p.x), sec) - 0.5 * sec);
    return length(p) * vec2<f32>(cos(a), sin(a));
  }
  if (mode == 5) {
    let q = abs(p);
    return vec2<f32>(max(q.x, q.y), min(q.x, q.y));
  }
  return abs(p);
}

// x: distance, y: slab index, z: face class (0 broad face, 1 long edge, 2 short edge)
fn mapFacet(p0: vec3<f32>) -> vec3<f32> { return mapFacetL(p0, 99); }

// lim = how many fold layers to evaluate. Secondary rays (shadows, occlusion, reflections) use a coarser scene: they are soft and dim
// anyway, so the picture is the same and each ray is much cheaper.
fn mapFacetL(p0: vec3<f32>, lim: i32) -> vec3<f32> {
  var p = p0;                                                           // no global mirror: each universe's cut decides (both axes, left/right only, top/bottom only, radial...)
  // fill the screen: more layers, spread to the window shape (wide windows spread sideways, tall ones upwards)
  let aspect = u.res.x / u.res.y;
  let sx = pow(clamp(aspect / 1.78, 1.0, 8.0), 0.70);
  let sy = pow(clamp(1.78 / aspect, 1.0, 8.0), 0.70);
  let n = min(7 + i32(u.complexity * 4.0) + i32((sx - 1.0) * 1.5 + (sy - 1.0) * 1.5), 12);
  let sc = 1.0 - 0.35 * u.collapse + 0.6 * u.explode;
  let thick = 0.009 + 0.012 * u.bass + 0.010 * u.kick;
  var best = vec3<f32>(1e5, 0.0, 0.0);
  let nn = min(n, lim);
  for (var i = 0; i < nn; i++) {
    let fi = f32(i);
    // each layer belongs to a universe: its own kaleidoscope cut and its own rotation, so the large, medium and small layers
    // (layers 0-2 / 3-5 / 6+) can come from different universes
    let uni = u.lay[i].x;
    let mode = i32(u.lay[i].y + 0.5);
    // one-sided cuts only mirror one axis: alternate the offset on the other axis so the layers spread to BOTH sides of it
    // instead of piling up on one half of the screen
    // FUNNEL (u.cam.w = 0..1): the layers converge toward the centre and sink in depth, like looking down a cone, and a size wave runs
    // inward along the layers, so the picture seems to be sucked into the centre
    let fn_ = clamp(u.cam.w, 0.0, 1.0);
    var off = vec3<f32>(0.70 * sx, 0.38 * sy, 0.0) * sc * mix(1.0, pow(0.80, fi), fn_);
    let flip = select(1.0, -1.0, (i % 2) == 1);
    if (mode == 1) { off.y = off.y * flip; }
    if (mode == 6) { off.x = off.x * flip; }
    off.z = 0.40 + 0.25 * fn_;                                              // each layer sits deeper (farther from the camera) than the previous one
    p = vec3<f32>(fold2(p.xy, mode), p.z) - off;
    let a = rot(u.seed.x * 3.0 + uni * 1.9 + fi * 0.75 + u.time * 0.10 * (1.0 + 0.6 * u.build)) * p.xy;
    p = vec3<f32>(a.x, a.y, p.z);
    let t = rot(0.55 + u.seed.y * 1.4 + uni * 0.8 + 0.45 * sin(u.time * 0.27 + fi * 1.3)) * p.yz;
    p = vec3<f32>(p.x, t.x, t.y);
    // lay.z = how much of this layer is shown: during a change of universe the old elements shrink away and the new ones grow in
    let zs = u.lay[i].z;
    if (zs < 0.03) { continue; }
    let wave = 1.0 + 0.40 * fn_ * sin(u.travel * 1.1 - fi * 0.9);            // inward-running size wave
    let h = vec2<f32>(0.52, 0.34) * sc * pow(0.84, fi) * wave * zs;
    // alternate panels: rectangle / triangle (apex up)
    let dBottom = -p.y - h.y;
    var dSide = abs(p.x) - h.x;
    if ((i % 2) == 1) {
      let len = length(vec2<f32>(h.y * 2.0, h.x));
      dSide = (abs(p.x) * 2.0 * h.y + p.y * h.x - h.x * h.y) / len;
    }
    let dTop = select(p.y - h.y, -1e5, (i % 2) == 1);
    let d2 = max(max(dBottom, dTop), dSide);
    let dz = abs(p.z) - thick * zs;
    let d = max(d2, dz);
    if (d < best.x) {
      var fc = 0.0;
      if (dz < d2) { fc = select(2.0, 1.0, max(dBottom, dTop) > dSide); }
      best = vec3<f32>(d, fi, fc);
    }
  }
  return best;
}

fn facetNormal(p: vec3<f32>) -> vec3<f32> {
  let e = vec2<f32>(0.001, -0.001);
  return normalize(e.xyy * mapFacet(p + e.xyy).x + e.yyx * mapFacet(p + e.yyx).x + e.yxy * mapFacet(p + e.yxy).x + e.xxx * mapFacet(p + e.xxx).x);
}

const LIGHT: vec3<f32> = vec3<f32>(0.35, 0.55, -0.75);

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
  let ui = i32(u.lay[i32(id + 0.5)].x + 0.5) * 3;                  // this layer's universe palette
  let vr = i32(u.lay[i32(id + 0.5)].w + 0.5);                      // colour variant: rotates face / side / edge
  let cFace = u.upal[ui + (vr % 3)].xyz;
  let cSide = u.upal[ui + ((1 + vr) % 3)].xyz;
  let cEdge = u.upal[ui + ((2 + vr) % 3)].xyz;
  let n = facetNormal(p);
  let L = normalize(vec3<f32>(0.35, 0.55, -0.75));
  let lit = 0.35 + 0.65 * abs(dot(n, L));
  let ndv = abs(dot(n, -rd));
  let pump = 1.0 + 0.5 * u.kick + 0.25 * u.bass;
  if ((u.flags & 1u) != 0u) {
    // ANIME / toon shading, the usual cel recipe: the light is cut into three flat tones with hard edges, the shadow tone is tinted
    // cool instead of just darker, a hard-edged specular shape, a flat rim light and an ink outline on the silhouette
    var l2 = abs(dot(n, L));
    if ((u.flags & 2u) != 0u && qShadow() > 0u) {                    // ray traced toon: panels cast hard cel shadows on each other
      l2 = l2 * select(0.25, 1.0, softShadow(p + n * 0.012, normalize(LIGHT)) > 0.5);
    }
    let s1 = smoothstep(0.30, 0.32, l2);
    let s2 = smoothstep(0.66, 0.68, l2);
    var base = cFace;
    if (fc > 1.5) { base = cSide; } else if (fc > 0.5) { base = mix(cEdge, cFace, 0.12); }
    var ca = mix(base * vec3<f32>(0.50, 0.46, 0.72), base * 0.88, s1);
    ca = mix(ca, base * 1.12 + vec3<f32>(0.04), s2);
    let rr = reflect(rd, n);
    ca = mix(ca, vec3<f32>(1.0), smoothstep(0.80, 0.82, abs(dot(rr, L))) * 0.8 * select(0.0, 1.0, fc < 0.5));      // specular shape
    ca = mix(ca, base * 1.25 + vec3<f32>(0.10), smoothstep(0.78, 0.80, 1.0 - ndv) * 0.5 * s1);                       // rim light
    ca = mix(vec3<f32>(0.03, 0.02, 0.06), ca, smoothstep(0.17, 0.20, ndv));                                           // ink outline
    if (fc > 0.5 && fc < 1.5) { ca = ca * (1.0 + 0.8 * u.kick); }
    return ca * pump;
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
    let cr = cFace * (0.30 + 0.85 * lt * shadow) * ao + refl * (0.22 + 0.55 * fres) + vec3<f32>(1.0) * spec * 0.45;
    return cr * pump;
  }
  var c: vec3<f32>;
  if (fc < 0.5) {
    c = cFace * (0.55 + 0.6 * lit) * (0.8 + 0.4 * ndv);
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
  let D = D0 * (1.0 - 0.55 * fn_);                                // camera distance to the first layer plane
  let px0 = 2.0 / u.res.y;                                        // angular size of a pixel at tan(45 deg) = 1
  let ro = fwd * -D;
  let rd = normalize(fwd + (uv.x * right + uv.y * up) * 2.0);
  var acc = vec3<f32>(0.0);
  var T = 1.0;
  var t = 0.05;
  for (var i = 0u; i < u.steps; i++) {
    let m = mapFacet(ro + rd * t);
    let px = px0 * t;
    if (m.x < px) {
      let alpha = select(select(0.0, 1.0, m.x < 0.3 * px), smoothstep(px, -0.5 * px, m.x), (u.flags & 4u) != 0u);    // edge anti-aliasing (flag)
      acc += T * alpha * facetShade(ro + rd * t, rd, m.y, m.z);
      T = T * (1.0 - alpha);
      if (T < 0.02) { break; }
    }
    t += max(abs(m.x) * 0.9, 0.5 * px);
    if (t > D + 9.0) { break; }
  }
  return vec4<f32>(acc, 1.0 - T);                                  // alpha = coverage: the background colour is added in composite
}

// ---------------------------------------------------------------- scene 1: kaleidoscopic star (mirror folds)
fn mapStar(p0: vec3<f32>) -> vec3<f32> {
  var q = p0;
  let r0 = rot(u.time * 0.15) * q.xz;
  q = vec3<f32>(r0.x, q.y, r0.y);
  let n = 2 + i32(u.complexity * 4.0);
  let tube = TUBE_R + 0.008 * u.kick;
  let sc = 1.0 - 0.3 * u.collapse + 0.5 * u.explode;
  var best = vec3<f32>(1e5, 0.0, 0.5);
  for (var i = 0; i < n; i++) {
    q = abs(q) - vec3<f32>(0.45 + 0.15 * sin(u.seed.x * 6.28), 0.35, 0.25 + 0.1 * u.seed.y) * sc;
    let a1 = rot(0.6 + u.seed.z * 2.0 + u.time * 0.1) * q.xy;
    q = vec3<f32>(a1.x, a1.y, q.z);
    let a2 = rot(0.4 + u.seed.w * 2.0) * q.yz;
    q = vec3<f32>(q.x, a2.x, a2.y);
    let di = sdCapH(q, vec3<f32>(0.0), vec3<f32>(0.0, 0.0, 0.95 * sc), tube);
    if (di.x < best.x) { best = vec3<f32>(di.x, f32(i % 3), di.y); }
  }
  return best;
}

fn map(p: vec3<f32>) -> vec3<f32> {
  return mapStar(p);
}

fn palette(id: f32) -> vec3<f32> {
  let i = i32(id);
  if (i == 0) { return u.pal0.xyz; }
  if (i == 1) { return u.pal1.xyz; }
  return u.pal2.xyz;
}

// Per-generator glow normalisation: more overlapping tubes (star, high complexity) must not blow out.
fn glow_gain() -> f32 {
  return 1.0 / (1.0 + 0.8 * u.complexity);
}

fn calcNormal(p: vec3<f32>) -> vec3<f32> {
  let e = vec2<f32>(0.0015, -0.0015);
  return normalize(e.xyy * map(p + e.xyy).x + e.yyx * map(p + e.yyx).x + e.yxy * map(p + e.yxy).x + e.xxx * map(p + e.xxx).x);
}

// Lightsaber-style blade: saturated colour body, a narrow near-white core, no hardware. The colour comes from the
// glow around it (see march), so the body is kept below clipping to stay coloured instead of washing out to white.
fn shadeTube(p: vec3<f32>, rd: vec3<f32>, id: f32, h: f32) -> vec3<f32> {
  let n = calcNormal(p);
  let ndv = clamp(abs(dot(n, -rd)), 0.0, 1.0);
  let col = palette(id);
  let core = smoothstep(0.70, 0.98, ndv);
  let power = 1.25 * (1.0 + 0.45 * u.kick + 0.25 * u.bass);
  return mix(col * (0.75 + 0.35 * ndv), mix(col, vec3<f32>(1.0), 0.8), core * 0.95) * power;
}

// One ray through the scene: opaque-ish tube surfaces (front-to-back) plus a tight halo from the neon light.
fn march(ro: vec3<f32>, rd: vec3<f32>, tmax: f32, atten: f32) -> vec3<f32> {
  var acc = vec3<f32>(0.0);
  var T = 1.0;
  var t = 0.02;
  let pa = 1.0 / (u.res.y * u.fov);
  for (var i = 0u; i < u.steps; i++) {
    let h = map(ro + rd * t);
    let pw = t * pa;
    let step = max(abs(h.x) * 0.8, 0.5 * pw);
    acc += T * palette(h.y) * (step * 0.0055 * glow_gain() / (h.x * h.x + 0.0012)) * atten * exp(-t * 0.09);
    if (h.x < 1.2 * pw) {
      let alpha = smoothstep(1.2 * pw, -0.3 * pw, h.x);
      if (alpha > 0.01) {
        acc += T * alpha * shadeTube(ro + rd * t, rd, h.y, h.z) * atten;
        T = T * (1.0 - alpha);
        if (T < 0.03) { break; }
      }
    }
    t += step;
    if (t > tmax) { break; }
  }
  return acc;
}

// Ray tree: the primary ray plus mirror reflections on a glossy floor (the "ray tracing" knob).
fn trace(ro0: vec3<f32>, rd0: vec3<f32>) -> vec3<f32> {
  var ro = ro0;
  var rd = rd0;
  var acc = vec3<f32>(0.0);
  var atten = 1.0;
  let has_floor = false;
  for (var b = 0u; b <= u.bounces; b++) {
    var tmax = 16.0;
    var hit = false;
    if (has_floor && rd.y < -0.001) {
      let tf = (FLOOR_Y - ro.y) / rd.y;
      if (tf > 0.0 && tf < tmax) { tmax = tf; hit = true; }
    }
    acc += march(ro, rd, tmax, atten);
    if (!hit) { break; }
    ro = ro + rd * tmax;
    acc += atten * vec3<f32>(0.0012, 0.0018, 0.0042);        // faint floor sheen
    rd = vec3<f32>(rd.x, -rd.y, rd.z);
    ro = ro + rd * 0.02;
    atten = atten * 0.45;
  }
  return acc;
}

@fragment
fn fs(in: VOut) -> @location(0) vec4<f32> {
  let frag = vec2<f32>(in.pos.x, u.res.y - in.pos.y);
  let uv = (frag - 0.5 * u.res) / u.res.y;
  let yaw = u.cam.x;
  let pitch = u.cam.y;
  let dist = u.cam.z;
  let ro = vec3<f32>(dist * sin(yaw) * cos(pitch), dist * sin(pitch) + 0.3, -dist * cos(yaw) * cos(pitch));
  let fwd = normalize(-ro);
  let right = normalize(cross(vec3<f32>(0.0, 1.0, 0.0), fwd));
  let up = cross(fwd, right);
  if (u.gen == 0u) { let f = facetFrag(uv); return vec4<f32>(f.rgb * u.gain * u.fade, f.a); }
  let rd = normalize(uv.x * right + uv.y * up + u.fov * fwd);
  var col = trace(ro, rd) * u.gain * u.fade;
                                                           // HDR out: tone mapping happens in composite.wgsl
  return vec4<f32>(col, clamp(max(col.r, max(col.g, col.b)) * 2.0, 0.0, 1.0));      // coverage for the background colour
}
