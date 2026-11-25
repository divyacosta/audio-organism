"""The performance report: the program runs at Ultra for a while and says what each part of a frame costs.

`VIS_REPORT=<file.json>` makes app.py force Ultra (VSync and the dynamic resolution off), wait for the warm-up, measure for MEASURE seconds, write the numbers here and quit.
`relatorio_desempenho.py` starts the program that way and turns the numbers into relatorio_desempenho.md. VIS_SYNTH=1 feeds it the test music, so the load is the same every time."""
import ctypes
import json
import os
import platform
import time
from ctypes import wintypes

WARMUP, MEASURE = 6.0, 20.0                       # seconds of warm-up (shaders, caches) and of measuring

STAGES = {"áudio": "Análise do som (FFT, batida)", "cena": "Diretor (cena, câmera, parâmetros)", "GPU": "Desenho da imagem (chamada ao renderizador, inclui a espera pela placa)",
          "UI": "Painel de controles (pygame) e prévias", "web": "Painel novo (estado para a página)"}


class _Mem(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def memory_mb():
    """(working set now, peak working set) of this process in MB (Windows; (0, 0) elsewhere)."""
    try:
        m = _Mem()
        m.cb = ctypes.sizeof(_Mem)
        k32, ps = ctypes.windll.kernel32, ctypes.windll.psapi
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        ps.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Mem), wintypes.DWORD]
        ps.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(m), m.cb)
        return m.WorkingSetSize / 1048576, m.PeakWorkingSetSize / 1048576
    except Exception:
        return 0.0, 0.0


class Recorder:
    """Collects the frame times and the cost of each stage while the program runs, and writes the report when the time is up."""

    def __init__(self, path):
        self.path, self.t0, self.cpu0, self.dts, self.tms, self.started = path, 0.0, 0.0, [], [], False

    def step(self, clock_t, dt, tm):
        """Once a frame. Returns True when the report was written (the program should quit)."""
        if not self.started:
            if clock_t < WARMUP:
                return False
            self.started, self.t0, self.cpu0 = True, time.perf_counter(), time.process_time()
        self.dts.append(dt)
        if len(self.dts) % 15 == 0:
            self.tms.append(dict(tm))
        return time.perf_counter() - self.t0 >= MEASURE

    def write(self, rend, cfg, preset):
        wall, cpu = time.perf_counter() - self.t0, time.process_time() - self.cpu0
        d = sorted(self.dts)
        n = len(d)
        stages = {k: sum(t.get(k, 0.0) for t in self.tms) / max(1, len(self.tms)) for k in STAGES}
        now, peak = memory_mb()
        out = dict(when=time.strftime("%Y-%m-%d %H:%M:%S"), gpu=rend.gpu_name, backend=str(rend.backend), preset=preset, res=round(float(rend.res), 1),
                   scene=list(rend.scene_size), steps=int(getattr(rend, "steps", 0)), frames=n, seconds=round(wall, 2), avg_fps=round(n / max(sum(d), 1e-6), 1),
                   p1_fps=round(1.0 / max(d[max(0, int(n * 0.99) - 1)], 1e-6), 1), worst_ms=round(d[-1] * 1000, 1), avg_ms=round(sum(d) / n * 1000, 2),
                   p99_ms=round(d[max(0, int(n * 0.99) - 1)] * 1000, 2), stages={k: round(v, 2) for k, v in stages.items()}, cpu_pct=round(100 * cpu / max(wall, 1e-6), 1),
                   mem_mb=round(now), mem_peak_mb=round(peak), python=platform.python_version(), os=platform.platform(), fps_out=int(cfg.get("fps_out", 0)))
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        return out


def markdown(r, capped=None):
    """The report as text for a person: where a frame goes, how the frames come out, what the program holds."""
    frame = max(r["avg_ms"], 1e-6)
    rows = [(STAGES[k], v) for k, v in r["stages"].items() if v > 0.005]
    used = sum(v for _, v in rows)
    lines = [f"# Relatório de desempenho — qualidade {r['preset']}", "",
             f"Gerado em {r['when']}  ·  {r['seconds']} s medidos depois do aquecimento  ·  {r['frames']} quadros  ·  **sem limite de FPS**, para mostrar do que o programa é capaz", "",
             "## O que roda", "",
             f"- **Placa de vídeo:** {r['gpu']} ({r['backend']})",
             f"- **Imagem:** {r['scene'][0]}×{r['scene'][1]} (resolução interna {r['res']}%, {r['steps']} passos por raio)",
             f"- **Sistema:** {r['os']}  ·  Python {r['python']}", "",
             "## Quanto custa cada parte de um quadro", "",
             f"Um quadro leva em média **{r['avg_ms']} ms** ({r['avg_fps']} fps).", "",
             "| Parte | ms por quadro | % do quadro |", "|---|---:|---:|"]
    for name, v in sorted(rows, key=lambda x: -x[1]):
        lines.append(f"| {name} | {v:.2f} | {100 * v / frame:.0f}% |")
    lines.append(f"| Resto (eventos, espera, limitador, cópia da prévia) | {max(0.0, frame - used):.2f} | {100 * max(0.0, frame - used) / frame:.0f}% |")
    if capped:
        lines += ["", f"Com o limite de {capped['fps_out']} fps do programa ligado: **{capped['avg_fps']} fps** em média, 1% mais lento {capped['p1_fps']} fps, "
                      f"e {capped['cpu_pct']}% de um núcleo (o limitador dorme entre os quadros)."]
    lines += ["", "## Como os quadros saem", "",
              f"- **Média:** {r['avg_fps']} fps (meta do programa: {r['fps_out']} fps)",
              f"- **1% mais lento:** {r['p1_fps']} fps (quadro de {r['p99_ms']} ms)",
              f"- **Pior quadro:** {r['worst_ms']} ms", "",
              "## O que o programa consome", "",
              f"- **Processador:** {r['cpu_pct']}% de um núcleo (soma de todas as threads do programa; 100% = um núcleo inteiro)",
              f"- **Memória:** {r['mem_mb']} MB em uso, pico de {r['mem_peak_mb']} MB", "",
              "## Como ler", "",
              "- A parte **Desenho da imagem** mede a chamada ao renderizador no processador; com o VSync desligado ela inclui esperar a placa terminar. Se ela domina, o limite é a placa de vídeo.",
              "- Se **Painel de controles** ou **Diretor** dominam, o limite é o Python e dá para otimizar sem trocar de motor.",
              "- A memória da placa de vídeo não é medida aqui.", ""]
    return "\n".join(lines)
