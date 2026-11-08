# -*- coding: utf-8 -*-
"""Quantumator – Rechenkern (sympy). Wird von main.py im Hintergrund geladen."""
import sys
import os
import re
import json
import math
import random
import queue
import threading
import functools
from fractions import Fraction
from collections import Counter
from tokenize import TokenError

try:
    import sympy as sp
    import mpmath
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations,
        implicit_multiplication_application, convert_xor)
    from sympy.core.relational import Relational, Equality
    from sympy.core.function import AppliedUndef
    from sympy.logic.boolalg import BooleanAtom
except ImportError:  # pragma: no cover
    raise ImportError("sympy fehlt – pip install sympy")

SUB = str.maketrans("0123456789+-", "₀₁₂₃₄₅₆₇₈₉₊₋")
SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


# ════════════════════════════════════════════════════════════════════════
#  RECHENKERN
# ════════════════════════════════════════════════════════════════════════
class Raw(str):
    """Fertiger Anzeigetext."""


class Out:
    """Wert + Zusatztext (z. B. '+ C')."""
    def __init__(self, value, note=""):
        self.value, self.note = value, note


class Sol(list):
    """Lösungsmenge: Liste von Dicts {Symbol: Wert}."""
    numeric = False


class UserFunc:
    def __init__(self, name, params, expr, src=""):
        self.name, self.params, self.expr, self.src = name, params, sp.sympify(expr), src

    def __call__(self, *args):
        if len(args) != len(self.params):
            raise TypeError("%s erwartet %d Argument(e)" % (self.name, len(self.params)))
        return self.expr.subs(dict(zip(self.params, args)), simultaneous=True)


OPEN, CLOSE = "([{", ")]}"
FUNC_RE = re.compile(r"^\s*([^\W\d]\w*)\s*\(\s*([^()=]*?)\s*\)\s*(:=|=)\s*(.+?)\s*$")
ASSIGN_RE = re.compile(r"^\s*([^\W\d]\w*)\s*(:=|=)\s*(.+?)\s*$")
LONE_EQ = re.compile(r"(?<![<>=!:])=(?!=)")

GLOBALS = {k: getattr(sp, k) for k in
           ("Integer", "Float", "Rational", "Symbol", "Function", "Eq",
            "factorial", "factorial2", "Lambda", "Tuple")}
TRANSFORMS = standard_transformations + (convert_xor, implicit_multiplication_application)

UNI = {"×": "*", "÷": "/", "−": "-", "–": "-", "·": "*", "⋅": "*", "²": "^2", "³": "^3",
       "π": " pi ", "∞": " oo ", "≤": "<=", "≥": ">=", "“": '"', "”": '"', "‘": "'", "’": "'",
       "∙": "*", "ⁿ": "^n"}


def split_top(s, seps=","):
    parts, cur, depth, q = [], [], 0, None
    for c in s:
        if q:
            cur.append(c)
            if c == q:
                q = None
            continue
        if c in "\"'":
            q = c
            cur.append(c)
            continue
        if c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth -= 1
        if depth == 0 and c in seps:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    parts.append("".join(cur))
    return parts


def find_top_eq(p):
    depth, q = 0, None
    for i, c in enumerate(p):
        if q:
            if c == q:
                q = None
            continue
        if c in "\"'":
            q = c
        elif c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth -= 1
        elif c == "=" and depth == 0:
            prev = p[i - 1] if i > 0 else ""
            nxt = p[i + 1] if i + 1 < len(p) else ""
            if prev in "<>=!:" or nxt == "=":
                continue
            return i
    return -1


def match_close(s, i):
    depth, q = 0, None
    for j in range(i, len(s)):
        c = s[j]
        if q:
            if c == q:
                q = None
            continue
        if c in "\"'":
            q = c
        elif c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth -= 1
            if depth == 0:
                return j
    raise ValueError("Die Klammern passen nicht zusammen.")


def conv_group(s):
    """Wandelt 'a=b' innerhalb von Klammern rekursiv in Eq(a,b) um."""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in "\"'":
            j = s.find(c, i + 1)
            j = n - 1 if j < 0 else j
            out.append(s[i:j + 1])
            i = j + 1
        elif c in OPEN:
            j = match_close(s, i)
            out.append(c + conv_args(s[i + 1:j]) + s[j])
            i = j + 1
        elif c in CLOSE:
            raise ValueError("Die Klammern passen nicht zusammen.")
        else:
            out.append(c)
            i += 1
    return "".join(out)


def conv_args(s):
    res = []
    for p in split_top(s, ","):
        k = find_top_eq(p)
        if k >= 0:
            res.append("Eq(%s,%s)" % (conv_group(p[:k]), conv_group(p[k + 1:])))
        else:
            res.append(conv_group(p))
    return ",".join(res)


def to_base(n, b):
    n, b = int(n), int(b)
    if not 2 <= b <= 36:
        raise ValueError("Die Basis muss zwischen 2 und 36 liegen.")
    digs = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    neg, n, s = n < 0, abs(n), ""
    while True:
        n, r = divmod(n, b)
        s = digs[r] + s
        if n == 0:
            break
    return ("-" if neg else "") + s


