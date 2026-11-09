#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QUANTUMATOR – Wissenschaftlicher Super-Rechner (100 % offline)

Android-App (APK) bauen:   siehe README  (GitHub Actions, kein PC nötig)
Am PC / in Termux testen:  pip install sympy   und   python main.py
                           → Browser: http://127.0.0.1:8765
"""
import sys
import os

# ───────────── Build-Hilfe:  python main.py --prepare  (nur Standardbibliothek) ─────────────
SPEC = """[app]
title = Quantumator
package.name = quantumator
package.domain = org.quantumator
source.dir = .
source.include_exts = py,png
source.exclude_dirs = .github,bin,.buildozer,__pycache__
version = 1.2.0
requirements = python3,sympy,mpmath
orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/icon.png
android.api = 33
android.minapi = 24
android.archs = arm64-v8a
android.permissions = INTERNET
android.accept_sdk_license = True
android.allow_backup = True
p4a.bootstrap = webview
p4a.port = 5000

[buildozer]
log_level = 2
warn_on_root = 0
"""


def make_icon(path, size=512, opaque=False):
    import zlib
    import struct
    import math

    def clamp(v, a=0.0, b=1.0):
        return a if v < a else b if v > b else v

    def seg_dist(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        t = clamp(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    def mix(c1, c2, t):
        return tuple(c1[i] + (c2[i] - c1[i]) * t for i in range(3))

    S = size / 512.0
    gold, blue = (240, 200, 90), (70, 150, 255)
    sigma = [((200, 196), (312, 196)), ((200, 196), (258, 256)), ((258, 256), (200, 316)), ((200, 316), (312, 316))]
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            X, Y = x / S, y / S
            # abgerundetes Quadrat
            qx, qy = abs(X - 256) - (256 - 96), abs(Y - 256) - (256 - 96)
            d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - 96
            a = 1.0 if opaque else clamp(0.5 - d * S)
            t = clamp((X + Y) / 1024.0)
            col = mix((6, 10, 24), (14, 28, 62), t)
            # Ring + Schwanz (Q)
            dr = abs(math.hypot(X - 240, Y - 236) - 140) - 20
            dt = seg_dist(X, Y, 330, 326, 410, 406) - 20
            dq = min(dr, dt)
            cq = clamp(0.5 - dq * S)
            if cq > 0:
                col = mix(col, mix(gold, blue, clamp((X + Y - 200) / 560.0)), cq)
            # Sigma
            ds = min(seg_dist(X, Y, *s[0], *s[1]) for s in sigma) - 11
            cs = clamp(0.5 - ds * S)
            if cs > 0:
                col = mix(col, (255, 255, 255), cs)
            row += bytes((int(col[0]), int(col[1]), int(col[2]), int(a * 255)))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


def prepare():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "buildozer.spec"), "w", encoding="utf-8") as fh:
        fh.write(SPEC)
    make_icon(os.path.join(here, "icon.png"))
    print("buildozer.spec und icon.png erzeugt.")


if "--prepare" in sys.argv:
    prepare()
    sys.exit(0)

# ═════════════════════════════════════════════════════════════════════════
import re
import json
import threading
import http.server
import socketserver
import webbrowser

ON_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ
DATA_DIR = os.environ.get("ANDROID_PRIVATE") or os.path.expanduser("~")
CONFIG_PATH = os.path.join(DATA_DIR, ".quantumator.json")

def B(label, ins=None, kind="fn"):
    return (label, label if ins is None else ins, kind)


KEYPADS = {
    "Basis": [
        [B("C", "<C>", "del"), B("⌫", "<DEL>", "del"), B("(", kind="op"), B(")", kind="op"),
         B(";", kind="op"), B("÷", "/", "op")],
        [B("7", kind="num"), B("8", kind="num"), B("9", kind="num"), B("×", "*", "op"),
         B("x²", "^2"), B("xʸ", "^(□)")],
        [B("4", kind="num"), B("5", kind="num"), B("6", kind="num"), B("−", "-", "op"),
         B("√", "√(¦)"), B("n!", "!")],
        [B("1", kind="num"), B("2", kind="num"), B("3", kind="num"), B("+", kind="op"),
         B("a⁄b", "(¦)/(□)"), B("|x|", "|¦|")],
        [B("0", kind="num"), B(",", "<DEC>", "num"), B("π", "π"), B("e"), B("ans"),
         B("=", "<EQ>", "acc")],
        [B("x"), B("y"), B("◀", "<LEFT>", "op"), B("▶", "<RIGHT>", "op"), B("⇥", "<NEXT>", "op"),
         B("Gl.=", "=", "op")],
    ],
    "Funktionen": [
        [B("sin", "sin(¦)"), B("cos", "cos(¦)"), B("tan", "tan(¦)"),
         B("sinh", "sinh(¦)"), B("cosh", "cosh(¦)"), B("tanh", "tanh(¦)")],
        [B("sin⁻¹", "asin(¦)"), B("cos⁻¹", "acos(¦)"), B("tan⁻¹", "atan(¦)"),
         B("sinh⁻¹", "asinh(¦)"), B("cosh⁻¹", "acosh(¦)"), B("tanh⁻¹", "atanh(¦)")],
        [B("ln", "ln(¦)"), B("lg", "lg(¦)"), B("logₐ", "log(¦;□)"),
         B("eˣ", "e^(¦)"), B("10ˣ", "10^(¦)"), B("ⁿ√", "wurzel(¦;□)")],
        [B("√", "√(¦)"), B("∛", "∛(¦)"), B("|x|", "|¦|"),
         B("⌊x⌋", "boden(¦)"), B("⌈x⌉", "decke(¦)"), B("Γ", "gamma(¦)")],
        [B("→Grad", "grad(¦)"), B("→Bog.", "bogen(¦)"), B("erf", "erf(¦)"),
         B("atan2", "atan2(¦;□)"), B("max", "maxi(¦)"), B("min", "mini(¦)")],
        [B("x"), B("y"), B("t"), B("n"), B("k"), B("∞", "∞")],
    ],
    "Komplex": [
        [B("i", kind="acc"), B("Re", "re(¦)"), B("Im", "im(¦)"), B("|z|", "|¦|"),
         B("arg", "arg(¦)"), B("z̄", "konj(¦)")],
        [B("polar", "polar(¦)"), B("kart.", "kart(¦)"), B("r,φ→z", "kart(¦;□)"),
         B("zⁿ", "^(□)"), B("ⁿ√z", "wurzeln(¦;□)"), B("1ⁿ√", "einheitswurzeln(¦)")],
        [B("e^(iφ)", "e^(i*¦)"), B("a+bi", "(¦+□*i)"), B("√", "√(¦)"),
         B("sin", "sin(¦)"), B("cos", "cos(¦)"), B("ln", "ln(¦)")],
        [B("(", kind="op"), B(")", kind="op"), B("π", "π"), B("e"), B("ans"),
         B("=", "<EQ>", "acc")],
    ],
    "Gleichungen": [
        [B("=", "=", "acc"), B("<", kind="op"), B(">", kind="op"), B("≤", "<=", "op"),
         B("≥", ">=", "op"), B("löse", "loese(¦;x)")],
        [B("System", "¦=□; □=□"), B("vereinf.", "vereinfache(¦)"), B("expand", "expandiere(¦)"),
         B("faktor", "faktorisiere(¦)"), B("kürzen", "kuerze(¦)"), B("Partialbr.", "partialbruch(¦;x)")],
        [B("Nullst.", "nullstellen(¦;x)"), B("einsetz.", "subs(¦;x;□)"), B("nlöse", "nloese(¦;x;□)"),
         B("Poly÷", "polydiv(¦;□;x)"), B("Koeff.", "koeffizienten(¦;x)"), B("trigvf.", "trigvereinfache(¦)")],
        [B("Extrema", "extrema(¦;x)"), B("Wendep.", "wendepunkte(¦;x)"), B("Tangente", "tangente(¦;x;□)"),
         B("f(x)=", "f(x)=¦"), B("g(x)=", "g(x)=¦"), B("x")],
    ],
    "Analysis": [
        [B("∫", "∫¦ dx", "acc"), B("∫ₐᵇ", "∫_{□}^{□} □ dx", "acc"), B("d/dx", "d/dx □"),
         B("d²/dx²", "d^2/dx^2 □"), B("∂/∂x", "∂/∂x □"), B("∞", "∞")],
        [B("Σ", "∑_{k=1}^{□} □", "acc"), B("Π", "∏_{k=1}^{□} □", "acc"), B("lim", "lim_{x→□} □"),
         B("lim⁺", "lim_{x→□+} □"), B("lim⁻", "lim_{x→□-} □"), B("⇥", "<NEXT>", "op")],
        [B("Taylor", "taylor(¦;x;0;6)"), B("Reihe", "reihe(¦;x;0;6)"), B("DGL", "dgl(¦)"),
         B("Laplace", "laplace(¦;t;s)"), B("L⁻¹", "invlaplace(¦;s;t)"), B("∇", "gradient(¦;x;y)")],
        [B("∫ num.", "nint(¦;x;□;□)"), B("y(x)", "y(x)"), B("y′", "ableitung(y(x);x)"),
         B("x"), B("y"), B("t")],
    ],
    "Matrix": [
        [B("Matrix", "matrix([[¦;□];[□;□]])"), B("Vektor", "vektor(¦;□;□)"), B("det", "det(¦)"),
         B("A⁻¹", "inv(¦)"), B("Aᵀ", "transp(¦)"), B("Rang", "rang(¦)")],
        [B("Spur", "spur(¦)"), B("λ", "eigenwerte(¦)"), B("v⃗", "eigenvektoren(¦)"),
         B("LGS", "lgs(¦;□)"), B("RREF", "rref(¦)"), B("Kern", "nullraum(¦)")],
        [B("a·b", "skalar(¦;□)"), B("a×b", "kreuz(¦;□)"), B("‖v‖", "norm(¦)"),
         B("∠", "winkel(¦;□)"), B("E", "einheitsmatrix(¦)"), B("0", "nullmatrix(¦;□)")],
        [B("A"), B("B"), B("A·B", "*", "op"), B("A^-1", "^-1", "op"),
         B("A=", "A=matrix([[¦]])"), B("B=", "B=matrix([[¦]])")],
    ],
    "Zahlen": [
        [B("ggT", "ggT(¦;□)"), B("kgV", "kgV(¦;□)"), B("mod", "rest(¦;□)"),
         B("Primf.", "primfaktoren(¦)"), B("prim?", "istprim(¦)"), B("nächste P", "naechste_primzahl(¦)")],
        [B("Teiler", "teiler(¦)"), B("φ(n)", "totient(¦)"), B("Fib", "fib(¦)"),
         B("nCr", "binomial(¦;□)"), B("nPr", "perm(¦;□)"), B("modinv", "modinv(¦;□)")],
        [B("→Bin", "bin(¦)"), B("→Hex", "hex(¦)"), B("→Oct", "oct(¦)"),
         B("→Basis", "zubasis(¦;□)"), B("Basis→", 'vonbasis("¦";□)'), B("Zufall", "zufall()")],
        [B("Mittel", "mittel(¦)"), B("Median", "median(¦)"), B("σ", "stabw(¦)"),
         B("σ²", "varianz(¦)"), B("Min", "minimum(¦)"), B("Max", "maximum(¦)")],
        [B("%", "prozent(¦;□)"), B("Φ(x)", "normcdf(¦;0;1)"), B("φ(x)", "normpdf(¦)"),
         B("Binom", "binompmf(¦;□;□)"), B("Poisson", "poissonpmf(¦;□)"), B("Σ Liste", "summe(¦)")],
    ],
}

HELP_TEXT = """\
QUANTUMATOR – KURZHILFE
═════════════════════════════════════
FORMELSCHREIBWEISE (mit den Symbol-Tasten oder direkt tippen)
 Integral      ∫ x² dx · ∫₀³ x² dx · ∫_{0}^{π} sin(x) dx · ∫∫ x*y dx dy
 Summe/Produkt ∑_{k=1}^{10} k² · ∑_{k=1}^{∞} 1/k² · ∏_{k=1}^{5} k
 Grenzwert     lim_{x→0} sin(x)/x · lim_{x→∞} 1/x · lim_{x→0+} 1/x
 Ableitung     d/dx x³ · d²/dx² sin(x) · ∂/∂x (x²·y)
 Wurzeln       √16 · √(x+1) · ∛27 · Betrag |x−2| · Potenzen x² xⁿ x^{n+1}
 Platzhalter □ → Taste ⇥ springt zum nächsten □, ◀ ▶ bewegen den Cursor
 Über dem Ergebnis steht die Eingabe als gesetzte Formel (Vorschau beim Tippen);
 Tippen auf die Formel schaltet zwischen Formel und Text um.

EINGABE
 • Enter = berechnen · ↑/↓ = Verlauf · Esc = Zeile löschen
 • Argumente trennt man mit  ;   z. B. ggT(12;18)
 • Dezimal „Komma“ an:  3,14 = 3.14 (dann ; als Trenner!)
 • Implizite Multiplikation:  2x, 3(x+1), 2pi, 5i
 • Potenz ^ · Fakultät !  · Rest %  · Grad-Zeichen 90°
 • Analysis-Funktionen (ableitung, integral …) und der Graph
   rechnen immer im Bogenmaß.
 • Ergebnisse sind exakt (Brüche, Wurzeln, π …) und
   zusätzlich numerisch (≈) – Stellenzahl oben einstellbar.
 • ans = letztes Ergebnis

BEISPIELE
 Grundrechnen   (1+2)^3/4 · 7! · sqrt(8) · 0,1+0,2
 Winkel         sin(30) (GRAD)  ·  umschalten oben: GRAD/RAD
 Komplex        (3+4i)*(1-2i) · wurzel(-4) · polar(3+4i)
                wurzeln(1;3) · exp(i*pi) · kart(2;60)
 Variablen      a=5 · b=a^2+1 · Name := Wert · vergiss a · vergiss alle
 Funktionen     f(x)=x^2+1 · f(3) · g(x;y)=x*y
 Gleichungen    x^2-4=0 · x^2+1=0 · sin(x)=0,5 · cos(x)=x
 Systeme        x+y=5; x-y=1   (oder 3 Gleichungen …)
 Ungleichung    x^2>4 · (x-1)(x+2)<=0
 Analysis       ableitung(x*sin(x);x) · integral(x^2;x;0;3)
                grenzwert(sin(x)/x;x;0) · summe(1/k^2;k;1;oo)
                taylor(exp(x);x;0;5) · laplace(sin(t);t;s)
 DGL            dgl(ableitung(y(x);x;2)+y(x)=0)
 Matrizen       A=matrix([[1;2];[3;4]]) · det(A) · inv(A)
                A*A · A^-1 · eigenwerte(A) · lgs(A;vektor(1;2))
 Zahlen         primfaktoren(360) · ggT(48;18) · binomial(5;2)
                hex(255) · vonbasis("FF";16) · fib(30)
 Statistik      mittel(1;2;3;4) · stabw(2;4;4;5) · normcdf(1)

GRAPH (wie GeoGebra – Reiter „Graph“, jede Zeile = ein Objekt)
 Funktionen    f(x)=sin(x) · x^2-2 · y=sqrt(x) · g(x)=a*f(x)+1
               (Funktionen dürfen aufeinander aufbauen, f′(x) = Ableitung)
 Schieberegler a=2 legt einen an; jeder unbekannte Buchstabe (a, b, k …)
               wird automatisch ein Regler  ▶ = animieren, min/max änderbar
 Kurven        Kreis x^2+y^2=9 · Ellipse x^2/9+y^2/4=1 · x^3+y^3=6*x*y
               kreis((1;2);3) · x=3 (senkrechte Gerade)
 Parameter     (cos(t);sin(2*t));t=0..2*pi
 Polar         r=1+cos(t) · r=2*sin(3*t);t=0..2*pi
 Ungleichung   y>x^2 · x^2+y^2<=9 (Bereich wird gefärbt)
 Punkte        A=(1;2) · Strecke strecke(A;B) · gerade(A;B)
               polygon(A;B;(0;4))
 Fläche        flaeche(x^2;0;2) → Integral wird berechnet
 Analysis      ableitung(sin(x);x) · tangente(x^2;x;1) · integral(x^2;x)
 3D            z=sin(x)*cos(y) → Knopf „3D“, Ziehen = drehen, 2 Finger = zoomen
 Knöpfe        ⌂ einpassen · 1:1 gleiche Achsen · Gitter/Fein/Polar/Aus
               ◎ Nullstellen, Hoch-/Tiefpunkte, Schnittpunkte, y-Achsenabschnitt
               ⌖ Spur (Finger entlang der Kurve, zeigt f′) · ⤢ Vollbild
 Bedienung     Tippen = Koordinaten · Doppeltippen = einpassen
               Zwei Finger waagerecht/senkrecht = nur diese Achse zoomen
 Punkte mit ;  schreiben, z. B. (1;2); mit Dezimalkomma ist (1,2) ebenfalls ein Punkt.

