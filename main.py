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
version = 1.0.0
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


def make_icon(path, size=512):
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
            a = clamp(0.5 - d * S)
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
         B("x²", "^2"), B("xʸ", "^")],
        [B("4", kind="num"), B("5", kind="num"), B("6", kind="num"), B("−", "-", "op"),
         B("√", "wurzel(|)"), B("n!", "!")],
        [B("1", kind="num"), B("2", kind="num"), B("3", kind="num"), B("+", kind="op"),
         B("1/x", "1/(|)"), B("|x|", "betrag(|)")],
        [B("0", kind="num"), B(",", "<DEC>", "num"), B("π", "pi"), B("e"), B("ans"),
         B("=", "<EQ>", "acc")],
        [B("x"), B("y"), B("z"), B("a"), B("b"), B("Gl.=", "=", "op")],
    ],
    "Funktionen": [
        [B("sin", "sin(|)"), B("cos", "cos(|)"), B("tan", "tan(|)"),
         B("sinh", "sinh(|)"), B("cosh", "cosh(|)"), B("tanh", "tanh(|)")],
        [B("sin⁻¹", "asin(|)"), B("cos⁻¹", "acos(|)"), B("tan⁻¹", "atan(|)"),
         B("sinh⁻¹", "asinh(|)"), B("cosh⁻¹", "acosh(|)"), B("tanh⁻¹", "atanh(|)")],
        [B("ln", "ln(|)"), B("lg", "lg(|)"), B("logₐ", "log(|;)"),
         B("eˣ", "exp(|)"), B("10ˣ", "10^(|)"), B("ⁿ√", "wurzel(|;)")],
        [B("|x|", "betrag(|)"), B("sign", "vorzeichen(|)"), B("⌊x⌋", "boden(|)"),
         B("⌈x⌉", "decke(|)"), B("runde", "runde(|;)"), B("Γ", "gamma(|)")],
        [B("→Grad", "grad(|)"), B("→Bog.", "bogen(|)"), B("erf", "erf(|)"),
         B("atan2", "atan2(|;)"), B("max", "maxi(|)"), B("min", "mini(|)")],
        [B("x"), B("y"), B("t"), B("n"), B("k"), B("ans")],
    ],
    "Komplex": [
        [B("i", kind="acc"), B("Re", "re(|)"), B("Im", "im(|)"), B("|z|", "betrag(|)"),
         B("arg", "arg(|)"), B("z̄", "konj(|)")],
        [B("polar", "polar(|)"), B("kart.", "kart(|)"), B("r,φ→z", "kart(|;)"),
         B("zⁿ", "^"), B("ⁿ√z", "wurzeln(|;)"), B("1ⁿ√", "einheitswurzeln(|)")],
        [B("e^(iφ)", "exp(i*|)"), B("a+bi", "(|+ *i)"), B("√", "wurzel(|)"),
         B("sin", "sin(|)"), B("cos", "cos(|)"), B("ln", "ln(|)")],
        [B("(", kind="op"), B(")", kind="op"), B("π", "pi"), B("e"), B("ans"),
         B("=", "<EQ>", "acc")],
    ],
    "Gleichungen": [
        [B("=", "=", "acc"), B("<", kind="op"), B(">", kind="op"), B("≤", "<=", "op"),
         B("≥", ">=", "op"), B("löse", "loese(|;x)")],
        [B("System", "|=; ="), B("vereinf.", "vereinfache(|)"), B("expand", "expandiere(|)"),
         B("faktor", "faktorisiere(|)"), B("kürzen", "kuerze(|)"), B("Partialbr.", "partialbruch(|;x)")],
        [B("Nullst.", "nullstellen(|;x)"), B("einsetz.", "subs(|;x;)"), B("nlöse", "nloese(|;x;)"),
         B("Poly÷", "polydiv(|;;x)"), B("Koeff.", "koeffizienten(|;x)"), B("trigvf.", "trigvereinfache(|)")],
        [B("Extrema", "extrema(|;x)"), B("Wendep.", "wendepunkte(|;x)"), B("Tangente", "tangente(|;x;)"),
         B("f(x)=", "f(x)="), B("g(x)=", "g(x)="), B("x"), ],
    ],
    "Analysis": [
        [B("d/dx", "ableitung(|;x)"), B("d²/dx²", "ableitung(|;x;2)"), B("∫ dx", "integral(|;x)"),
         B("∫ₐᵇ", "integral(|;x;;)"), B("lim", "limes(|;x;)"), B("lim⁺", "limes_plus(|;x;)")],
        [B("lim⁻", "limes_minus(|;x;)"), B("Σ", "summe(|;k;1;n)"), B("Π", "produkt(|;k;1;n)"),
         B("Taylor", "taylor(|;x;0;6)"), B("Reihe", "reihe(|;x;0;6)"), B("DGL", "dgl(|)")],
        [B("Laplace", "laplace(|;t;s)"), B("L⁻¹", "invlaplace(|;s;t)"), B("∇", "gradient(|;x;y)"),
         B("∫ num.", "nint(|;x;;)"), B("∞", "oo", "op"), B("−∞", "-oo", "op")],
        [B("y(x)", "y(x)"), B("y′", "ableitung(y(x);x)"), B("f(x)=", "f(x)="),
         B("x"), B("y"), B("t")],
    ],
    "Matrix": [
        [B("Matrix", "matrix([[|;];[;]])"), B("Vektor", "vektor(|;;)"), B("det", "det(|)"),
         B("A⁻¹", "inv(|)"), B("Aᵀ", "transp(|)"), B("Rang", "rang(|)")],
        [B("Spur", "spur(|)"), B("λ", "eigenwerte(|)"), B("v⃗", "eigenvektoren(|)"),
         B("LGS", "lgs(|;)"), B("RREF", "rref(|)"), B("Kern", "nullraum(|)")],
        [B("a·b", "skalar(|;)"), B("a×b", "kreuz(|;)"), B("‖v‖", "norm(|)"),
         B("∠", "winkel(|;)"), B("E", "einheitsmatrix(|)"), B("0", "nullmatrix(|;)")],
        [B("A"), B("B"), B("A·B", "*", "op"), B("A^-1", "^-1", "op"),
         B("A=", "A=matrix([[|]])"), B("B=", "B=matrix([[|]])")],
    ],
    "Zahlen": [
        [B("ggT", "ggT(|;)"), B("kgV", "kgV(|;)"), B("mod", "rest(|;)"),
         B("Primf.", "primfaktoren(|)"), B("prim?", "istprim(|)"), B("nächste P", "naechste_primzahl(|)")],
        [B("Teiler", "teiler(|)"), B("φ(n)", "totient(|)"), B("Fib", "fib(|)"),
         B("nCr", "binomial(|;)"), B("nPr", "perm(|;)"), B("modinv", "modinv(|;)")],
        [B("→Bin", "bin(|)"), B("→Hex", "hex(|)"), B("→Oct", "oct(|)"),
         B("→Basis", "zubasis(|;)"), B("Basis→", 'vonbasis("|";)'), B("Zufall", "zufall()")],
        [B("Mittel", "mittel(|)"), B("Median", "median(|)"), B("σ", "stabw(|)"),
         B("σ²", "varianz(|)"), B("Min", "minimum(|)"), B("Max", "maximum(|)")],
        [B("%", "prozent(|;)"), B("Φ(x)", "normcdf(|;0;1)"), B("φ(x)", "normpdf(|)"),
         B("Binom", "binompmf(|;;)"), B("Poisson", "poissonpmf(|;)"), B("Σ Liste", "summe(|)")],
    ],
}