def as_vector(vals):
    vals = list(vals)
    try:
        return sp.Matrix([sp.sympify(t) for t in vals])
    except Exception:
        return sp.Tuple(*vals)


class Engine:
    def __init__(self):
        self.vars = {}
        self.funcs = {}
        self.defs = {}
        self.ans = sp.Integer(0)
        self.deg = True
        self.digits = 15
        self.decimal_comma = True
        self.builtin = set(self._ns().keys())

    # ───────────── Hilfsfunktionen ─────────────
    def prepare(self, s):
        s = s.strip()
        for a, b in UNI.items():
            s = s.replace(a, b)
        s = re.sub(r"√\s*(\d+(?:[.,]\d+)?|[^\W\d]\w*)", r"wurzel(\1)", s)
        s = s.replace("√", "wurzel")
        s = s.replace("°", "" if self.deg else "*pi/180")
        if self.decimal_comma:
            s = re.sub(r"(?<=\d),(?=\d)", ".", s)
        s = s.replace(";", ",")

        def dec(m):
            f = Fraction(m.group(0))
            return "Rational(%d,%d)" % (f.numerator, f.denominator)
        s = re.sub(r"(?<![\w.])\d+\.\d+(?![\w.])", dec, s)
        return s

    def _parse(self, code, ns):
        ns = dict(ns)
        for m in re.finditer(r"(?<![\w.])([^\W\d_]\w*)\s*\(", code):
            n = m.group(1)
            if n in ns or n in GLOBALS:
                continue
            if len(n) == 1 and n not in "yuvwhYUVWFGH":
                continue
            ns[n] = sp.Function(n)
        return parse_expr(code, local_dict=ns, global_dict=GLOBALS,
                          transformations=TRANSFORMS, evaluate=True)

    def expr_from(self, text, free=()):
        """Textausdruck -> sympy-Ausdruck (für Graphen)."""
        old = self.deg
        self.deg = False          # Graphen immer im Bogenmaß
        try:
            s = self.prepare(text)
            s = re.sub(r"^\s*[^\W\d]\w*(\(\s*\w+\s*\))?\s*(:=|=)\s*(?!=)", "", s)
            ns = {k: v for k, v in self._ns().items() if k not in free}
            v = self._parse(conv_group(s), ns)
            if isinstance(v, Out):
                v = v.value
            return sp.sympify(v)
        finally:
            self.deg = old

    def _var(self, expr, v=None):
        if v is not None:
            return v
        fs = sp.sympify(expr).free_symbols
        if not fs:
            return sp.Symbol("x")
        if len(fs) == 1:
            return next(iter(fs))
        for s in fs:
            if s.name == "x":
                return s
        return sorted(fs, key=lambda s: s.name)[0]

    def _E(self, f, x=None):
        if isinstance(f, UserFunc):
            e = f.expr
            if len(f.params) == 1 and isinstance(x, sp.Symbol):
                e = e.subs(f.params[0], x)
            return e
        if callable(f) and not isinstance(f, sp.Basic):
            return f(x if isinstance(x, sp.Symbol) else sp.Symbol("x"))
        return sp.sympify(f)

    @staticmethod
    def _flat(args):
        if len(args) == 1 and isinstance(args[0], (list, tuple, sp.Tuple, sp.MatrixBase)):
            return list(args[0])
        return list(args)

    # ───────────── Anzeige ─────────────
    def clean(self, t):
        t = t.replace("ⅈ", "i").replace("ⅇ", "e").replace("⋅", "·")
        if self.decimal_comma:
            t = re.sub(r"(?<=\d)\.(?=\d)", ",", t)
        if len(t) > 30000:
            t = t[:30000] + " …"
        return t

    def one_line(self, v):
        if isinstance(v, sp.Float):
            return self.clean(self.fr(v))
        if isinstance(v, sp.Basic):
            try:
                t = sp.pretty(v, use_unicode=True, wrap_line=False, num_columns=400)
            except Exception:
                t = str(v)
            if "\n" in t:
                t = sp.sstr(v)
                t = t.replace("sqrt(", "√(").replace("**", "^").replace("*", "·")
                t = re.sub(r"\bI\b", "i", t).replace("pi", "π")
            return self.clean(t)
        return self.clean(str(v))

    def pretty(self, v):
        if isinstance(v, sp.Float):
            return self.clean(self.fr(v))
        if getattr(v, "is_Atom", False) or getattr(v, "is_Rational", False):
            return self.clean(str(v))
        try:
            return self.clean(sp.pretty(v, use_unicode=True, wrap_line=False, num_columns=400))
        except Exception:
            return self.clean(str(v))

    def fr(self, x):
        d = self.digits
        mpmath.mp.dps = d + 12
        try:
            t = mpmath.nstr(mpmath.mpf(str(x)), d)
            return t[:-2] if t.endswith(".0") else t
        except Exception:
            return str(x)

    def fmt_num(self, v):
        d = self.digits
        n = sp.N(v, d + 8)
        if n.has(sp.oo, -sp.oo, sp.zoo, sp.nan):
            return str(n)
        re_, im_ = n.as_real_imag()
        thr = sp.Float(10) ** (-(d + 4))
        if abs(im_) < thr * max(1, abs(re_)):
            return self.fr(re_)
        s_im = "i" if abs(abs(im_) - 1) < thr else self.fr(abs(im_)) + "·i"
        if abs(re_) < thr * max(1, abs(im_)):
            return ("−" if im_ < 0 else "") + s_im
        return "%s %s %s" % (self.fr(re_), "−" if im_ < 0 else "+", s_im)

    def approx_of(self, v):
        try:
            if isinstance(v, sp.MatrixBase):
                if v.free_symbols or all(isinstance(t, sp.Integer) for t in v):
                    return None
                rows = [[self.fmt_num(t) for t in v.row(r)] for r in range(v.rows)]
                w = [max(len(rows[r][c]) for r in range(v.rows)) for c in range(v.cols)]
                return self.clean("\n".join(
                    "[ " + "  ".join(rows[r][c].rjust(w[c]) for c in range(v.cols)) + " ]"
                    for r in range(v.rows)))
            if not isinstance(v, sp.Expr) or v.free_symbols:
                return None
            if v.is_Integer or isinstance(v, sp.Float) or not v.is_number:
                return None
            if v.has(sp.oo, -sp.oo, sp.zoo, sp.nan):
                return None
            return self.clean(self.fmt_num(v))
        except Exception:
            return None

    def render_sol(self, sol):
        if not sol:
            return "Keine Lösung", []
        lines, aps = [], []
        for idx, d in enumerate(sol, 1):
            items = list(d.items())
            if len(items) == 1 and len(sol) > 1:
                k, v = items[0]
                label = "%s%s" % (getattr(k, "name", str(k)), str(idx).translate(SUB))
                lines.append("%s = %s" % (label, self.one_line(v)))
                a = self.approx_of(v)
                if a:
                    aps.append("%s ≈ %s" % (label, a))
            else:
                lines.append(",  ".join("%s = %s" % (getattr(k, "name", str(k)), self.one_line(v))
                                        for k, v in items))
                ap = []
                for k, v in items:
                    a = self.approx_of(v)
                    if a:
                        ap.append("%s ≈ %s" % (getattr(k, "name", str(k)), a))
                if ap:
                    aps.append(",  ".join(ap))
        extra = []
        if aps:
            extra.append(("Näherung", "\n".join(aps)))
        if sol.numeric:
            extra.append(("Hinweis", "Numerisch bestimmte reelle Lösungen im Bereich [−50, 50]; "
                                     "weitere Lösungen sind möglich."))
        return "\n".join(lines), extra

    def render(self, v):
        note, extra = "", []
        if isinstance(v, Out):
            note, v = v.note, v.value
        if isinstance(v, Raw):
            return self.clean(str(v)), extra
        if isinstance(v, (bool, BooleanAtom)):
            return ("Wahr" if bool(v) else "Falsch"), extra
        if isinstance(v, Sol):
            return self.render_sol(v)
        if isinstance(v, (list, tuple, set, frozenset, sp.Tuple)):
            items = list(v)
            lines, aps = [], []
            for n, it in enumerate(items, 1):
                lines.append("%d)  %s" % (n, self.one_line(it)))
                a = self.approx_of(it)
                if a:
                    aps.append("%d)  ≈ %s" % (n, a))
            if aps:
                extra.append(("Näherung", "\n".join(aps)))
            return ("\n".join(lines) if lines else "∅  (leer)"), extra
        v = sp.sympify(v)
        if v is sp.zoo:
            return "Nicht definiert  (Division durch Null → ∞)", extra
        main = self.pretty(v) + note
        a = self.approx_of(v)
        if a and a != main:
            extra.append(("≈ Numerisch", a))
        try:
            if isinstance(v, sp.Expr) and v.is_number and not v.free_symbols and v.is_real is False:
                d = self.digits
                r = sp.N(sp.Abs(v), d + 5)
                th = sp.N(sp.arg(v), d + 5)
                extra.append(("Polarform",
                              "r = %s     φ = %s rad = %s°" % (
                                  self.clean(self.fr(r)), self.clean(self.fr(th)),
                                  self.clean(self.fr(sp.N(th * 180 / sp.pi, d + 5))))))
        except Exception:
            pass
        return main, extra

    # ───────────── Namespace ─────────────
    def _ns(self, exclude=()):
        ns = {}
        deg, S = self.deg, self

        def tin(x):
            x = sp.sympify(x)
            return x * sp.pi / 180 if deg else x

        def tout(r):
            return r * 180 / sp.pi if deg else r

        def A(names, f):
            for n in names.split():
                ns[n] = f

        # Konstanten
        A("pi", sp.pi)
        A("e", sp.E)
        A("i j", sp.I)
        A("oo unendlich", sp.oo)
        A("phi", sp.GoldenRatio)
        A("ans", self.ans)

        # Trigonometrie (Grad/Bogenmaß)
        for n, f in (("sin", sp.sin), ("cos", sp.cos), ("tan", sp.tan),
                     ("cot", sp.cot), ("sec", sp.sec), ("csc", sp.csc)):
            ns[n] = (lambda f: lambda x: f(tin(x)))(f)
        for n, f in (("asin arcsin", sp.asin), ("acos arccos", sp.acos),
                     ("atan arctan", sp.atan), ("acot arccot", sp.acot)):
            A(n, (lambda f: lambda x: tout(f(sp.sympify(x))))(f))
        A("atan2", lambda y, x: tout(sp.atan2(y, x)))
        for n, f in (("sinh", sp.sinh), ("cosh", sp.cosh), ("tanh", sp.tanh), ("coth", sp.coth),
                     ("asinh arsinh", sp.asinh), ("acosh arcosh", sp.acosh),
                     ("atanh artanh", sp.atanh)):
            A(n, f)
        A("grad", lambda x: sp.sympify(x) * 180 / sp.pi)
        A("bogen", lambda x: sp.sympify(x) * sp.pi / 180)

        # Exponential / Logarithmus / Wurzeln / Rundung
        A("exp", sp.exp)
        A("ln", sp.log)
        A("lg", lambda x: sp.log(x, 10))
        A("ld", lambda x: sp.log(x, 2))
        A("log", lambda x, b=10: sp.log(x, b))
        A("wurzel sqrt", lambda x, n=2: sp.sqrt(x) if n == 2 else sp.root(x, n))
        A("cbrt", lambda x: sp.root(x, 3))
        A("betrag abs", sp.Abs)
        A("vorzeichen sign", sp.sign)
        A("boden floor", sp.floor)
        A("decke ceil", sp.ceiling)
        A("runde round", lambda x, n=0: sp.Float(sp.N(x, 40)).round(int(n)))
        A("gamma", sp.gamma)
        A("erf", sp.erf)
        A("erfc", sp.erfc)
        A("zeta", sp.zeta)
        A("lambertw", sp.LambertW)
        A("maxi", lambda *a: sp.Max(*S._flat(a)))
        A("mini", lambda *a: sp.Min(*S._flat(a)))

        # Komplexe Zahlen
        A("re", sp.re)
        A("im", sp.im)
        A("arg", lambda z: tout(sp.arg(sp.sympify(z))))
        A("konj conj", sp.conjugate)

        def polar(z):
            z = sp.sympify(z)
            r = sp.simplify(sp.Abs(z))
            th = tout(sp.simplify(sp.arg(z)))
            u = "°" if deg else " rad"
            la, lb = S.approx_of(r), S.approx_of(th)
            ex_r, ex_t = S.one_line(r), S.one_line(th)
            if re.search(r"atan|acos|asin|arg", ex_t) and lb:
                return Raw("r = %s%s\nφ ≈ %s%s" % (ex_r, ("   ≈ " + la) if la else "", lb, u))
            return Raw("r = %s%s\nφ = %s%s%s" % (
                ex_r, ("   ≈ " + la) if la else "",
                ex_t, u, ("   ≈ " + lb + u) if lb else ""))
        A("polar", polar)

        def kart(*a):
            if len(a) == 1:
                return sp.simplify(sp.expand_complex(sp.sympify(a[0])))
            r, ph = a
            ph = tin(ph)
            return sp.simplify(sp.expand_complex(r * (sp.cos(ph) + sp.I * sp.sin(ph))))
        A("kart kartesisch", kart)

        def wurzeln(z, n=2):
            z, n = sp.sympify(z), int(n)
            r, th = sp.Abs(z), sp.arg(z)
            return [sp.simplify(sp.expand_complex(
                sp.root(r, n) * sp.exp(sp.I * (th + 2 * sp.pi * k) / n))) for k in range(n)]
        A("wurzeln", wurzeln)
        A("einheitswurzeln", lambda n: wurzeln(1, n))

        # Algebra / Gleichungen
        A("loese löse solve", self.f_loese)
        A("nloese nlöse", self.f_nloese)
        A("vereinfache simplify", sp.simplify)
        A("expandiere expand", sp.expand)
        A("faktorisiere factor", sp.factor)
        A("kuerze kürze cancel", sp.cancel)
        A("trigvereinfache trigsimp", sp.trigsimp)
        A("partialbruch apart", lambda f, x=None: sp.apart(f, x) if x is not None else sp.apart(f))
        A("subs einsetzen ersetze", lambda f, x, v: sp.sympify(f).subs(x, v))
        A("koeffizienten", lambda p, x=None: sp.Poly(p, self._var(p, x)).all_coeffs())

        def polydiv(p, q, x=None):
            x = self._var(p, x)
            a, b = sp.div(p, q, x)
            return Raw("Quotient: %s\nRest:     %s" % (S.one_line(a), S.one_line(b)))
        A("polydiv polynomdivision", polydiv)
        A("nullstellen", lambda f, x=None: self.f_loese(self._E(f, x), self._var(self._E(f, x), x)))
        A("extrema", self.f_extrema)
        A("wendepunkte", self.f_wendepunkte)

        def tangente(f, x, x0):
            e = self._E(f, x)
            return sp.simplify(e.subs(x, x0) + sp.diff(e, x).subs(x, x0) * (x - x0))
        A("tangente", tangente)

        # Analysis
        def ableitung(f, x=None, n=1):
            e = self._E(f, x)
            return sp.diff(e, self._var(e, x), int(n))
        A("ableitung diff abl", ableitung)

        def integral(f, *a):
            x, lim = None, None
            if len(a) == 1:
                x = a[0]
            elif len(a) == 2:
                lim = a
            elif len(a) == 3:
                x, lim = a[0], a[1:]
            if x is not None and not isinstance(x, sp.Symbol):
                raise ValueError("integral(f; x) oder integral(f; x; a; b) – Variable erwartet.")
            e = self._E(f, x)
            x = self._var(e, x)
            if lim:
                return sp.integrate(e, (x, lim[0], lim[1]))
            return Out(sp.integrate(e, x), "  + C")
        A("integral integrate", integral)

        def limes(f, x, p, d="+-"):
            return sp.limit(self._E(f, x), x, p, d)
        A("limes grenzwert lim", limes)
        A("limes_plus grenzwert_rechts", lambda f, x, p: limes(f, x, p, "+"))
        A("limes_minus grenzwert_links", lambda f, x, p: limes(f, x, p, "-"))

        def summe(*a):
            if len(a) == 4 and isinstance(a[1], sp.Symbol):
                return sp.summation(a[0], (a[1], a[2], a[3]))
            return sp.Add(*S._flat(a))

        def produkt(*a):
            if len(a) == 4 and isinstance(a[1], sp.Symbol):
                return sp.product(a[0], (a[1], a[2], a[3]))
            return sp.Mul(*S._flat(a))
        A("summe sum", summe)
        A("produkt product", produkt)

        def reihe(f, x=None, x0=0, n=6):
            e = self._E(f, x)
            return sp.series(e, self._var(e, x), x0, int(n))
        A("reihe series", reihe)
        A("taylor", lambda f, x=None, x0=0, n=6: reihe(f, x, x0, n).removeO())

        def dgl(eq, func=None):
            if func is None:
                ufs = list(sp.sympify(eq).atoms(AppliedUndef))
                if not ufs:
                    raise ValueError("Keine unbekannte Funktion gefunden – z. B. y(x) verwenden.")
                func = ufs[0]
            return sp.dsolve(eq, func)
        A("dgl dsolve", dgl)

        def laplace(f, t=None, s=None):
            e = self._E(f, t)
            t = self._var(e, t)
            return sp.laplace_transform(e, t, s if s is not None else sp.Symbol("s"), noconds=True)
        A("laplace", laplace)
        A("invlaplace", lambda f, s=None, t=None: sp.inverse_laplace_transform(
            self._E(f, s), self._var(self._E(f, s), s), t if t is not None else sp.Symbol("t")))

        def gradient(f, *vs):
            e = self._E(f)
            vs = vs or tuple(sorted(e.free_symbols, key=lambda s: s.name))
            return sp.Matrix([sp.diff(e, v) for v in vs])
        A("gradient", gradient)

        def nint(f, x, a, b):
            return sp.N(sp.Integral(self._E(f, x), (x, a, b)), S.digits + 5)
        A("nint", nint)

        # Matrizen / Vektoren
        A("matrix", lambda rows: sp.Matrix(rows))
        A("vektor", lambda *a: sp.Matrix(S._flat(a)))
        A("det", lambda M: M.det())
        A("inv inverse", lambda M: M.inv())
        A("transp", lambda M: M.T)
        A("rang", lambda M: M.rank())
        A("spur", lambda M: M.trace())
        A("rref", lambda M: M.rref()[0])
        A("nullraum", lambda M: M.nullspace())
        A("einheitsmatrix", lambda n: sp.eye(int(n)))
        A("nullmatrix", lambda m, n=None: sp.zeros(int(m), int(n if n is not None else m)))
        A("skalar", lambda a, b: a.dot(b))
        A("kreuz", lambda a, b: a.cross(b))
        A("norm", lambda v: v.norm())
        A("winkel", lambda a, b: tout(sp.acos(a.dot(b) / (a.norm() * b.norm()))))
        A("diag", lambda *a: sp.diag(*a))

        def eigenwerte(M):
            lines = []
            for val, mult in M.eigenvals().items():
                ap = S.approx_of(val)
                lines.append("λ = %s%s%s" % (S.one_line(val), ("   ≈ " + ap) if ap else "",
                                             ("   (Vielfachheit %d)" % mult) if mult > 1 else ""))
            return Raw("\n".join(lines))
        A("eigenwerte eig", eigenwerte)

        def eigenvektoren(M):
            lines = []
            for val, mult, vecs in M.eigenvects():
                for v in vecs:
                    lines.append("λ = %s:   v = (%s)ᵀ" % (
                        S.one_line(val), ",  ".join(S.one_line(t) for t in sp.Matrix(v))))
            return Raw("\n".join(lines))
        A("eigenvektoren", eigenvektoren)

        def lgs(Am, b):
            try:
                return Am.LUsolve(b)
            except Exception:
                return sp.linsolve((Am, b))
        A("lgs", lgs)

        # Zahlentheorie / Kombinatorik
        A("fak fakultaet fakultät", sp.factorial)
        A("binomial nCr", sp.binomial)
        A("perm nPr", lambda n, k: sp.ff(n, k))
        A("ggT ggt GGT", lambda *a: functools.reduce(sp.gcd, S._flat(a)))
        A("kgV kgv KGV", lambda *a: functools.reduce(sp.lcm, S._flat(a)))
        A("rest", lambda a, b: sp.Mod(a, b))
        A("modinv", lambda a, m: sp.mod_inverse(a, m))
        A("potmod", lambda a, b, m: sp.Integer(pow(int(a), int(b), int(m))))
        A("istprim isprime", lambda n: sp.isprime(int(n)))
        A("naechste_primzahl nächste_primzahl nextprime", lambda n: sp.nextprime(int(n)))
        A("vorherige_primzahl prevprime", lambda n: sp.prevprime(int(n)))
        A("teiler divisors", lambda n: sp.divisors(int(n)))
        A("totient", lambda n: sp.totient(int(n)))
        A("fib fibonacci", lambda n: sp.fibonacci(int(n)))

        def primfaktoren(n):
            f = sp.factorint(int(n))
            if not f:
                return Raw(str(n))
            return Raw(" · ".join("%d%s" % (p, str(e).translate(SUP) if e > 1 else "")
                                  for p, e in sorted(f.items())))
        A("primfaktoren factorint", primfaktoren)
        A("zubasis", lambda n, b: Raw(to_base(n, b) + str(int(b)).translate(SUB)))
        A("bin", lambda n: Raw(to_base(n, 2) + "₂"))
        A("oct", lambda n: Raw(to_base(n, 8) + "₈"))
        A("hex", lambda n: Raw(to_base(n, 16) + "₁₆"))

        def vonbasis(s, b):
            return sp.Integer(int(str(s).strip("'\" "), int(b)))
        A("vonbasis", vonbasis)
        A("zufall", lambda: sp.Float(random.random()))
        A("zufallsint", lambda a, b: sp.Integer(random.randint(int(a), int(b))))

        # Statistik / Wahrscheinlichkeit
        A("mittel mittelwert", lambda *a: sp.Add(*S._flat(a)) / len(S._flat(a)))

        def median(*a):
            xs = sorted(S._flat(a), key=lambda v: float(sp.N(v)))
            n = len(xs)
            return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
        A("median", median)

        def modus(*a):
            xs = S._flat(a)
            c = Counter(xs)
            m = max(c.values())
            r = sorted([k for k, v in c.items() if v == m], key=lambda v: float(sp.N(v)))
            return r[0] if len(r) == 1 else r
        A("modus", modus)

        def var(a, ddof):
            xs = S._flat(a)
            m = sp.Add(*xs) / len(xs)
            return sp.simplify(sp.Add(*[(x - m) ** 2 for x in xs]) / (len(xs) - ddof))
        A("varianz", lambda *a: var(a, 1))
        A("varianz_p", lambda *a: var(a, 0))
        A("stabw", lambda *a: sp.sqrt(var(a, 1)))
        A("stabw_p", lambda *a: sp.sqrt(var(a, 0)))
        A("minimum", lambda *a: min(S._flat(a), key=lambda v: float(sp.N(v))))
        A("maximum", lambda *a: max(S._flat(a), key=lambda v: float(sp.N(v))))
        A("spannweite", lambda *a: max(S._flat(a), key=lambda v: float(sp.N(v)))
          - min(S._flat(a), key=lambda v: float(sp.N(v))))
        A("prozent", lambda p, g: sp.sympify(p) * g / 100)
        A("normpdf", lambda x, mu=0, s=1: sp.exp(-(x - mu) ** 2 / (2 * s ** 2)) / (s * sp.sqrt(2 * sp.pi)))
        A("normcdf", lambda x, mu=0, s=1: (1 + sp.erf((x - mu) / (s * sp.sqrt(2)))) / 2)
        A("binompmf", lambda n, p, k: sp.binomial(n, k) * p ** k * (1 - p) ** (n - k))
        A("binomcdf", lambda n, p, k: sp.Add(*[sp.binomial(n, j) * p ** j * (1 - p) ** (n - j)
                                              for j in range(int(k) + 1)]))
        A("poissonpmf", lambda l, k: sp.exp(-l) * l ** k / sp.factorial(k))

        # Benutzer-Variablen und -Funktionen
        for k, v in self.vars.items():
            ns[k] = v
        for k, v in self.funcs.items():
            ns[k] = v
        for k in exclude:
            ns.pop(k, None)
        return ns

    # ───────────── Löser ─────────────
    def f_loese(self, eqs, var=None):
        items = list(eqs) if isinstance(eqs, (list, tuple, sp.Tuple)) else [eqs]
        if var is None:
            vars_ = None
        elif isinstance(var, (list, tuple, sp.Tuple)):
            vars_ = list(var)
        else:
            vars_ = [var]
        if len(items) == 1 and isinstance(items[0], Relational) and not isinstance(items[0], Equality):
            rel = items[0]
            x = vars_[0] if vars_ else self._var(rel)
            try:
                return sp.solveset(rel, x, domain=sp.S.Reals)
            except Exception:
                return sp.solve(rel, x)
        eqs2 = []
        for e in items:
            if e is sp.true or e is True:
                continue
            if e is sp.false or e is False:
                return Sol([])
            eqs2.append(sp.Eq(e.lhs, e.rhs) if isinstance(e, Equality) else sp.sympify(e))
        if not eqs2:
            return Raw("Allgemeingültig (immer wahr)")
        if vars_ is None:
            fs = set()
            for e in eqs2:
                fs |= e.free_symbols
            fs = sorted(fs, key=lambda s: s.name)
            if not fs:
                raise ValueError("Keine Unbekannte in der Gleichung gefunden.")
            if len(eqs2) > 1:
                vars_ = fs
            else:
                vars_ = [next((s for s in fs if s.name == "x"), fs[0])]
        sol = None
        try:
            sol = sp.solve(eqs2, vars_, dict=True)
        except (NotImplementedError, ValueError, TypeError):
            sol = None
        if not sol and len(vars_) == 1 and len(eqs2) == 1:
            e = eqs2[0]
            expr = e.lhs - e.rhs if isinstance(e, Equality) else e
            roots = self._numeric_roots(expr, vars_[0])
            if roots:
                r = Sol([{vars_[0]: t} for t in roots])
                r.numeric = True
                return r
        return Sol(sol or [])

    def _numeric_roots(self, expr, x):
        try:
            f = sp.lambdify(x, expr, "mpmath")
        except Exception:
            return []
        roots = []
        mpmath.mp.dps = 30
        for s0 in (-50, -20, -10, -5, -3, -2, -1, -0.5, 0.1, 0.5, 1, 2, 3, 5, 10, 20, 50):
            try:
                r = mpmath.findroot(f, s0)
                if abs(mpmath.im(r)) > 1e-12 or abs(f(r)) > 1e-10:
                    continue
                r = mpmath.re(r)
                if abs(r) > 50:
                    continue
                if all(abs(r - q) > 1e-8 for q in roots):
                    roots.append(r)
            except Exception:
                continue
        return [sp.Float(mpmath.nstr(r, 30), 30) for r in sorted(roots)]

    def f_nloese(self, eq, x, start=0):
        e = eq.lhs - eq.rhs if isinstance(eq, Equality) else eq
        return sp.nsolve(e, x, start)

    def f_extrema(self, f, x=None):
        e = self._E(f, x)
        x = self._var(e, x)
        d2 = sp.diff(e, x, 2)
        lines = []
        for p in sp.solve(sp.diff(e, x), x):
            if p.is_real is False:
                continue
            try:
                s2 = float(sp.re(sp.N(d2.subs(x, p))))
            except Exception:
                s2 = 0
            kind = "Minimum" if s2 > 1e-12 else "Maximum" if s2 < -1e-12 else "unklar (Sattelpunkt?)"
            lines.append("x = %s:  %s,   f = %s" % (
                self.one_line(p), kind, self.one_line(sp.simplify(e.subs(x, p)))))
        return Raw("\n".join(lines) if lines else "Keine Extremstellen gefunden.")

    def f_wendepunkte(self, f, x=None):
        e = self._E(f, x)
        x = self._var(e, x)
        lines = []
        d3 = sp.diff(e, x, 3)
        for p in sp.solve(sp.diff(e, x, 2), x):
            if p.is_real is False:
                continue
            ok = ""
            try:
                if abs(sp.N(d3.subs(x, p))) < 1e-12:
                    ok = "  (f''' = 0: prüfen)"
            except Exception:
                pass
            lines.append("x = %s,   f = %s%s" % (
                self.one_line(p), self.one_line(sp.simplify(e.subs(x, p))), ok))
        return Raw("\n".join(lines) if lines else "Keine Wendepunkte gefunden.")

    # ───────────── Hauptauswertung ─────────────
    CALC_RE = re.compile(
        r"(?<![\w.])(ableitung|diff|abl|integral|integrate|limes|grenzwert|lim|limes_plus|limes_minus|"
        r"grenzwert_rechts|grenzwert_links|reihe|series|taylor|dgl|dsolve|laplace|invlaplace|"
        r"gradient|nint|extrema|wendepunkte|tangente)\s*\(")

    def evaluate(self, text):
        raw = text.strip()
        old_deg = self.deg
        calc = bool(self.CALC_RE.search(raw))
        if calc:
            self.deg = False      # Analysis rechnet immer im Bogenmaß
        try:
            res = self._evaluate(raw)
            if calc and old_deg and res.get("kind") == "ok" and re.search(r"\b(a?(sin|cos|tan|cot)h?)\b", raw):
                res["extra"].append(("Hinweis", "Analysis-Funktionen rechnen immer im Bogenmaß (rad)."))
            return res
        except ZeroDivisionError:
            return {"kind": "err", "msg": "Division durch Null."}
        except (SyntaxError, TokenError):
            return {"kind": "err", "msg": "Syntaxfehler – bitte Eingabe und Klammern prüfen."}
        except RecursionError:
            return {"kind": "err", "msg": "Der Ausdruck ist zu komplex."}
        except NotImplementedError:
            return {"kind": "err", "msg": "Diese Berechnung wird von der Engine nicht unterstützt."}
        except TypeError as e:
            m = str(e)
            if "argument" in m or "callable" in m:
                return {"kind": "err", "msg": "Falsche Anzahl oder Art der Argumente.\n(%s)" % m}
            return {"kind": "err", "msg": m}
        except Exception as e:
            return {"kind": "err", "msg": str(e) or type(e).__name__}
        finally:
            self.deg = old_deg

    def _evaluate(self, raw):
        m = re.match(r"^\s*(?:vergiss|clear|loesche)\s+(\w+)\s*$", raw, re.I)
        if m:
            name = m.group(1)
            if name.lower() in ("alle", "alles", "all"):
                self.vars.clear(); self.funcs.clear(); self.defs.clear()
                txt = "Alle Variablen und Funktionen gelöscht."
            elif name in self.vars or name in self.funcs:
                self.vars.pop(name, None); self.funcs.pop(name, None)
                self.defs.pop(name, None); self.defs.pop("()" + name, None)
                txt = "'%s' gelöscht." % name
            else:
                raise ValueError("'%s' ist nicht definiert." % name)
            return {"kind": "assign", "input": raw, "def": None, "main": txt, "extra": [], "value": None}
        s = self.prepare(raw)
        if s.count("(") != s.count(")"):
            raise ValueError("Die Klammern passen nicht zusammen.")
        ns = self._ns()

        # Funktionsdefinition  f(x)=...
        m = FUNC_RE.match(s)
        if m and not m.group(4).startswith("=") and (m.group(3) == ":=" or m.group(1) not in self.builtin):
            name = m.group(1)
            if name in self.builtin:
                raise ValueError("'%s' ist ein reservierter Name." % name)
            names = [p.strip() for p in m.group(2).split(",") if p.strip()]
            if not names:
                raise ValueError("Funktionsdefinition ohne Parameter.")
            for p in names:
                if p in self.builtin:
                    raise ValueError("Parametername '%s' ist reserviert." % p)
            params = [sp.Symbol(p) for p in names]
            ns2 = {k: v for k, v in ns.items() if k not in names and k != name}
            body = self._parse(conv_group(m.group(4)), ns2)
            if isinstance(body, Out):
                body = body.value
            self.funcs[name] = UserFunc(name, params, body, raw)
            self.defs["()" + name] = raw
            return {"kind": "assign", "input": raw, "def": raw,
                    "main": "%s(%s) = %s" % (name, ", ".join(names), self.one_line(sp.sympify(body))),
                    "extra": [], "value": None}

        # Zuweisung  a=5
        m = ASSIGN_RE.match(s)
        if m and not m.group(3).startswith("=") and (m.group(2) == ":=" or not LONE_EQ.search(m.group(3))):
            name = m.group(1)
            if name in self.builtin:
                raise ValueError("'%s' ist ein reservierter Name (Konstante/Funktion)." % name)
            v = self._parse(conv_group(m.group(3)), ns)
            if isinstance(v, Out):
                v = v.value
            if isinstance(v, Sol):
                vals = [x for d in v for x in d.values()]
                v = vals[0] if len(vals) == 1 else as_vector(vals)
            if isinstance(v, Relational) and not isinstance(v, Equality):
                v = self.f_loese([v])
            if isinstance(v, Raw):
                raise ValueError("Dieses Ergebnis ist ein Text und kann keiner Variablen zugewiesen werden.")
            if isinstance(v, (list, tuple)) and not isinstance(v, sp.Tuple):
                v = as_vector(v)
            self.vars[name] = sp.sympify(v)
            self.defs[name] = raw
            main, extra = self.render(self.vars[name])
            if name in ("x", "y", "z", "t"):
                extra.append(("Hinweis", "'%s' ist jetzt eine feste Zahl und kann nicht mehr als Unbekannte "
                                         "dienen.  Löschen mit:  vergiss %s" % (name, name)))
            return {"kind": "assign", "input": raw, "def": raw,
                    "main": "%s = %s" % (name, main) if "\n" not in main else "%s =\n%s" % (name, main),
                    "extra": extra, "value": self.vars[name]}

        # Gleichung / Gleichungssystem
        parts = split_top(s, ",")
        if any(find_top_eq(p) >= 0 for p in parts):
            code = "loese([" + conv_args(s) + "])"
        else:
            code = conv_group(s)
        v = self._parse(code, ns)
        if isinstance(v, Relational) and not isinstance(v, Equality):
            v = self.f_loese([v])
        if isinstance(v, sp.Expr) and not v.free_symbols and v.has(sp.I):
            try:
                v = sp.simplify(sp.expand_complex(v))
            except Exception:
                pass

        val = v.value if isinstance(v, Out) else v
        main, extra = self.render(v)
        # ans setzen
        newans = None
        if isinstance(val, Sol):
            vals = [x for d in val for x in d.values()]
            if len(vals) == 1:
                newans = vals[0]
            elif vals:
                newans = as_vector(vals)
        elif isinstance(val, (list, tuple)) and not isinstance(val, sp.Tuple):
            newans = as_vector(val)
        elif isinstance(val, sp.Basic) and not isinstance(val, BooleanAtom):
            newans = val
        elif isinstance(val, (int, float)) and not isinstance(val, bool):
            newans = sp.sympify(val)
        if newans is not None:
            self.ans = newans
        if isinstance(val, sp.Basic) and "dgl" not in raw.lower():
            und = sorted({f.func.__name__ for f in val.atoms(AppliedUndef)
                          if f.func.__name__ not in self.funcs})
            if und:
                extra.append(("Hinweis", "Unbekannte Funktion: %s – Tippfehler? "
                                         "(Hilfe → Funktionsliste)" % ", ".join(und)))
        return {"kind": "ok", "input": raw, "main": main, "extra": extra, "value": newans}


