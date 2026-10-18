"""Real-time music analysis: RMS, spectral flux onsets (kick/snare/hat), adaptive
normalisation, BPM estimation, energy tracking, drop / breakdown / silence detection."""
import collections
import math
import random
import threading
import time

import numpy as np

HOP = 512
WIN = 2048
RING = 1 << 17
N_BANDS = 64


class Capture:
    """WASAPI loopback capture into a ring buffer (mono float32)."""

    def __init__(self):
        import pyaudiowpatch as pyaudio
        self.pyaudio = pyaudio
        self.pa = pyaudio.PyAudio()
        self.ring = np.zeros(RING, np.float32)
        self.w = 0
        self.lock = threading.Lock()
        self.stream = None
        self.dev_index = None
        self.rate = 48000
        self.frames = 1024
        self.open()

    def open(self):
        pyaudio = self.pyaudio
        dev = self.pa.get_default_wasapi_loopback()
        self.dev_index = dev["index"]
        self.rate = int(dev["defaultSampleRate"])
        ch = dev["maxInputChannels"]

        def cb(data, frames, t, status):
            x = np.frombuffer(data, dtype=np.float32).reshape(-1, ch).mean(axis=1)
            n = len(x)
            with self.lock:
                i = self.w % RING
                if i + n <= RING:
                    self.ring[i:i + n] = x
                else:
                    k = RING - i
                    self.ring[i:] = x[:k]
                    self.ring[:n - k] = x[k:]
                self.w += n
            return (None, pyaudio.paContinue)

        self.stream = self.pa.open(
            format=pyaudio.paFloat32, channels=ch, rate=self.rate, input=True,
            input_device_index=dev["index"], frames_per_buffer=self.frames, stream_callback=cb,
        )

    def default_changed(self):
        try:
            return self.pa.get_default_wasapi_loopback()["index"] != self.dev_index
        except Exception:
            return False

    def reopen(self):
        try:
            self.stream.stop_stream()
            self.stream.close()
        except Exception:
            pass
        try:
            self.pa.terminate()
        except Exception:
            pass
        self.pa = self.pyaudio.PyAudio()
        self.open()

    def take(self, r):
        with self.lock:
            w = self.w
            if r is None or w - r > RING - 8 * HOP:
                r = w
            if w <= r:
                return np.zeros(0, np.float32), r
            data = self.ring[np.arange(r, w) % RING].copy()
        return data, w

    def close(self):
        try:
            self.stream.stop_stream()
            self.stream.close()
            self.pa.terminate()
        except Exception:
            pass


class Band:
    """Adaptive-normalised band tracker with spectral-flux onset detection."""

    def __init__(self, hop_dt, refractory, pmin=1.5):
        self.dt = hop_dt
        self.v = 0.0
        self.pmin = pmin
        self.peak = pmin
        self.floor = 0.0
        self.norm = 0.0
        self.flux = 0.0
        self.f1 = 0.0
        self.f2 = 0.0
        self.hist = collections.deque(maxlen=int(1.0 / hop_dt))
        self.ref = refractory
        self.since = 1e9
        self.k_peak = math.exp(-hop_dt / 30.0)
        self.k_floor = hop_dt / 10.0

    def push(self, amp):
        v = math.log1p(amp * 200.0)
        self.peak = max(v, self.peak * self.k_peak, self.pmin)
        if v < self.floor:
            self.floor = v
        else:
            self.floor += (v - self.floor) * self.k_floor
        rng = max(self.peak - self.floor, 0.45)
        self.norm = min(1.0, max(0.0, (v - self.floor) / rng))
        flux = max(0.0, v - self.v) / rng
        self.v = v
        self.since += self.dt
        hit = 0.0
        # peak-pick the previous sample against an adaptive threshold
        if len(self.hist) > 10:
            h = np.fromiter(self.hist, float)
            thr = h.mean() + 1.5 * h.std() + 0.05
        else:
            thr = 1e9
        if self.f1 > thr and self.f1 >= self.f2 and self.f1 >= flux and self.since > self.ref:
            hit = min(1.0, max(0.25, self.f1 / 0.35))
            self.since = 0.0
        self.hist.append(flux)
        self.f2, self.f1 = self.f1, flux
        self.flux = flux
        return hit


