"""See the picture on a phone: a small web server inside the program (port 8080).

The page at http://<this PC>:8080 shows the finished picture live (the same small copy the Palco thumbnail uses, sent as MJPEG)
and a row of buttons that act like the keys of the picture window (scenes 1..9, Auto, drop, strobe, tap).
It does not go through screen capture, so it works where remote-desktop tools show a black window.

Switched on in Ajustes (off by default: the port is closed until it is wanted). Anyone on the same network can open it."""
import io
import queue
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 8080
KEYS = set("123456789adst")                       # what the page may press: scenes, Auto, drop, strobe, tap

PAGE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Audio Organism</title>
<style>
body{margin:0;background:#07070c;color:#e8e9f0;font:15px system-ui,sans-serif;padding:12px 16px;display:flex;flex-direction:column;gap:12px}
img{width:100%;border-radius:10px;background:#000;display:block}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(56px,1fr));gap:8px}
button{font:inherit;color:#e8e9f0;background:#141622;border:1px solid #2a2d40;border-radius:10px;min-height:48px;cursor:pointer}
button:active{background:#2a1622}
h1{font-size:16px;margin:0;font-weight:600}
</style></head><body>
<h1>Audio Organism</h1>
<img src="/stream" alt="Imagem ao vivo do visualizador">
<div class="row">%SCENES%</div>
<div class="row"><button data-k="a">Auto</button><button data-k="d">Drop</button><button data-k="s">Strobe</button><button data-k="t">Tap</button></div>
<script>
document.querySelectorAll('button').forEach(b=>b.onclick=()=>fetch('/key?k='+b.dataset.k,{method:'POST'}));
</script></body></html>"""


_ip = [None, 0.0]


def local_ip():
    """The address of this PC on the network (no packet is sent: a UDP socket only picks the route). Asked again every 10 s."""
    import time
    if _ip[0] is None or time.monotonic() - _ip[1] > 10.0:
        _ip[0], _ip[1] = _route_ip(), time.monotonic()
    return _ip[0]


def _route_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class Stream:
    def __init__(self):
        self.server = None
        self.keys = queue.Queue()
        self.cond = threading.Condition()
        self.raw = None                            # (bytes, (w, h), fmt) of the newest picture, encoded on demand by the senders
        self.n = 0
        self.jpg, self.jpg_n = None, -1
        self.clients = 0

    @property
    def url(self):
        return f"http://{local_ip()}:{PORT}"

    def configure(self, on):
        """Open or close the port. Returns an error message, or None."""
        if on and self.server is None:
            try:
                self.server = ThreadingHTTPServer(("0.0.0.0", PORT), self._handler())
            except OSError as e:
                self.server = None
                return f"Ver no celular: a porta {PORT} está em uso ({e.strerror or e})"
            self.server.daemon_threads = True
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
        elif not on and self.server is not None:
            self.close()
        return None

    def close(self):
        if self.server is not None:
            srv, self.server = self.server, None
            threading.Thread(target=lambda: (srv.shutdown(), srv.server_close()), daemon=True).start()
        with self.cond:
            self.cond.notify_all()

    @property
    def wanted(self):
        return self.server is not None and self.clients > 0

    def push(self, rgba, size, fmt):
        """Hand over a new picture (cheap: only a reference; JPEG is made by the thread that sends it)."""
        with self.cond:
            self.raw = (rgba, size, fmt)
            self.n += 1
            self.cond.notify_all()

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.keys.get_nowait())
            except queue.Empty:
                return out

    def _jpeg(self):
        with self.cond:
            if self.jpg_n == self.n:
                return self.jpg
            raw, n = self.raw, self.n
        import pygame
        data, (w, h), fmt = raw
        surf = pygame.image.frombuffer(data, (w, h), "BGRA" if str(fmt).startswith("bgra") else "RGBA")
        buf = io.BytesIO()
        pygame.image.save(surf, buf, "f.jpg")
        with self.cond:
            self.jpg, self.jpg_n = buf.getvalue(), n
        return self.jpg

    def _handler(self):
        st = self
        scenes = "".join(f'<button data-k="{i}">{i}</button>' for i in range(1, 10))

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                path = urlparse(self.path).path
                if path == "/":
                    body = PAGE.replace("%SCENES%", scenes).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif path == "/stream":
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    st.clients += 1
                    last = -1
                    try:
                        while st.server is not None:
                            with st.cond:
                                if st.n == last or st.raw is None:
                                    st.cond.wait(1.0)
                                if st.n == last or st.raw is None:
                                    continue
                                last = st.n
                            jpg = st._jpeg()
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                    except (OSError, ValueError):
                        pass                                     # the phone closed the page
                    finally:
                        st.clients -= 1
                else:
                    self.send_error(404)

            def do_POST(self):
                u = urlparse(self.path)
                k = (parse_qs(u.query).get("k") or [""])[0]
                if u.path == "/key" and k in KEYS:
                    st.keys.put(k)
                    self.send_response(204)
                    self.end_headers()
                else:
                    self.send_error(400)

        return H
