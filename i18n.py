"""The language of the panel. The program is written in Portuguese; another language is a table `lang/<code>.json` of {Portuguese text: translation}.

Nothing in the code calls a translation function: the fonts of the panel (widgets.font) translate what they draw and what they measure, so every label,
help text and button changes language, and the layout measures the words it really draws. A text that has numbers in it is found through the entries that
have {n} in their place ("Drop em ~{n} compassos"). A line made of parts joined by "  ·  " is translated part by part. What has no entry stays as it is
(the names people give their scenes, for one)."""
import json
import locale
import os
import re
import sys

LANGS = [("Português", "pt"), ("English", "en")]
LANG = "pt"
_exact, _pat = {}, []
_NUM = r"(-?\d+(?:[.,]\d+)?)"


def base_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def system_lang():
    """The language of Windows: English for anything that is not Portuguese."""
    try:
        import ctypes
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "pt" if (lid & 0x3FF) == 0x16 else "en"
    except Exception:
        try:
            return "pt" if (locale.getlocale()[0] or "").lower().startswith(("pt", "portuguese")) else "en"
        except Exception:
            return "pt"


def set_lang(code):
    """Load the table of a language ("pt" needs none)."""
    global LANG, _exact, _pat
    code = code if code in [c for _, c in LANGS] else "pt"
    if code == LANG and (code == "pt" or _exact):
        return
    LANG, _exact, _pat = code, {}, []
    if code == "pt":
        return
    try:
        with open(os.path.join(base_dir(), "lang", code + ".json"), encoding="utf-8") as f:
            table = json.load(f)
    except Exception:
        return
    for k, v in table.items():
        if not isinstance(v, str) or not v:
            continue
        if "{n}" in k:
            rx = re.compile("^" + re.escape(k).replace(re.escape("{n}"), _NUM) + "$")
            _pat.append((rx, v))
        else:
            _exact[k] = v


def T(text):
    """The text in the language of the panel."""
    if LANG == "pt" or not isinstance(text, str) or not text:
        return text
    hit = _exact.get(text)
    if hit is not None:
        return hit
    if "  ·  " in text:
        return "  ·  ".join(T(p) for p in text.split("  ·  "))
    for rx, v in _pat:
        m = rx.match(text)
        if m:
            out = v
            for g in m.groups():
                out = out.replace("{n}", g, 1)
            return out
    return text
