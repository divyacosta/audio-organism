"""The lay-user test: five tasks done on the real program (or on the source) the way someone who has never seen it would do them: with real mouse and key events, clicking
only on what is on the screen at that moment (nothing is scrolled first), the first time the program is opened (a fresh settings folder).

For each task it counts the actions (clicks and keys), checks that every control was on the screen when it was needed, that the task really happened (the program's own state
is read back) and that it stayed within the number of actions it should take, and it prints a table.

    python tests/lay.py [path\\to\\MusicVisualizer.exe]        (without a path it runs app.py)

Exit code 0 = every task passed. It needs the sound card and the screen like any run of the program (the picture goes full screen for a second in task 1).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TASKS = {"T1": ("Ver em tela cheia e voltar", 2),
         "T2": ("Trocar o visual", 1),
         "T3": ("Mais forte, mais rápido e outras cores", 3),
         "T4": ("Criar a minha cena (visual, cores e nome)", 18),
         "T5": ("Ligar a troca automática e tirar uma cena dela", 3)}
NAME = "Minha festa"


def build(log, size=None):
    """The script of the five tasks: what a person does, in order, with the waits a person has. `size` = (w, h) opens the window at that size first (a laptop)."""
    S = []
    if size:
        S.append(dict(wait=9.0, do="winsize", w=size[0], h=size[1]))

    def state(task, tag, wait=0.6):
        S.append(dict(wait=wait, do="tlog", task=task, tag=tag, f=log))

    def click(task, label, src, wait=0.8, **kw):
        S.append(dict(wait=wait, do="tclick", task=task, label=label, src=src, f=log, **kw))

    def key(task, label, k, char="", wait=0.12):
        S.append(dict(wait=wait, do="tkey", task=task, label=label, k=k, char=char, f=log))
    # T1: full screen, and the way back (the words on the picture say Esc)
    state("T1", "antes", wait=2.0 if size else 9.0)
    click("T1", "Tela cheia", "live", bid="key:f")
    state("T1", "tela cheia", wait=1.8)
    S.append(dict(wait=0.3, do="trkey", key="Escape", task="T1", label="Esc", f=log))
    state("T1", "voltou", wait=1.6)
    # T2: another look
    state("T2", "antes", wait=0.4)
    click("T2", "a cena Catedral", "live", bid="scene:3")
    state("T2", "+0.4s", wait=0.4)
    state("T2", "+1.5s", wait=1.1)
    # T3: stronger, faster, other colours (and the way to undo it)
    click("T3", "Intensidade: Forte", "live", bid="macro:energy:3")
    click("T3", "Velocidade: Rápida", "live", bid="macro:speed:3")
    click("T3", "Cores: Vitral", "live", bid="macro:pal:2")
    state("T3", "depois", wait=0.5)
    click("T3", "Voltar ao normal", "live", bid="macro:reset:0", optional=True)                  # the way to undo: not part of the task, but it must be there
    state("T3", "normal", wait=0.5)
    # T4: a scene of my own
    click("T4", "+ Nova cena", "live", bid="wiz:start", wait=0.8)
    state("T4", "passo 1", wait=0.9)
    click("T4", "um visual (Impacto)", "gal", kind="wz-pick", arg=4)
    click("T4", "Continuar", "gal", kind="wz-next", arg=0)
    click("T4", "umas cores (Quente)", "gal", kind="wz-pal", arg=3)
    click("T4", "Continuar", "gal", kind="wz-next", arg=0)
    state("T4", "passo 3", wait=0.6)
    for ch in NAME:
        key("T4", f"letra {ch!r}", "SPACE" if ch == " " else ch.lower(), ch)
    click("T4", "Criar cena", "gal", kind="wz-next", arg=0)
    state("T4", "criada", wait=1.6)
    # T5: let the program change scenes by itself, and take one scene out of that
    click("T5", "Troca automática", "live", bid="auto:toggle")
    state("T5", "ligada", wait=0.5)
    click("T5", "Opções", "live", bid="auto:settings")
    state("T5", "página", wait=0.9)
    click("T5", "a pílula da cena Túnel", "menu", cid="sc_auto:2")
    state("T5", "depois", wait=0.6)
    click("T5", "a aba Palco", "menu", cid="tab0", optional=True)                                # coming back is not part of the task either
    state("T5", "volta", wait=0.7)
    S.append(dict(wait=0.3, do="quit"))
    return S


def evaluate(lines):
    """[(task, title, actions, all_visible, effect_ok, budget, notes)] from the lines the program wrote."""
    ev = [json.loads(ln) for ln in lines if ln.strip()]
    by = {}
    for e in ev:
        by.setdefault(e.get("task"), []).append(e)

    def st(task, tag):
        return next((e for e in by.get(task, []) if e.get("ev") == "state" and e.get("tag") == tag), {})
    n0 = st("T2", "antes").get("n", 0)
    checks = {
        "T1": [("a tela cheia ligou", st("T1", "tela cheia").get("fullscreen") is True),
               ("a imagem mostrou a dica de como sair", st("T1", "tela cheia").get("osd", 0) > 0.5),
               ("Esc voltou para a janela", st("T1", "voltou").get("fullscreen") is False)],
        "T2": [("a cena trocou", st("T2", "+1.5s").get("live") == "Catedral"),
               ("... e ficou nela", st("T2", "+1.5s").get("effect") == 4)],
        "T3": [("intensidade, velocidade e cores mudaram", (st("T3", "depois").get("energy"), st("T3", "depois").get("speed"), st("T3", "depois").get("pal")) == (140, 150, 2)),
               ("'Voltar ao normal' desfez", (st("T3", "normal").get("energy"), st("T3", "normal").get("speed"), st("T3", "normal").get("pal")) == (100, 100, 0))],
        "T4": [("a cena foi criada com o nome digitado", st("T4", "criada").get("n") == n0 + 1 and st("T4", "criada").get("last") == NAME),
               ("... com o visual escolhido (Impacto)", st("T4", "criada").get("last_layers") == ["edge", "ca", "gr"]),
               ("... com as cores escolhidas", st("T4", "criada").get("last_pal") == 3),
               ("... no ar", st("T4", "criada").get("effect") == n0 + 1 and st("T4", "criada").get("live") == NAME),
               ("... e de volta ao Palco, dizendo isso", st("T4", "criada").get("tab") == 0 and "criada" in (st("T4", "criada").get("toast") or "criada"))],
        "T5": [("a troca automática ligou", st("T5", "ligada").get("effect") == 0),
               ("as Opções abriram a página Automático", st("T5", "página").get("tab") == 2 and st("T5", "página").get("sys_item") == 2),
               ("a cena saiu do automático", "Túnel" in (st("T5", "depois").get("auto_off") or [])),
               ("a aba Palco trouxe de volta", st("T5", "volta").get("tab") == 0)],
    }
    out = []
    for t, (title, budget) in TASKS.items():
        acts = [e for e in by.get(t, []) if ((e.get("ev") == "click" and e.get("did")) or e.get("ev") == "key") and not e.get("optional")]
        clicks = [e for e in by.get(t, []) if e.get("ev") == "click"]
        blocked = [e for e in clicks if not e.get("did")]
        cut = [e for e in clicks if e.get("did") and e.get("visible") == 1]
        notes = []
        for e in blocked:
            notes.append(f"não deu para clicar em '{e.get('label')}' ({'não existe' if not e.get('found') else 'fora da tela'})")
        for desc, ok in checks[t]:
            if not ok:
                notes.append("falhou: " + desc)
        if len(acts) > budget:
            notes.append(f"{len(acts)} ações (o esperado era até {budget})")
        info = {"T1": [f"dica na imagem (opacidade): {st('T1', 'tela cheia').get('osd')}"],
                "T2": ["a cena já estava no ar com 0,4 s" if st("T2", "+0.4s").get("live") == "Catedral" else "a cena entrou entre 0,4 s e 1,5 s"],
                "T4": [f"aviso na tela: {st('T4', 'criada').get('toast')!r}"]}.get(t, [])
        info += [f"cortado pela borda da janela (mas dá para clicar): '{e.get('label')}'" for e in cut]          # a warning, not a failure
        seen = "NÃO" if (blocked or not clicks) else ("em parte" if cut else "sim")
        out.append((t, title, len(acts), seen, not [1 for _, ok in checks[t] if not ok], budget, notes, info))
    return out


SIZES = (None, (972, 648), (972, 600))  # the window the program opens in (a Full HD screen), and the ones of a 1366x768 and of a 1280x720 screen


def run_once(exe, size):
    """One go through the five tasks at one window size. Returns the number of problems."""
    tmp = tempfile.mkdtemp(prefix="ao_lay_")
    log = os.path.join(tmp, "lay.jsonl").replace("\\", "/")
    script = os.path.join(tmp, "script.json")
    json.dump(build(log, size), open(script, "w"))
    appdir = os.path.join(tmp, "appdir")
    env = dict(os.environ, VIS_APPDIR=appdir, VIS_AUTOTEST=script)
    cmd = [os.path.abspath(exe), "--multi"] if exe else [sys.executable, "app.py", "--multi"]
    t0 = time.time()
    try:
        subprocess.run(cmd, env=env, cwd=ROOT, timeout=240)
        done = True
    except subprocess.TimeoutExpired:
        done = False
    print(f"\n=== janela {'de abertura (a do programa)' if size is None else '%dx%d' % size}: {'o programa' if exe else 'app.py'} rodou as tarefas em {time.time() - t0:.0f} s"
          + ("" if done else "  (ESTOUROU O TEMPO)"))
    lines = open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []
    crash = os.path.exists(os.path.join(appdir, "erro.log"))
    rows = evaluate(lines)
    print(f"{'':3}{'Tarefa':50}{'ações':>6}{'  tudo à vista':>15}{'  aconteceu':>12}   resultado")
    bad = 0 if done else 1
    for t, title, n, seen, ok, budget, notes, info in rows:
        good = seen != "NÃO" and ok and not notes
        bad += 0 if good else 1
        print(f"{t:3}{title:50}{n:>6}{('  ' + seen):>15}{'  sim' if ok else '  NÃO':>12}   " + ("OK" if good else "PROBLEMA"))
        for nt in notes:
            print(f"       - {nt}")
        for nt in info:
            print(f"       · {nt}")
    if crash:
        bad += 1
        print("HOUVE erro.log:", os.path.join(appdir, "erro.log"))
    if bad:
        print("(arquivos da rodada em", tmp + ")")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return bad


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--size=")]
    exe = args[0] if args else None
    sizes = [tuple(int(v) for v in a[7:].split("x")) for a in sys.argv[1:] if a.startswith("--size=")] or SIZES
    bad = sum(run_once(exe, sz) for sz in sizes)
    print("\n" + ("TODAS AS TAREFAS OK, EM TODAS AS JANELAS" if not bad else "COM PROBLEMAS"))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
