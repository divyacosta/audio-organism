"""The performance report: the program runs at Ultra for a while and says what each part of a frame costs, and what each part is made of.

`VIS_REPORT=<file.json>` makes app.py force Ultra (VSync and the dynamic resolution off), wait for the warm-up, measure for MEASURE seconds, write the numbers here and quit.
`relatorio_desempenho.py` starts the program that way (three runs: no FPS cap, with the cap, and with the cProfile by function) and turns the numbers into
relatorio_desempenho.md. VIS_SYNTH=1 feeds it the test music, so the load is the same every time. The timers inside the program are in prof.py."""
import cProfile
import ctypes
import json
import os
import platform
import pstats
import time
from ctypes import wintypes

import prof

WARMUP, MEASURE = 6.0, 20.0                       # seconds of warm-up (shaders, caches) and of measuring
GROUPS = {"GPU": "Desenho da imagem", "UI": "Painel de controles e miniaturas", "áudio": "Análise do som", "cena": "Diretor e parâmetros", "Resto": "Resto do laço"}
HERE = os.path.dirname(os.path.abspath(__file__))


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


def _module(path):
    """Which part of the program or of the libraries a function belongs to."""
    p = path.replace("\\", "/")
    if not p or p.startswith("<") or p.startswith("~"):
        return "Python (embutido)"
    if p.startswith(HERE.replace("\\", "/")):
        return os.path.basename(p)
    if "site-packages/" in p:
        return p.split("site-packages/")[1].split("/")[0].split(".")[0]
    return "Python (biblioteca padrão)"


class Recorder:
    """Collects the frame times and the cost of each part while the program runs, and writes the report when the time is up.
    With `profile` it also runs cProfile over the measured time (slower: a second view, by function)."""

    def __init__(self, path, profile=False):
        self.path, self.t0, self.cpu0, self.dts, self.started, self.profile, self.pr = path, 0.0, 0.0, [], False, profile, None

    def step(self, clock_t, dt, tm):
        """Once a frame. Returns True when the time is up (the program should write the report and quit)."""
        if not self.started:
            if clock_t < WARMUP:
                return False
            self.started, self.t0, self.cpu0 = True, time.perf_counter(), time.process_time()
            prof.reset()
            if self.profile:
                self.pr = cProfile.Profile()
                self.pr.enable()
        self.dts.append(dt)
        return time.perf_counter() - self.t0 >= MEASURE

    def write(self, rend, cfg, preset):
        wall, cpu = time.perf_counter() - self.t0, time.process_time() - self.cpu0
        if self.pr is not None:
            self.pr.disable()
        d = sorted(self.dts)
        n = len(d)
        parts = {k: round(v * 1000.0 / n, 3) for k, v in prof.totals().items()}          # ms per frame, by "Group/part"
        now, peak = memory_mb()
        out = dict(when=time.strftime("%Y-%m-%d %H:%M:%S"), gpu=rend.gpu_name, backend=str(rend.backend), preset=preset, res=round(float(rend.res), 1),
                   scene=list(rend.scene_size), steps=int(getattr(rend, "steps", 0)), frames=n, seconds=round(wall, 2), avg_fps=round(n / max(sum(d), 1e-6), 1),
                   p1_fps=round(1.0 / max(d[max(0, int(n * 0.99) - 1)], 1e-6), 1), worst_ms=round(d[-1] * 1000, 1), avg_ms=round(sum(d) / n * 1000, 2),
                   p99_ms=round(d[max(0, int(n * 0.99) - 1)] * 1000, 2), parts=parts, cpu_pct=round(100 * cpu / max(wall, 1e-6), 1),
                   mem_mb=round(now), mem_peak_mb=round(peak), python=platform.python_version(), os=platform.platform(), fps_out=int(cfg.get("fps_out", 0)))
        if self.pr is not None:
            funcs, mods = [], {}
            for (fn, line, name), (cc, nc, tt, ct, _c) in pstats.Stats(self.pr).stats.items():
                ms = tt * 1000.0 / n
                m = _module(fn)
                mods[m] = mods.get(m, 0.0) + ms
                real = bool(fn) and not fn.startswith("<") and not fn.startswith("~")
                funcs.append(dict(name=name, where=f"{os.path.basename(fn)}:{line}" if real else "", module=m, calls=round(nc / n, 2), ms=round(ms, 3)))
            funcs.sort(key=lambda f: -f["ms"])
            out["funcs"] = funcs[:40]
            out["modules"] = {k: round(v, 3) for k, v in sorted(mods.items(), key=lambda kv: -kv[1])[:20]}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        return out