class Analyzer:
    def __init__(self, rate):
        self.rate = rate
        self.hop_dt = HOP / rate
        self.hop_rate = rate / HOP
        self.buf = np.zeros(WIN, np.float32)
        self.pending = np.zeros(0, np.float32)
        self.win = np.hanning(WIN).astype(np.float32)
        freqs = np.fft.rfftfreq(WIN, 1.0 / rate)

        def sl(lo, hi):
            a = int(np.searchsorted(freqs, lo))
            return a, max(int(np.searchsorted(freqs, hi)), a + 1)

        self.sl = {"kick": sl(40, 120), "bass": sl(20, 200), "body": sl(150, 330),
                   "mid": sl(250, 4000), "snare": sl(1800, 6500), "high": sl(6500, 16000)}
        edges = np.logspace(math.log10(30), math.log10(min(16000, rate / 2 - 1)), N_BANDS + 1)
        self.edges = []
        for i in range(N_BANDS):
            a = int(np.searchsorted(freqs, edges[i]))
            self.edges.append((a, max(int(np.searchsorted(freqs, edges[i + 1])), a + 1)))
        hd = self.hop_dt
        self.b = {"kick": Band(hd, 0.14, 1.8), "bass": Band(hd, 0.1, 1.8), "body": Band(hd, 0.1, 1.5),
                  "mid": Band(hd, 0.1, 1.6), "snare": Band(hd, 0.07, 1.2), "high": Band(hd, 0.05, 0.9)}
        self.hits_t = collections.deque(maxlen=64)
        self.bands = np.zeros(N_BANDS)
        self.band_peak = 0.5
        # onset envelope for BPM
        self.env = collections.deque(maxlen=int(8 * self.hop_rate))
        self.hop_count = 0
        self.bpm = 0.0
        self.conf = 0.0
        self.pend_bpm = 0.0
        self.pend_n = 0
        self.phase = 0.0
        # per-frame outputs
        self.kick = self.snare = self.hat = 0.0
        self.kick_hit = self.snare_hit = self.hat_hit = 0.0
        self.bass = self.mid = self.high = 0.0
        self.ei = 0.0
        self.e_vfast = self.e_fast = self.energy = self.e_slow = self.e_long = 0.0
        self.high_slow = 0.0
        self.calm_t = 0.0
        self.bd_min = 1.0
        self.bd_min_last = 0.2
        self.breakdown_flag = False
        self.bd = 0.0
        self.drop = 0.0
        self.drop_b = 0.0
        self.drop_event = 0.0
        self.drop_cd = 0.0
        self.tension = 0.0
        self.now_t = 0.0
        self.hit_ts = collections.deque(maxlen=256)
        self.roll = 0.0
        self.strobe_phase = 0.0
        self.strobe_amp = 0.0
        self.strobe = 0.0
        self.flash = 0.0
        self.drop_flash = 0.0
        self.beat_n = 0
        self.max_sub = 8
        self.bursts_enabled = True
        self.pp = 0.0
        self.burst_left = 0
        self.burst_cd = 6.0
        self.burst_amp = 0.0
        self.burst_pulse = 0.0
        self.burst_event = 0.0
        self.rms = 0.0
        self.sil_t = 0.0
        self.silence = 0.0
        self.lf = -90.0                                  # short-term loudness, dB (about 0.5 s)
        self.l_hist = collections.deque(maxlen=int(60 * 60))   # last 60 s of loudness, one value per frame
        self.l_ref = -30.0                               # the track's own "full" level: 85th percentile of the recent loudness
        self.active_t = 0.0                              # seconds since the music started (or came back after a silence)
        self.was_silent = True
        self.sec_t = 0.0
        # rhythm counter: bar / phrase position from the tracked beat and the kick, plus the rhythm of the melody on a 16-step grid
        self.beat_in_bar = 0                              # 0..3 (0 = the downbeat, "the one")
        self.bar_n = -1                                   # bars since the music (or the last drop) started
        self.phrase_len = 8                               # bars per phrase
        self.beat_event = self.bar_event = self.phrase_event = 0.0
        self.down_acc = np.zeros(4)                       # kick / bass weight at each of the 4 beat positions: the heaviest one is the downbeat
        self.down_off = 0
        self.kick_grid = np.zeros(16)
        self.mel_grid = np.zeros(16)
        self.mel_count = 0
        self.mel_density = 0.0                            # 0..1: melody notes per bar (12 = full)
        self.mel_hit = 0.0                                # envelope of the melody notes
        self.mel_ev = 0.0
        self._hm = 0.0
        self.wave = collections.deque(maxlen=256)         # (min, max) of every hop: the waveform of the last ~2.7 s
        self.wave_peak = 0.05
        self.fading = False                              # a slow fade-out (end of a track), not a breakdown
        self.low = False                                 # loudness well under the track's level (hysteresis)
        self.cand, self.cand_t = "CALM", 0.0             # state candidate and how long it has been stable
        self.wC = 1.0
        self.wG = self.wH = 0.0
        self.state = "CALM"
        self.last_t = None
        self.last_data = 0.0
        self.r = None
        self._hk = self._hs = self._hh = 0.0
        self._rms_hop = 0.0

    # ------------------------------------------------------------------ input
    def pump(self, cap, now):
        data, self.r = cap.take(self.r)
        dtw = 0.0 if self.last_t is None else now - self.last_t
        self.last_t = now
        if len(data):
            self.last_data = now
            self.feed(data)
        elif now - self.last_data > 0.12:       # loopback delivers nothing while silent
            self.feed(np.zeros(int(min(dtw, 0.1) * self.rate), np.float32))

    def feed(self, chunk):
        self.pending = np.concatenate((self.pending, chunk.astype(np.float32)))
        if len(self.pending) > 16 * HOP:
            self.pending = self.pending[-16 * HOP:]
        while len(self.pending) >= HOP:
            c, self.pending = self.pending[:HOP], self.pending[HOP:]
            self._hop(c)

    # ------------------------------------------------------------------- hop
    def _hop(self, chunk):
        self.buf = np.concatenate((self.buf[HOP:], chunk))
        self._rms_hop = float(np.sqrt(np.mean(chunk * chunk)))
        mag = np.abs(np.fft.rfft(self.buf * self.win)) * (4.0 / WIN)
        amp = {k: float(np.sqrt(np.mean(mag[a:b] ** 2))) for k, (a, b) in self.sl.items()}
        hk = self.b["kick"].push(amp["kick"])
        self.b["bass"].push(amp["bass"])
        hb = self.b["body"].push(amp["body"])
        hm = self.b["mid"].push(amp["mid"])
        hs = self.b["snare"].push(amp["snare"])
        hh = self.b["high"].push(amp["high"])
        if hk > self.b["kick"].norm * 0 and self.b["bass"].norm < 0.12:
            hk = 0.0
        snare_hit = max(hs, hb * 0.0 if hs == 0 else hb)
        if hk or snare_hit:
            self.hits_t.append(self.hop_count * self.hop_dt)
        if hm and not hs:                                      # a note of the melody: a mid-band onset that is not the snare
            self._hm = max(self._hm, hm)
        lo, hi_ = float(chunk.min()), float(chunk.max())
        self.wave.append((lo, hi_))
        self.wave_peak = max(abs(lo), abs(hi_), self.wave_peak * math.exp(-self.hop_dt / 4.0), 0.02)
        self._hk = max(self._hk, hk)
        self._hs = max(self._hs, snare_hit)
        self._hh = max(self._hh, hh)
        self.ei = 0.5 * self.b["bass"].norm + 0.3 * self.b["mid"].norm + 0.2 * self.b["high"].norm
        # log spectrum bands for the GPU
        raw = np.log1p(np.array([mag[a:b].mean() for a, b in self.edges]) * 200.0)
        self.band_peak = max(raw.max(), self.band_peak * math.exp(-self.hop_dt / 15.0), 0.4)
        nb = np.clip(raw / self.band_peak, 0, 1) ** 1.6
        self.bands = np.where(nb > self.bands, nb, self.bands * math.exp(-self.hop_dt / 0.12) + nb * 0.0)
        # onset envelope + BPM
        b = self.b
        self.env.append(b["kick"].flux + 0.6 * b["snare"].flux + 0.3 * b["body"].flux + 0.25 * b["high"].flux)
        self.hop_count += 1
        if self.hop_count % int(0.5 * self.hop_rate) == 0:
            self._estimate_bpm()
        # silence
        self.rms += (self._rms_hop - self.rms) * 0.3
        if self.rms < 1.4e-3 or self.lf < self.l_ref - 40.0:          # below -57 dBFS, or 40 dB under the track's own level
            self.sil_t += self.hop_dt
        else:
            self.sil_t = 0.0
        # beat-phase nudge from real kick onsets
        if hk > 0 and self.conf > 0.3 and self.bpm > 0:
            err = self.phase if self.phase < 0.5 else self.phase - 1.0
            if abs(err) < 0.25:
                self.phase -= err * 0.35

    def _estimate_bpm(self):
        n = len(self.env)
        if n < 4 * self.hop_rate:
            return
        env = np.array(self.env, np.float32)
        env -= env.mean()
        now = self.hop_count * self.hop_dt
        recent = sum(1 for t in self.hits_t if now - t < 8.0)
        if float(env.std()) < 0.02 or recent < 6:
            self.conf *= 0.85
            return
        env = np.convolve(env, [0.25, 0.5, 0.25], "same")
        nf = 1 << int(math.ceil(math.log2(2 * n)))
        F = np.fft.rfft(env, nf)
        ac = np.fft.irfft(F * np.conj(F))[:n]
        ac = ac / (ac[0] + 1e-9)
        bpms = np.arange(70.0, 180.5, 0.5)
        lag = 60.0 / bpms * self.hop_rate

        def at(l):
            i = np.minimum(l.astype(int), n - 2)
            fr = l - i
            return ac[i] * (1 - fr) + ac[i + 1] * fr

        s = at(lag) + 0.5 * at(np.minimum(2 * lag, n - 2)) + 0.25 * at(np.minimum(4 * lag, n - 2))
        prior = np.exp(-0.5 * (np.log2(bpms / 125.0) / 0.7) ** 2)
        s = s * (0.6 + 0.4 * prior)
        i = int(np.argmax(s))
        best = float(s[i])
        c = max(0.0, min(1.0, (best - float(np.median(s))) / (abs(best) + 1e-9)))
        cand = float(bpms[i])
        self.conf += (c - self.conf) * 0.35
        if self.bpm == 0:
            if c > 0.25:
                self.bpm = cand
            return
        ratio = cand / self.bpm
        if abs(ratio - 1) < 0.05:
            self.bpm += (cand - self.bpm) * 0.3
            self.pend_n = 0
        elif c > 0.35:
            if self.pend_n and abs(cand / self.pend_bpm - 1) < 0.04:
                self.pend_n += 1
            else:
                self.pend_bpm, self.pend_n = cand, 1
            octave = abs(ratio - 2) < 0.08 or abs(ratio - 0.5) < 0.04
            odd = any(abs(ratio - r) < 0.05 for r in (4 / 3, 0.75, 1.5, 2 / 3))      # a 3:4 or 2:3 relation is almost always a wrong guess, not a tempo change
            if self.pend_n >= (10 if odd else 6 if octave else 3):
                self.bpm, self.pend_n = cand, 0
        else:
            self.pend_n = 0

    # ----------------------------------------------------------------- frame
    def update(self, dt):
        k = lambda tau: 1.0 - math.exp(-dt / tau)
        # transient envelopes
        self.kick_hit, self.snare_hit, self.hat_hit = self._hk, self._hs, self._hh
        self._hk = self._hs = self._hh = 0.0
        self.kick = max(self.kick * math.exp(-dt / 0.16), self.kick_hit)
        self.snare = max(self.snare * math.exp(-dt / 0.12), self.snare_hit)
        self.hat = max(self.hat * math.exp(-dt / 0.06), self.hat_hit)
        self.now_t += dt
        if self.kick_hit or self.snare_hit:
            self.hit_ts.append(self.now_t)
        r1 = sum(1 for t in self.hit_ts if self.now_t - t < 1.0)
        rb = sum(1 for t in self.hit_ts if 1.0 <= self.now_t - t < 5.0) / 4.0
        roll_t = max(0.0, min(1.0, (r1 - 1.6 * max(rb, 1.5) - 1.0) / 4.0))
        self.roll += (roll_t - self.roll) * k(0.3)
        # smoothed band intensities
        for name, tgt in (("bass", self.b["bass"].norm), ("mid", self.b["mid"].norm), ("high", self.b["high"].norm)):
            cur = getattr(self, name)
            setattr(self, name, cur + (tgt - cur) * k(0.04 if tgt > cur else 0.2))
        # energy
        self.e_vfast += (self.ei - self.e_vfast) * k(0.12)
        self.e_fast += (self.ei - self.e_fast) * k(0.5)
        self.energy += (self.ei - self.energy) * k(1.5)
        self.e_slow += (self.ei - self.e_slow) * k(8.0)
        self.e_long += (self.ei - self.e_long) * k(25.0)
        self.high_slow += (self.high - self.high_slow) * k(6.0)
        # silence
        tgt = 1.0 if self.sil_t > 0.5 else 0.0
        self.silence += (tgt - self.silence) * k(0.6 if tgt > self.silence else 0.15)
        # loudness in dB against the track's own level (what the ear calls "the part of the song")
        ldb = 20.0 * math.log10(self.rms + 1e-6)
        self.lf += (ldb - self.lf) * k(0.5)
        self.l_hist.append(self.lf)
        self.sec_t += dt
        if self.sec_t > 0.5 and len(self.l_hist) > 120:
            self.sec_t = 0.0
            h = np.fromiter(self.l_hist, np.float32)
            h = h[h > -50.0]
            if len(h) > 60:
                self.l_ref = float(np.percentile(h, 85))
            hl = list(self.l_hist)
            if len(hl) > 480:
                l1, l3, l7 = sum(hl[-30:]) / 30.0, sum(hl[-210:-150]) / 60.0, sum(hl[-480:-420]) / 60.0
                self.fading = (l1 - l7 < -8.0 and l1 < l3 - 2.0)
            else:
                self.fading = False
        if self.silence > 0.6:
            self.was_silent = True
            self.active_t = 0.0
        elif self.was_silent and self.silence < 0.3:           # the music is back: everything that was learned about the last track is stale
            self.was_silent = False
            self.tension = 0.0
            self.calm_t = 0.0
            self.breakdown_flag = False
            self.l_hist.clear()
            self.bar_n, self.down_acc[:] = -1, 0.0
            self.kick_grid[:] = self.mel_grid[:] = 0.0
            self.e_long = self.e_slow = self.energy
        else:
            self.active_t += dt
        warm = self.active_t > 6.0 and not self.was_silent
        if self.lf < self.l_ref - 7.0:
            self.low = True
        elif self.lf > self.l_ref - 4.5:
            self.low = False
        # beat phase advance
        if self.bpm > 0:
            self.phase = (self.phase + dt * self.bpm / 60.0) % 1.0
        # breakdown / drop
        if self.e_fast < min(0.30, 0.65 * self.e_long):
            self.calm_t += dt
        elif self.e_fast > 0.85 * self.e_long and self.e_fast > 0.2:
            self.calm_t = 0.0
        if self.calm_t > 1.2:
            self.bd_min = min(self.bd_min, self.e_fast)
        else:
            self.bd_min = 1.0
        flag = (self.calm_t > 1.2 or self.low) and self.silence < 0.5 and warm and not self.fading
        self.bd += ((1.0 if flag else 0.0) - self.bd) * k(0.5)
        self.drop_cd = max(0.0, self.drop_cd - dt)
        self.drop_event = 0.0
        strong = self.kick_hit > 0.4 and self.b["bass"].norm > 0.5
        after_break = self.breakdown_flag and self.ei > 2.0 * max(self.bd_min_last, 0.05) + 0.12 and strong
        sudden = (self.e_vfast - self.e_slow) > 0.33 and strong
        n_h = len(self.l_hist)
        db_jump = False
        if warm and n_h > 600:                                    # a clear step up, from a low part to the track's full level
            hh = self.l_hist
            l1 = sum(list(hh)[-60:]) / 60.0
            lb = sum(list(hh)[-480:-120]) / 360.0
            db_jump = (l1 - lb > 5.0 and self.kick_hit > 0.3)
        if (warm and (after_break or sudden or db_jump)) and self.drop_cd <= 0:
            self.drop = 1.0
            self.drop_b = 1.0
            self.drop_event = 1.0
            self.drop_cd = 8.0
        if after_break:
            self.breakdown_flag = False
            self.calm_t = 0.0
        if flag:
            self.breakdown_flag = True
            self.bd_min_last = self.bd_min
        self.drop *= math.exp(-dt / 3.0)
        self.drop_b *= math.exp(-dt / 0.6)
        # tension / build-up
        build = max(0.0, min(1.0, (self.e_fast - self.e_slow) * 2.5 + (self.high - self.high_slow) * 1.5 + 0.6 * self.roll))
        if self.drop_event:
            self.tension = 0.0
        if not warm:
            build = 0.0
        self.tension += (build - self.tension) * k(1.5)
        # background lighting: BPM-synced strobe that accelerates with the build-up, flashes on rolls and drops
        act = self.tension > 0.35 and self.drop < 0.3 and self.silence < 0.5
        amp_t = max(0.0, min(1.0, (self.tension - 0.3) / 0.5)) if act else 0.0
        self.strobe_amp += (amp_t - self.strobe_amp) * k(0.15)
        t_ = self.tension
        sub = min(self.max_sub, 1 if t_ < 0.5 else 2 if t_ < 0.7 else 4 if t_ < 0.85 else 8)
        rate = (self.bpm / 60.0 if self.bpm > 0 else 2.0) * sub
        self.strobe_phase = (self.strobe_phase + dt * rate) % 1.0
        self.strobe = math.exp(-self.strobe_phase * 7.0) * self.strobe_amp
        self.flash *= math.exp(-dt / 0.08)
        if self.snare_hit and self.roll > 0.3:
            self.flash = max(self.flash, 0.5 + 0.5 * self.roll)
        self.drop_flash *= math.exp(-dt / 0.35)
        if self.drop_event:
            self.drop_flash = 1.0
        # occasional 1/4-beat (16th-note) stutter bursts, aligned to the tracked beat phase
        self.burst_event = 0.0
        self.burst_cd = max(0.0, self.burst_cd - dt)
        if self.pp - self.phase > 0.5:                      # beat boundary
            self.beat_n += 1
            if self.burst_left > 0:
                self.burst_left -= 1
            if (self.burst_left == 0 and self.burst_cd <= 0 and self.bpm > 0 and self.conf > 0.4
                    and self.energy > 0.2 and self.drop < 0.3 and self.silence < 0.5
                    and self.bursts_enabled and self.beat_n % 4 == 3 and random.random() < 0.5):
                self.burst_left = 2 if random.random() < 0.3 else 1
                self.burst_cd = random.uniform(10.0, 22.0)
                self.burst_event = 1.0
        self._rhythm(dt)
        self.pp = self.phase
        self.burst_amp += ((1.0 if self.burst_left > 0 else 0.0) - self.burst_amp) * k(0.03)
        self.burst_pulse = math.exp(-((self.phase * 4.0) % 1.0) * 6.0) * self.burst_amp * 0.75
        # state weights
        E = self.energy
        wC = 1.0 - _ss(0.16, 0.30, E)
        wH = _ss(0.42, 0.60, E)
        wG = max(0.0, 1.0 - wC - wH)
        for nm, v in (("wC", wC), ("wG", wG), ("wH", wH)):
            setattr(self, nm, getattr(self, nm) + (v - getattr(self, nm)) * k(0.7))
        if self.silence > 0.6:
            want = "SILENCE"
        elif self.drop > 0.35:
            want = "DROP"
        elif self.bd > 0.5:
            want = "BREAKDOWN"
        else:
            want = ("CALM", "GROOVE", "HIGH ENERGY")[int(np.argmax([self.wC, self.wG, self.wH]))]
        # a part of a song lasts seconds, not frames: silence and drops show at once, everything else must hold for 2.5 s
        if want in ("SILENCE", "DROP") or self.state in ("SILENCE", "DROP"):
            self.state, self.cand_t = want, 0.0
        elif want == self.state:
            self.cand_t = 0.0
        else:
            self.cand_t = self.cand_t + dt if want == self.cand else 0.0
            self.cand = want
            if self.cand_t >= (1.5 if want == "BREAKDOWN" else 2.5):
                self.state, self.cand_t = want, 0.0

    def _rhythm(self, dt):
        """Beat / bar / phrase counter and the 16-step rhythm of kick and melody. Runs once per frame, after the beat phase advanced."""
        self.beat_event = self.bar_event = self.phrase_event = 0.0
        wrapped = self.pp - self.phase > 0.5                 # a new beat starts
        # which of the 4 beat positions carries the kick: the downbeat
        nb = self.beat_n + (1 if self.phase > 0.5 else 0)    # the beat a hit belongs to (the nearest one)
        if self.kick_hit and self.conf > 0.3:
            self.down_acc[nb % 4] += 0.6 + self.bass
        if wrapped:
            self.down_acc *= 0.97
            best = int(np.argmax(self.down_acc))
            if best != self.down_off and self.down_acc[best] > 1.35 * self.down_acc[self.down_off] + 0.8:      # hysteresis: do not flip-flop
                self.down_off = best
        if self.drop_event and self.bpm > 0:                 # a drop lands on the one
            self.down_off = nb % 4
            self.down_acc[:] = 0.0
            self.down_acc[self.down_off] = 3.0
            self.bar_n = -1
            self.kick_grid[:] = self.mel_grid[:] = 0.0
        if wrapped and self.bpm > 0 and self.silence < 0.5:
            self.beat_event = 1.0
            self.beat_in_bar = (self.beat_n - self.down_off) % 4
            if self.beat_in_bar == 0:
                self.bar_n += 1
                self.bar_event = 1.0
                self.kick_grid *= 0.85
                self.mel_grid *= 0.85
                self.mel_density += (min(1.0, self.mel_count / 12.0) - self.mel_density) * 0.4
                self.mel_count = 0
                if self.bar_n >= 0 and self.bar_n % self.phrase_len == 0:
                    self.phrase_event = 1.0
        # 16-step grid position inside the bar
        step = int(((self.beat_in_bar + self.phase) % 4.0) * 4.0) % 16
        if self.kick_hit and self.bpm > 0:
            self.kick_grid[step] += 1.0
        self.mel_ev = self._hm
        self._hm = 0.0
        if self.mel_ev and self.bpm > 0:
            self.mel_grid[step] += 1.0
            self.mel_count += 1
        self.mel_hit = max(self.mel_hit * math.exp(-dt / 0.14), self.mel_ev)

    @property
    def phrase_pos(self):
        return max(0, self.bar_n) % self.phrase_len

    @property
    def bar_phase(self):
        """0..1 through the bar (continuous)."""
        return ((self.beat_in_bar + self.phase) % 4.0) / 4.0

    @property
    def phrase_phase(self):
        """0..1 through the phrase (continuous)."""
        return ((self.phrase_pos * 4.0 + self.beat_in_bar + self.phase) % (4.0 * self.phrase_len)) / (4.0 * self.phrase_len)

    @property
    def alive(self):
        return 1.0 - 0.92 * self.silence


