"""Update check and self-update from GitHub Releases (no login: the repository must be public).

  check()      asks api.github.com for the latest release and compares it with version.VERSION
  download()   fetches the release's MusicVisualizer.exe to a temp folder, verifying size (and SHA-256 when the release has a .sha256 file)
  apply()      starts a tiny batch script that waits for this program to close, swaps the exe and starts the new one

Everything network-related runs in a background thread (see Updater); the program never blocks on it, and a failed download never touches
the installed exe.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request

from version import ASSET, REPO, VERSION

API = "https://api.github.com/repos/{repo}/releases/latest"
HEADERS = {"User-Agent": "AudioOrganism-updater", "Accept": "application/vnd.github+json"}


def parse(v):
    """'v1.2.3' -> (1, 2, 3); anything unparsable -> (0,)."""
    try:
        return tuple(int(x) for x in str(v).strip().lstrip("vV").split("-")[0].split("."))
    except ValueError:
        return (0,)


def check(repo=None, timeout=8):
    """-> dict(ok, newer, version, url, size, sha_url, notes, error)"""
    repo = repo or REPO
    if not repo:
        return dict(ok=False, error="repositório não configurado")
    try:
        req = urllib.request.Request(API.format(repo=repo), headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except Exception as e:
        return dict(ok=False, error=f"sem acesso ao GitHub ({type(e).__name__})")
    tag = data.get("tag_name", "")
    assets = {a.get("name"): a for a in data.get("assets", [])}
    exe = assets.get(ASSET)
    if exe is None:
        return dict(ok=False, error=f"a versão {tag} não tem o arquivo {ASSET}")
    sha = assets.get(ASSET + ".sha256")
    return dict(ok=True, newer=parse(tag) > parse(VERSION), version=tag.lstrip("vV"), url=exe.get("browser_download_url"),
                size=int(exe.get("size", 0)), sha_url=(sha or {}).get("browser_download_url"), notes=(data.get("body") or "")[:400])


def download(info, progress=None, timeout=20):
    """Download the new exe. Returns the path, or raises RuntimeError. `progress(fraction)` is called while downloading."""
    folder = os.path.join(tempfile.gettempdir(), "AudioOrganism", "update")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, "MusicVisualizer_new.exe")
    part = dest + ".part"
    h = hashlib.sha256()
    try:
        req = urllib.request.Request(info["url"], headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or info.get("size") or 0)
            got = 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if progress and total:
                    progress(min(1.0, got / total))
    except Exception as e:
        raise RuntimeError(f"falha no download ({type(e).__name__})")
    if info.get("size") and os.path.getsize(part) != info["size"]:
        os.remove(part)
        raise RuntimeError("o arquivo baixado está incompleto")
    if info.get("sha_url"):
        try:
            req = urllib.request.Request(info["sha_url"], headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                want = r.read().decode().split()[0].lower()
            if want != h.hexdigest().lower():
                os.remove(part)
                raise RuntimeError("a verificação SHA-256 do arquivo falhou")
        except RuntimeError:
            raise
        except Exception:
            pass                                                       # checksum file unreachable: the size check above still passed
    if os.path.exists(dest):
        os.remove(dest)
    os.replace(part, dest)
    return dest


def can_self_update():
    return bool(getattr(sys, "frozen", False)) and os.name == "nt"


def apply(new_exe):
    """Swap the running exe for `new_exe` after this process exits, then start it. The caller must exit right after this returns."""
    target = sys.executable
    script = os.path.join(tempfile.gettempdir(), "AudioOrganism", "update", "swap.bat")
    with open(script, "w", encoding="utf-8") as f:
        f.write(f'''@echo off
set tries=0
:wait
ping 127.0.0.1 -n 2 >nul
set /a tries+=1
move /y "{new_exe}" "{target}" >nul 2>&1
if errorlevel 1 (
  if %tries% LSS 40 goto wait
  exit /b 1
)
start "" "{target}"
del "%~f0"
''')
    flags = 0x00000008 | 0x00000200 | 0x08000000                     # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
    subprocess.Popen(["cmd", "/c", script], creationflags=flags, close_fds=True)


class Updater:
    """Background wrapper: state in `self.state` = idle | checking | uptodate | available | downloading | ready | error."""

    def __init__(self):
        self.state, self.info, self.error, self.progress, self.path = "idle", None, "", 0.0, None
        self._lock = threading.Lock()

    def start_check(self):
        if self.state in ("checking", "downloading") or not REPO:
            return False
        self.state = "checking"
        threading.Thread(target=self._check, daemon=True).start()
        return True

    def _check(self):
        r = check()
        with self._lock:
            if not r["ok"]:
                self.state, self.error = "error", r["error"]
            else:
                self.info = r
                self.state = "available" if r["newer"] else "uptodate"

    def start_download(self):
        if self.state != "available" or not self.info:
            return False
        self.state, self.progress = "downloading", 0.0
        threading.Thread(target=self._download, daemon=True).start()
        return True

    def _download(self):
        try:
            self.path = download(self.info, lambda p: setattr(self, "progress", p))
            self.state = "ready"
        except RuntimeError as e:
            self.state, self.error = "error", str(e)