HELP_TEXT = """\
QUANTUMATOR – KURZHILFE
═════════════════════════════════════
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

GRAPH
 Funktionen mit ;  trennen, z. B.  sin(x); x^2/10
 Ziehen = verschieben · Mausrad = zoomen · Doppelklick = Reset

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


def eval_point(f, x):
    try:
        c = complex(f(x))
        if abs(c.imag) > 1e-9 * max(1.0, abs(c.real)):
            return None
        y = c.real
        if y != y or abs(y) == float("inf"):
            return None
        return y
    except Exception:
        return None


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
           "vars": vars_snapshot()}
    if r["kind"] == "assign":
        save_defs()
    return res


def api_plot(data):
    err = not_ready()
    if err:
        return {"series": [], "errors": [err], "xmin": 0, "xmax": 1, "n": 1}
    sp = E.sp
    x = sp.Symbol("x")
    series, errs = [], []
    xmin, xmax = float(data["xmin"]), float(data["xmax"])
    n = max(20, min(1500, int(data.get("n", 300))))
    ENGINE.decimal_comma = bool(data.get("dec", True))
    for p in data.get("funcs", [])[:8]:
        try:
            ex = ENGINE.expr_from(p, ("x",))
            extra = ex.free_symbols - {x}
            if extra:
                raise ValueError("Unbekannte Größe: " + ", ".join(sorted(s.name for s in extra)))
            f = sp.lambdify(x, ex, modules=["math", "mpmath"])
            series.append({"name": p, "ys": [eval_point(f, xmin + (xmax - xmin) * i / n) for i in range(n + 1)]})
        except Exception as ex:
            errs.append("%s → %s" % (p, ex))
    return {"series": series, "errors": errs, "xmin": xmin, "xmax": xmax, "n": n}


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
            elif self.path == "/api/plot":
                out = api_plot(data)
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
--p0:#B8860B;--p1:#1F6FEB;--p2:#C0392B;--p3:#2E7D32;--p4:#8E44AD}
[data-theme=dark]{--bg:#03050A;--bg2:#070C16;--card:#09101C;--line:#2F7BFF;--line2:#1B3A73;--text:#E6EEFF;--dim:#7F95C0;--pat:#0A1424;--dot:#16305C;
--inbg:#050911;--knum:#0B1423;--kfn:#0E1B33;--kop:#12274C;--kacc:#3B87FF;--kacc2:#2262D6;--kaccfg:#FFFFFF;--kdel:#2A0F14;--kdelfg:#FF7B7B;
--sel:#173A78;--err:#FF7B7B;--g1:#7DBBFF;--g2:#2F7BFF;--glow:0 0 0 1px rgba(47,123,255,.10),0 8px 28px rgba(47,123,255,.14);--kshadow:0 2px 6px rgba(0,0,0,.5);
--p0:#4DA3FF;--p1:#FFD166;--p2:#FF7B7B;--p3:#4ADE80;--p4:#C792EA}
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
#gin{width:100%;font:16px ui-monospace,Menlo,Consolas,monospace;background:var(--inbg);color:var(--text);border:1.5px solid var(--line2);border-radius:12px;padding:11px;margin-bottom:8px;outline:none;-webkit-user-select:text;user-select:text}
#gin:focus{border-color:var(--line)}
#cv{width:100%;height:56vh;display:block;background:var(--inbg);border:1px solid var(--line2);border-radius:12px;touch-action:none}
#ginfo{font-size:11px;color:var(--dim);margin:7px 2px;min-height:15px}
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
   <input id="gin" value="sin(x); x^2/10" autocomplete="off" autocapitalize="off" spellcheck="false">
   <div class="actions" style="margin:0 0 8px"><button class="btn acc" id="gplot">Zeichnen</button><button class="btn" id="gfrom">Aus Eingabe</button><button class="btn" id="greset">Reset</button></div>
   <div id="ginfo"></div><canvas id="cv"></canvas>
   <div class="empty" style="padding:8px">Ziehen = verschieben · Zwei Finger = zoomen · Funktionen mit ;  trennen</div>
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
<div class="sheet" id="sheet"><div class="grab"></div><h3>EINSTELLUNGEN</h3><div id="srows"></div><div class="ver">Quantumator 1.0 · rechnet 100 % offline auf diesem Gerät</div></div>
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
  setStatus(); if (typeof draw === 'function') draw();
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
      b.onclick = () => { st[s.k] = v; saveSet(); applyTheme(); renderSheet(); buzz(); }; g.append(b); });
    r.append(l, g); box.append(r); });
}
const openSheet = on => { $('#sheet').classList.toggle('on', on); $('#back').classList.toggle('on', on); if (on) renderSheet(); };
$('#tSet').onclick = () => openSheet(true); $('#back').onclick = () => openSheet(false);

/* Navigation */
const navBtns = $$('#nav button');
function go(v){
  const i = navBtns.findIndex(b => b.dataset.v === v);
  navBtns.forEach((b, j) => b.classList.toggle('on', j === i));
  $('#ind').style.transform = 'translateX(' + (i*100) + '%)';
  $$('.view').forEach(x => x.classList.toggle('on', x.id === 'v-' + v));
  if (v === 'graph') { sizeCanvas(); plot(false); }
  $('main').scrollTo({top:0});
}
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
  if (s === '<DEL>'){ if (a !== b) inp.setRangeText('', a, b, 'end'); else if (a > 0) inp.setRangeText('', a-1, a, 'end'); return; }
  const pos = s.indexOf('|'), text = s.replace('|','');
  inp.setRangeText(text, a, b, 'end');
  if (pos >= 0) { const c = a + pos; inp.setSelectionRange(c, c); }
}
function clearInp(){ inp.value = ''; }
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
const EXAMPLES = ['x^2-4=0','integral(x^2;x;0;3)','(3+4i)^2','sin(30)','primfaktoren(360)','det(matrix([[1;2];[3;4]]))','ableitung(x*sin(x);x)','x+y=5; x-y=1'];
function showWelcome(){
  const box = $('#result'); box.innerHTML = '';
  box.append(el('div','Bereit.','main'));
  box.lastChild.style.fontSize = '22px';
  box.append(el('div','Beispiele zum Antippen','ex-t'));
  const w = document.createElement('div'); w.className = 'ex';
  EXAMPLES.forEach(x => { const c = el('button', x, 'xchip'); c.onclick = () => { inp.value = x; buzz(); calc(); }; w.append(c); });
  box.append(w);
}
function showResult(r){
  const box = $('#result'); box.innerHTML = '';
  if (r.kind === 'err'){ box.append(el('div','Fehler','errh'), el('pre', r.msg, 'err')); lastText = ''; return; }
  const m = el('pre', r.main, 'main'); const len = Math.max(...r.main.split('\n').map(x => x.length));
  m.style.fontSize = len > 34 ? '14px' : len > 22 ? '17px' : len > 12 ? '21px' : '26px';
  box.append(el('div', r.input, 'echo'), m);
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

/* Graph */
const cv = $('#cv'), ctx = cv.getContext('2d');
let V = {x0:-10,x1:10,y0:-6,y1:6}, W = 300, H = 300, data = null, seq = 0, timer = null;
function sizeCanvas(){
  const d = window.devicePixelRatio || 1; W = cv.clientWidth; H = cv.clientHeight;
  cv.width = W*d; cv.height = H*d; ctx.setTransform(d,0,0,d,0,0); draw();
}
window.addEventListener('resize', sizeCanvas);
function splitTop(s){ const out = []; let cur = '', d = 0; for (const c of s){ if ('([{'.includes(c)) d++; if (')]}'.includes(c)) d--;
  if (c === ';' && d === 0){ out.push(cur); cur = ''; } else cur += c; } out.push(cur); return out.map(x => x.trim()).filter(Boolean); }
function schedule(){ draw(); clearTimeout(timer); timer = setTimeout(() => plot(false), 60); }
async function plot(auto){
  const funcs = splitTop($('#gin').value); const my = ++seq;
  if (!funcs.length){ data = null; draw(); return; }
  try {
    const r = await post('/api/plot', {funcs, xmin:V.x0, xmax:V.x1, n:Math.max(60, Math.ceil(W/2)), dec:st.dec});
    if (my !== seq) return;
    data = r; if (auto) autoY();
    $('#ginfo').textContent = r.errors && r.errors.length ? 'Fehler: ' + r.errors.join(' | ') : '';
  } catch(e){ $('#ginfo').textContent = 'Keine Verbindung zum Rechenkern.'; }
  draw();
}
function autoY(){
  const ys = []; (data.series||[]).forEach(s => s.ys.forEach(y => { if (y !== null) ys.push(y); }));
  if (ys.length < 5){ V.y0 = -5; V.y1 = 5; return; }
  ys.sort((a,b) => a-b); let lo = ys[Math.floor(ys.length*0.04)], hi = ys[Math.min(ys.length-1, Math.floor(ys.length*0.96))];
  if (hi-lo < 1e-9){ lo -= 1; hi += 1; } const pad = (hi-lo)*0.25; V.y0 = lo-pad; V.y1 = hi+pad;
}
function niceStep(span, target){ const raw = Math.max(span,1e-12)/target, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const m of [1,2,5,10]) if (raw <= m*mag) return m*mag; return 10*mag; }
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmt = v => { const s = String(parseFloat(v.toPrecision(10))); return st.dec ? s.replace('.',',') : s; };
function draw(){
  if (!W || !H) return;
  ctx.clearRect(0,0,W,H);
  const X = x => (x-V.x0)/(V.x1-V.x0)*W, Y = y => H-(y-V.y0)/(V.y1-V.y0)*H;
  const sx = niceStep(V.x1-V.x0, 6), sy = niceStep(V.y1-V.y0, 6);
  const ax = Math.min(Math.max(X(0),4), W-44), ay = Math.min(Math.max(Y(0),4), H-16);
  ctx.font = '10px system-ui'; ctx.lineWidth = 1;
  for (let v = Math.ceil(V.x0/sx)*sx; v <= V.x1; v += sx){ ctx.strokeStyle = css('--pat'); ctx.beginPath(); ctx.moveTo(X(v),0); ctx.lineTo(X(v),H); ctx.stroke();
    if (Math.abs(v) > sx/2){ ctx.fillStyle = css('--dim'); ctx.fillText(fmt(v), X(v)+2, ay+11); } }
  for (let v = Math.ceil(V.y0/sy)*sy; v <= V.y1; v += sy){ ctx.strokeStyle = css('--pat'); ctx.beginPath(); ctx.moveTo(0,Y(v)); ctx.lineTo(W,Y(v)); ctx.stroke();
    if (Math.abs(v) > sy/2){ ctx.fillStyle = css('--dim'); ctx.fillText(fmt(v), ax+3, Y(v)-3); } }
  ctx.strokeStyle = css('--line'); ctx.lineWidth = 2;
  if (V.x0 <= 0 && 0 <= V.x1){ ctx.beginPath(); ctx.moveTo(X(0),0); ctx.lineTo(X(0),H); ctx.stroke(); }
  if (V.y0 <= 0 && 0 <= V.y1){ ctx.beginPath(); ctx.moveTo(0,Y(0)); ctx.lineTo(W,Y(0)); ctx.stroke(); }
  if (!data) return;
  ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  data.series.forEach((s, idx) => {
    ctx.strokeStyle = css('--p' + (idx % 5)); ctx.lineWidth = 2.4; ctx.beginPath(); let pen = false, prev = null;
    s.ys.forEach((y, i) => {
      if (y === null){ pen = false; prev = null; return; }
      const px = X(data.xmin + (data.xmax-data.xmin)*i/data.n), py = Y(y);
      if (Math.abs(py) > 1e6 || (prev !== null && Math.abs(py-prev) > H*2)){ pen = false; prev = null; if (Math.abs(py) > 1e6) return; }
      if (!pen){ ctx.moveTo(px,py); pen = true; } else ctx.lineTo(px,py); prev = py;
    });
    ctx.stroke(); ctx.fillStyle = css('--p' + (idx % 5)); ctx.font = '11px system-ui'; ctx.fillText('━ ' + s.name, 8, 15 + idx*14);
  });
}
const pts = new Map();
cv.addEventListener('pointerdown', e => { cv.setPointerCapture(e.pointerId); pts.set(e.pointerId, {x:e.offsetX, y:e.offsetY}); });
cv.addEventListener('pointermove', e => {
  if (!pts.has(e.pointerId)) return;
  const old = pts.get(e.pointerId), nw = {x:e.offsetX, y:e.offsetY};
  if (pts.size === 1){
    const sx = (V.x1-V.x0)/W, sy = (V.y1-V.y0)/H, dx = nw.x-old.x, dy = nw.y-old.y;
    V.x0 -= dx*sx; V.x1 -= dx*sx; V.y0 += dy*sy; V.y1 += dy*sy; schedule();
  } else if (pts.size === 2){
    const other = [...pts.entries()].find(([id]) => id !== e.pointerId)[1];
    const d0 = Math.hypot(old.x-other.x, old.y-other.y), d1 = Math.hypot(nw.x-other.x, nw.y-other.y);
    if (d0 > 0 && d1 > 0) zoom((nw.x+other.x)/2, (nw.y+other.y)/2, d0/d1);
  }
  pts.set(e.pointerId, nw);
});
['pointerup','pointercancel'].forEach(t => cv.addEventListener(t, e => pts.delete(e.pointerId)));
function zoom(px, py, f){
  const cx = V.x0 + px/W*(V.x1-V.x0), cy = V.y1 - py/H*(V.y1-V.y0);
  V = {x0:cx-(cx-V.x0)*f, x1:cx+(V.x1-cx)*f, y0:cy-(cy-V.y0)*f, y1:cy+(V.y1-cy)*f}; schedule();
}
cv.addEventListener('wheel', e => { e.preventDefault(); zoom(e.offsetX, e.offsetY, e.deltaY < 0 ? 0.85 : 1/0.85); }, {passive:false});
cv.addEventListener('dblclick', () => { V = {x0:-10,x1:10,y0:-6,y1:6}; plot(true); });
$('#gplot').onclick = () => { plot(true); buzz(); };
$('#greset').onclick = () => { V = {x0:-10,x1:10,y0:-6,y1:6}; plot(true); buzz(); };
$('#gin').addEventListener('keydown', e => { if (e.key === 'Enter') plot(true); });
$('#gfrom').onclick = () => { const t = inp.value.trim().replace(/^\s*[A-Za-z_]\w*(\(\s*\w+\s*\))?\s*(:=|=)\s*(?!=)/, ''); if (t) $('#gin').value = t; plot(true); buzz(); };

/* Start */
$('#helptxt').textContent = HELP;
applyTheme(); renderHist(); renderVars(); showWelcome(); go('calc');
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