def _ss(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


class Synth:
    """Synthetic 128 BPM track (calm -> groove -> breakdown -> drop) for tests."""

    def __init__(self, rate=48000, bpm=128.0):
        self.rate, self.bpm, self.t = rate, bpm, 0.0
        self.rng = np.random.default_rng(1)

    def chunk(self, n):
        r = self.rate
        t = self.t + np.arange(n) / r
        self.t += n / r
        bp = 60.0 / self.bpm
        sec = t[0]
        out = np.zeros(n)
        pad = sum(np.sin(2 * np.pi * f * t) for f in (220.0, 277.2, 329.6)) * 0.02
        phase = (t % bp)
        kick = np.sin(2 * np.pi * (45 * phase + 3.5 * (1 - np.exp(-30 * phase)))) * np.exp(-phase * 9)
        hat_ph = (t + bp / 2) % bp
        hat = np.diff(self.rng.standard_normal(n + 1)) * np.exp(-hat_ph * 60)
        hat8 = np.diff(self.rng.standard_normal(n + 1)) * np.exp(-(t % (bp / 2)) * 70)
        sn_ph = (t + bp) % (2 * bp)
        sn_ph = (sn_ph - bp) % (2 * bp)
        snare = self.rng.standard_normal(n) * np.exp(-sn_ph * 16)
        bass = np.sin(2 * np.pi * 55 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * t / (bp * 2)))
        roll = np.zeros(n)
        if 15.0 <= sec < 17.0:
            u = (t - 15.0)
            period = 0.47 * np.exp(-u * 1.15) + 0.05
            ph = np.cumsum(1.0 / period) / r * 1.0
            roll = self.rng.standard_normal(n) * np.exp(-((ph * 0 + (np.modf(np.cumsum(1.0 / period) / r * 1.0)[0] * period)) * 22)) * (0.15 + 0.25 * u / 2)
        if sec < 6:
            out += pad
        elif sec < 14:
            out += pad + 0.5 * kick + 0.07 * hat + 0.1 * bass
        elif sec < 17:
            out += pad * 0.6 + 0.01 * np.diff(self.rng.standard_normal(n + 1)) * (sec - 13) / 3 + roll
        else:
            out += 0.1 * pad + 0.9 * kick + 0.35 * snare + 0.12 * hat8 + 0.3 * bass
        return out.astype(np.float32)


def selftest():
    rate = 48000
    an = Analyzer(rate)
    syn = Synth(rate)
    dt = 1 / 60
    t = 0.0
    kicks = 0
    for f in range(int(32 * 60)):
        an.feed(syn.chunk(int(rate * dt)))
        an.update(dt)
        t += dt
        if an.kick_hit:
            kicks += 1
        if f % 60 == 59:
            print(f"t={t:4.0f}s bpm={an.bpm:6.1f} conf={an.conf:.2f} E={an.energy:.2f} "
                  f"bass={an.bass:.2f} mid={an.mid:.2f} hi={an.high:.2f} state={an.state:10s} "
                  f"drop={an.drop:.2f} bd={an.bd:.2f} kicks={kicks}")


if __name__ == "__main__":
    selftest()
