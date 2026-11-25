"""The new panel: the same Menu, shown by a web page (ui_web/panel.html) instead of the pygame window.

A small server on 127.0.0.1:8765 (this computer only). The page is a VIEW of the Menu: the program publishes what the current tab holds (cards of rows, scenes, state) as JSON,
the page draws it and sends back what the person does (set a value, press a button, open an item). The Menu keeps all the rules, so nothing is decided twice.

  GET  /          the page
  GET  /events    server-sent events: the snapshot, again every time it changes
  POST /cmd       {"op": ..., ...}  queued here, run by the main loop (apply) so the Menu is only ever touched from one thread

Nothing here opens a port unless the panel is switched on (Sistema > Aplicativo)."""
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765
BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(BASE, "ui_web", "panel.html")


def _call(v, cfg):
    """A label, a help line or a button text may be a function of the settings."""
    if callable(v):
        try:
            return v(cfg)
        except Exception:
            return ""
    return v


def _row(menu, r):
    """One row of a card as plain data for the page."""
    cfg, kind = menu.cfg, r["kind"]
    d = dict(id=r["id"], kind=kind, label=_call(r.get("label", ""), cfg) or "", help=_call(r.get("help", ""), cfg) or "", on=bool(menu.enabled(r)))
    if kind in ("seg", "dd", "radio"):
        if kind == "radio":
            d["value"], d["val"] = r.get("value"), cfg.get(r["id"])
        else:
            d["val"] = cfg.get(r["id"])
        d["opts"] = [[str(a), b] for a, b in r.get("opts", [])] if kind != "radio" else []
        d["tile"] = bool(r.get("tile"))
    elif kind == "toggle":
        d["val"] = bool(r["get"](cfg)) if "get" in r else bool(cfg.get(r["id"]))
        d["flow"] = bool(r.get("flow"))
    elif kind == "slider":
        d.update(val=cfg.get(r["id"], 0), lo=r["lo"], hi=r["hi"], step=r.get("step", 1), unit=r.get("unit", ""))
    elif kind == "text":
        d.update(val=str(cfg.get(r["id"], "")), ph=r.get("placeholder", ""))
    elif kind == "action":
        d.update(btn=_call(r.get("btn", ""), cfg), primary=bool(r.get("primary")), danger=bool(r.get("danger")))
    elif kind == "item":
        d.update(item=r["item"], tag=r.get("tag", ""), group=r.get("group", ""), sel=int(cfg.get("ed_item", 0)) == r["item"])
        if r.get("sw"):
            d.update(sw=r["sw"], swv=bool(cfg.get(r["sw"], True)))
    elif kind == "layer":
        import layers as LY
        i = r["idx"]
        ls = cfg.get("layers") or []
        if 0 <= i < len(ls):
            L = ls[i]
            info = LY.TYPES.get(L.get("t"), LY.TYPES["fb"])
            d.update(idx=i, label=info["label"], tag=info["tag"], on=bool(L.get("on", True)), sel=i == cfg.get("ly_sel", 0), help=LY.detail_of(L))
    return d


def snapshot(menu, extra=None):
    """Everything the page needs to draw the panel as it is now."""
    cfg = menu.cfg
    cards = []
    if menu.tab in (1, 2) and not (menu.tab == 1 and menu.scene_view != "editor"):
        import menu as M
        for title, rows in M.TABS[menu.tab][1]:
            cards.append(dict(title=title, rows=[_row(menu, r) for r in rows if r["kind"] not in ("ear", "scene", "swatches", "edbar")]))
    scn = cfg.get("scenes") or []
    toast = menu.toast[0] if menu.toast and menu.toast[1] > time.perf_counter() else ""
    col, st = menu.ed_status() if menu.scene_view == "editor" else (None, "")
    d = dict(tab=menu.tab, adv=bool(cfg.get("advanced")), advn=menu.adv_hidden(), view=menu.scene_view, cards=cards,
             scenes=[s.get("scene_name", "?") for s in scn], live=menu.live_i, edit=int(cfg.get("scene_edit", 0)), auto=cfg.get("effect", 0) == 0,
             macros=dict(energy=cfg.get("macro_energy", 100), speed=cfg.get("macro_speed", 100)), toast=toast, undo=bool(menu.toast and len(menu.toast) > 2 and menu.toast[2]),
             state=st, dirty=menu.is_dirty(), livemode=bool(cfg.get("live")), sys=int(cfg.get("sys_item", 0)), search=str(cfg.get("search", "")))
    d.update(extra or {})
    return d


