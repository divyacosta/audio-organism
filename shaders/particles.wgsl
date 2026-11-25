// Particles on the GPU: a compute pass moves up to 262144 of them (flow, burst on the kick, or orbit) and an instanced draw lays them over the
// picture as soft additive points. Positions are in a screen-like space: x in [-aspect, aspect], y in [-1, 1], z is depth (0 near).
struct P { pos: vec4<f32>, vel: vec4<f32> };               // pos.xyz + life, vel.xyz + seed
struct S {
  dt: f32, time: f32, bass: f32, kick: f32,
  mid: f32, high: f32, count: f32, mode: f32,
  size: f32, aspect: f32, amount: f32, trail: f32,                       // trail: 0 points, up to ~1 long streaks behind them (the trail only on the particles)
  c0: vec4<f32>, c1: vec4<f32>,
};
@group(0) @binding(0) var<storage, read_write> pw: array<P>;
@group(0) @binding(1) var<storage, read> pr: array<P>;
@group(0) @binding(2) var<uniform> s: S;

fn hash(x: f32) -> f32 { return fract(sin(x * 127.1 + 311.7) * 43758.5453); }
fn hash3(x: f32) -> vec3<f32> { return vec3<f32>(hash(x), hash(x + 17.3), hash(x + 41.9)); }

fn flow(p: vec3<f32>, t: f32) -> vec3<f32> {
  let a = sin(p.y * 2.1 + t * 0.7) + cos(p.z * 1.7 - t * 0.5);
  let b = sin(p.z * 2.3 + t * 0.6) + cos(p.x * 1.9 + t * 0.4);
  let c = sin(p.x * 2.0 - t * 0.5) + cos(p.y * 2.4 + t * 0.3);
  return vec3<f32>(a, b, c) * 0.5;
}

@compute @workgroup_size(256)
fn update(@builtin(global_invocation_id) id: vec3<u32>) {
  let i = id.x;
  if (f32(i) >= s.count) { return; }
  var p = pw[i];
  var pos = p.pos.xyz;
  var vel = p.vel.xyz;
  var life = p.pos.w;
  let seed = f32(i) * 0.37 + 1.0;
  let mode = i32(s.mode + 0.5);
  life = life - s.dt * (0.12 + 0.25 * hash(seed));
  var respawn = life <= 0.0;
  if (mode == 1 && s.kick > 0.5 && hash(seed + floor(s.time * 30.0)) < 0.06) { respawn = true; }   // burst: part of them restart at the centre on every kick
  if (respawn) {
    let r = hash3(seed + s.time * 13.0);
    life = 0.6 + 0.8 * r.z;
    if (mode == 1) {
      let a = r.x * 6.2831853;
      pos = vec3<f32>(cos(a), sin(a), 0.0) * 0.02 + vec3<f32>(0.0, 0.0, r.y * 0.6);
      vel = vec3<f32>(cos(a), sin(a), (r.y - 0.5) * 0.2) * (0.35 + 0.9 * r.z) * (0.6 + 1.4 * s.kick);
    } else if (mode == 2) {
      let a = r.x * 6.2831853;
      let rad = 0.25 + 0.75 * r.y;
      pos = vec3<f32>(cos(a) * rad * s.aspect * 0.8, sin(a) * rad, r.z * 1.5);
      vel = vec3<f32>(0.0);
    } else {
      pos = vec3<f32>((r.x * 2.0 - 1.0) * s.aspect, r.y * 2.0 - 1.0, r.z * 2.5);
      vel = vec3<f32>(0.0);
    }
  }
  if (mode == 1) {
    vel = vel * pow(0.35, s.dt) + vec3<f32>(0.0, -0.03, 0.0) * s.dt;                    // burst: drag and a little weight
    pos = pos + vel * s.dt;
  } else if (mode == 2) {
    let r = length(pos.xy / vec2<f32>(s.aspect * 0.8, 1.0));
    let sp = (0.25 + 0.5 * s.mid + 0.8 * s.bass) / max(r, 0.2);
    let c = cos(sp * s.dt);
    let sn = sin(sp * s.dt);
    pos = vec3<f32>(pos.x * c - pos.y * sn, pos.x * sn + pos.y * c, pos.z);
    pos = pos * (1.0 + (s.kick * 0.9) * s.dt);                                        // the ring breathes with the kick
  } else {
    let speed = 0.25 + 0.7 * s.mid + 0.5 * s.bass;
    pos = pos + flow(pos, s.time) * speed * s.dt;
    pos.z = pos.z - (0.15 + 0.4 * s.bass) * s.dt;                                      // drifting towards the viewer
    if (pos.z < 0.0) { pos.z = pos.z + 2.5; }
    if (abs(pos.x) > s.aspect * 1.2 || abs(pos.y) > 1.2) { life = 0.0; }
  }
  pw[i] = P(vec4<f32>(pos, life), vec4<f32>(vel, seed));
}

