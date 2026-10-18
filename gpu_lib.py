"""Shader library: WGSL files on disk, `#include "file.wgsl"` support and hot reload.

Save a .wgsl file while the program runs and it is rebuilt on the fly. If the new source has an error, the
last working shader keeps running and the error is reported (shown in the control window).
"""
import os
import re
import time

INCLUDE = re.compile(r'^\s*#include\s+"([^"]+)"\s*$')


def _short(err):
    """One readable line from a wgpu/naga error: the reason plus where (line numbers refer to the expanded source)."""
    text = str(err)
    loc = re.search(r"wgsl:(\d+):(\d+)", text)
    reasons = [l.strip() for l in text.splitlines() if re.search(r"error", l, re.I) and "validation error" not in l.lower()]
    caret = re.search(r"\^+\s*(.+)", text)
    first = reasons[0] if reasons else (text.strip().splitlines()[0] if text.strip() else "erro")
    out = re.sub(r"^Shader '[^']*'\s*", "", first)
    if caret and caret.group(1).strip() not in out:
        out += "  ->  " + caret.group(1).strip()
    if loc:
        out += f"  (linha {loc.group(1)})"
    return out[:220]


class Shader:
    def __init__(self, lib, name, filename):
        self.lib, self.name, self.filename = lib, name, filename
        self.module = None
        self.error = None
        self.deps = {}
        self.version = 0

    def build(self):
        """Compile from disk. Keeps the previous module when the new source is broken."""
        try:
            src, deps = self.lib.expand(self.filename)
        except Exception as e:                       # missing file / include loop
            self.error = _short(e)
            return False
        self.deps = {p: self.lib.mtime(p) for p in deps}
        try:
            module = self.lib.device.create_shader_module(code=src, label=self.name)
        except Exception as e:
            self.error = _short(e)
            return False
        self.module, self.error = module, None
        self.version += 1
        return True

    def stale(self):
        return any(self.lib.mtime(p) != m for p, m in self.deps.items())


class ShaderLib:
    def __init__(self, device, folder):
        self.device, self.folder = device, folder
        self.shaders = {}
        self.reloads = 0
        self._last = 0.0

    def mtime(self, path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return -1.0

    def expand(self, filename, _stack=()):
        path = os.path.join(self.folder, filename)
        if path in _stack:
            raise RuntimeError(f"#include em ciclo: {filename}")
        if len(_stack) > 8:
            raise RuntimeError("#include fundo demais")
        deps = [path]
        out = []
        with open(path, encoding="utf-8") as f:
            for line in f.read().splitlines():
                m = INCLUDE.match(line)
                if m:
                    text, sub = self.expand(m.group(1), _stack + (path,))
                    out.append(text)
                    deps += sub
                else:
                    out.append(line)
        return "\n".join(out), deps

    def load(self, name, filename):
        sh = Shader(self, name, filename)
        self.shaders[name] = sh
        sh.build()
        return sh

    def poll(self, interval=0.4):
        """Rebuild shaders whose files changed. Returns the list of shaders that got a NEW working module."""
        now = time.perf_counter()
        if now - self._last < interval:
            return []
        self._last = now
        changed = []
        for sh in self.shaders.values():
            if sh.stale():
                before = sh.version
                sh.build()
                if sh.version != before:
                    changed.append(sh)
                    self.reloads += 1
        return changed

    def status(self):
        """(ok, message): the first shader error, if any."""
        for sh in self.shaders.values():
            if sh.error:
                return False, f"{sh.filename}: " + sh.error.splitlines()[0][:110]
        return True, "ok"
