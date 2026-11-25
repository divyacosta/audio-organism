"""Performance report at Ultra quality:   python relatorio_desempenho.py   [--exe dist\\MusicVisualizer.exe]

Starts the program with the test music, Ultra preset, VSync and dynamic resolution off; it warms up, measures for 20 s and quits by itself (windows open for about 35 s: do not
touch them). Writes relatorio_desempenho.md and keeps every run as relatorios/AAAA-MM-DD_HHMM.json, so two runs can be compared (before / after a change, Vulkan / Direct3D 12:
    python relatorio_desempenho.py --backend vulkan       and      --backend d3d12 ).
"""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import report


def main():
    args = sys.argv[1:]
    exe = args[args.index("--exe") + 1] if "--exe" in args else None
    extra = ["--backend", args[args.index("--backend") + 1]] if "--backend" in args else []
    cmd = ([exe] if exe else [sys.executable, os.path.join(HERE, "app.py")]) + extra
    t0 = time.time()

    def run(label, fps=None, profile=False):
        tmp = os.path.join(tempfile.mkdtemp(prefix="ao_rep_"), "r.json")
        env = dict(os.environ, VIS_REPORT=tmp, VIS_SYNTH="1")
        if fps:
            env["VIS_REPORT_FPS"] = str(fps)
        if profile:
            env["VIS_REPORT_PROF"] = "1"
        print(f"medindo em qualidade Ultra, {label} (cerca de 35 s)...", flush=True)
        try:
            subprocess.run(cmd, env=env, cwd=HERE, timeout=240)
        except subprocess.TimeoutExpired:
            print("o programa não terminou a tempo")
        if not os.path.exists(tmp):
            return None
        with open(tmp, encoding="utf-8") as f:
            return json.load(f)
    r = run("sem limite de FPS", 1000)
    if r is None:
        print("sem resultado: o programa fechou antes de medir (veja a saída acima)")
        return 1
    capped = run("com o limite do programa")
    profiled = run("com o profiler por função", 1000, profile=True)
    os.makedirs(os.path.join(HERE, "relatorios"), exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M")
    tag = ("_" + extra[1]) if extra else ""
    with open(os.path.join(HERE, "relatorios", stamp + tag + ".json"), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    md = report.markdown(r, capped, profiled)
    with open(os.path.join(HERE, "relatorio_desempenho.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    print(f"({time.time() - t0:.0f} s)  salvo em relatorio_desempenho.md e relatorios/{stamp}{tag}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