struct VO { @builtin(position) pos: vec4<f32>, @location(0) q: vec2<f32>, @location(1) col: vec4<f32>, @location(2) tr: f32 };

fn motion(p: P) -> vec3<f32> {                                        // where a particle is going (the same rules as update)
  let mode = i32(s.mode + 0.5);
  if (mode == 1) { return p.vel.xyz; }
  if (mode == 2) { return vec3<f32>(-p.pos.y, p.pos.x, 0.0) * (0.25 + 0.5 * s.mid + 0.8 * s.bass); }
  return flow(p.pos.xyz, s.time) * (0.25 + 0.7 * s.mid + 0.5 * s.bass) - vec3<f32>(0.0, 0.0, 0.15 + 0.4 * s.bass);
}

@vertex
fn vs(@builtin(vertex_index) vi: u32, @builtin(instance_index) ii: u32) -> VO {
  var corners = array<vec2<f32>, 6>(vec2<f32>(-1.0, -1.0), vec2<f32>(1.0, -1.0), vec2<f32>(-1.0, 1.0), vec2<f32>(-1.0, 1.0), vec2<f32>(1.0, -1.0), vec2<f32>(1.0, 1.0));
  let q = corners[vi];
  let p = pr[ii];
  let persp = 1.0 / (1.0 + p.pos.z * 0.55);
  let c = vec2<f32>(p.pos.x * persp / s.aspect, p.pos.y * persp);
  let sz = s.size * persp * (0.7 + 0.8 * s.high) * 0.012;
  var o: VO;
  o.pos = vec4<f32>(c + q * vec2<f32>(sz / s.aspect, sz), 0.0, 1.0);
  o.q = q;
  o.tr = 0.0;
  if (s.trail > 0.01) {                                               // a streak: the quad runs from a little ahead of the point back along where it came from
    let v = motion(p);
    let back = p.pos.xyz - v * (0.25 + 1.2 * s.trail);
    let pb = 1.0 / (1.0 + max(back.z, 0.0) * 0.55);
    let cb = vec2<f32>(back.x * pb / s.aspect, back.y * pb);
    var dir = c - cb;
    let len_ = length(dir * vec2<f32>(s.aspect, 1.0));
    if (len_ > 1e-4) {
      dir = dir / len_;
      let nrm = vec2<f32>(-dir.y, dir.x);
      let t = q.y * 0.5 + 0.5;                                            // 0 tail, 1 head
      let along = mix(cb, c + dir * vec2<f32>(1.0 / s.aspect, 1.0) * sz, t);
      o.pos = vec4<f32>(along + nrm * vec2<f32>(1.0 / s.aspect, 1.0) * q.x * sz * 0.6, 0.0, 1.0);
      o.tr = 1.0;
    }
  }
  let h = hash(p.vel.w);
  let fade = smoothstep(0.0, 0.25, p.pos.w) * clamp(p.pos.w * 1.5, 0.0, 1.0);
  let tint = mix(s.c0.rgb, s.c1.rgb, h);
  let glow = (0.5 + 1.6 * s.kick + 0.6 * s.high) * s.amount * persp * fade * select(1.0, 0.3, s.mode > 0.5 && s.mode < 1.5);       // the burst piles up at the centre: dimmer
  o.col = vec4<f32>(tint * glow, glow * 0.6);
  return o;
}

@fragment
fn fs(in: VO) -> @location(0) vec4<f32> {
  if (in.tr > 0.5) {                                                    // a streak: soft across, brighter at the head
    let t = in.q.y * 0.5 + 0.5;
    return in.col * exp(-in.q.x * in.q.x * 3.0) * t * t;
  }
  let d = dot(in.q, in.q);
  let a = exp(-d * 4.0) * step(d, 1.0);
  return in.col * a;
}