def apply(menu, c):
    """Run one command of the page on the Menu (called by the main loop, never by a server thread)."""
    op = c.get("op")
    if op == "tab":
        menu.press("tab%d" % int(c["i"]))
    elif op == "set":
        menu.set_value(str(c["id"]), c["value"])
    elif op == "press":
        menu.press(str(c["id"]))
    elif op == "item":
        menu.select_item(int(c["k"]))
    elif op == "layer":
        menu.layer_action((str(c["what"]), int(c["i"])))
    elif op == "scene":
        i, what = int(c["i"]), c.get("what")
        if what == "play":
            menu.play_scene(i)
        elif what == "open":
            menu.open_scene(i)
    elif op == "adv":
        menu.press("advanced")
    elif op == "undo":
        menu.undo_last()
    menu.touch()
    menu.need = True


def open_window(url):
    """The panel in a window of its own, with no browser chrome (Edge in app mode; the default browser if Edge is not there)."""
    for exe in (shutil.which("msedge"), r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if exe and os.path.exists(exe):
            try:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1400,860"])
                return True
            except OSError:
                pass
    return webbrowser.open(url)


class WebUI:
    def __init__(self):
        self.server = None
        self.cmds = queue.Queue()
        self.cond = threading.Condition()
        self.data, self.version = b"{}", 0
        self.t_pub = 0.0

    @property
    def url(self):
        return f"http://127.0.0.1:{PORT}"

    def configure(self, on):
        """Open or close the port. Returns an error message, or None."""
        if on and self.server is None:
            try:
                self.server = ThreadingHTTPServer(("127.0.0.1", PORT), self._handler())
            except OSError as e:
                self.server = None
                return f"Painel novo: a porta {PORT} está em uso ({e.strerror or e})"
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
        elif not on and self.server is not None:
            self.close()
        return None

    def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        with self.cond:
            self.version += 1
            self.cond.notify_all()

    def poll(self):
        out = []
        while not self.cmds.empty():
            out.append(self.cmds.get_nowait())
        return out

    def publish(self, menu, extra=None, every=0.1):
        """Once a frame: when the panel changed (and at most `every` seconds apart) the page gets the new snapshot."""
        now = time.monotonic()
        if self.server is None or now - self.t_pub < every:
            return
        self.t_pub = now
        data = json.dumps(snapshot(menu, extra), ensure_ascii=False).encode("utf-8")
        if data != self.data:
            with self.cond:
                self.data, self.version = data, self.version + 1
                self.cond.notify_all()

    def _handler(self):
        ui = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.split("?")[0] == "/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    seen = -1
                    try:
                        while ui.server is not None:
                            with ui.cond:
                                if ui.version == seen:
                                    ui.cond.wait(15.0)
                                v, data = ui.version, ui.data
                            if v != seen:
                                seen = v
                                self.wfile.write(b"data: " + data + b"\n\n")
                            else:
                                self.wfile.write(b": keep\n\n")
                            self.wfile.flush()
                    except (OSError, ValueError):
                        pass
                    return
                try:
                    with open(PAGE, "rb") as f:
                        body = f.read()
                except OSError:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path.split("?")[0] == "/cmd":
                    try:
                        n = int(self.headers.get("Content-Length", 0))
                        c = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
                        if isinstance(c, dict):
                            ui.cmds.put(c)
                    except (ValueError, OSError):
                        pass
                self.send_response(204)
                self.end_headers()

        return H
