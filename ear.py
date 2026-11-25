"""What the program hears besides the beat: the chord, the melody note, the brightness, risers, vocals, how busy the rhythm is, the stereo width, repeated
sections and tempo changes. Everything is measured on the same audio the Analyzer already has (no extra packages); each reading comes with a confidence,
and `tiles()` turns them into the captioned meters of the Ao vivo tab.

These are estimates: the chord and the melody are right on clear harmony and wrong on noise, the vocal reading is a guess from the spectrum, and a repeated
section is "the sound is like that of another moment", not a score."""
import collections
import math

import numpy as np

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
WIN = 2048
_MAJ = np.zeros(12)
_MAJ[[0, 4, 7]] = 1.0
_MIN = np.zeros(12)
_MIN[[0, 3, 7]] = 1.0
CHORDS = [(NOTE_NAMES[k] + suffix, np.roll(m, k)) for m, suffix in ((_MAJ, ""), (_MIN, "m")) for k in range(12)]


def mmss(sec):
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


class Ear:
    def __init__(self, rate, hop_dt):
        self.rate, self.hop_dt = rate, hop_dt
        self.freqs = np.fft.rfftfreq(WIN, 1.0 / rate)
        self._cm = (self.freqs > 100) & (self.freqs < 12000)
        self.cen = 0.0                                        # spectral centroid, Hz (smoothed)
        self._cen_hist = collections.deque(maxlen=32)         # log2 of the centroid, 10 per second
        self._cen_acc = 0.0
        self._mins = collections.deque(maxlen=24)             # the last ~0.25 s of spectra: their minimum is the sustained sound, without the drum hits
        self._fl_hist = collections.deque(maxlen=80)          # (log2 centroid, dB above 3 kHz) of that sustained sound, 10 per second
        self.riser = 0.0
        self.vocal = 0.0
        self.density = 0.0                                    # onsets per second
        self._ev = collections.deque()
        self.chord, self.chord_conf = "--", 0.0
        self.chroma = np.zeros(12)
        self.note, self.note_conf, self.note_hz = "--", 0.0, 0.0
        self._note_prev = None
        self.width = 0.0                                      # 0 = mono, 1 = all side (set from the capture)
        self._feats = []                                      # (track time, feature vector), one per second
        self._feat_acc = 0.0
        self._rep_acc = 0.0
        self.repeat_at, self.repeat_sim = None, 0.0
        self._bpm_hist = collections.deque(maxlen=40)
        self._bpm_acc = 0.0
        self.tempo_spread = 0.0
        self._kmag = None
        self._kfreqs = None
        # for the drawings of the Ao vivo tab
        self.hist = {k: collections.deque(maxlen=60) for k in ("cen", "dens", "vol", "tens")}      # 2 per second: the last 30 s
        self._hist_acc = 0.0
        self.chord_seq = []                                   # the last distinct chords, newest last
        self._chord_cand, self._chord_cand_t = "--", 0.0
        self.grid = np.zeros((4, 16))                         # kick, snare, hat, bass hits of this bar on a 16-step grid (strength 0..1)
        self.grid_prev = np.zeros((4, 16))                    # ... and of the bar before
        self.grid_step, self.grid_bar = -1, 0
        self._pos_prev = 0.0
        self._bass_hi = False
        self.peak = np.zeros(64)                              # peak hold of the spectrum
        self.lf_long, self.lf_peak = -60.0, -60.0
        self.lr, self.corr = None, 0.0                        # the latest stereo samples and the phase correlation (set from the capture)
        self.sect = []                                        # [(start, end, label)] of the last minutes, by the sound
        self.sect_now = ""

    # ------------------------------------------------------------------- inputs
    def hop(self, mag):
        """Called with the magnitude spectrum of every analysis hop: the brightness."""
        self._mins.append(mag)
        m = mag[self._cm]
        tot = float(m.sum())
        if tot < 1e-6:
            return
        c = float((self.freqs[self._cm] * m).sum() / tot)
        k = 1.0 - math.exp(-self.hop_dt / 0.5)
        self.cen = c if self.cen <= 0 else self.cen + (c - self.cen) * k

    def key_frame(self, kmag, kfreqs, pc_idx, pc_mask, silent):
        """Called with the long-window spectrum (about 12 times a second): chord, melody note and the vocal estimate."""
        self._kmag, self._kfreqs = kmag, kfreqs
        if silent:
            self.note, self.note_conf, self.chord, self.chord_conf = "--", 0.0, "--", 0.0
            self.vocal *= 0.9
            return
        # chord: a short memory of the chroma against the 24 triads
        ch = np.bincount(pc_idx, weights=kmag[pc_mask] ** 0.8, minlength=12)
        ch = ch / (ch.sum() + 1e-9)
        self.chroma += (ch - self.chroma) * (1.0 - math.exp(-0.083 / 1.2))
        c = self.chroma - self.chroma.mean()
        sc = [float(np.dot(c, t - t.mean())) / (np.linalg.norm(c) * np.linalg.norm(t - t.mean()) + 1e-9) for _, t in CHORDS]
        order = np.argsort(sc)[::-1]
        best, second = sc[order[0]], sc[order[1]]
        self.chord_conf = max(0.0, min(1.0, (best - 0.35) * 2.0 + (best - second)))
        self.chord = CHORDS[order[0]][0] if self.chord_conf > 0.2 else "--"
        # melody: the strongest peak between 130 and 1500 Hz, if it stands well above the rest and its harmonics are there
        sel = (kfreqs > 130) & (kfreqs < 1500)
        seg = kmag[sel]
        fs = kfreqs[sel]
        med = float(np.median(seg)) + 1e-9
        i = int(np.argmax(seg))
        prom = float(seg[i]) / med
        f0 = float(fs[i])
        harm = 0.0
        for h in (2, 3, 4):
            j = int(round(f0 * h / (kfreqs[1] - kfreqs[0])))
            if j + 2 < len(kmag):
                harm += float(kmag[max(0, j - 1):j + 2].max()) / med
        harm /= 3.0
        self.note_conf = max(0.0, min(1.0, (math.log10(max(prom, 1.0)) - 0.8) * 1.2))
        if self.note_conf > 0.25:
            midi = int(round(69 + 12 * math.log2(f0 / 440.0)))
            name = NOTE_NAMES[midi % 12] + str(midi // 12 - 1)
            if name == self._note_prev:                       # two readings in a row: believed
                self.note, self.note_hz = name, f0
            self._note_prev = name
        else:
            self._note_prev = None
            self.note = "--"
        # vocal: voice-band presence over the whole spectrum, with harmonics (a tone, not noise); smoothed
        tot = float((kmag[(kfreqs > 80) & (kfreqs < 8000)] ** 2).sum()) + 1e-9
        pres = float((kmag[(kfreqs > 1000) & (kfreqs < 3400)] ** 2).sum()) / tot
        mid = float((kmag[(kfreqs > 250) & (kfreqs < 3400)] ** 2).sum()) / tot
        tonal = max(0.0, min(1.0, (math.log10(max(harm, 1.0)) - 0.5) * 1.5)) if prom > 6 else 0.0
        score = max(0.0, min(1.0, (mid - 0.35) * 3.0)) * max(0.0, min(1.0, pres * 6.0)) * tonal
        self.vocal += (score - self.vocal) * (1.0 - math.exp(-0.083 / 1.5))

    # -------------------------------------------------------------------- per frame
    def tick(self, dt, an):
        """Called every frame with the analyzer: onset density, riser, repeats, tempo."""
        now = an.now_t
        silent = an.silence > 0.6
        if an.kick_hit or an.snare_hit or an.hat_hit:
            self._ev.append(now)
        while self._ev and now - self._ev[0] > 4.0:
            self._ev.popleft()
        self.density += (len(self._ev) / 4.0 - self.density) * (1.0 - math.exp(-dt / 1.0))
        # riser: the sustained part of the sound (the minimum of the last quarter second, so drum hits do not count) gets brighter and louder in the highs
        # for several seconds in a steady climb
        self._cen_acc += dt
        if self._cen_acc >= 0.1:
            self._cen_acc = 0.0
            if len(self._mins) >= 12 and not silent:
                fl = np.min(np.array(self._mins), axis=0)
                m = fl[self._cm]
                tot = float(m.sum())
                hi = float((fl[self.freqs > 3000.0] ** 2).sum())
                if tot > 1e-7:
                    self._fl_hist.append((math.log2(max(1.0, float((self.freqs[self._cm] * m).sum() / tot))), 10.0 * math.log10(hi + 1e-12)))
            else:
                self._fl_hist.clear()
        r = 0.0
        for n in (20, 30, 50, 80):                                    # climbs of 2, 3, 5 and 8 seconds
            if len(self._fl_hist) < n:
                break
            y = np.array(list(self._fl_hist)[-n:])
            t = np.arange(n) * 0.1
            for col, lo, scale, rmin, rise in ((0, 0.04, 0.18, 0.75, 0.0), (1, 1.0, 2.5, 0.85, 4.0)):
                v = y[:, col]
                if v.std() < 1e-6 or (v[-5:].mean() - v[:5].mean()) < rise:
                    continue
                slope = float(np.polyfit(t, v, 1)[0])
                cc = float(np.corrcoef(t, v)[0, 1])
                r = max(r, max(0.0, min(1.0, (slope - lo) / scale)) * max(0.0, min(1.0, (cc - rmin) / 0.15 + 0.2)))
        self.riser += (r - self.riser) * (1.0 - math.exp(-dt / (0.25 if r > self.riser else 0.8)))
        # tempo: how steady the BPM has been over the last 40 s
        self._bpm_acc += dt
        if self._bpm_acc >= 1.0:
            self._bpm_acc = 0.0
            if an.bpm > 0 and an.conf > 0.4 and not silent:
                self._bpm_hist.append(an.bpm)
            if len(self._bpm_hist) >= 8:
                h = list(self._bpm_hist)[-20:]
                self.tempo_spread = max(h) - min(h)
        self._drawing_data(dt, an, silent)
        # sections: a description of the sound every second, compared with the earlier ones every two
        self._feat_acc += dt
        if self._feat_acc >= 1.0 and not silent and an.active_t > 4.0:
            self._feat_acc = 0.0
            b = np.asarray(an.bands, float).reshape(8, -1).mean(axis=1)
            ch = self.chroma / (self.chroma.sum() + 1e-9)
            self._feats.append((an.track_time, np.concatenate((b * 2.0, ch * 4.0))))
            if len(self._feats) > 1800:
                del self._feats[:300]
        self._rep_acc += dt
        if self._rep_acc >= 2.0:
            self._rep_acc = 0.0
            self._find_repeat()
            self._cluster()

    def _drawing_data(self, dt, an, silent):
        """What the drawings need: the grid of drum hits, the histories, the chord sequence, the peak hold and the loudness."""
        if an.bpm > 0 and an.conf > 0.3 and not silent:
            pos = (an.beat_in_bar + an.phase) / max(1, an.bpb)
            if pos < self._pos_prev - 0.5:                                # a new bar: this one becomes the ghost
                self.grid_prev, self.grid = self.grid, np.zeros((4, 16))
                self.grid_bar += 1
            self._pos_prev = pos
            step = max(0, min(15, int(pos * 16)))
            self.grid_step = step
            bass_hi = an.bass > 0.55
            hits = (an.kick_hit, an.snare_hit, an.hat_hit, 0.9 if (bass_hi and not self._bass_hi) else 0.0)
            self._bass_hi = bass_hi
            for r, h in enumerate(hits):
                if h > 0:
                    self.grid[r, step] = max(self.grid[r, step], min(1.0, 0.35 + 0.65 * min(1.0, h)))
        else:
            self.grid_step = -1
        self._hist_acc += dt
        if self._hist_acc >= 0.5:
            self._hist_acc = 0.0
            self.hist["cen"].append(max(0.0, min(1.0, (math.log2(max(self.cen, 200.0)) - 7.6) / 4.0)) if self.cen > 0 else 0.0)
            self.hist["dens"].append(min(1.0, self.density / 10.0))
            self.hist["vol"].append(max(0.0, min(1.0, (an.lf + 50.0) / 50.0)))
            self.hist["tens"].append(max(0.0, min(1.0, an.tension)))
        if self.chord != "--" and not silent:
            if self.chord == self._chord_cand:
                self._chord_cand_t += dt
            else:
                self._chord_cand, self._chord_cand_t = self.chord, 0.0
            if self._chord_cand_t > 0.6 and (not self.chord_seq or self.chord_seq[-1] != self._chord_cand):
                self.chord_seq.append(self._chord_cand)
                del self.chord_seq[:-6]
        self.peak = np.maximum(np.asarray(an.bands, float), self.peak - dt * 0.35)
        if an.lf > -80:
            self.lf_long += (an.lf - self.lf_long) * (1.0 - math.exp(-dt / 6.0))
        self.lf_peak = max(an.lf, self.lf_peak - dt * 3.0)

    def _cluster(self, win=6, thr=0.55):
        """Names the sections of the last three minutes (A, B, ...) by how alike their sound is."""
        feats = self._feats[-180:]
        if len(feats) < 20:
            self.sect, self.sect_now = [], ""
            return
        v = np.array([f for _, f in feats])
        v = v - v.mean(axis=0)
        k = np.ones(win) / win
        v = np.stack([np.convolve(v[:, d], k, mode="same") for d in range(v.shape[1])], axis=1)
        cents, counts, labels = [], [], []
        for row in v:
            n = np.linalg.norm(row)
            best, bs = -1, -2.0
            if n > 1e-9:
                for i, c in enumerate(cents):
                    s = float(row @ c) / (n * np.linalg.norm(c) + 1e-9)
                    if s > bs:
                        best, bs = i, s
            if best < 0 or (bs < thr and len(cents) < 8):
                cents.append(row.copy())
                counts.append(1)
                labels.append(len(cents) - 1)
            else:
                counts[best] += 1
                cents[best] = cents[best] + (row - cents[best]) / counts[best]
                labels.append(best)
        runs = []                                                     # [label, first index, last index]
        for i, lab in enumerate(labels):
            if runs and runs[-1][0] == lab:
                runs[-1][2] = i
            else:
                runs.append([lab, i, i])
        merged = []
        for r in runs:                                                # a run shorter than 6 s is a transition: it joins the one before
            if merged and (r[2] - r[1] + 1 < 6 or merged[-1][0] == r[0]):
                merged[-1][2] = r[2]
            else:
                merged.append(r)
        runs = merged
        self.sect = [(feats[a][0], feats[b][0], chr(65 + lab)) for lab, a, b in runs]
        self.sect_now = chr(65 + runs[-1][0])

    def sentence(self, an):
        """A line that says what the music is doing now: [(text, highlighted)]."""
        if an.silence > 0.6:
            return [("Sem áudio. Toque uma música no computador.", False)]
        out = []

        def add(t, hl=False):
            out.append((t, hl))
        if an.key_name != "--":
            add(an.key_name, True)
            add(", ")
        if an.bpm > 0 and an.conf > 0.4:
            add(f"{an.bpm:.0f} BPM", True)
            add(", ")
        add("som ")
        add("escuro" if self.cen < 1400 else ("médio" if self.cen < 3200 else "brilhante"), True)
        if self.density >= 7.0:
            add(" e ")
            add("denso", True)
        elif self.density < 3.0:
            add(" e ")
            add("esparso", True)
        add(", com voz" if self.vocal > 0.4 else ", sem voz")
        if self.riser > 0.35:
            add(", ")
            add("subindo", True)
        if self.repeat_at is not None:
            add(" — soa igual a ")
            add(mmss(self.repeat_at), True)
        elif len(self._feats) > 40:
            add(" — parte nova")
        add(".")
        return out

    def _find_repeat(self, win=8, gap=24):
        n = len(self._feats)
        if n < win + gap + win:
            self.repeat_at, self.repeat_sim = None, 0.0
            return
        v = np.array([f for _, f in self._feats])
        v = v - v.mean(axis=0)
        cs = np.vstack((np.zeros((1, v.shape[1])), np.cumsum(v, axis=0)))
        wm = (cs[win:] - cs[:-win]) / win                       # wm[j] = mean of v[j : j + win]
        cur = wm[n - win]
        idx = np.arange(0, n - win - gap + 1)
        if len(idx) == 0:
            return
        cand = wm[idx]
        sims = (cand @ cur) / (np.linalg.norm(cand, axis=1) * np.linalg.norm(cur) + 1e-9)
        j = int(np.argmax(sims))
        self.repeat_sim = float(sims[j])
        self.repeat_at = self._feats[idx[j]][0] if self.repeat_sim > 0.85 else None

    # ------------------------------------------------------------------ the captions
    def tiles(self, an):
        """The meters of the Ao vivo tab: (caption, value, level 0..1, lit). Level 0..1 draws the bar; lit says the reading is believed."""
        silent = an.silence > 0.6
        out = []

        def add(cap, val, lvl, lit=True):
            out.append((cap, val if not silent else "—", 0.0 if silent else max(0.0, min(1.0, lvl)), lit and not silent))
        add("Kick", "batendo" if an.kick > 0.35 else "—", an.kick, an.kick > 0.35)
        add("Caixa", "batendo" if an.snare > 0.35 else "—", an.snare, an.snare > 0.35)
        add("Chimbal", "batendo" if an.hat > 0.35 else "—", an.hat, an.hat > 0.35)
        add("Graves", "pesados" if an.bass > 0.5 else "—", an.bass, an.bass > 0.5)
        add("Tom", an.key_name if an.key_name != "--" else "—", an.key_conf, an.key_name != "--")
        add("Acorde", self.chord if self.chord != "--" else "—", self.chord_conf, self.chord != "--")
        add("Melodia", self.note if self.note != "--" else "—", self.note_conf, self.note != "--")
        if self.cen > 0:
            lab = "escuro" if self.cen < 1400 else ("médio" if self.cen < 3200 else "brilhante")
            add("Brilho", f"{lab} · {self.cen / 1000:.1f} kHz", (math.log2(max(self.cen, 200)) - 7.6) / 4.0)
        else:
            add("Brilho", "—", 0.0, False)
        add("Riser", "subindo" if self.riser > 0.35 else "—", self.riser, self.riser > 0.35)
        add("Vocal", "provável" if self.vocal > 0.4 else "não", self.vocal * 1.6, self.vocal > 0.4)
        lab = "baixa" if self.density < 3.0 else ("média" if self.density < 7.0 else "alta")
        add("Densidade", f"{lab} · {self.density:.1f}/s", self.density / 10.0)
        add("Estéreo", f"{self.width * 100:.0f}% largo" if self.width > 0 else "mono", self.width * 1.6, self.width > 0)
        if self.repeat_at is not None:
            add("Seção", f"igual a {mmss(self.repeat_at)}", self.repeat_sim, True)
        else:
            add("Seção", "parte nova" if len(self._feats) > 40 else "ouvindo…", 0.0, False)
        if an.bpm > 0 and an.conf > 0.4:
            add("Andamento", ("estável" if self.tempo_spread < 1.5 else "variando") + f" · {an.bpm:.0f}", 1.0 - min(1.0, self.tempo_spread / 8.0), self.tempo_spread < 1.5)
        else:
            add("Andamento", "ouvindo…", 0.0, False)
        add("Tensão", "build-up" if an.tension > 0.5 else ("subindo" if an.tension > 0.25 else "—"), an.tension, an.tension > 0.5)
        add("Volume", f"{an.lf:.0f} dB" if an.lf > -80 else "—", (an.lf + 50) / 50.0)
        return out
