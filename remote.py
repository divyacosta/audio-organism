"""Control from outside the program: OSC messages over UDP (port 9000) and MIDI notes (any MIDI input of Windows, through winmm - no extra package).
Both only turn into the keys of the picture window, so everything that works with the keyboard works from a controller or from another program:

  OSC   /scene 3 (or /scene/3)   scene 3          /auto  /strobe  /drop  /fullscreen  /stage  /vsync  /tap
  MIDI  notes 60..68 = scenes 1..9, 69 Auto, 70 drop, 71 strobe, 72 full screen, 73 stage mode, 74 VSync, 75 tap tempo

Switched on in Ajustes (off by default: the port is closed until it is wanted)."""
import queue
import socket
import struct
import sys
import threading

OSC_PORT = 9000
NOTE_KEYS = {69: "a", 70: "d", 71: "s", 72: "f", 73: "p", 74: "v", 75: "t"}
OSC_KEYS = {"auto": "a", "strobe": "s", "drop": "d", "fullscreen": "f", "stage": "p", "vsync": "v", "tap": "t"}


def parse_osc(data):
    """(address, [args]) of an OSC message, or None when it is not one. Ints and floats only (the rest is skipped)."""
    try:
        end = data.index(b"\0")
        addr = data[:end].decode("ascii", "replace")
        if not addr.startswith("/"):
            return None
        pos = (end + 4) & ~3
        args = []
        if pos < len(data) and data[pos:pos + 1] == b",":
            tend = data.index(b"\0", pos)
            tags = data[pos + 1:tend].decode("ascii", "replace")
            pos = (tend + 4) & ~3
            for t in tags:
                if t == "i":
                    args.append(struct.unpack(">i", data[pos:pos + 4])[0])
                    pos += 4
                elif t == "f":
                    args.append(struct.unpack(">f", data[pos:pos + 4])[0])
                    pos += 4
                elif t in "TF":
                    args.append(t == "T")
                elif t == "s":
                    e = data.index(b"\0", pos)
                    args.append(data[pos:e].decode("utf-8", "replace"))
                    pos = (e + 4) & ~3
                else:
                    break
        return addr, args
    except Exception:
        return None


def osc_key(addr, args):
    """The key an OSC message stands for, or None."""
    parts = [p for p in addr.lower().split("/") if p]
    if not parts:
        return None
    if parts[0] == "scene":
        n = None
        if len(parts) > 1 and parts[1].isdigit():
            n = int(parts[1])
        elif args and isinstance(args[0], (int, float)) and not isinstance(args[0], bool):
            n = int(args[0])
        return str(n) if n is not None and 1 <= n <= 9 else None
    if args and isinstance(args[0], (int, float)) and args[0] == 0:         # a button released (value 0) does nothing
        return None
    return OSC_KEYS.get(parts[0])


def midi_key(status, d1, d2):
    """The key a MIDI note-on stands for, or None."""
    if status & 0xF0 != 0x90 or d2 == 0:
        return None
    if 60 <= d1 <= 68:
        return str(d1 - 59)
    return NOTE_KEYS.get(d1)


class Remote:
    def __init__(self):
        self.q = queue.SimpleQueue()
        self.osc_on = self.midi_on = False
        self._sock = None
        self._thread = None
        self._midi = []                     # (handle, callback) pairs, kept alive
        self.error = None
        self._want = (False, False)

    # ------------------------------------------------------------------ OSC
    def _osc_loop(self, sock):
        while self._sock is sock:
            try:
                data, _ = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            msg = parse_osc(data)
            if msg:
                k = osc_key(*msg)
                if k:
                    self.q.put(k)

    def _start_osc(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", OSC_PORT))
            sock.settimeout(0.3)
        except OSError as e:
            self.error = f"OSC: porta {OSC_PORT} ocupada ({str(e)[:40]})"
            return False
        self._sock = sock
        self._thread = threading.Thread(target=self._osc_loop, args=(sock,), daemon=True)
        self._thread.start()
        return True

    def _stop_osc(self):
        s, self._sock = self._sock, None
        if s is not None:
            try:
                s.close()
            except OSError:
                pass

    # ----------------------------------------------------------------- MIDI
    def _start_midi(self):
        if sys.platform != "win32":
            self.error = "MIDI só no Windows"
            return False
        import ctypes
        from ctypes import wintypes
        winmm = ctypes.windll.winmm
        n = winmm.midiInGetNumDevs()
        if n == 0:
            self.error = "MIDI: nenhum dispositivo de entrada"
            return False
        CB = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.UINT, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t)

        def cb(h, msg, inst, p1, p2):
            if msg == 0x3C3:                                         # MIM_DATA
                k = midi_key(p1 & 0xFF, (p1 >> 8) & 0xFF, (p1 >> 16) & 0xFF)
                if k:
                    self.q.put(k)
        callback = CB(cb)
        opened = 0
        for i in range(n):
            h = wintypes.HANDLE()
            if winmm.midiInOpen(ctypes.byref(h), i, callback, 0, 0x30000) == 0:          # CALLBACK_FUNCTION
                winmm.midiInStart(h)
                self._midi.append((h, callback))
                opened += 1
        if not opened:
            self.error = "MIDI: não consegui abrir a entrada"
            return False
        return True

    def _stop_midi(self):
        if sys.platform != "win32":
            return
        import ctypes
        for h, _ in self._midi:
            try:
                ctypes.windll.winmm.midiInStop(h)
                ctypes.windll.winmm.midiInClose(h)
            except Exception:
                pass
        self._midi = []

    # -------------------------------------------------------------------- API
    def configure(self, osc, midi):
        """Switch the two inputs on or off. Returns a message when one cannot start (once)."""
        self.error = None
        want = (bool(osc), bool(midi))
        if want == self._want:                                   # nothing asked for has changed: do not retry what failed
            return None
        old, self._want = self._want, want
        if want[0] != old[0]:
            self.osc_on = self._start_osc() if want[0] else (self._stop_osc() or False)
        if want[1] != old[1]:
            self.midi_on = self._start_midi() if want[1] else (self._stop_midi() or False)
        return self.error

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                return out

    def close(self):
        self._stop_osc()
        self._stop_midi()