FUNKTIONSLISTE (Auswahl)
 sin cos tan asin acos atan sinh cosh tanh … ln lg ld log(x;b) exp
 wurzel(x;n) betrag vorzeichen boden decke runde gamma erf zeta
 re im arg konj polar kart wurzeln einheitswurzeln
 loese nloese vereinfache expandiere faktorisiere kuerze
 partialbruch subs nullstellen extrema wendepunkte tangente
 ableitung integral limes limes_plus limes_minus summe produkt
 reihe taylor dgl laplace invlaplace gradient nint
 matrix vektor det inv transp rang spur rref nullraum
 eigenwerte eigenvektoren lgs skalar kreuz norm winkel
 ggT kgV rest modinv potmod istprim primfaktoren teiler totient
 fib binomial perm bin oct hex zubasis vonbasis zufall
 mittel median modus varianz stabw minimum maximum
 normpdf normcdf binompmf binomcdf poissonpmf prozent
Umlaut-freie Schreibweise (loese, kuerze …) geht immer.
"""




# ═════════════════════════════════════════════════════════════════════════
#  RECHENKERN wird im Hintergrund geladen (sympy braucht auf dem Handy einige Sekunden)
# ═════════════════════════════════════════════════════════════════════════
ENGINE, E, LOAD_ERR = None, None, None
READY = threading.Event()


def load_engine():
    global ENGINE, E, LOAD_ERR
    try:
        import engine as _e
        E = _e
        ENGINE = _e.Engine()
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                for d in json.load(fh).get("defs", []):
                    ENGINE.evaluate(d)
        except Exception:
            pass
    except Exception as ex:
        LOAD_ERR = "Rechenkern konnte nicht geladen werden: %s" % ex
    finally:
        READY.set()


def vars_snapshot():
    out = []
    if ENGINE is None:
        return out
    for k, v in sorted(ENGINE.vars.items()):
        out.append({"kind": "v", "name": k, "text": ENGINE.one_line(v).replace("\n", " ")})
    for k, f in sorted(ENGINE.funcs.items()):
        out.append({"kind": "f", "name": k, "text": "%s(%s) = %s" % (
            k, ", ".join(p.name for p in f.params), ENGINE.one_line(f.expr))})
    return out


def save_defs():
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump({"defs": list(ENGINE.defs.values())}, fh, ensure_ascii=False)
    except Exception:
        pass


def not_ready():
    READY.wait(180)
    if LOAD_ERR or ENGINE is None:
        return LOAD_ERR or "Der Rechenkern startet noch – bitte kurz warten."
    return None


def api_eval(data):
    err = not_ready()
    if err:
        return {"kind": "err", "msg": err, "extra": [], "vars": []}
    e = ENGINE
    e.deg = bool(data.get("deg", True))
    e.decimal_comma = bool(data.get("dec", True))
    e.digits = max(4, min(120, int(data.get("digits", 15))))
    box = {}

    def work():
        try:
            box["r"] = e.evaluate(str(data.get("text", "")))
        except Exception as ex:
            box["r"] = {"kind": "err", "msg": str(ex)}
    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(60)
    r = box.get("r") or {"kind": "err", "msg": "Zeitüberschreitung (60 s) – die Berechnung ist zu aufwendig."}
    res = {"kind": r["kind"], "input": r.get("input", ""), "main": r.get("main", ""),
           "extra": [[a, b] for a, b in r.get("extra", [])], "msg": r.get("msg", ""),
           "tex": r.get("tex"), "itex": r.get("itex"), "vars": vars_snapshot()}
    if r["kind"] == "assign":
        save_defs()
    return res


def api_preview(data):
    if not READY.is_set() or ENGINE is None:
        return {"tex": None}
    ENGINE.decimal_comma = bool(data.get("dec", True))
    box = {}

    def work():
        box["t"] = ENGINE.preview_tex(str(data.get("text", "")))
    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(5)
    return {"tex": box.get("t")}


def api_gparse(data):
    entries = [str(t) for t in data.get("entries", [])][:40]
    err = not_ready()
    if err:
        return {"results": [{"kind": "err", "msg": err} for _ in entries]}
    ENGINE.decimal_comma = bool(data.get("dec", True))
    box = {}

    def work():
        try:
            box["r"] = ENGINE.graph_batch(entries)
        except Exception as ex:
            box["r"] = [{"kind": "err", "msg": str(ex)} for _ in entries]
    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(25)
    return {"results": box.get("r") or [{"kind": "err", "msg": "Zeitüberschreitung beim Analysieren."} for _ in entries]}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif p == "/api/ready":
            self._send(200, json.dumps({"ready": READY.is_set(), "error": LOAD_ERR}), "application/json")
        elif p == "/api/state":
            self._send(200, json.dumps({"vars": vars_snapshot()}), "application/json")
        else:
            self._send(404, "Nicht gefunden", "text/plain; charset=utf-8")

    def do_POST(self):
        try:
            ln = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(ln).decode("utf-8") or "{}")
            if self.path == "/api/eval":
                out = api_eval(data)
            elif self.path == "/api/preview":
                out = api_preview(data)
            elif self.path == "/api/gparse":
                out = api_gparse(data)
            else:
                return self._send(404, "{}", "application/json")
            self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        except Exception as ex:
            self._send(200, json.dumps({"kind": "err", "msg": str(ex), "extra": [], "vars": []}),
                       "application/json; charset=utf-8")


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    srv, port = None, 5000
    ports = [5000] if ON_ANDROID else range(8765, 8785)
    for port in ports:
        try:
            srv = Server(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        print("Kein freier Port gefunden.")
        sys.exit(1)
    threading.Thread(target=load_engine, daemon=True).start()
    url = "http://127.0.0.1:%d" % port
    print("\n  QUANTUMATOR läuft (offline, nur auf diesem Gerät): %s\n" % url)
    if not ON_ANDROID:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")


PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
<meta name="theme-color" content="#ffffff" id="themecolor">
<title>Quantumator</title>
<style>
:root{--bg:#FFFFFF;--bg2:#FFF9E8;--card:#FFFFFF;--line:#C9A227;--line2:#EBDDAA;--text:#2A2413;--dim:#8C7B43;--pat:#F7EFD6;--dot:#EBD98F;
--inbg:#FFFEFA;--knum:#FFFFFF;--kfn:#FFF8E0;--kop:#FCEEBF;--kacc:#D4AF37;--kacc2:#B8901A;--kaccfg:#FFFFFF;--kdel:#FDE9E5;--kdelfg:#B3261E;
--sel:#F8E7A6;--err:#B3261E;--g1:#E8C547;--g2:#A97F14;--glow:0 6px 22px rgba(201,162,39,.16);--kshadow:0 2px 5px rgba(120,95,20,.10);
--p0:#B8860B;--p1:#1F6FEB;--p2:#C0392B;--p3:#2E7D32;--p4:#8E44AD;--p5:#00897B;--p6:#E67E22;--p7:#6D4C41}
[data-theme=dark]{--bg:#03050A;--bg2:#070C16;--card:#09101C;--line:#2F7BFF;--line2:#1B3A73;--text:#E6EEFF;--dim:#7F95C0;--pat:#0A1424;--dot:#16305C;
--inbg:#050911;--knum:#0B1423;--kfn:#0E1B33;--kop:#12274C;--kacc:#3B87FF;--kacc2:#2262D6;--kaccfg:#FFFFFF;--kdel:#2A0F14;--kdelfg:#FF7B7B;
--sel:#173A78;--err:#FF7B7B;--g1:#7DBBFF;--g2:#2F7BFF;--glow:0 0 0 1px rgba(47,123,255,.10),0 8px 28px rgba(47,123,255,.14);--kshadow:0 2px 6px rgba(0,0,0,.5);
--p0:#4DA3FF;--p1:#FFD166;--p2:#FF7B7B;--p3:#4ADE80;--p4:#C792EA;--p5:#2DD4BF;--p6:#FB923C;--p7:#F472B6}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;height:100%;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;overscroll-behavior:none;-webkit-user-select:none;user-select:none}
body,header,.frame,.inner,.key,.btn,.tab,#result,#inp,nav,.sheet,.seg button{transition:background-color .4s ease,border-color .4s ease,color .4s ease,box-shadow .4s ease}
.pattern{background-color:var(--bg);background-image:linear-gradient(45deg,var(--pat) 1px,transparent 1px),linear-gradient(-45deg,var(--pat) 1px,transparent 1px),radial-gradient(var(--dot) 1.3px,transparent 1.8px);background-size:16px 16px}
#app{display:flex;flex-direction:column;height:100dvh;padding-top:env(safe-area-inset-top);background:linear-gradient(180deg,var(--bg) 0%,var(--bg2) 100%)}
header{padding:9px 12px;border-bottom:2px solid var(--line);box-shadow:var(--glow)}
.hrow{display:flex;align-items:center;justify-content:space-between;gap:8px}
.brand{display:flex;align-items:center;gap:9px;background:var(--bg);border:1.5px solid var(--line);border-radius:14px;padding:5px 14px 5px 8px;box-shadow:var(--glow)}
.brand svg{display:block}
.brand b{display:block;font-size:17px;letter-spacing:2.4px;color:var(--line);font-weight:800}
.brand small{display:block;font-size:9px;color:var(--dim);letter-spacing:.4px;margin-top:1px}
.tools{display:flex;gap:6px;background:var(--card);border:1.5px solid var(--line);border-radius:14px;padding:4px;box-shadow:var(--glow)}
.tool{min-width:38px;height:34px;border:0;border-radius:10px;background:transparent;color:var(--text);font-weight:800;font-size:12px;display:grid;place-items:center;touch-action:manipulation;transition:transform .12s,background-color .2s}
.tool:active{transform:scale(.9);background:var(--sel)}
.tool.pill{background:var(--kacc);color:var(--kaccfg);padding:0 11px}
.tool svg{width:19px;height:19px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
main{flex:1;overflow:auto;padding:10px 10px 4px;-webkit-overflow-scrolling:touch;scrollbar-width:none}
main::-webkit-scrollbar{display:none}
.view{display:none}
.view.on{display:block;animation:up .32s cubic-bezier(.2,.85,.25,1)}
@keyframes up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.frame{border:1.5px solid var(--line);padding:8px;border-radius:20px;margin-bottom:10px;box-shadow:var(--glow)}
.inner{background:var(--card);border:1px solid var(--line2);padding:10px;border-radius:14px}
.irow{display:flex;align-items:center;gap:7px}
.prompt{color:var(--line);font:800 24px ui-monospace,Menlo,Consolas,monospace}
#inp{flex:1;min-width:0;font:21px ui-monospace,Menlo,Consolas,monospace;background:var(--inbg);color:var(--text);border:1.5px solid var(--line2);border-radius:12px;padding:11px 10px;outline:none;caret-color:var(--line);-webkit-user-select:text;user-select:text}
#inp:focus{border-color:var(--line);box-shadow:0 0 0 3px color-mix(in srgb,var(--line) 18%,transparent)}
.kb{width:42px;height:44px;border:1.5px solid var(--line2);background:var(--card);color:var(--text);border-radius:12px;font-size:19px;touch-action:manipulation;transition:transform .12s}
.kb:active{transform:scale(.9)}
#status{font-size:11px;color:var(--dim);margin:7px 3px 6px}
#result{background:var(--inbg);border:1px solid var(--line2);border-radius:12px;padding:10px;max-height:31vh;min-height:92px;overflow:auto;-webkit-user-select:text;user-select:text}
#result>*{animation:up .3s cubic-bezier(.2,.85,.25,1) both}
#result pre{margin:0;font:13px/1.3 ui-monospace,Menlo,Consolas,monospace;white-space:pre;overflow-x:auto}
#result .main{font-weight:800;margin:3px 0;color:var(--text)}
#result .echo{font-size:11px;color:var(--dim);font-family:ui-monospace,Menlo,monospace;word-break:break-all}
#result .lab{font-size:10.5px;font-weight:800;letter-spacing:.8px;color:var(--line);margin-top:9px;text-transform:uppercase}
#result .err{color:var(--err)}#result .errh{color:var(--err);font-weight:800;font-size:19px}
.ex{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.ex-t{font-size:11px;color:var(--dim);font-weight:700;letter-spacing:.6px}
.xchip{border:1px solid var(--line2);background:var(--kfn);color:var(--text);border-radius:999px;padding:7px 12px;font:12px ui-monospace,Menlo,monospace;touch-action:manipulation;transition:transform .12s}
.xchip:active{transform:scale(.94)}
.actions{display:flex;gap:7px;margin-top:8px}
.btn{flex:1;border:1px solid var(--line2);background:var(--kfn);color:var(--text);font-weight:700;font-size:12px;padding:11px 6px;border-radius:12px;touch-action:manipulation;transition:transform .12s,background-color .3s}
.btn:active{transform:scale(.95)}
.btn.del{background:var(--kdel);color:var(--kdelfg)}
.btn.acc{background:linear-gradient(135deg,var(--kacc),var(--kacc2));color:var(--kaccfg);border-color:var(--kacc)}
.tabs{display:flex;gap:5px;overflow-x:auto;padding:1px 1px 8px;scrollbar-width:none;scroll-behavior:smooth}
.tabs::-webkit-scrollbar{display:none}
.tab{flex:0 0 auto;border:1px solid var(--line2);background:var(--bg);color:var(--dim);font-weight:700;font-size:12px;padding:9px 14px;border-radius:999px;touch-action:manipulation}
.tab.on{background:linear-gradient(135deg,var(--kacc),var(--kacc2));color:var(--kaccfg);border-color:var(--kacc);box-shadow:var(--kshadow)}
.pad{display:none;grid-template-columns:repeat(6,1fr);gap:6px}
.pad.on{display:grid;animation:padin .26s cubic-bezier(.2,.85,.25,1) both}
@keyframes padin{from{opacity:0;transform:translateX(calc(var(--dir,1)*22px))}to{opacity:1;transform:none}}
.key{min-height:50px;border:1px solid var(--line2);border-radius:14px;font-weight:700;font-size:18px;color:var(--text);padding:2px;touch-action:manipulation;line-height:1.1;box-shadow:var(--kshadow);transition:transform .09s ease,background-color .25s,box-shadow .09s,border-color .4s}
.key.s{font-size:11.5px}
.key:active,.key.pr{transform:scale(.92);box-shadow:none;border-color:var(--line);filter:brightness(.96)}
.k-num{background:var(--knum)}.k-fn{background:var(--kfn)}.k-op{background:var(--kop)}
.k-acc{background:linear-gradient(135deg,var(--kacc),var(--kacc2));color:var(--kaccfg);border-color:var(--kacc)}.k-del{background:var(--kdel);color:var(--kdelfg)}
nav{position:relative;display:flex;margin:6px 10px calc(8px + env(safe-area-inset-bottom));background:var(--card);border:1.5px solid var(--line);border-radius:20px;box-shadow:var(--glow);overflow:hidden}
nav .ind{position:absolute;top:0;bottom:0;left:0;width:20%;background:linear-gradient(135deg,var(--kacc),var(--kacc2));border-radius:18px;transition:transform .38s cubic-bezier(.3,1.25,.5,1)}
nav button{position:relative;flex:1;border:0;background:transparent;color:var(--dim);padding:8px 0 7px;font-size:10.5px;font-weight:700;transition:color .25s;touch-action:manipulation}
nav button svg{display:block;margin:0 auto 2px;width:21px;height:21px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
nav button.on{color:var(--kaccfg)}
.list{list-style:none;margin:0;padding:0}
.list li{display:flex;gap:8px;align-items:center;border:1px solid var(--line2);background:var(--inbg);border-radius:12px;padding:11px;margin-bottom:6px;font:13px ui-monospace,Menlo,Consolas,monospace;word-break:break-all;animation:up .3s both;transition:transform .12s}
.list li:active{transform:scale(.98)}
.list li span{flex:1}.list li small{color:var(--dim)}
.list li .x{border:1px solid var(--line2);background:var(--kdel);color:var(--kdelfg);border-radius:10px;padding:7px 11px;font-weight:800}
.empty{color:var(--dim);font-size:13px;padding:16px;text-align:center}

.gwrap{position:relative}
.gbar{display:flex;gap:6px;overflow-x:auto;padding-bottom:8px;scrollbar-width:none}
.gbar::-webkit-scrollbar{display:none}
.gb{flex:0 0 auto;min-width:42px;height:38px;border:1px solid var(--line2);background:var(--kfn);color:var(--text);border-radius:12px;font-weight:800;font-size:12px;padding:0 11px;touch-action:manipulation;transition:transform .12s,background-color .25s}
.gb:active{transform:scale(.92)}
.gb.on{background:linear-gradient(135deg,var(--kacc),var(--kacc2));color:var(--kaccfg);border-color:var(--kacc)}
.gb.fsonly{display:none}
#cv{width:100%;height:46vh;display:block;background:var(--inbg);border:1px solid var(--line2);border-radius:14px;touch-action:none;cursor:crosshair}
#gtip{position:absolute;pointer-events:none;background:var(--card);color:var(--text);border:1.5px solid var(--line);border-radius:10px;padding:5px 10px;font:700 12px ui-monospace,Menlo,monospace;opacity:0;transition:opacity .18s;white-space:nowrap;box-shadow:var(--glow);z-index:3}
#galg{margin-top:10px}
.arow{display:flex;align-items:center;gap:7px;margin-bottom:6px}
.adot{width:30px;height:30px;border-radius:50%;border:2.5px solid var(--line);flex:0 0 auto;padding:0;transition:transform .12s,background-color .25s}
.adot:active{transform:scale(.85)}
.ain{flex:1;min-width:0;font:15px ui-monospace,Menlo,Consolas,monospace;background:var(--inbg);color:var(--text);border:1.5px solid var(--line2);border-radius:12px;padding:10px;outline:none;-webkit-user-select:text;user-select:text}
.ain:focus{border-color:var(--line)}
.adel{width:34px;height:34px;flex:0 0 auto;border:1px solid var(--line2);background:var(--kdel);color:var(--kdelfg);border-radius:10px;font-weight:800}
.aerr{font-size:11px;color:var(--err);margin:-2px 0 8px 37px}
.ainfo{font-size:11px;color:var(--dim);margin:-2px 0 8px 37px}
.slrow{border:1px solid var(--line2);background:var(--inbg);border-radius:12px;padding:8px 10px;margin-bottom:7px}
.sltop{display:flex;align-items:center;gap:9px}
.sltop input[type=range]{flex:1;min-width:0;accent-color:var(--line)}
.sln{font:800 16px ui-monospace,Menlo,monospace;color:var(--line);min-width:18px}
.slv{font:700 12px ui-monospace,Menlo,monospace;min-width:48px;text-align:right}
.slp{width:36px;height:32px;border:0;border-radius:10px;background:linear-gradient(135deg,var(--kacc),var(--kacc2));color:var(--kaccfg);font-weight:800}
.slrow2{display:flex;align-items:center;gap:6px;margin-top:6px;color:var(--dim)}
.slmm{width:62px;font:12px ui-monospace,Menlo,monospace;background:var(--card);color:var(--text);border:1px solid var(--line2);border-radius:8px;padding:5px}
.mk-wrap{display:flex;gap:5px;overflow-x:auto;padding:8px 0 2px;scrollbar-width:none}
.mk-wrap::-webkit-scrollbar{display:none}
.mk{flex:0 0 auto;min-width:38px;height:36px;border:1px solid var(--line2);background:var(--kfn);color:var(--text);border-radius:10px;font:700 14px ui-monospace,Menlo,monospace;padding:0 9px;touch-action:manipulation}
.mk:active{background:var(--sel)}
body.gfs header,body.gfs nav{display:none}
body.gfs #v-graph .gwrap{position:fixed;inset:0;z-index:30;background:var(--bg)}
body.gfs #cv{height:100%;border-radius:0;border:0}
body.gfs .gbar{position:absolute;top:calc(8px + env(safe-area-inset-top));left:8px;right:8px;z-index:2;padding-bottom:0}
body.gfs .gb{background:color-mix(in srgb,var(--card) 88%,transparent);backdrop-filter:blur(6px)}
body.gfs .gb.on{background:linear-gradient(135deg,var(--kacc),var(--kacc2))}
body.gfs .gb.fsonly{display:block}
body.gfs #galg{position:fixed;left:0;right:0;bottom:0;max-height:58vh;overflow:auto;z-index:31;margin:0;background:var(--card);border-top:2px solid var(--line);border-radius:22px 22px 0 0;padding:14px 12px calc(14px + env(safe-area-inset-bottom));transform:translateY(105%);transition:transform .42s cubic-bezier(.2,.9,.25,1);box-shadow:0 -10px 40px rgba(0,0,0,.3)}
body.gfs.alg #galg{transform:none}

#preview{display:none;margin:8px 2px 0;padding:8px 12px;border:1px dashed var(--line2);border-radius:12px;background:var(--inbg);font-size:20px;overflow-x:auto;color:var(--text);animation:up .25s both}
.echoTex{font-size:15px;color:var(--dim);overflow-x:auto;margin-bottom:2px}
.resTex{overflow-x:auto;padding:4px 0;color:var(--text);cursor:pointer}
.atex{margin:-2px 0 7px 37px;font-size:16px;overflow-x:auto;color:var(--text)}
.tex{display:inline-block;white-space:nowrap;font-family:"Cambria Math","STIX Two Math","Latin Modern Math","Noto Serif",Georgia,"Times New Roman",serif;line-height:1.4;vertical-align:middle;-webkit-user-select:text;user-select:text}
.tex i{font-style:italic}.tex .mr{font-style:normal}
.tex .mo{margin:0 .22em}.tex .mt{font-family:system-ui,sans-serif;font-size:.8em}
.tex .sp{display:inline-block;width:.17em}
.tex .mf{display:inline-flex;flex-direction:column;align-items:center;vertical-align:middle;margin:0 .14em;text-align:center}
.tex .mfn{padding:0 .2em .1em;border-bottom:1.4px solid currentColor}
.tex .mfd{padding:.1em .2em 0}
.tex .mf.nob .mfn{border-bottom:0}
.tex .msq{display:inline-flex;align-items:stretch;vertical-align:middle}
.tex .msi{align-self:flex-start;font-size:.6em;margin-right:-.3em}
.tex .msr{font-size:1.2em;line-height:1;align-self:flex-end;margin-right:-.05em}
.tex .msb{border-top:1.4px solid currentColor;padding:.08em .1em 0 .1em}
.tex sup,.tex sub{font-size:.7em;line-height:0}
.tex .mss{display:inline-flex;flex-direction:column;vertical-align:middle;font-size:.7em;line-height:1.15;margin-left:.04em}
.tex .mbig{display:inline-flex;flex-direction:column;align-items:center;vertical-align:middle;margin:0 .12em}
.tex .mbig .mop{font-size:1.7em;line-height:1}
.tex .mbig .mup,.tex .mbig .mdn{font-size:.68em;line-height:1.15}
.tex .mint{display:inline-flex;align-items:center;vertical-align:middle;margin-right:.1em}
.tex .mi{font-size:2.1em;line-height:1;font-weight:200;transform:scaleX(.8)}
.tex .mis{display:inline-flex;flex-direction:column;justify-content:space-between;font-size:.68em;margin-left:-.35em;min-height:2.6em;line-height:1.1}
.tex .mp{display:inline-flex;align-items:center;vertical-align:middle}
.tex .mp.tall>.dl{transform:scaleY(1.9);font-weight:200;margin:0 .06em}
.tex .mtb{border-collapse:collapse;margin:0 .15em;display:inline-table;vertical-align:middle}
.tex .mtb td{padding:.12em .5em;text-align:center}
.tex .mtb.l td{text-align:left}
.tex .mov{border-top:1.3px solid currentColor}
.tex .mac{display:inline-flex;flex-direction:column;align-items:center;line-height:1}.tex .mah{font-size:.7em;line-height:.6}
pre.help{font:12px/1.45 ui-monospace,Menlo,Consolas,monospace;white-space:pre-wrap;margin:0;background:var(--inbg);border:1px solid var(--line2);border-radius:12px;padding:12px;-webkit-user-select:text;user-select:text}
.back{position:fixed;inset:0;background:rgba(0,0,0,.45);opacity:0;pointer-events:none;transition:opacity .3s;z-index:20}
.back.on{opacity:1;pointer-events:auto}
.sheet{position:fixed;left:0;right:0;bottom:0;z-index:21;background:var(--card);border-top:2px solid var(--line);border-radius:24px 24px 0 0;padding:14px 16px calc(20px + env(safe-area-inset-bottom));transform:translateY(105%);transition:transform .42s cubic-bezier(.2,.9,.25,1);box-shadow:0 -10px 40px rgba(0,0,0,.25)}
.sheet.on{transform:none}
.grab{width:42px;height:4px;border-radius:2px;background:var(--line2);margin:0 auto 12px}
.sheet h3{margin:0 0 10px;font-size:15px;color:var(--line);letter-spacing:1.5px}
.srow{margin-bottom:12px}
.srow label{display:block;font-size:11px;font-weight:700;color:var(--dim);margin-bottom:5px;letter-spacing:.5px}
.seg{display:flex;gap:4px;background:var(--inbg);border:1px solid var(--line2);border-radius:12px;padding:3px;overflow-x:auto;scrollbar-width:none}
.seg button{flex:1 0 auto;border:0;background:transparent;color:var(--text);font-weight:700;font-size:12.5px;padding:9px 12px;border-radius:9px;touch-action:manipulation}
.seg button.on{background:linear-gradient(135deg,var(--kacc),var(--kacc2));color:var(--kaccfg)}
.ver{font-size:10px;color:var(--dim);text-align:center;margin-top:6px}
#splash{position:fixed;inset:0;z-index:50;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;transition:opacity .6s ease,visibility .6s}
#splash.hide{opacity:0;visibility:hidden}
#splash .lg{width:96px;height:96px;filter:drop-shadow(0 0 18px color-mix(in srgb,var(--line) 45%,transparent))}
#splash .ring{transform-origin:22px 22px;animation:spin 2.4s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
#splash b{font-size:26px;letter-spacing:6px;color:var(--line);font-weight:800}
#splash small{color:var(--dim);font-size:12px;letter-spacing:1px;animation:pulse 1.4s ease-in-out infinite}
@keyframes pulse{50%{opacity:.35}}

@media (min-width:900px){
 main{display:grid;grid-template-columns:minmax(440px,5fr) 6fr;gap:12px;align-items:start;padding:12px 14px 6px}
 #v-calc{grid-column:1;grid-row:1}
 .view.on:not(#v-calc){grid-column:2;grid-row:1}
 #cv{height:calc(100dvh - 380px);min-height:340px}
 .key{min-height:62px;font-size:22px}.key.s{font-size:13.5px}
 #inp{font-size:24px}#result{max-height:28vh}
 .brand b{font-size:21px}.tab{font-size:13px;padding:10px 16px}
 nav{margin-left:auto;margin-right:auto;width:min(720px,70%)}
}
</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute"><defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" style="stop-color:var(--g1)"/><stop offset="1" style="stop-color:var(--g2)"/></linearGradient></defs></svg>
<div id="splash" class="pattern">
 <svg class="lg" viewBox="0 0 48 48"><g class="ring"><circle cx="22" cy="22" r="15" fill="none" stroke="url(#lg)" stroke-width="4.5" stroke-dasharray="70 30"/></g><path d="M31 31l10 10" stroke="url(#lg)" stroke-width="4.5" stroke-linecap="round"/><path d="M16 15h12M16 15l7 7-7 7h12" fill="none" stroke="var(--text)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
 <b>QUANTUMATOR</b><small>Rechenkern wird gestartet …</small>
</div>
<div id="app">
<header class="pattern"><div class="hrow">
 <div class="brand">
  <svg width="38" height="38" viewBox="0 0 48 48"><circle cx="22" cy="22" r="15" fill="none" stroke="url(#lg)" stroke-width="4.5"/><path d="M31 31l10 10" stroke="url(#lg)" stroke-width="4.5" stroke-linecap="round"/><path d="M16 15h12M16 15l7 7-7 7h12" fill="none" stroke="var(--text)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
  <div><b>QUANTUMATOR</b><small>Super-Rechner · offline</small></div></div>
 <div class="tools">
  <button class="tool pill" id="tAngle"></button>
  <button class="tool" id="tTheme" aria-label="Design"></button>
  <button class="tool" id="tSet" aria-label="Einstellungen"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg></button>
 </div></div></header>
<main>
 <section class="view on" id="v-calc">
  <div class="frame pattern"><div class="inner">
   <div class="irow"><span class="prompt">›</span><input id="inp" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" inputmode="none" placeholder="Rechnung eingeben …">
   <button class="kb" id="kbBtn" aria-label="Systemtastatur">⌨</button></div>
   <div id="preview"></div>
   <div id="status"></div>
   <div id="result"></div>
   <div class="actions"><button class="btn" id="copyBtn">Kopieren</button><button class="btn" id="useBtn">↥ Übernehmen</button><button class="btn del" id="clrBtn">Löschen</button></div>
  </div></div>
  <div class="frame pattern"><div class="inner">
   <div class="tabs" id="ktabs"></div><div id="kpads"></div>
  </div></div>
 </section>
 <section class="view" id="v-hist"><div class="frame pattern"><div class="inner">
   <ul class="list" id="hlist"></ul>
   <div class="actions"><button class="btn del" id="hclr">Verlauf leeren</button></div></div></div></section>
 <section class="view" id="v-vars"><div class="frame pattern"><div class="inner">
   <ul class="list" id="vlist"></ul>
   <div class="actions"><button class="btn del" id="vclr">Alle löschen</button></div></div></div></section>
 <section class="view" id="v-graph"><div class="frame pattern"><div class="inner">
   <div class="gwrap" id="gwrap">
    <div class="gbar" id="gbar">
     <button class="gb" id="gbFit">⌂ Einpassen</button><button class="gb" id="gbEq">1:1</button><button class="gb" id="gbGrid">Gitter</button>
     <button class="gb" id="gbSp">◎ Punkte</button><button class="gb" id="gbTr">⌖ Spur</button><button class="gb" id="g3d">3D</button>
     <button class="gb" id="gbFs">⤢</button><button class="gb fsonly" id="gbList">☰ Liste</button>
    </div>
    <canvas id="cv"></canvas><div id="gtip"></div>
   </div>
   <div id="galg">
    <div id="arows"></div>
    <div class="actions"><button class="btn acc" id="aAdd">＋ Objekt</button><button class="btn" id="aTpl">Vorlagen ▾</button></div>
    <div class="ex" id="tpl" hidden></div>
    <div id="slid" style="margin-top:10px"></div>
    <div class="mk-wrap" id="mkeys"></div>
    <div class="empty" style="padding:8px;font-size:11.5px;line-height:1.5">Ziehen = verschieben · zwei Finger = zoomen (waagerecht/senkrecht = nur eine Achse)<br>Tippen = Koordinaten · Doppeltippen = einpassen · ◎ = Nullstellen, Extrema, Schnittpunkte</div>
   </div>
  </div></div></section>
 <section class="view" id="v-help"><div class="frame pattern"><div class="inner"><pre class="help" id="helptxt"></pre></div></div></section>
</main>
<nav id="nav"><div class="ind" id="ind"></div>
 <button data-v="calc" class="on"><svg viewBox="0 0 24 24"><rect x="5" y="3" width="14" height="18" rx="3"/><path d="M8 7h8M8 12h.01M12 12h.01M16 12h.01M8 16h.01M12 16h.01M16 16h.01"/></svg>Rechner</button>
 <button data-v="hist"><svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7M3 4v4h4M12 8v5l3 2"/></svg>Verlauf</button>
 <button data-v="vars"><svg viewBox="0 0 24 24"><path d="M5 5l14 14M19 5L5 19"/></svg>Variablen</button>
 <button data-v="graph"><svg viewBox="0 0 24 24"><path d="M3 20h18M3 20V4M6 16c3-9 5-9 8-2s4 4 5-6"/></svg>Graph</button>
 <button data-v="help"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01"/></svg>Hilfe</button>
</nav>
</div>
<div class="back" id="back"></div>
<div class="sheet" id="sheet"><div class="grab"></div><h3>EINSTELLUNGEN</h3><div id="srows"></div><div class="ver">Quantumator 1.2 · rechnet 100 % offline auf diesem Gerät</div></div>
<script>
const KEYPADS = __KEYPADS__;
const HELP = __HELP__;
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const st = Object.assign({deg:true,dec:true,digits:15,dark:false,haptic:true}, JSON.parse(localStorage.getItem('qm_set')||'{}'));
let hist = JSON.parse(localStorage.getItem('qm_hist')||'[]'), lastText = '', busy = false, vars = [];
const saveSet = () => localStorage.setItem('qm_set', JSON.stringify(st));
const inp = $('#inp');
const buzz = (n=6) => { if (st.haptic && navigator.vibrate) try { navigator.vibrate(n); } catch(e){} };
const SUN = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
const MOON = '<svg viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';

function applyTheme(){
  document.documentElement.dataset.theme = st.dark ? 'dark' : 'light';
  $('#themecolor').content = st.dark ? '#03050A' : '#ffffff';
  $('#tTheme').innerHTML = st.dark ? SUN : MOON;
  $('#tAngle').textContent = st.deg ? 'GRAD' : 'RAD';
  setStatus(); if (typeof refreshColors === 'function'){ refreshColors(); draw(); }
}
function setStatus(t){
  $('#status').textContent = t || ((st.deg?'Grad':'Bogenmaß') + ' · ' + (st.dec?'Dezimalkomma · Argumente mit ;':'Dezimalpunkt') + ' · ' + st.digits + ' Stellen');
}
$('#tTheme').onclick = () => { st.dark = !st.dark; saveSet(); applyTheme(); buzz(); };
$('#tAngle').onclick = () => { st.deg = !st.deg; saveSet(); applyTheme(); buzz(); };

/* Einstellungen */
const SET = [
 {k:'deg', t:'Winkeleinheit', o:[[true,'Grad °'],[false,'Bogenmaß rad']]},
 {k:'dec', t:'Dezimaltrenner', o:[[true,'Komma ,'],[false,'Punkt .']]},
 {k:'digits', t:'Nachkommastellen (Näherung)', o:[6,10,15,20,30,50,100].map(v => [v, String(v)])},
 {k:'dark', t:'Design', o:[[false,'☀ Tag (Gold)'],[true,'☾ Nacht (Blau)']]},
 {k:'haptic', t:'Vibration beim Tippen', o:[[true,'An'],[false,'Aus']]}];
function renderSheet(){
  const box = $('#srows'); box.innerHTML = '';
  SET.forEach(s => { const r = document.createElement('div'); r.className = 'srow';
    const l = document.createElement('label'); l.textContent = s.t; const g = document.createElement('div'); g.className = 'seg';
    s.o.forEach(([v, name]) => { const b = document.createElement('button'); b.textContent = name; if (st[s.k] === v) b.classList.add('on');
      b.onclick = () => { st[s.k] = v; saveSet(); applyTheme(); renderSheet(); buzz(); if (s.k === 'dec' && typeof scheduleParse === 'function') scheduleParse(); }; g.append(b); });
    r.append(l, g); box.append(r); });
}
const openSheet = on => { $('#sheet').classList.toggle('on', on); $('#back').classList.toggle('on', on); if (on) renderSheet(); };
$('#tSet').onclick = () => openSheet(true); $('#back').onclick = () => openSheet(false);

/* Navigation */
const navBtns = $$('#nav button');
let curView = 'calc', rightView = 'graph', lastWide = null;
const isWide = () => window.matchMedia('(min-width: 900px)').matches;
function go(v){
  curView = v; const wide = isWide(); lastWide = wide;
  if (wide && v !== 'calc') rightView = v;
  const i = navBtns.findIndex(b => b.dataset.v === v);
  navBtns.forEach((b, j) => b.classList.toggle('on', j === i));
  $('#ind').style.transform = 'translateX(' + (i*100) + '%)';
  document.body.classList.toggle('wide', wide);
  $$('.view').forEach(x => { const id = x.id.slice(2); x.classList.toggle('on', wide ? (id === 'calc' || id === rightView) : id === v); });
  if (v === 'graph' || (wide && rightView === 'graph')) graphShow();
  if (!wide) $('main').scrollTo({top:0});
}
window.addEventListener('resize', () => { if (lastWide !== null && isWide() !== lastWide) go(curView); });
navBtns.forEach(b => b.onclick = () => { go(b.dataset.v); buzz(); });

/* Tastatur */
const ktabs = $('#ktabs'), kpads = $('#kpads'), names = Object.keys(KEYPADS); let curTab = 0;
names.forEach((name, i) => {
  const t = document.createElement('button'); t.className = 'tab' + (i?'':' on'); t.textContent = name; t.onclick = () => { selectTab(i); buzz(); };
  const p = document.createElement('div'); p.className = 'pad' + (i?'':' on');
  KEYPADS[name].forEach(row => row.forEach(([label, ins, kind]) => {
    const k = document.createElement('button'); k.className = 'key k-' + kind + (label.length > 3 ? ' s' : ''); k.textContent = label;
    if (ins === '<DEL>') holdRepeat(k, () => press(ins)); else k.onclick = () => { press(ins); buzz(); };
    p.appendChild(k);
  }));
  ktabs.appendChild(t); kpads.appendChild(p);
});
function selectTab(i){
  const dir = i >= curTab ? 1 : -1; curTab = i;
  $$('#ktabs .tab').forEach((x, j) => x.classList.toggle('on', j === i));
  $$('#kpads .pad').forEach((x, j) => { x.style.setProperty('--dir', dir); x.classList.toggle('on', j === i); });
  $$('#ktabs .tab')[i].scrollIntoView({inline:'center', block:'nearest', behavior:'smooth'});
}
let sx = 0, sy = 0;
kpads.addEventListener('touchstart', e => { sx = e.touches[0].clientX; sy = e.touches[0].clientY; }, {passive:true});
kpads.addEventListener('touchend', e => { const dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy;
  if (Math.abs(dx) > 60 && Math.abs(dx) > 2*Math.abs(dy)) { const n = curTab + (dx < 0 ? 1 : -1); if (n >= 0 && n < names.length) { selectTab(n); buzz(); } } }, {passive:true});
function holdRepeat(k, fn){
  let t1 = null, t2 = null;
  const stop = () => { clearTimeout(t1); clearInterval(t2); k.classList.remove('pr'); };
  k.addEventListener('pointerdown', e => { e.preventDefault(); k.classList.add('pr'); fn(); buzz(); t1 = setTimeout(() => { t2 = setInterval(() => { fn(); buzz(3); }, 55); }, 380); });
  ['pointerup','pointerleave','pointercancel'].forEach(ev => k.addEventListener(ev, stop));
}
function press(s){
  if (s === '<C>') return clearInp();
  if (s === '<EQ>') return calc();
  if (s === '<DEC>') s = st.dec ? ',' : '.';
  const a = inp.selectionStart ?? inp.value.length, b = inp.selectionEnd ?? a;
  if (s === '<LEFT>'){ const c = Math.max(0, a - (a === b ? 1 : 0)); inp.setSelectionRange(c, c); return; }
  if (s === '<RIGHT>'){ const c = Math.min(inp.value.length, b + (a === b ? 1 : 0)); inp.setSelectionRange(c, c); return; }
  if (s === '<NEXT>'){ nextPlaceholder(); return; }
  if (s === '<DEL>'){ if (a !== b) inp.setRangeText('', a, b, 'end'); else if (a > 0) inp.setRangeText('', a-1, a, 'end'); schedulePreview(); return; }
  const pos = s.indexOf('¦'), text = s.replace('¦',''), ph = text.indexOf('□');
  inp.setRangeText(text, a, b, 'end');
  if (pos >= 0){ const c = a + pos; inp.setSelectionRange(c, c); }
  else if (ph >= 0) inp.setSelectionRange(a + ph, a + ph + 1);
  schedulePreview();
}
function nextPlaceholder(){
  const v = inp.value; let i = v.indexOf('□', inp.selectionEnd ?? 0); if (i < 0) i = v.indexOf('□');
  if (i >= 0) inp.setSelectionRange(i, i + 1); else inp.setSelectionRange(v.length, v.length);
}
let pvT = null, pvSeq = 0;
function schedulePreview(){ clearTimeout(pvT); pvT = setTimeout(doPreview, 220); }
async function doPreview(){
  const t = inp.value.trim(), box = $('#preview');
  if (!t){ box.style.display = 'none'; box.innerHTML = ''; return; }
  const my = ++pvSeq;
  try { const r = await post('/api/preview', {text:t, dec:st.dec}); if (my !== pvSeq) return;
    if (r.tex){ box.innerHTML = texToHtml(r.tex, {dec:st.dec}); box.style.display = 'block'; } else box.style.display = 'none'; } catch(e){}
}
inp.addEventListener('input', schedulePreview);
function clearInp(){ inp.value = ''; schedulePreview(); }
$('#clrBtn').onclick = () => { clearInp(); buzz(); };
$('#kbBtn').onclick = () => { const on = inp.inputMode === 'none'; inp.inputMode = on ? 'text' : 'none'; inp.blur(); inp.focus(); };
inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); calc(); } });
async function copyText(t){
  try { await navigator.clipboard.writeText(t); }
  catch(e){ const x = document.createElement('textarea'); x.value = t; document.body.appendChild(x); x.select(); document.execCommand('copy'); x.remove(); }
}
$('#copyBtn').onclick = async () => { if (!lastText) return; await copyText(lastText); setStatus('✓ Ergebnis kopiert'); buzz(12); setTimeout(() => setStatus(), 1500); };
$('#useBtn').onclick = () => { if (!lastText) return; press(lastText.split('\n')[0].replace(/\s+/g,' ')); buzz(); };

/* Rechnen */
async function post(url, body){
  const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  return r.json();
}
function el(tag, text, cls){ const e = document.createElement(tag); if (cls) e.className = cls; e.textContent = text; return e; }
const EXAMPLES = ['x^2-4=0','∫₀³ x² dx','∑_{k=1}^{10} k²','lim_{x→0} sin(x)/x','d/dx x³','(3+4i)²','√2/2','x+y=5; x-y=1','det(matrix([[1;2];[3;4]]))','primfaktoren(360)'];
function showWelcome(){
  const box = $('#result'); box.innerHTML = '';
  box.append(el('div','Bereit.','main'));
  box.lastChild.style.fontSize = '22px';
  box.append(el('div','Beispiele zum Antippen','ex-t'));
  const w = document.createElement('div'); w.className = 'ex';
  EXAMPLES.forEach(x => { const c = el('button', x, 'xchip'); c.onclick = () => { inp.value = x; buzz(); calc(); }; w.append(c); });
  box.append(w);
}
function mathEl(tex, cls){ const d = document.createElement('div'); d.className = cls; try { d.innerHTML = texToHtml(tex, {dec:st.dec}); } catch(e){ return null; } return d; }
function showResult(r){
  const box = $('#result'); box.innerHTML = '';
  if (r.kind === 'err'){ box.append(el('div','Fehler','errh'), el('pre', r.msg, 'err')); lastText = ''; return; }
  const echo = r.itex ? mathEl(r.itex, 'echoTex') : null;
  box.append(echo || el('div', r.input, 'echo'));
  const m = el('pre', r.main, 'main'); const len = Math.max(...r.main.split('\n').map(x => x.length));
  m.style.fontSize = len > 34 ? '14px' : len > 22 ? '17px' : len > 12 ? '21px' : '26px';
  const f = r.tex ? mathEl(r.tex, 'resTex') : null;
  if (f){
    const L = r.tex.length; f.style.fontSize = L > 90 ? '16px' : L > 50 ? '20px' : L > 25 ? '24px' : '28px';
    m.style.display = 'none';
    f.onclick = () => { f.style.display = 'none'; m.style.display = 'block'; };
    m.onclick = () => { m.style.display = 'none'; f.style.display = 'block'; };
    box.append(f, m);
  } else box.append(m);
  (r.extra||[]).forEach(([l,t]) => box.append(el('div', l, 'lab'), el('pre', t, 'ext')));
  lastText = r.main; box.scrollTo({top:0});
}
async function calc(){
  const t = inp.value.trim(); if (!t || busy) return;
  busy = true; setStatus('⏳ Berechne …');
  try {
    const res = await post('/api/eval', {text:t, deg:st.deg, dec:st.dec, digits:st.digits});
    showResult(res); buzz(res.kind === 'err' ? [20,40,20] : 14);
    if (res.kind !== 'err'){
      hist.push({inp:res.input, out:(res.main||'').split('\n')[0]}); hist = hist.slice(-200);
      localStorage.setItem('qm_hist', JSON.stringify(hist)); renderHist();
    }
    if (res.vars) { vars = res.vars; renderVars(); }
  } catch(e){ showResult({kind:'err', msg:'Keine Verbindung zum Rechenkern.\nBitte die App neu starten.'}); }
  busy = false; setStatus();
}
function renderHist(){
  const ul = $('#hlist'); ul.innerHTML = '';
  if (!hist.length) { ul.append(el('div','Noch keine Berechnungen.','empty')); return; }
  hist.slice().reverse().forEach(h => { const li = document.createElement('li');
    const s = document.createElement('span'); s.append(h.inp, document.createElement('br')); s.append(el('small','→ ' + h.out));
    li.append(s); li.onclick = () => { inp.value = h.inp; go('calc'); buzz(); }; ul.append(li); });
}
$('#hclr').onclick = () => { hist = []; localStorage.setItem('qm_hist','[]'); renderHist(); buzz(); };
function renderVars(){
  const ul = $('#vlist'); ul.innerHTML = '';
  if (!vars.length) { ul.append(el('div','Keine Variablen oder Funktionen.\nBeispiel:  a=5   oder   f(x)=x^2+1','empty')); ul.firstChild.style.whiteSpace = 'pre-line'; return; }
  vars.forEach(v => { const li = document.createElement('li'); const s = el('span', v.kind === 'v' ? v.name + ' = ' + v.text : v.text);
    li.onclick = () => { press(v.name); go('calc'); buzz(); };
    const x = el('button','✕','x'); x.onclick = async ev => { ev.stopPropagation(); const r = await post('/api/eval',{text:'vergiss '+v.name,deg:st.deg,dec:st.dec,digits:st.digits}); vars = r.vars||[]; renderVars(); buzz(); };
    li.append(s, x); ul.append(li); });
}
$('#vclr').onclick = async () => { const r = await post('/api/eval',{text:'vergiss alle',deg:st.deg,dec:st.dec,digits:st.digits}); vars = r.vars||[]; renderVars(); buzz(); };

/*GE-BEGIN*/
function sec(x){return 1/Math.cos(x);} function csc(x){return 1/Math.sin(x);} function cot(x){return 1/Math.tan(x);}
function sinc(x){return x===0?1:Math.sin(x)/x;}
function rroot(b,q){return b<0?-Math.pow(-b,1/q):Math.pow(b,1/q);}
function gamma(x){
  if(x<0.5) return Math.PI/(Math.sin(Math.PI*x)*gamma(1-x));
  x-=1; const c=[0.99999999999980993,676.5203681218851,-1259.1392167224028,771.32342877765313,-176.61502916214059,12.507343278686905,-0.13857109526572012,9.9843695780195716e-6,1.5056327351493116e-7];
  let a=c[0]; const t=x+7.5; for(let i=1;i<9;i++) a+=c[i]/(x+i);
  return Math.sqrt(2*Math.PI)*Math.pow(t,x+0.5)*Math.exp(-t)*a;
}
function factorial(n){return Math.round(n)===n&&n>=0&&n<=20?[1,1,2,6,24,120,720,5040,40320,362880,3628800,39916800,479001600,6227020800,87178291200,1307674368000,20922789888000,355687428096000,6402373705728000,121645100408832000,2432902008176640000][n]:gamma(n+1);}
function erf(x){const z=Math.abs(x),t=1/(1+0.5*z);const r=t*Math.exp(-z*z-1.26551223+t*(1.00002368+t*(0.37409196+t*(0.09678418+t*(-0.18628806+t*(0.27886807+t*(-1.13520398+t*(1.48851587+t*(-0.82215223+t*0.17087277)))))))));return x>=0?1-r:r-1;}
function erfc(x){return 1-erf(x);}
function Heaviside(x,h){return x<0?0:x>0?1:(h===undefined?0.5:h);}
function binomial(n,k){return factorial(n)/(factorial(k)*factorial(n-k));}
function LambertW(x){if(x<-1/Math.E)return NaN;let w=x<1?0:Math.log(x);for(let i=0;i<40;i++){const e=Math.exp(w),f=w*e-x;w-=f/(e*(w+1)-(w+2)*f/(2*w+2));}return w;}
function loggamma(x){return Math.log(Math.abs(gamma(x)));}
function compileJS(js){return new Function('x','y','t','P','return ('+js+');');}
function evalAt(f,x,y,t,P){try{const v=f(x,y,t,P);return typeof v==='number'?v:NaN;}catch(e){return NaN;}}
function niceStep(span,target){const raw=Math.max(span,1e-300)/target,mag=Math.pow(10,Math.floor(Math.log10(raw)));for(const m of [1,2,5,10])if(raw<=m*mag)return m*mag;return 10*mag;}
/* Marching Squares: liefert Strecken [x1,y1,x2,y2,…] in Pixeln */
function marchSegs(F,P,V,W,H,cell){
  const nx=Math.ceil(W/cell)+1,ny=Math.ceil(H/cell)+1,sx=(V.x1-V.x0)/W,sy=(V.y1-V.y0)/H,vals=new Float64Array(nx*ny);
  for(let j=0;j<ny;j++){const Y=V.y1-j*cell*sy;for(let i=0;i<nx;i++)vals[j*nx+i]=evalAt(F,V.x0+i*cell*sx,Y,0,P);}
  const out=[],it=(a,b)=>a/(a-b);
  for(let j=0;j<ny-1;j++)for(let i=0;i<nx-1;i++){
    const a=vals[j*nx+i],b=vals[j*nx+i+1],c=vals[(j+1)*nx+i+1],d=vals[(j+1)*nx+i];
    if(!(isFinite(a)&&isFinite(b)&&isFinite(c)&&isFinite(d)))continue;
    const code=(a>0?8:0)|(b>0?4:0)|(c>0?2:0)|(d>0?1:0);
    if(code===0||code===15)continue;
    if(Math.abs(a)>1e12||Math.abs(b)>1e12||Math.abs(c)>1e12||Math.abs(d)>1e12)continue;
    const top=[(i+it(a,b))*cell,j*cell],right=[(i+1)*cell,(j+it(b,c))*cell],bottom=[(i+it(d,c))*cell,(j+1)*cell],left=[i*cell,(j+it(a,d))*cell];
    const seg=(p,q)=>out.push(p[0],p[1],q[0],q[1]);
    switch(code){
      case 1:case 14:seg(left,bottom);break;
      case 2:case 13:seg(bottom,right);break;
      case 3:case 12:seg(left,right);break;
      case 4:case 11:seg(top,right);break;
      case 6:case 9:seg(top,bottom);break;
      case 7:case 8:seg(left,top);break;
      case 5:{const m=(a+b+c+d)/4;if(m>0){seg(left,top);seg(bottom,right);}else{seg(top,right);seg(left,bottom);}break;}
      case 10:{const m=(a+b+c+d)/4;if(m>0){seg(top,right);seg(left,bottom);}else{seg(left,top);seg(bottom,right);}break;}
    }
  }
  return out;
}
/* Spezialpunkte: Nullstellen N, Hoch H, Tief T, y-Achsenabschnitt Y, Schnittpunkte S */
function specialPoints(fl,P,x0,x1){
  const N=700,out=[],xs=new Float64Array(N+1),dx=(x1-x0)/N,ys=fl.map(()=>new Float64Array(N+1));
  for(let i=0;i<=N;i++)xs[i]=x0+i*dx;
  fl.forEach((o,k)=>{for(let i=0;i<=N;i++)ys[k][i]=evalAt(o.f,xs[i],0,0,P);});
  const ok=v=>isFinite(v)&&Math.abs(v)<1e7;
  const bis=(g,a,b)=>{let fa=g(a),fb=g(b);if(!(isFinite(fa)&&isFinite(fb)))return NaN;for(let n=0;n<60;n++){const m=(a+b)/2,fm=g(m);if(!isFinite(fm))return NaN;if((fa<0)===(fm<0)){a=m;fa=fm;}else{b=m;fb=fm;}}return (a+b)/2;};
  fl.forEach((o,k)=>{
    const f=x=>evalAt(o.f,x,0,0,P),Y=ys[k];let cnt=0;
    for(let i=0;i<N&&cnt<24;i++){const a=Y[i],b=Y[i+1];
      if(ok(a)&&ok(b)){
        if(a===0){out.push({x:xs[i],y:0,t:'N',c:o.c});cnt++;}
        else if(a*b<0){const r=bis(f,xs[i],xs[i+1]);if(isFinite(r)&&Math.abs(f(r))<1e-6*Math.max(1,Math.abs(a),Math.abs(b))){out.push({x:r,y:0,t:'N',c:o.c});cnt++;}}
      }
    }
    for(let i=1;i<N&&cnt<48;i++){const a=Y[i-1],b=Y[i],c=Y[i+1];
      if(ok(a)&&ok(b)&&ok(c)){const d1=b-a,d2=c-b;
        if((d1>0&&d2<0)||(d1<0&&d2>0)){const mx=d1>0;let lo=xs[i-1],hi=xs[i+1];
          for(let n=0;n<60;n++){const m1=lo+(hi-lo)/3,m2=hi-(hi-lo)/3,f1=f(m1),f2=f(m2);if(!isFinite(f1)||!isFinite(f2))break;if((f1<f2)===mx)lo=m1;else hi=m2;}
          const xm=(lo+hi)/2,ym=f(xm);
          if(isFinite(ym)&&Math.abs(ym)<1e7){if(Math.abs(ym)<1e-9)out.push({x:xm,y:0,t:'N',c:o.c});else out.push({x:xm,y:ym,t:mx?'H':'T',c:o.c});cnt++;}
        }}
    }
    if(x0<=0&&0<=x1){const y0=f(0);if(isFinite(y0))out.push({x:0,y:y0,t:'Y',c:o.c});}
  });
  for(let p=0;p<fl.length;p++)for(let q=p+1;q<fl.length;q++){
    const g=x=>evalAt(fl[p].f,x,0,0,P)-evalAt(fl[q].f,x,0,0,P);let cnt=0;
    for(let i=0;i<N&&cnt<20;i++){const a=ys[p][i]-ys[q][i],b=ys[p][i+1]-ys[q][i+1];
      if(ok(a)&&ok(b)){
        if(a===0){const yy=ys[p][i];if(ok(yy)){out.push({x:xs[i],y:yy,t:'S',c:'#8E4EC6'});cnt++;}}
        else if(a*b<0){const r=bis(g,xs[i],xs[i+1]);if(isFinite(r)&&Math.abs(g(r))<1e-6*Math.max(1,Math.abs(a),Math.abs(b))){out.push({x:r,y:evalAt(fl[p].f,r,0,0,P),t:'S',c:'#8E4EC6'});cnt++;}}
      }}
  }
  const tol=Math.abs(x1-x0)*1e-7,res=[];
  out.forEach(q=>{if(!res.some(r=>r.t===q.t&&Math.abs(r.x-q.x)<tol&&Math.abs(r.y-q.y)<1e-6+Math.abs(q.y)*1e-6))res.push(q);});
  return res;
}
function simpson(f,P,a,b,n){if(!isFinite(a)||!isFinite(b)||a===b)return 0;n=n||400;const h=(b-a)/n;let s=evalAt(f,a,0,0,P)+evalAt(f,b,0,0,P);for(let i=1;i<n;i++)s+=evalAt(f,a+i*h,0,0,P)*(i%2?4:2);return s*h/3;}
/*GE-END*/
/*TEX-BEGIN*/
const TEX_GREEK={alpha:'α',beta:'β',gamma:'γ',delta:'δ',epsilon:'ε',varepsilon:'ε',zeta:'ζ',eta:'η',theta:'θ',vartheta:'ϑ',iota:'ι',kappa:'κ',lambda:'λ',mu:'μ',nu:'ν',xi:'ξ',pi:'π',rho:'ρ',sigma:'σ',tau:'τ',upsilon:'υ',phi:'φ',varphi:'φ',chi:'χ',psi:'ψ',omega:'ω',Gamma:'Γ',Delta:'Δ',Theta:'Θ',Lambda:'Λ',Xi:'Ξ',Pi:'Π',Sigma:'Σ',Phi:'Φ',Psi:'Ψ',Omega:'Ω'};
const TEX_OP={cdot:'·',times:'×',pm:'±',mp:'∓',div:'÷',to:'→',rightarrow:'→',leftarrow:'←',leftrightarrow:'↔',Rightarrow:'⇒',Leftarrow:'⇐',Leftrightarrow:'⇔',implies:'⇒',le:'≤',leq:'≤',ge:'≥',geq:'≥',ne:'≠',neq:'≠',approx:'≈',sim:'∼',equiv:'≡',propto:'∝',in:'∈',notin:'∉',subset:'⊂',subseteq:'⊆',cup:'∪',cap:'∩',land:'∧',lor:'∨',mid:'∣',circ:'∘',star:'⋆',bullet:'•',wedge:'∧',vee:'∨',ll:'≪',gg:'≫',mapsto:'↦'};
const TEX_ATOM={infty:'∞',partial:'∂',nabla:'∇',ldots:'…',cdots:'⋯',dots:'…',vdots:'⋮',degree:'°',prime:'′',emptyset:'∅',varnothing:'∅',forall:'∀',exists:'∃',neg:'¬',angle:'∠',triangle:'△',lbrace:'{',rbrace:'}',langle:'⟨',rangle:'⟩',lfloor:'⌊',rfloor:'⌋',lceil:'⌈',rceil:'⌉',hbar:'ℏ',ell:'ℓ',Re:'ℜ',Im:'ℑ',aleph:'ℵ',top:'⊤',bot:'⊥'};
const TEX_FUNCS=new Set(['sin','cos','tan','cot','sec','csc','arcsin','arccos','arctan','sinh','cosh','tanh','coth','ln','log','exp','max','min','det','gcd','lcm','arg','sup','inf','deg','dim','ker','mod','lg','sgn','Pr']);
const TEX_BIG={sum:'∑',prod:'∏',bigcup:'⋃',bigcap:'⋂',coprod:'∐'};
const TEX_INT={int:'∫',iint:'∬',iiint:'∭',oint:'∮'};
const TEX_BB={R:'ℝ',N:'ℕ',Z:'ℤ',Q:'ℚ',C:'ℂ',P:'ℙ'};
function texToHtml(src,opt){
  opt=opt||{};
  const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const toks=[];
  for(let k=0;k<src.length;){
    const c=src[k];
    if(c==='\\'){
      const n=src[k+1];
      if(n==='\\'){toks.push({t:'nl'});k+=2;continue;}
      const m=/^\\([A-Za-z]+)/.exec(src.slice(k));
      if(m){
        if((m[1]==='text'||m[1]==='mbox'||m[1]==='textbf')&&src[k+m[0].length]==='{'){
          let d=0,j=k+m[0].length;const st=j+1;
          for(;j<src.length;j++){if(src[j]==='{')d++;else if(src[j]==='}'){d--;if(d===0)break;}}
          toks.push({t:'text',v:src.slice(st,j)});k=j+1;continue;
        }
        toks.push({t:'cmd',v:m[1]});k+=m[0].length;continue;
      }
      toks.push({t:'cmd',v:n===undefined?'':n});k+=2;continue;
    }
    if(c==='{'||c==='}'||c==='^'||c==='_'||c==='&'){toks.push({t:c});k++;continue;}
    if(c===' '||c==='\n'||c==='\t'){k++;continue;}
    const m=/^\d+(?:[.,]\d+)?/.exec(src.slice(k));
    if(m){toks.push({t:'num',v:m[0]});k+=m[0].length;continue;}
    toks.push({t:'ch',v:c});k++;
  }
  let p=0,up=0;
  const peek=()=>toks[p];
  const isStop=st=>{const t=toks[p];if(!t)return true;
    if(t.t==='}'&&st.has('}'))return true;
    if((t.t==='&'||t.t==='nl')&&st.has('cell'))return true;
    if(t.t==='cmd'&&t.v==='right'&&st.has('right'))return true;
    if(t.t==='cmd'&&t.v==='end'&&st.has('end'))return true;
    return false;};
  const S_CLOSE=new Set(['}']);
  function seq(st){let h='';while(!isStop(st)){const b=p;h+=item();if(p===b)p++;}return h;}
  function group(){const t=peek();if(!t)return '';if(t.t==='{'){p++;const h=seq(S_CLOSE);if(peek()&&peek().t==='}')p++;return h;}return atom().h;}
  function chHtml(c){
    if(/[A-Za-z]/.test(c))return up>0?'<span class="mr">'+c+'</span>':'<i>'+c+'</i>';
    if(c==='+')return '<span class="mo">+</span>';
    if(c==='-')return '<span class="mo">−</span>';
    if(c==='='||c==='<'||c===">")return '<span class="mo">'+esc(c)+'</span>';
    if(c==='*')return '∗';
    if(c===',')return ',<span class="sp"></span>';
    if(c==="'")return '′';
    return esc(c);
  }
  function delim(t){if(!t)return '';if(t.t==='ch')return t.v==='.'?'':t.v;if(t.t==='cmd'){if(t.v==='{'||t.v==='lbrace')return '{';if(t.v==='}'||t.v==='rbrace')return '}';if(t.v==='|')return '‖';if(TEX_ATOM[t.v])return TEX_ATOM[t.v];return '';}if(t.t==='{')return '{';if(t.t==='}')return '}';return '';}
  function skipBraced(){if(peek()&&peek().t==='{'){while(peek()&&peek().t!=='}')p++;p++;}}
  function envName(){let n='';if(peek()&&peek().t==='{'){p++;while(peek()&&peek().t!=='}'){const t=toks[p++];n+=(t.v||'');}p++;}return n;}
  function atom(){
    const t=toks[p++];if(!t)return {h:'',k:'n'};
    switch(t.t){
      case 'num':return {h:'<span class="mn">'+esc(opt.dec?t.v.replace('.',','):t.v)+'</span>',k:'n'};
      case 'text':return {h:'<span class="mt">'+esc(t.v)+'</span>',k:'n'};
      case '{':{const h=seq(S_CLOSE);if(peek()&&peek().t==='}')p++;return {h,k:'n'};}
      case 'ch':return {h:chHtml(t.v),k:'n'};
      case 'cmd':return cmd(t.v);
      case '&':case 'nl':return {h:'',k:'n'};
      default:return {h:esc(t.t),k:'n'};
    }
  }
  function cmd(v){
    if(TEX_GREEK[v])return {h:(v[0]===v[0].toUpperCase()?'<span class="mr">'+TEX_GREEK[v]+'</span>':'<i>'+TEX_GREEK[v]+'</i>'),k:'n'};
    if(TEX_OP[v])return {h:'<span class="mo">'+TEX_OP[v]+'</span>',k:'n'};
    if(TEX_ATOM[v])return {h:TEX_ATOM[v],k:'n'};
    if(TEX_BIG[v]){while(peek()&&peek().t==='cmd'&&(peek().v==='limits'||peek().v==='nolimits'))p++;return {h:TEX_BIG[v],k:'big'};}
    if(TEX_INT[v]){while(peek()&&peek().t==='cmd'&&(peek().v==='limits'||peek().v==='nolimits'))p++;return {h:TEX_INT[v],k:'int'};}
    if(v==='lim'){while(peek()&&peek().t==='cmd'&&(peek().v==='limits'||peek().v==='nolimits'))p++;return {h:'<span class="mr">lim</span>',k:'big'};}
    if(TEX_FUNCS.has(v))return {h:'<span class="mr">'+v+'</span><span class="sp"></span>',k:'n'};
    switch(v){
      case 'frac':case 'dfrac':case 'tfrac':{const a=group(),b=group();return {h:'<span class="mf"><span class="mfn">'+a+'</span><span class="mfd">'+b+'</span></span>',k:'n'};}
      case 'binom':case 'dbinom':{const a=group(),b=group();return {h:'<span class="mp"><span class="dl">(</span><span class="mf nob"><span class="mfn">'+a+'</span><span class="mfd">'+b+'</span></span><span class="dl">)</span></span>',k:'n'};}
      case 'sqrt':{let idx='';if(peek()&&peek().t==='ch'&&peek().v==='['){p++;while(peek()&&!(peek().t==='ch'&&peek().v===']'))idx+=item();p++;}
        const b=group();return {h:'<span class="msq">'+(idx?'<sup class="msi">'+idx+'</sup>':'')+'<span class="msr">√</span><span class="msb">'+b+'</span></span>',k:'n'};}
      case 'left':{const o=delim(toks[p++]);const inner=seq(new Set(['right']));let c='';
        if(peek()&&peek().t==='cmd'&&peek().v==='right'){p++;c=delim(toks[p++]);}
        const tall=/class="(mf|mtb|mbig|mint|msq)/.test(inner);
        return {h:'<span class="mp'+(tall?' tall':'')+'"><span class="dl">'+esc(o)+'</span><span class="mpc">'+inner+'</span><span class="dl">'+esc(c)+'</span></span>',k:'n'};}
      case 'right':return {h:'',k:'n'};
      case 'begin':{
        const env=envName();if(env==='array')skipBraced();
        const rows=[[]];
        for(;;){
          const cell=seq(new Set(['cell','end']));rows[rows.length-1].push(cell);
          const t=peek();if(!t)break;
          if(t.t==='&'){p++;continue;}
          if(t.t==='nl'){p++;rows.push([]);continue;}
          if(t.t==='cmd'&&t.v==='end'){p++;skipBraced();break;}
          p++;
        }
        const left=/^(array|aligned|cases)$/.test(env)||/^(align)/.test(env);
        const body='<table class="mtb'+(left?' l':'')+'">'+rows.map(r=>'<tr>'+r.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')+'</table>';
        const D={pmatrix:['(',')'],bmatrix:['[',']'],Bmatrix:['{','}'],vmatrix:['|','|'],Vmatrix:['‖','‖'],cases:['{','']};
        const d=D[env];
        if(!d)return {h:body,k:'n'};
        return {h:'<span class="mp tall"><span class="dl">'+esc(d[0])+'</span>'+body+'<span class="dl">'+esc(d[1])+'</span></span>',k:'n'};}
      case 'operatorname':case 'mathrm':case 'mathsf':case 'mathit':case 'textrm':{up++;const h=group();up--;return {h:'<span class="mr">'+h+'</span>',k:'n'};}
      case 'mathbf':case 'boldsymbol':case 'bm':{const h=group();return {h:'<b>'+h+'</b>',k:'n'};}
      case 'mathbb':{const t=peek();let h='';if(t&&t.t==='{'){p++;while(peek()&&peek().t!=='}'){const q=toks[p++];h+=TEX_BB[q.v]||q.v||'';}p++;}else{const q=toks[p++];h=q?(TEX_BB[q.v]||q.v):'';}return {h:esc(h),k:'n'};}
      case 'mathcal':case 'mathscr':case 'mathfrak':{const h=group();return {h:'<i>'+h+'</i>',k:'n'};}
      case 'overline':case 'bar':{const h=group();return {h:'<span class="mov">'+h+'</span>',k:'n'};}
      case 'underline':{const h=group();return {h:'<u>'+h+'</u>',k:'n'};}
      case 'hat':case 'widehat':{const h=group();return {h:'<span class="mac"><span class="mah">^</span>'+h+'</span>',k:'n'};}
      case 'vec':{const h=group();return {h:'<span class="mac"><span class="mah">→</span>'+h+'</span>',k:'n'};}
      case 'tilde':case 'widetilde':{const h=group();return {h:'<span class="mac"><span class="mah">~</span>'+h+'</span>',k:'n'};}
      case 'dot':{const h=group();return {h:'<span class="mac"><span class="mah">˙</span>'+h+'</span>',k:'n'};}
      case 'displaystyle':case 'textstyle':case 'scriptstyle':case 'limits':case 'nolimits':case '!':case 'allowbreak':return {h:'',k:'n'};
      case 'big':case 'Big':case 'bigg':case 'Bigg':case 'bigl':case 'bigr':case 'Bigl':case 'Bigr':case 'biggl':case 'biggr':{return {h:esc(delim(toks[p++])),k:'n'};}
      case ',':case ';':case ':':case ' ':case 'thinspace':case 'medspace':return {h:'<span class="sp"></span>',k:'n'};
      case 'quad':return {h:'<span class="sp" style="width:1em"></span>',k:'n'};
      case 'qquad':return {h:'<span class="sp" style="width:2em"></span>',k:'n'};
      case '{':return {h:'{',k:'n'};case '}':return {h:'}',k:'n'};
      case '|':return {h:'‖',k:'n'};
      case '%':case '#':case '&':case '_':case '$':return {h:v,k:'n'};
      default:return {h:'<span class="mr">\\'+esc(v)+'</span>',k:'n'};
    }
  }
  function scriptArg(){const t=peek();if(!t)return '';if(t.t==='{'){p++;const h=seq(S_CLOSE);if(peek()&&peek().t==='}')p++;return h;}return atom().h;}
  function item(){
    const a=atom();let sub=null,sup=null;
    while(peek()&&(peek().t==='^'||peek().t==='_')){const k=toks[p++].t;const arg=scriptArg();if(k==='^')sup=arg;else sub=arg;}
    if(a.k==='int'){return '<span class="mint"><span class="mi">'+a.h+'</span>'+((sub!==null||sup!==null)?'<span class="mis"><span>'+(sup||'')+'</span><span>'+(sub||'')+'</span></span>':'')+'</span>';}
    if(a.k==='big'){if(sub===null&&sup===null)return '<span class="mbig"><span class="mop">'+a.h+'</span></span>';return '<span class="mbig"><span class="mup">'+(sup||'')+'</span><span class="mop">'+a.h+'</span><span class="mdn">'+(sub||'')+'</span></span>';}
    if(sub!==null&&sup!==null)return a.h+'<span class="mss"><span>'+sup+'</span><span>'+sub+'</span></span>';
    if(sup!==null)return a.h+'<sup>'+sup+'</sup>';
    if(sub!==null)return a.h+'<sub>'+sub+'</sub>';
    return a.h;
  }
  return '<span class="tex">'+seq(new Set())+'</span>';
}
/*TEX-END*/


/* ===== Graph-Oberfläche ===== */
const GST = {grid:0, eq:false, sp:false, tr:false, d3:false};
let items = [], sl = {}, P = {}, V = {x0:-10,x1:10,y0:-6,y1:6}, W = 300, H = 300;
let selMark = null, specials = [], lastIn = null, parsedOnce = false, animOn = false, drawQ = false;
const view3 = {yaw:-0.7, pitch:0.55, zoom:1, R:5}, slUI = {}, COL = {p:[]};
const cv = $('#cv'), ctx = cv.getContext('2d'), tip = $('#gtip'), offc = document.createElement('canvas');
const GRIDS = ['Gitter','Fein','Polar','Aus'];
const TYPEC = {N:'#2E9E5B', H:'#E5484D', T:'#3E63DD', Y:'#F5A623', S:'#8E4EC6'};
const TYPEN = {N:'Nullstelle', H:'Hochpunkt', T:'Tiefpunkt', Y:'y-Achsenabschnitt', S:'Schnittpunkt'};
function refreshColors(){
  const g = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  ['line','line2','dim','text','pat','inbg','bg','kacc','kacc2','g1','g2'].forEach(k => COL[k] = g('--' + k));
  COL.p = [0,1,2,3,4,5,6,7].map(i => g('--p' + i));
}
const colorOf = i => COL.p[i % 8] || '#888888';
function hexRGB(h){ h = (h || '#888888').replace('#',''); if (h.length === 3) h = h.split('').map(c => c+c).join(''); return [parseInt(h.slice(0,2),16)||0, parseInt(h.slice(2,4),16)||0, parseInt(h.slice(4,6),16)||0]; }
const X = x => (x - V.x0) / (V.x1 - V.x0) * W, Y = y => H - (y - V.y0) / (V.y1 - V.y0) * H;
const fmt2 = v => { const s = String(parseFloat(v.toPrecision(5))); return st.dec ? s.replace('.',',') : s; };
const fmt = v => { const s = String(parseFloat(v.toPrecision(10))); return st.dec ? s.replace('.',',') : s; };

/* Laden / Speichern */
(function(){
  let g = null; try { g = JSON.parse(localStorage.getItem('qm_g') || 'null'); } catch(e){}
  if (g && Array.isArray(g.items) && g.items.length){
    items = g.items.map(i => ({text:String(i.text || ''), vis:i.vis !== false}));
    if (g.V && isFinite(g.V.x0) && g.V.x1 > g.V.x0 && g.V.y1 > g.V.y0) V = g.V;
    if (g.GST) { Object.assign(GST, g.GST); GST.d3 = false; }
    if (g.sl) for (const n in g.sl) sl[n] = Object.assign({dir:1}, g.sl[n], {anim:false});
  } else items = [{text:'f(x)=sin(x)', vis:true}, {text:'a*x^2/10', vis:true}];
})();
let gsT = null;
function gsaveNow(){ try { localStorage.setItem('qm_g', JSON.stringify({items:items.map(i => ({text:i.text, vis:i.vis})), sl, V, GST})); } catch(e){} }
function gsaveSoon(){ clearTimeout(gsT); gsT = setTimeout(gsaveNow, 400); }

/* Zeichenfläche */
function sizeCanvas(){
  const d = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) return;
  W = w; H = h; cv.width = Math.round(w*d); cv.height = Math.round(h*d); ctx.setTransform(d,0,0,d,0,0);
  if (GST.eq) equalize(); draw();
}
new ResizeObserver(() => sizeCanvas()).observe(cv);
function requestDraw(){ if (drawQ) return; drawQ = true; requestAnimationFrame(() => { drawQ = false; draw(); }); }
function equalize(){ const cy = (V.y0 + V.y1)/2, sp = (V.x1 - V.x0) * H / W; V.y0 = cy - sp/2; V.y1 = cy + sp/2; }
function graphShow(){ sizeCanvas(); if (!parsedOnce){ parsedOnce = true; reparse(); } requestDraw(); }

/* Objekte (Algebra-Liste) */
function setNote(it, t, err){ const e = it.noteEl; if (!e) return; if (e.textContent !== t) e.textContent = t; e.className = err ? 'aerr' : 'ainfo'; e.style.display = t ? 'block' : 'none'; }
function updateNote(it){
  const r = it.res;
  if (it.texEl){ if (r && r.kind !== 'err' && r.tex){ try { it.texEl.innerHTML = texToHtml(r.tex, {dec:st.dec}); it.texEl.style.display = 'block'; } catch(e){ it.texEl.style.display = 'none'; } } else it.texEl.style.display = 'none'; }
  if (!r){ setNote(it, ''); return; }
  if (r.kind === 'err') setNote(it, r.msg, true);
  else if (r.kind === 'surface') setNote(it, GST.d3 ? '3D-Fläche' : 'Nur im 3D-Modus sichtbar (Knopf „3D“)');
  else if (r.kind === 'slider') setNote(it, 'Schieberegler ' + r.name + ' (siehe unten)');
  else if (r.kind === 'def') setNote(it, 'Definition gespeichert');
  else if (r.kind !== 'area') setNote(it, '');
}
function renderAlg(focusIdx){
  const box = $('#arows'); box.innerHTML = '';
  items.forEach((it, i) => {
    const wrap = document.createElement('div'), row = document.createElement('div'); row.className = 'arow';
    const dot = document.createElement('button'); dot.className = 'adot'; dot.setAttribute('aria-label', 'Sichtbarkeit');
    const paint = () => { dot.style.borderColor = colorOf(i); dot.style.background = it.vis ? colorOf(i) : 'transparent'; };
    paint(); dot.onclick = () => { it.vis = !it.vis; paint(); gsaveSoon(); requestDraw(); buzz(); };
    const inp = document.createElement('input'); inp.className = 'ain'; inp.value = it.text; inp.placeholder = 'f(x)=…   x²+y²=9   (1;2)   y>x^2';
    inp.autocomplete = 'off'; inp.autocapitalize = 'off'; inp.spellcheck = false; inp.setAttribute('autocorrect','off');
    inp.addEventListener('input', () => { it.text = inp.value; scheduleParse(); });
    inp.addEventListener('focus', () => { lastIn = inp; });
    inp.addEventListener('keydown', e => { if (e.key === 'Enter'){ e.preventDefault(); clearTimeout(ptimer); reparse(); inp.blur(); } });
    const del = document.createElement('button'); del.className = 'adel'; del.textContent = '✕';
    del.onclick = () => { items.splice(i, 1); if (!items.length) items.push({text:'', vis:true}); renderAlg(); scheduleParse(); buzz(); };
    row.append(dot, inp, del);
    const texEl = document.createElement('div'); texEl.className = 'atex'; texEl.style.display = 'none'; it.texEl = texEl;
    const note = document.createElement('div'); note.className = 'ainfo'; note.style.display = 'none';
    it.noteEl = note; it.inEl = inp; wrap.append(row, texEl, note); box.append(wrap); updateNote(it);
  });
  if (focusIdx !== undefined && items[focusIdx]) items[focusIdx].inEl.focus();
}
function addItem(text){ items.push({text:text || '', vis:true}); renderAlg(items.length - 1); if (text) scheduleParse(); buzz(); }
let ptimer = null, pseq = 0;
function scheduleParse(){ clearTimeout(ptimer); ptimer = setTimeout(reparse, 350); gsaveSoon(); }
function compileItem(it){
  const r = it.res; it.c = null;
  if (!r || ['err','empty','slider','def'].includes(r.kind)) return;
  try {
    const c = {};
    for (const k of ['js','jx','jy','lo','hi','jx1','jy1','jx2','jy2']) if (r[k] != null) c[k] = compileJS(r[k]);
    if (r.pts) c.pts = r.pts.map(p => [compileJS(p[0]), compileJS(p[1])]);
    for (const k in c) if (typeof c[k] === 'function') { try { c[k](1,1,1,P); } catch(e){ if (e instanceof ReferenceError) throw e; } }
    it.c = c;
  } catch(e){ it.res = {kind:'err', msg:'Nicht darstellbar: ' + e.message, params:[]}; }
}
async function reparse(){
  const my = ++pseq; let r;
  try { r = await post('/api/gparse', {entries:items.map(i => i.text), dec:st.dec}); }
  catch(e){ items.forEach(it => setNote(it, 'Keine Verbindung zum Rechenkern.', true)); return; }
  if (my !== pseq) return;
  (r.results || []).forEach((res, i) => { const it = items[i]; if (!it) return; it.res = res; });
  syncSliders();
  items.forEach(it => { compileItem(it); it.areaNote = false; updateNote(it); });
  gsaveSoon(); requestDraw();
}

/* Schieberegler */
function mkSlider(v){ const m = Math.max(5, Math.ceil(Math.abs(v) * 2)); return {v:v, defv:v, min:-m, max:m, anim:false, dir:1}; }
function syncSliders(){
  const need = new Set(), defs = {};
  items.forEach(it => { const r = it.res; if (!r) return; if (r.kind === 'slider'){ defs[r.name] = r; need.add(r.name); } (r.params || []).forEach(n => need.add(n)); });
  let changed = false;
  for (const n of need){
    const d = defs[n];
    if (!sl[n]){ sl[n] = mkSlider(d ? d.value : 1); changed = true; }
    else if (d && sl[n].defv !== d.value){ sl[n] = mkSlider(d.value); changed = true; }
  }
  for (const n of Object.keys(sl)) if (!need.has(n)){ delete sl[n]; changed = true; }
  for (const k of Object.keys(P)) if (!sl[k]) delete P[k];
  for (const n in sl) P[n] = sl[n].v;
  if (changed || Object.keys(slUI).length !== Object.keys(sl).length) renderSliders();
}
function setRange(r, s){ r.min = s.min; r.max = s.max; r.step = (s.max - s.min) / 400; r.value = s.v; }
function renderSliders(){
  const box = $('#slid'); box.innerHTML = ''; for (const k in slUI) delete slUI[k];
  const names = Object.keys(sl).sort(); if (!names.length) return;
  box.append(el('div', 'Schieberegler', 'ex-t'));
  names.forEach(n => {
    const s = sl[n], row = document.createElement('div'); row.className = 'slrow';
    const lab = el('span', n, 'sln'), val = el('span', fmt(s.v), 'slv');
    const range = document.createElement('input'); range.type = 'range'; setRange(range, s);
    range.oninput = () => { s.v = parseFloat(range.value); P[n] = s.v; val.textContent = fmt(s.v); requestDraw(); gsaveSoon(); };
    const play = el('button', s.anim ? '❚❚' : '▶', 'slp'); play.onclick = () => { s.anim = !s.anim; play.textContent = s.anim ? '❚❚' : '▶'; if (s.anim) startAnim(); buzz(); };
    const mk = (v, key) => { const i = document.createElement('input'); i.type = 'number'; i.value = v; i.className = 'slmm'; i.onchange = () => { const x = parseFloat(i.value); if (isFinite(x)){ s[key] = x; if (s.min >= s.max) s.max = s.min + 1; s.v = Math.min(s.max, Math.max(s.min, s.v)); P[n] = s.v; setRange(range, s); val.textContent = fmt(s.v); requestDraw(); gsaveSoon(); } }; return i; };
    const line2 = document.createElement('div'); line2.className = 'slrow2';
    line2.append(el('small', 'min'), mk(s.min, 'min'), el('small', 'max'), mk(s.max, 'max'));
    const top = document.createElement('div'); top.className = 'sltop'; top.append(lab, range, val, play);
    row.append(top, line2); box.append(row); slUI[n] = {range, val, play};
  });
}
function animTick(){
  let any = false;
  for (const n in sl){ const s = sl[n]; if (!s.anim) continue; any = true;
    s.v += s.dir * (s.max - s.min) / 260;
    if (s.v >= s.max){ s.v = s.max; s.dir = -1; } if (s.v <= s.min){ s.v = s.min; s.dir = 1; }
    P[n] = s.v; const u = slUI[n]; if (u){ u.range.value = s.v; u.val.textContent = fmt(s.v); } }
  if (any){ draw(); requestAnimationFrame(animTick); } else animOn = false;
}
function startAnim(){ if (!animOn){ animOn = true; requestAnimationFrame(animTick); } }

/* Zeichnen – 2D */
function drawSegs(s){ ctx.beginPath(); for (let k = 0; k < s.length; k += 4){ ctx.moveTo(s[k], s[k+1]); ctx.lineTo(s[k+2], s[k+3]); } ctx.stroke(); }
function drawGrid(){
  const mode = GST.grid, xs = niceStep(V.x1 - V.x0, 6), ys = niceStep(V.y1 - V.y0, 6);
  const sxp = (V.x1 - V.x0) / W, syp = (V.y1 - V.y0) / H;
  const ax = Math.min(Math.max(X(0), 4), W - 46), ay = Math.min(Math.max(Y(0), 4), H - 16);
  ctx.lineWidth = 1; ctx.strokeStyle = COL.line2; ctx.font = '10px system-ui'; ctx.fillStyle = COL.dim;
  if (mode === 2){
    const rm = Math.max(Math.hypot(V.x0, V.y0), Math.hypot(V.x1, V.y0), Math.hypot(V.x0, V.y1), Math.hypot(V.x1, V.y1));
    ctx.globalAlpha = .5;
    for (let k = 1; k * xs <= rm && k < 150; k++){ ctx.beginPath(); ctx.ellipse(X(0), Y(0), k*xs/sxp, k*xs/syp, 0, 0, 2*Math.PI); ctx.stroke(); }
    for (let a = 0; a < 12; a++){ const t = a * Math.PI / 6; ctx.beginPath(); ctx.moveTo(X(0), Y(0)); ctx.lineTo(X(rm*Math.cos(t)), Y(rm*Math.sin(t))); ctx.stroke(); }
    ctx.globalAlpha = 1;
    for (let k = 1; k * xs <= V.x1 && k < 150; k++) ctx.fillText(fmt(k*xs), X(k*xs) + 2, ay + 11);
  } else {
    if (mode === 1){ ctx.globalAlpha = .22; const mx = xs/5, my = ys/5;
      for (let v = Math.ceil(V.x0/mx)*mx; v <= V.x1; v += mx){ ctx.beginPath(); ctx.moveTo(X(v), 0); ctx.lineTo(X(v), H); ctx.stroke(); }
      for (let v = Math.ceil(V.y0/my)*my; v <= V.y1; v += my){ ctx.beginPath(); ctx.moveTo(0, Y(v)); ctx.lineTo(W, Y(v)); ctx.stroke(); } }
    ctx.globalAlpha = (mode === 3) ? 0 : .55;
    for (let v = Math.ceil(V.x0/xs)*xs; v <= V.x1; v += xs){ ctx.beginPath(); ctx.moveTo(X(v), 0); ctx.lineTo(X(v), H); ctx.stroke(); }
    for (let v = Math.ceil(V.y0/ys)*ys; v <= V.y1; v += ys){ ctx.beginPath(); ctx.moveTo(0, Y(v)); ctx.lineTo(W, Y(v)); ctx.stroke(); }
    ctx.globalAlpha = 1;
    for (let v = Math.ceil(V.x0/xs)*xs; v <= V.x1; v += xs) if (Math.abs(v) > xs/2) ctx.fillText(fmt(v), X(v) + 2, ay + 11);
    for (let v = Math.ceil(V.y0/ys)*ys; v <= V.y1; v += ys) if (Math.abs(v) > ys/2) ctx.fillText(fmt(v), ax + 3, Y(v) - 3);
  }
  ctx.strokeStyle = COL.line; ctx.lineWidth = 2;
  if (V.x0 <= 0 && 0 <= V.x1){ ctx.beginPath(); ctx.moveTo(X(0), 0); ctx.lineTo(X(0), H); ctx.stroke(); }
  if (V.y0 <= 0 && 0 <= V.y1){ ctx.beginPath(); ctx.moveTo(0, Y(0)); ctx.lineTo(W, Y(0)); ctx.stroke(); }
  ctx.fillStyle = COL.line; ctx.font = 'italic 12px system-ui'; ctx.fillText('x', W - 12, Math.min(Math.max(Y(0) - 6, 12), H - 4)); ctx.fillText('y', Math.min(Math.max(X(0) + 6, 4), W - 10), 12);
}
function drawFunc(f, col){
  ctx.strokeStyle = col; ctx.lineWidth = 2.6; ctx.beginPath();
  const sxp = (V.x1 - V.x0) / W, step = W > 700 ? 2 : 1; let on = false, prev = 0;
  for (let px = 0; px <= W; px += step){
    const y = evalAt(f, V.x0 + px * sxp, 0, 0, P); if (!isFinite(y)){ on = false; continue; }
    const py = Y(y); if (Math.abs(py) > 1e5){ on = false; continue; }
    if (on && Math.abs(py - prev) > H * 1.5) on = false;
    if (!on){ ctx.moveTo(px, py); on = true; } else ctx.lineTo(px, py);
    prev = py;
  }
  ctx.stroke();
}
function drawParam(fx, fy, lo, hi, col, polar){
  const a = evalAt(lo,0,0,0,P), b = evalAt(hi,0,0,0,P); if (!isFinite(a) || !isFinite(b) || a === b) return;
  ctx.strokeStyle = col; ctx.lineWidth = 2.4; ctx.lineJoin = 'round'; ctx.beginPath();
  const n = 1800, lim = Math.max(W, H) * 2; let on = false, px0 = 0, py0 = 0;
  for (let k = 0; k <= n; k++){
    const t = a + (b - a) * k / n; let x, y;
    if (polar){ const r = evalAt(fx,0,0,t,P); x = r * Math.cos(t); y = r * Math.sin(t); } else { x = evalAt(fx,0,0,t,P); y = evalAt(fy,0,0,t,P); }
    if (!isFinite(x) || !isFinite(y)){ on = false; continue; }
    const px = X(x), py = Y(y); if (Math.abs(px) > 1e5 || Math.abs(py) > 1e5){ on = false; continue; }
    if (on && Math.hypot(px - px0, py - py0) > lim) on = false;
    if (!on){ ctx.moveTo(px, py); on = true; } else ctx.lineTo(px, py);
    px0 = px; py0 = py;
  }
  ctx.stroke();
}
function drawIneq(it, col, cell){
  const f = it.c.js, op = it.res.op, nx = Math.ceil(W / cell), ny = Math.ceil(H / cell);
  offc.width = nx; offc.height = ny; const oc = offc.getContext('2d'), img = oc.createImageData(nx, ny), d = img.data, rgb = hexRGB(col);
  const sxp = (V.x1 - V.x0) / W, syp = (V.y1 - V.y0) / H;
  for (let j = 0; j < ny; j++){ const y = V.y1 - (j + .5) * cell * syp;
    for (let i = 0; i < nx; i++){ const v = evalAt(f, V.x0 + (i + .5) * cell * sxp, y, 0, P);
      if (isFinite(v) && (op === '<' ? v < 0 : op === '<=' ? v <= 0 : op === '>' ? v > 0 : v >= 0)){ const k = (j * nx + i) * 4; d[k] = rgb[0]; d[k+1] = rgb[1]; d[k+2] = rgb[2]; d[k+3] = 72; } } }
  oc.putImageData(img, 0, 0); ctx.imageSmoothingEnabled = false; ctx.drawImage(offc, 0, 0, nx, ny, 0, 0, nx * cell, ny * cell); ctx.imageSmoothingEnabled = true;
  ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.setLineDash(op === '<' || op === '>' ? [7, 5] : []); drawSegs(marchSegs(f, P, V, W, H, cell)); ctx.setLineDash([]);
}
function drawArea(it, col){
  const c = it.c, lo = evalAt(c.lo,0,0,0,P), hi = evalAt(c.hi,0,0,0,P); if (!isFinite(lo) || !isFinite(hi) || lo === hi) return;
  const a = Math.min(lo, hi), b = Math.max(lo, hi), sxp = (V.x1 - V.x0) / W, n = Math.max(40, Math.min(700, Math.ceil((b - a) / sxp)));
  ctx.beginPath(); ctx.moveTo(X(a), Y(0));
  for (let k = 0; k <= n; k++){ const x = a + (b - a) * k / n, y = evalAt(c.js, x, 0, 0, P); if (isFinite(y)) ctx.lineTo(X(x), Y(Math.max(-1e5, Math.min(1e5, y)))); }
  ctx.lineTo(X(b), Y(0)); ctx.closePath(); ctx.globalAlpha = .28; ctx.fillStyle = col; ctx.fill(); ctx.globalAlpha = 1;
  ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.setLineDash([5, 4]);
  [a, b].forEach(x => { ctx.beginPath(); ctx.moveTo(X(x), Y(0)); ctx.lineTo(X(x), Y(evalAt(c.js, x, 0, 0, P))); ctx.stroke(); }); ctx.setLineDash([]);
  it.areaNote = true; setNote(it, 'Integral ≈ ' + fmt2(simpson(c.js, P, lo, hi)) + '   (von ' + fmt2(lo) + ' bis ' + fmt2(hi) + ')');
}
function dot(x, y, col, r){ ctx.beginPath(); ctx.arc(x, y, r, 0, 2*Math.PI); ctx.fillStyle = col; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = COL.bg; ctx.stroke(); }
function pxy(fx, fy){ return [X(evalAt(fx,0,0,0,P)), Y(evalAt(fy,0,0,0,P))]; }
function draw(){
  if (!W || !H) return;
  ctx.clearRect(0, 0, W, H);
  if (GST.d3) return draw3D();
  drawGrid();
  const busy = ptr.size > 0 || animOn, cell = busy ? 6 : 3;
  items.forEach((it, i) => { if (!it.vis || !it.c) return; const k = it.res.kind, col = colorOf(i);
    if (k === 'ineq') drawIneq(it, col, cell);
    else if (k === 'area') drawArea(it, col);
    else if (k === 'polygon'){
      const pts = it.c.pts.map(p => pxy(p[0], p[1])); if (pts.some(p => !isFinite(p[0]) || !isFinite(p[1]))) return;
      ctx.beginPath(); pts.forEach((p, n) => n ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath();
      ctx.globalAlpha = .2; ctx.fillStyle = col; ctx.fill(); ctx.globalAlpha = 1; ctx.strokeStyle = col; ctx.lineWidth = 2.4; ctx.stroke();
      pts.forEach(p => dot(p[0], p[1], col, 4)); } });
  items.forEach((it, i) => { if (!it.vis || !it.c) return; const k = it.res.kind, c = it.c, col = colorOf(i);
    if (k === 'func') drawFunc(c.js, col);
    else if (k === 'implicit'){ ctx.strokeStyle = col; ctx.lineWidth = 2.4; ctx.lineCap = 'round'; drawSegs(marchSegs(c.js, P, V, W, H, busy ? 5 : 3)); }
    else if (k === 'vline'){ const x = evalAt(c.js,0,0,0,P); if (isFinite(x)){ ctx.strokeStyle = col; ctx.lineWidth = 2.6; ctx.beginPath(); ctx.moveTo(X(x), 0); ctx.lineTo(X(x), H); ctx.stroke(); } }
    else if (k === 'param') drawParam(c.jx, c.jy, c.lo, c.hi, col, false);
    else if (k === 'polar') drawParam(c.js, null, c.lo, c.hi, col, true);
    else if (k === 'segment' || k === 'line'){
      const a = pxy(c.jx1, c.jy1), b = pxy(c.jx2, c.jy2); if (![...a, ...b].every(isFinite)) return;
      let p = a, q = b; if (k === 'line'){ const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy); if (l < 1e-9) return; const m = (W + H) * 4 / l; p = [a[0] - dx * m, a[1] - dy * m]; q = [a[0] + dx * m, a[1] + dy * m]; }
      ctx.strokeStyle = col; ctx.lineWidth = 2.6; ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke();
      if (k === 'segment'){ dot(a[0], a[1], col, 4); dot(b[0], b[1], col, 4); } } });
  items.forEach((it, i) => { if (!it.vis || !it.c || it.res.kind !== 'point') return; const p = pxy(it.c.jx, it.c.jy); if (!isFinite(p[0]) || !isFinite(p[1])) return;
    dot(p[0], p[1], colorOf(i), 6); if (it.res.label){ ctx.fillStyle = COL.text; ctx.font = 'bold 13px system-ui'; ctx.fillText(it.res.label, p[0] + 9, p[1] - 9); } });
  specials = [];
  if (GST.sp){ const fl = []; items.forEach((it, i) => { if (it.vis && it.c && it.res.kind === 'func') fl.push({f:it.c.js, c:colorOf(i)}); });
    if (fl.length) specials = specialPoints(fl, P, V.x0, V.x1);
    specials.forEach(p => dot(X(p.x), Y(p.y), TYPEC[p.t] || '#888', 5)); }
  if (selMark){ const px = X(selMark.x), py = Y(selMark.y); ctx.strokeStyle = COL.line; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, H); ctx.moveTo(0, py); ctx.lineTo(W, py); ctx.stroke(); ctx.setLineDash([]);
    ctx.beginPath(); ctx.arc(px, py, 8, 0, 2*Math.PI); ctx.lineWidth = 2.5; ctx.strokeStyle = COL.text; ctx.stroke(); dot(px, py, COL.line, 4); }
}

/* Zeichnen – 3D */
function draw3D(){
  const surf = []; items.forEach((it, i) => { if (it.vis && it.c && it.res.kind === 'surface') surf.push({f:it.c.js, i}); });
  const R = view3.R, s = Math.min(W, H) / (2.5 * R) * view3.zoom, cx = W / 2, cy = H / 2 + 8;
  const cyw = Math.cos(view3.yaw), syw = Math.sin(view3.yaw), cp = Math.cos(view3.pitch), spp = Math.sin(view3.pitch);
  const pr = (x, y, z) => { const X1 = x * cyw - y * syw, Y1 = x * syw + y * cyw, Y2 = Y1 * cp - z * spp, Z2 = Y1 * spp + z * cp; return [cx + X1 * s, cy - Z2 * s, Y2]; };
  ctx.lineWidth = 1; ctx.strokeStyle = COL.line2; ctx.globalAlpha = .5;
  for (let k = -5; k <= 5; k++){ const v = k * R / 5; let a = pr(v, -R, 0), b = pr(v, R, 0); ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    a = pr(-R, v, 0); b = pr(R, v, 0); ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); }
  ctx.globalAlpha = 1;
  const c1 = hexRGB(COL.g1), c2 = hexRGB(COL.g2), N = 38;
  surf.forEach(sf => {
    const zv = [], quads = []; let zmax = 1e-9;
    for (let i = 0; i <= N; i++){ zv.push([]); for (let j = 0; j <= N; j++){ const z = evalAt(sf.f, -R + 2*R*i/N, -R + 2*R*j/N, 0, P); zv[i].push(z); if (isFinite(z)) zmax = Math.max(zmax, Math.abs(z)); } }
    const zs = zmax > 1.8 * R ? 1.8 * R / zmax : 1; let zmin = Infinity, zhi = -Infinity;
    zv.forEach(r => r.forEach(z => { if (isFinite(z)){ zmin = Math.min(zmin, z * zs); zhi = Math.max(zhi, z * zs); } }));
    const span = Math.max(1e-9, zhi - zmin);
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++){
      const zz = [zv[i][j], zv[i+1][j], zv[i+1][j+1], zv[i][j+1]]; if (zz.some(z => !isFinite(z))) continue;
      const xs = [-R + 2*R*i/N, -R + 2*R*(i+1)/N], ys = [-R + 2*R*j/N, -R + 2*R*(j+1)/N];
      const q = [pr(xs[0], ys[0], zz[0]*zs), pr(xs[1], ys[0], zz[1]*zs), pr(xs[1], ys[1], zz[2]*zs), pr(xs[0], ys[1], zz[3]*zs)];
      quads.push({q, d:(q[0][2] + q[1][2] + q[2][2] + q[3][2]) / 4, t:((zz[0] + zz[1] + zz[2] + zz[3]) / 4 * zs - zmin) / span}); }
    quads.sort((a, b) => b.d - a.d);
    quads.forEach(o => { const t = Math.max(0, Math.min(1, o.t)); ctx.beginPath(); ctx.moveTo(o.q[0][0], o.q[0][1]); for (let k = 1; k < 4; k++) ctx.lineTo(o.q[k][0], o.q[k][1]); ctx.closePath();
      ctx.fillStyle = 'rgb(' + Math.round(c1[0] + (c2[0] - c1[0]) * t) + ',' + Math.round(c1[1] + (c2[1] - c1[1]) * t) + ',' + Math.round(c1[2] + (c2[2] - c1[2]) * t) + ')'; ctx.fill();
      ctx.strokeStyle = COL.bg; ctx.globalAlpha = .35; ctx.lineWidth = .6; ctx.stroke(); ctx.globalAlpha = 1; });
  });
  ctx.lineWidth = 2; ctx.strokeStyle = COL.line; ctx.fillStyle = COL.line; ctx.font = 'bold 13px system-ui';
  [[[-R,0,0],[R,0,0],'x'],[[0,-R,0],[0,R,0],'y'],[[0,0,-R],[0,0,R],'z']].forEach(([a, b, n]) => { const p = pr(...a), q = pr(...b); ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke(); ctx.fillText(n, q[0] + 5, q[1] - 5); });
  if (!surf.length){ ctx.fillStyle = COL.dim; ctx.font = '13px system-ui'; ctx.textAlign = 'center'; ctx.fillText('Objekt eingeben:  z=sin(x)*cos(y)', W / 2, 24); ctx.textAlign = 'start'; }
}

/* Berühren, Verschieben, Zoomen, Spur */
const ptr = new Map(); let moved = false, downT = 0, downPos = null, lastTap = {t:0, x:0, y:0};
function showTip(px, py, text){ tip.textContent = text; tip.style.opacity = 1;
  const w = tip.offsetWidth || 120; tip.style.left = Math.max(4, Math.min(cv.offsetLeft + W - w - 4, cv.offsetLeft + px + 12)) + 'px'; tip.style.top = Math.max(4, cv.offsetTop + py - 40) + 'px'; }
function hideTip(){ tip.style.opacity = 0; selMark = null; }
function coordText(x, y){ return '(' + fmt2(x) + ' | ' + fmt2(y) + ')'; }
function zoomXY(px, py, fx, fy){
  const cx = V.x0 + px / W * (V.x1 - V.x0), cy = V.y1 - py / H * (V.y1 - V.y0);
  const nx0 = cx - (cx - V.x0) * fx, nx1 = cx + (V.x1 - cx) * fx, ny0 = cy - (cy - V.y0) * fy, ny1 = cy + (V.y1 - cy) * fy;
  if (!(nx1 - nx0 > 1e-9 && nx1 - nx0 < 1e9 && ny1 - ny0 > 1e-9 && ny1 - ny0 < 1e9)) return;
  V = {x0:nx0, x1:nx1, y0:ny0, y1:ny1}; if (GST.eq) equalize(); requestDraw(); gsaveSoon();
}
function firstFunc(){ for (let i = 0; i < items.length; i++){ const it = items[i]; if (it.vis && it.c && it.res.kind === 'func') return it; } return null; }
function traceTo(px){
  const it = firstFunc(); if (!it) return;
  const sxp = (V.x1 - V.x0) / W, x = V.x0 + px * sxp, y = evalAt(it.c.js, x, 0, 0, P); if (!isFinite(y)) return;
  const h = sxp * .5, m = (evalAt(it.c.js, x + h, 0, 0, P) - evalAt(it.c.js, x - h, 0, 0, P)) / (2 * h);
  selMark = {x, y}; showTip(px, Y(y), coordText(x, y) + (isFinite(m) ? '   f′ ≈ ' + fmt2(m) : '')); requestDraw();
}
function tap(px, py){
  const now = Date.now();
  if (now - lastTap.t < 320 && Math.hypot(px - lastTap.x, py - lastTap.y) < 30){ lastTap.t = 0; GST.d3 ? resetView3() : autoFit(); return; }
  lastTap = {t:now, x:px, y:py};
  if (GST.d3 || GST.tr) return;
  let best = null, bd = 26;
  specials.forEach(p => { const d = Math.hypot(X(p.x) - px, Y(p.y) - py); if (d < bd){ bd = d; best = {x:p.x, y:p.y, t:(TYPEN[p.t] || '') + ' ' + coordText(p.x, p.y)}; } });
  items.forEach(it => { if (it.vis && it.c && it.res.kind === 'point'){ const x = evalAt(it.c.jx,0,0,0,P), y = evalAt(it.c.jy,0,0,0,P), d = Math.hypot(X(x) - px, Y(y) - py); if (d < bd){ bd = d; best = {x, y, t:(it.res.label ? it.res.label + ' ' : '') + coordText(x, y)}; } } });
  if (!best){ const sxp = (V.x1 - V.x0) / W, x = V.x0 + px * sxp; bd = 30;
    items.forEach(it => { if (it.vis && it.c && it.res.kind === 'func'){ const y = evalAt(it.c.js, x, 0, 0, P), d = Math.abs(Y(y) - py); if (isFinite(y) && d < bd){ bd = d; best = {x, y, t:coordText(x, y)}; } } }); }
  if (best){ selMark = {x:best.x, y:best.y}; showTip(X(best.x), Y(best.y), best.t); buzz(8); } else hideTip();
  requestDraw();
}
cv.addEventListener('pointerdown', e => {
  cv.setPointerCapture(e.pointerId); ptr.set(e.pointerId, {x:e.offsetX, y:e.offsetY});
  if (ptr.size === 1){ moved = false; downT = Date.now(); downPos = {x:e.offsetX, y:e.offsetY}; if (GST.tr && !GST.d3) traceTo(e.offsetX); } else moved = true;
  if (!GST.tr) tip.style.opacity = 0;
});
cv.addEventListener('pointermove', e => {
  if (!ptr.has(e.pointerId)) return;
  const old = ptr.get(e.pointerId), nw = {x:e.offsetX, y:e.offsetY};
  if (ptr.size === 1){
    if (Math.hypot(nw.x - downPos.x, nw.y - downPos.y) > 6) moved = true;
    if (GST.d3){ view3.yaw += (nw.x - old.x) * .01; view3.pitch = Math.max(-1.45, Math.min(1.45, view3.pitch + (nw.y - old.y) * .008)); requestDraw(); }
    else if (GST.tr) traceTo(nw.x);
    else if (moved){ const sx = (V.x1 - V.x0) / W, sy = (V.y1 - V.y0) / H, dx = nw.x - old.x, dy = nw.y - old.y;
      V = {x0:V.x0 - dx * sx, x1:V.x1 - dx * sx, y0:V.y0 + dy * sy, y1:V.y1 + dy * sy}; selMark = null; requestDraw(); gsaveSoon(); }
  } else if (ptr.size === 2){
    const other = [...ptr.entries()].find(([id]) => id !== e.pointerId)[1];
    const ox = Math.abs(old.x - other.x), oy = Math.abs(old.y - other.y), nx = Math.abs(nw.x - other.x), ny = Math.abs(nw.y - other.y);
    const d0 = Math.hypot(ox, oy), d1 = Math.hypot(nx, ny);
    if (d0 > 0 && d1 > 0){
      if (GST.d3){ view3.zoom = Math.max(.3, Math.min(6, view3.zoom * d1 / d0)); requestDraw(); }
      else { let fx = d0 / d1, fy = d0 / d1; if (!GST.eq){ if (ox > 40 && nx > 10) fx = ox / nx; if (oy > 40 && ny > 10) fy = oy / ny; }
        zoomXY((nw.x + other.x) / 2, (nw.y + other.y) / 2, fx, fy); } }
  }
  ptr.set(e.pointerId, nw);
});
['pointerup', 'pointercancel'].forEach(t => cv.addEventListener(t, e => {
  const single = ptr.size === 1; ptr.delete(e.pointerId);
  if (t === 'pointerup' && single && !moved && Date.now() - downT < 400) tap(e.offsetX, e.offsetY);
  if (!ptr.size) requestDraw();
}));
cv.addEventListener('wheel', e => { e.preventDefault(); const f = e.deltaY < 0 ? .85 : 1 / .85; if (GST.d3){ view3.zoom = Math.max(.3, Math.min(6, view3.zoom / f)); requestDraw(); } else zoomXY(e.offsetX, e.offsetY, f, f); }, {passive:false});

/* Einpassen */
function resetView3(){ view3.yaw = -0.7; view3.pitch = 0.55; view3.zoom = 1; requestDraw(); }
function autoFit(){
  if (GST.d3){ resetView3(); return; }
  const fy = [], bx = [], by = []; const sxp = (V.x1 - V.x0) / W; let hasF = false;
  items.forEach(it => { if (!it.vis || !it.c) return; const c = it.c, k = it.res.kind;
    if (k === 'func'){ hasF = true; for (let i = 0; i <= 300; i++){ const y = evalAt(c.js, V.x0 + (V.x1 - V.x0) * i / 300, 0, 0, P); if (isFinite(y)) fy.push(y); } }
    else if (k === 'param' || k === 'polar'){ const a = evalAt(c.lo,0,0,0,P), b = evalAt(c.hi,0,0,0,P);
      for (let i = 0; i <= 500; i++){ const t = a + (b - a) * i / 500; let x, y; if (k === 'polar'){ const r = evalAt(c.js,0,0,t,P); x = r * Math.cos(t); y = r * Math.sin(t); } else { x = evalAt(c.jx,0,0,t,P); y = evalAt(c.jy,0,0,t,P); } if (isFinite(x) && isFinite(y)){ bx.push(x); by.push(y); } } }
    else if (k === 'point'){ const x = evalAt(c.jx,0,0,0,P), y = evalAt(c.jy,0,0,0,P); if (isFinite(x) && isFinite(y)){ bx.push(x); by.push(y); } }
    else if (k === 'segment' || k === 'line'){ [[c.jx1, c.jy1], [c.jx2, c.jy2]].forEach(p => { const x = evalAt(p[0],0,0,0,P), y = evalAt(p[1],0,0,0,P); if (isFinite(x) && isFinite(y)){ bx.push(x); by.push(y); } }); }
    else if (k === 'polygon'){ c.pts.forEach(p => { const x = evalAt(p[0],0,0,0,P), y = evalAt(p[1],0,0,0,P); if (isFinite(x) && isFinite(y)){ bx.push(x); by.push(y); } }); } });
  if (!hasF && !bx.length) { V = {x0:-10, x1:10, y0:-6, y1:6}; if (GST.eq) equalize(); requestDraw(); return; }
  let y0, y1, x0 = V.x0, x1 = V.x1;
  if (fy.length > 4){ fy.sort((a, b) => a - b); let lo = fy[Math.floor(fy.length * .04)], hi = fy[Math.min(fy.length - 1, Math.floor(fy.length * .96))]; if (hi - lo < 1e-9){ lo -= 1; hi += 1; } const p = (hi - lo) * .25; y0 = lo - p; y1 = hi + p; }
  if (bx.length){ let a = Math.min(...bx), b = Math.max(...bx), c = Math.min(...by), d = Math.max(...by); if (b - a < 1e-9){ a -= 1; b += 1; } if (d - c < 1e-9){ c -= 1; d += 1; }
    const px = (b - a) * .2, py = (d - c) * .2; if (!hasF || !fy.length){ x0 = a - px; x1 = b + px; } else { x0 = Math.min(x0, a - px); x1 = Math.max(x1, b + px); }
    y0 = y0 === undefined ? c - py : Math.min(y0, c - py); y1 = y1 === undefined ? d + py : Math.max(y1, d + py); }
  if (y0 === undefined){ y0 = -5; y1 = 5; }
  V = {x0, x1, y0, y1}; if (GST.eq) equalize(); selMark = null; hideTip(); requestDraw(); gsaveSoon();
}

/* Werkzeugleiste, Vorlagen, Mathe-Tasten */
function syncBar(){
  $('#gbEq').classList.toggle('on', GST.eq); $('#gbSp').classList.toggle('on', GST.sp); $('#gbTr').classList.toggle('on', GST.tr);
  $('#g3d').classList.toggle('on', GST.d3); $('#gbGrid').textContent = GRIDS[GST.grid]; $('#gbFs').textContent = document.body.classList.contains('gfs') ? '⤡' : '⤢';
  items.forEach(updateNote);
}
$('#gbFit').onclick = () => { autoFit(); buzz(); };
$('#gbEq').onclick = () => { GST.eq = !GST.eq; if (GST.eq) equalize(); syncBar(); requestDraw(); gsaveSoon(); buzz(); };
$('#gbGrid').onclick = () => { GST.grid = (GST.grid + 1) % GRIDS.length; syncBar(); requestDraw(); gsaveSoon(); buzz(); };
$('#gbSp').onclick = () => { GST.sp = !GST.sp; syncBar(); requestDraw(); gsaveSoon(); buzz(); };
$('#gbTr').onclick = () => { GST.tr = !GST.tr; hideTip(); syncBar(); requestDraw(); gsaveSoon(); buzz(); };
$('#g3d').onclick = () => { GST.d3 = !GST.d3; hideTip(); syncBar(); requestDraw(); buzz(); };
$('#gbFs').onclick = () => { document.body.classList.toggle('gfs'); if (!document.body.classList.contains('gfs')) document.body.classList.remove('alg'); syncBar(); setTimeout(sizeCanvas, 60); buzz(); };
$('#gbList').onclick = () => { document.body.classList.toggle('alg'); buzz(); };
const TPL = [['Funktion','f(x)=x^2-2'], ['Parameter','a*sin(b*x)'], ['Schieber','a=2'], ['Kreis','x^2+y^2=9'], ['Ellipse','x^2/9+y^2/4=1'], ['Implizit','x^3+y^3=6*x*y'],
  ['Punkt','A=(1;2)'], ['Strecke','strecke((0;0);(3;4))'], ['Gerade','gerade((0;0);(2;1))'], ['Polygon','polygon((0;0);(3;0);(0;4))'], ['Kurve','(cos(t);sin(2*t));t=0..2*pi'],
  ['Polar','r=1+cos(t)'], ['Ungleichung','y>x^2'], ['Fläche','flaeche(x^2;0;2)'], ['Ableitung','ableitung(sin(x);x)'], ['Tangente','tangente(x^2;x;1)'], ['3D-Fläche','z=sin(x)*cos(y)']];
(function(){ const box = $('#tpl'); TPL.forEach(([n, t]) => { const b = el('button', n, 'xchip'); b.onclick = () => { addItem(t); box.hidden = true; }; box.append(b); });
  const b = el('button', '↧ aus Rechner', 'xchip'); b.onclick = () => { const t = inp.value.trim().replace(/^\s*[A-Za-z_]\w*(\(\s*\w+\s*\))?\s*(:=|=)\s*(?!=)/, ''); addItem(t); box.hidden = true; }; box.append(b); })();
$('#aAdd').onclick = () => addItem('');
$('#aTpl').onclick = () => { const b = $('#tpl'); b.hidden = !b.hidden; };
const MK = ['x','y','t','π','^','²','√(','(',')',';','|','sin(','cos(','tan(','ln(','e^(','abs(','sqrt(','<','>','=','a','b'];
(function(){ const box = $('#mkeys'); MK.forEach(k => { const b = el('button', k.replace(/\($/, ''), 'mk'); b.addEventListener('pointerdown', e => e.preventDefault());
  b.onclick = () => { const t = lastIn || (items[0] && items[0].inEl); if (!t) return; let s = k === 'π' ? 'pi' : k === '√(' ? 'sqrt(' : k === '²' ? '^2' : k;
    const a = t.selectionStart ?? t.value.length, z = t.selectionEnd ?? a; t.setRangeText(s, a, z, 'end'); t.focus(); t.dispatchEvent(new Event('input')); buzz(4); }; box.append(b); }); })();

/* Start */
$('#helptxt').textContent = HELP;
applyTheme(); renderHist(); renderVars(); showWelcome(); renderAlg(); renderSliders(); syncBar(); go('calc');
async function boot(){
  const t0 = Date.now();
  for (;;){
    try { const r = await (await fetch('/api/ready')).json();
      if (r.ready){ if (r.error) showResult({kind:'err', msg:r.error}); break; } } catch(e){}
    await sleep(350);
  }
  await sleep(Math.max(0, 1100 - (Date.now() - t0)));
  $('#splash').classList.add('hide');
  try { const s = await (await fetch('/api/state')).json(); vars = s.vars || []; renderVars(); } catch(e){}
}
boot();
</script>
</body>
</html>
"""

PAGE = (PAGE_TEMPLATE
        .replace("__KEYPADS__", json.dumps(KEYPADS, ensure_ascii=False))
        .replace("__HELP__", json.dumps(HELP_TEXT, ensure_ascii=False)))


if __name__ == "__main__":
    main()