def markdown(r, capped=None, profiled=None):
    """The report as text for a person: where a frame goes (each part and its sub-parts), how the frames come out, what the program holds."""
    frame = max(r["avg_ms"], 1e-6)
    groups = {}
    for k, v in r["parts"].items():
        g, _, sub = k.partition("/")
        groups.setdefault(g, []).append((sub or g, v))
    tot = {g: sum(v for _, v in subs) for g, subs in groups.items()}
    lines = [f"# Relatório de desempenho — qualidade {r['preset']}", "",
             f"Gerado em {r['when']}  ·  {r['seconds']} s medidos depois do aquecimento  ·  {r['frames']} quadros  ·  **sem limite de FPS**, para mostrar do que o programa é capaz", "",
             "## O que roda", "",
             f"- **Placa de vídeo:** {r['gpu']} ({r['backend']})",
             f"- **Imagem:** {r['scene'][0]}×{r['scene'][1]} (resolução interna {r['res']}%, {r['steps']} passos por raio)",
             f"- **Sistema:** {r['os']}  ·  Python {r['python']}", "",
             "## Quanto custa cada parte de um quadro, e cada subparte", "",
             f"Um quadro leva em média **{r['avg_ms']} ms** ({r['avg_fps']} fps). Cada subparte é um cronômetro dentro do programa; a soma delas fecha o quadro.", "",
             "| Parte / subparte | ms por quadro | % do quadro | % da parte |", "|---|---:|---:|---:|"]
    for g in sorted(tot, key=lambda g: -tot[g]):
        lines.append(f"| **{GROUPS.get(g, g)}** | **{tot[g]:.2f}** | **{100 * tot[g] / frame:.0f}%** | |")
        for name, v in sorted(groups[g], key=lambda x: -x[1]):
            lines.append(f"| &nbsp;&nbsp;&nbsp;{name} | {v:.2f} | {100 * v / frame:.1f}% | {100 * v / max(tot[g], 1e-9):.0f}% |")
    lost = max(0.0, frame - sum(tot.values()))
    lines.append(f"| *Não coberto por nenhum cronômetro* | {lost:.2f} | {100 * lost / frame:.1f}% | |")
    if capped:
        lines += ["", f"Com o limite de {capped['fps_out']} fps do programa ligado: **{capped['avg_fps']} fps** em média, 1% mais lento {capped['p1_fps']} fps, "
                      f"e {capped['cpu_pct']}% de um núcleo (o limitador dorme entre os quadros)."]
    lines += ["", "## Como os quadros saem", "",
              f"- **Média:** {r['avg_fps']} fps",
              f"- **1% mais lento:** {r['p1_fps']} fps (quadro de {r['p99_ms']} ms)",
              f"- **Pior quadro:** {r['worst_ms']} ms", "",
              "## O que o programa consome", "",
              f"- **Processador:** {r['cpu_pct']}% de um núcleo (soma de todas as threads do programa; 100% = um núcleo inteiro)",
              f"- **Memória:** {r['mem_mb']} MB em uso, pico de {r['mem_peak_mb']} MB", ""]
    if profiled and profiled.get("funcs"):
        lines += ["## Por módulo e por função (com profiler)", "",
                  f"Medição com o `cProfile` ligado: os tempos saem inflados (o profiler também custa), então use as proporções, não os valores. Média de {profiled['avg_fps']} fps nesta execução.", "",
                  "### Tempo próprio por módulo", "", "| Módulo | ms por quadro |", "|---|---:|"]
        for m, v in profiled["modules"].items():
            lines.append(f"| {m} | {v:.2f} |")
        lines += ["", "### As 25 funções mais caras (tempo próprio)", "", "| Função | Onde | Módulo | Chamadas por quadro | ms por quadro |", "|---|---|---|---:|---:|"]
        for f in profiled["funcs"][:25]:
            lines.append(f"| `{f['name']}` | {f['where']} | {f['module']} | {f['calls']} | {f['ms']:.3f} |")
        lines.append("")
    lines += ["## Como ler", "",
              "- **Desenho da imagem:** os cronômetros dentro dele medem o processador montando e enviando os comandos. O tempo que o programa passa **esperando a placa de vídeo** "
              "aparece em *obter a imagem da janela* e em *entregar o quadro*: se essas duas dominam, a placa é o limite.",
              "- Na visão por função, `proxy_func` do `wgpu` mostra o custo de chamar a API da placa a partir do Python (dezenas de chamadas por quadro).",
              "- Se **Painel de controles** ou **Diretor** dominam, o limite é o Python e dá para otimizar sem trocar de motor.",
              "- O tempo de cada passe dentro da placa (cena, bloom, TAA...) não é medido aqui; seria preciso consultar cronômetros da própria placa.",
              "- A memória da placa de vídeo também não é medida.", ""]
    return "\n".join(lines)
