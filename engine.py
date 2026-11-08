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



# ───────────── Formelschreibweise: ∫ ∑ ∏ lim d/dx √ ∛ |x| ⁿ ₙ ─────────────
SUPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿ⁽⁾", "0123456789+-n()")
SUBT = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋₍₎", "0123456789+-()")
SUP_RE = re.compile("[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿ⁽⁾]+")
SUB_RE = re.compile("[₀₁₂₃₄₅₆₇₈₉₊₋₍₎]+")
LIM_RE = re.compile(r"(?<![A-Za-z0-9_])lim\s*(?=_)")
DER_RE = re.compile(r"(?<![A-Za-z0-9_])[d∂]\s*(?:\^\s*\{?\s*(\d+)\s*\}?)?\s*/\s*[d∂]\s*([^\W\d_])"
                    r"\s*(?:\^\s*\{?\s*(\d+)\s*\}?)?")
SCRIPT_TOKEN = re.compile(r"-?(?:\d+(?:\.\d+)?|[^\W\d_]\w*|∞)")
LATEX_OPTS = dict(mul_symbol="dot", inv_trig_style="power", ln_notation=True)


def take_term(s, i):
    """Operand bis zum nächsten +/- auf Klammerebene 0 (ohne Vorzeichen/Exponenten)."""
    n = len(s)
    j = i
    while j < n and s[j] == " ":
        j += 1
    start, depth = j, 0
    while j < n:
        c = s[j]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0:
            if c in ",;=<>":
                break
            if c in "+-" and j > start:
                k = j - 1
                while k >= start and s[k] == " ":
                    k -= 1
                if k < start or s[k] in "^*/(+-,·×÷":
                    pass
                elif s[k] in "eE" and k > start and s[k - 1].isdigit():
                    pass
                else:
                    break
        j += 1
    return s[start:j].strip(), j


def take_operand(s, i):
    n = len(s)
    while i < n and s[i] == " ":
        i += 1
    if i < n and s[i] == "(":
        j = match_close(s, i)
        return s[i:j + 1], j + 1
    m = re.match(r"\d+(?:[.,]\d+)?|[^\W\d]\w*", s[i:])
    if m:
        return m.group(0), i + m.end()
    return None, i


def parse_scripts(s, i):
    sub = sup = None
    while True:
        j = i
        while j < len(s) and s[j] == " ":
            j += 1
        if j < len(s) and s[j] in "_^":
            kind, k = s[j], j + 1
            if k < len(s) and s[k] == "{":
                e = match_close(s, k)
                val, i = s[k + 1:e], e + 1
            else:
                m = SCRIPT_TOKEN.match(s[k:])
                if not m:
                    break
                val, i = m.group(0), k + m.end()
            if kind == "_":
                sub = val
            else:
                sup = val
        else:
            break
    return sub, sup, i


def find_dvar(s, start):
    depth = 0
    for j in range(start, len(s)):
        c = s[j]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0 and c == "d":
            m = re.match(r"d([A-Za-zα-ωΑ-Ωθ])(?![\w])", s[j:])
            if not m:
                continue
            if j > start and s[j - 1] == "/":
                continue
            k = j - 1
            while k >= start and (s[k].isdigit() or s[k] == "."):
                k -= 1
            if k >= start and (s[k].isalpha() or s[k] == "_"):
                continue
            return j, m.group(1), j + 2
    return -1, "", -1


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
    def _sym_ops(self, s):
        if not re.search(r"[∫∑∏]|lim\s*_|[d∂]\s*[\^/]", s):
            return s
        for _ in range(60):
            cands = []
            for ch in "∫∑∏":
                k = s.rfind(ch) if ch == "∫" else s.find(ch)
                if k >= 0:
                    cands.append((k, ch))
            m = LIM_RE.search(s)
            if m:
                cands.append((m.start(), "lim"))
            m2 = DER_RE.search(s)
            if m2:
                cands.append((m2.start(), "der"))
            if not cands:
                break
            ints = [c for c in cands if c[1] == "∫"]
            k, kind = max(ints) if ints else min(cands)
            if kind == "∫":
                i = k + 1
                sub, sup, i = parse_scripts(s, i)
                if sub is None and sup is None and s[i:].lstrip().startswith("("):
                    s = s[:k] + "integral" + s[i:]
                    continue
                pos, var, end = find_dvar(s, i)
                if pos < 0:
                    raise ValueError("Beim Integral fehlt „dx“ am Ende, z. B.  ∫ x² dx  oder  ∫₀³ x² dx")
                body = self._sym_ops(s[i:pos].strip())
                if not body:
                    raise ValueError("Beim Integral fehlt der Integrand.")
                args = [body, var]
                if sub is not None or sup is not None:
                    if sub is None or sup is None:
                        raise ValueError("Bitte beide Integralgrenzen angeben: ∫_{a}^{b}")
                    args += [self._sym_ops(sub), self._sym_ops(sup)]
                s = s[:k] + "integral(" + ";".join(args) + ")" + s[end:]
            elif kind in ("∑", "∏"):
                fname = "summe" if kind == "∑" else "produkt"
                i = k + 1
                sub, sup, i = parse_scripts(s, i)
                if sub is None and sup is None:
                    if s[i:].lstrip().startswith("("):
                        s = s[:k] + fname + s[i:]
                        continue
                    raise ValueError("%s braucht Grenzen, z. B.  %s_{k=1}^{n} k²" % (kind, kind))
                if sub is None or sup is None or "=" not in sub:
                    raise ValueError("Schreibweise:  %s_{k=1}^{n} Term" % kind)
                var, lo = sub.split("=", 1)
                term, j = take_term(s, i)
                if not term:
                    raise ValueError("Nach %s fehlt der Term." % kind)
                s = s[:k] + "%s(%s;%s;%s;%s)" % (fname, self._sym_ops(term), var.strip(),
                                                self._sym_ops(lo), self._sym_ops(sup)) + s[j:]
            elif kind == "lim":
                m = LIM_RE.search(s)
                sub, sup, i = parse_scripts(s, m.end())
                parts = re.split(r"→|->", sub or "", maxsplit=1)
                if sub is None or len(parts) != 2:
                    raise ValueError("Schreibweise:  lim_{x→a} Ausdruck")
                var, pt = parts[0].strip(), parts[1].strip()
                pt = re.sub(r"\s*\^\s*\{?([+-])\}?\s*$", r"\1", pt)
                fname = "limes"
                if pt.endswith("+") and len(pt) > 1:
                    fname, pt = "limes_plus", pt[:-1]
                elif pt.endswith("-") and len(pt) > 1:
                    fname, pt = "limes_minus", pt[:-1]
                term, j = take_term(s, i)
                if not term:
                    raise ValueError("Nach lim fehlt der Ausdruck.")
                s = s[:m.start()] + "%s(%s;%s;%s)" % (fname, self._sym_ops(term), var, self._sym_ops(pt)) + s[j:]
            else:
                m = DER_RE.search(s)
                n = int(m.group(1) or m.group(3) or 1)
                term, j = take_term(s, m.end())
                if not term:
                    raise ValueError("Nach d/dx fehlt der Ausdruck.")
                s = s[:m.start()] + "ableitung(%s;%s;%d)" % (self._sym_ops(term), m.group(2), n) + s[j:]
        return s

    def symbolize(self, s):
        s = SUP_RE.sub(lambda m: "^{" + m.group(0).translate(SUPT) + "}", s)
        s = SUB_RE.sub(lambda m: "_{" + m.group(0).translate(SUBT) + "}", s)
        for ch, n in (("∛", 3), ("∜", 4)):
            while ch in s:
                k = s.index(ch)
                op, j = take_operand(s, k + 1)
                if op is None:
                    raise ValueError("Nach %s fehlt eine Zahl, ein Name oder eine Klammer." % ch)
                s = s[:k] + "wurzel(%s;%d)" % (op, n) + s[j:]
        if "|" in s and s.count("|") % 2 == 0:
            out, opened = [], False
            for c in s:
                if c == "|":
                    out.append(")" if opened else "betrag(")
                    opened = not opened
                else:
                    out.append(c)
            s = "".join(out)
        s = self._sym_ops(s)
        for _ in range(8):
            t = re.sub(r"\^\{([^{}]*)\}", r"^(\1)", s)
            if t == s:
                break
            s = t
        s = re.sub(r"_\{([^{}]*)\}", lambda m: "_" + re.sub(r"\W", "", m.group(1)), s)
        if "□" in s:
            raise ValueError("Bitte alle Platzhalter □ ausfüllen.")
        return s

    def prepare(self, s, dec_rational=True):
        s = self.symbolize(s.strip())
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
        if dec_rational:
            s = re.sub(r"(?<![\w.])\d+\.\d+(?![\w.])", dec, s)
        return s

    def _parse(self, code, ns, evaluate=True, gl=None):
        ns = dict(ns)
        for m in re.finditer(r"(?<![\w.])([^\W\d_]\w*)\s*\(", code):
            n = m.group(1)
            if n in ns or n in GLOBALS:
                continue
            if len(n) == 1 and n not in "fgyuvwhFGHYUVW":
                continue
            ns[n] = sp.Function(n)
        return parse_expr(code, local_dict=ns, global_dict=gl or GLOBALS,
                          transformations=TRANSFORMS, evaluate=evaluate)

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
        if isinstance(f, Out):
            f = f.value
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
            def run(ee, xx):
                return sp.integrate(ee, (xx, lim[0], lim[1])) if lim else sp.integrate(ee, xx)
            r = run(e, x)
            if r.has(sp.Integral) and not x.is_real:
                try:                      # |x|, √(x²) … gelingen oft mit reeller Variable
                    xr = sp.Symbol(x.name, real=True)
                    r2 = run(e.subs(x, xr), xr)
                    if not r2.has(sp.Integral):
                        r = r2.subs(xr, x) if not lim else r2
                except Exception:
                    pass
            return r if lim else Out(r, "  + C")
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

    # ───────────── LaTeX-Ausgabe & Formel-Vorschau ─────────────
    def _safe(self, fn):
        try:
            return fn()
        except Exception:
            return None

    def tex_val(self, v):
        if isinstance(v, sp.Float):
            return self.fr(v)
        return sp.latex(v, **LATEX_OPTS)

    @staticmethod
    def _arr(lines):
        return lines[0] if len(lines) == 1 else r"\begin{array}{l}" + r"\\".join(lines) + r"\end{array}"

    def render_tex(self, v):
        note = ""
        if isinstance(v, Out):
            note, v = v.note, v.value
        if isinstance(v, Raw) or v is None:
            return None
        if isinstance(v, (bool, BooleanAtom)):
            return r"\text{Wahr}" if bool(v) else r"\text{Falsch}"
        if isinstance(v, Sol):
            if not v:
                return r"\text{Keine Lösung}"
            lines = []
            for idx, d in enumerate(v, 1):
                items = list(d.items())
                if len(items) == 1 and len(v) > 1:
                    k, val = items[0]
                    lines.append("%s_{%d} = %s" % (sp.latex(k), idx, self.tex_val(val)))
                else:
                    lines.append(r",\;".join("%s = %s" % (sp.latex(k), self.tex_val(val)) for k, val in items))
            return self._arr(lines)
        if isinstance(v, (list, tuple, set, frozenset, sp.Tuple)):
            items = list(v)
            if not items:
                return r"\varnothing"
            return self._arr([r"%d)\;\;%s" % (n, self.tex_val(sp.sympify(it))) for n, it in enumerate(items, 1)])
        v = sp.sympify(v)
        if v is sp.zoo:
            return r"\text{nicht definiert}"
        t = self.tex_val(v)
        if note.strip() == "+ C":
            t += " + C"
        return t

    GL_PREVIEW = dict(GLOBALS, factorial=lambda n: sp.factorial(n, evaluate=False), Add=sp.Add, Mul=sp.Mul,
                      Pow=sp.Pow, Gt=sp.Gt, Lt=sp.Lt, Ge=sp.Ge, Le=sp.Le, Ne=sp.Ne, Mod=sp.Mod)

    def _pns(self):
        ns = {k: v for k, v in self._ns().items() if k not in self.vars and k not in self.funcs and k != "ans"}
        S = self

        def A(names, f):
            for n in names.split():
                ns[n] = f

        def integ(f, *a):
            f = sp.sympify(f)
            if len(a) == 0:
                return sp.Integral(f, S._var(f))
            if len(a) == 1:
                return sp.Integral(f, a[0])
            if len(a) == 2:
                return sp.Integral(f, (S._var(f), a[0], a[1]))
            return sp.Integral(f, (a[0], a[1], a[2]))

        def deriv(f, x=None, n=1):
            f = sp.sympify(f)
            x = S._var(f, x)
            return sp.Derivative(f, (x, int(n))) if int(n) > 1 else sp.Derivative(f, x)

        def sm(*a):
            if len(a) == 4 and isinstance(a[1], sp.Symbol):
                return sp.Sum(a[0], (a[1], a[2], a[3]))
            return sp.Add(*S._flat(a), evaluate=False)

        def pd(*a):
            if len(a) == 4 and isinstance(a[1], sp.Symbol):
                return sp.Product(a[0], (a[1], a[2], a[3]))
            return sp.Mul(*S._flat(a), evaluate=False)

        A("integral integrate", integ)
        A("ableitung diff abl", deriv)
        A("summe sum", sm)
        A("produkt product", pd)
        A("limes grenzwert lim", lambda f, x, p, d="+-": sp.Limit(f, x, p, d))
        A("limes_plus grenzwert_rechts", lambda f, x, p: sp.Limit(f, x, p, "+"))
        A("limes_minus grenzwert_links", lambda f, x, p: sp.Limit(f, x, p, "-"))
        A("wurzel sqrt", lambda x, n=2: sp.sqrt(x, evaluate=False) if n == 2 else sp.root(x, n, evaluate=False))
        A("betrag abs", lambda x: sp.Abs(x, evaluate=False))
        A("fak fakultaet fakultät", lambda n: sp.factorial(n, evaluate=False))
        for n, f in (("sin", sp.sin), ("cos", sp.cos), ("tan", sp.tan), ("cot", sp.cot), ("sec", sp.sec),
                     ("csc", sp.csc), ("asin arcsin", sp.asin), ("acos arccos", sp.acos),
                     ("atan arctan", sp.atan), ("acot arccot", sp.acot)):
            A(n, f)
        A("ln", sp.log)
        A("lg ld log", None)
        for n in ("lg", "ld", "log"):
            ns[n] = sp.Function(n)
        ns["DEGSYM"] = sp.Symbol(r"{}^{\circ}")
        return ns

    def preview_tex(self, raw):
        try:
            return self._preview_tex(raw)
        except Exception:
            return None

    def _preview_tex(self, raw):
        raw = raw.strip().replace(":=", "=")
        if not raw or "□" in raw:
            return None
        raw = raw.replace("°", "*DEGSYM")
        s = self.prepare(raw, dec_rational=False)
        if s.count("(") != s.count(")"):
            return None
        ns = self._pns()
        if any(find_top_eq(p) >= 0 for p in split_top(s, ",")):
            v = self._parse("[" + conv_args(s) + "]", ns, evaluate=False, gl=self.GL_PREVIEW)
            items = list(v)
        else:
            v = self._parse(conv_group(s), ns, evaluate=False, gl=self.GL_PREVIEW)
            items = [v]
        out = []
        for it in items:
            if isinstance(it, (bool, BooleanAtom)) or it is None:
                return None
            out.append(sp.latex(it, **LATEX_OPTS))
        return self._arr(out)

    # ───────────── Graph-Analyse (Quantumator-Graph) ─────────────
    GP_CMD = re.compile(r"^\s*(kreis|circle|strecke|segment|gerade|line|polygon|vieleck|flaeche|fläche|area)"
                        r"\s*\((.*)\)\s*$", re.I)
    GP_LABEL = re.compile(r"^\s*([^\W\d]\w*)\s*(?::=|=)\s*(\(.*\))\s*$")
    GP_RANGE = re.compile(r"^(.*?)[,;]?\s*\bt\s*(?:=|in)\s*\[?\s*(.+?)\s*\.\.\s*(.+?)\]?\s*$")
    GJS_FUNCS = {n: n for n in ("gamma", "erf", "erfc", "factorial", "Heaviside", "LambertW", "loggamma",
                                "rroot", "zeta", "besselj", "bessely", "Ei", "Si", "Ci", "digamma",
                                "beta", "binomial", "sinc")}

    @staticmethod
    def _gmsg(ex):
        if isinstance(ex, (SyntaxError, TokenError)):
            return "Syntaxfehler – Eingabe prüfen."
        if isinstance(ex, ZeroDivisionError):
            return "Division durch Null."
        if isinstance(ex, TypeError):
            return "Falsche Argumente."
        return str(ex) or type(ex).__name__

    @staticmethod
    def _tuple_parts(s):
        s = s.strip()
        if s.startswith("(") and s.endswith(")"):
            try:
                if match_close(s, 0) == len(s) - 1:
                    parts = split_top(s[1:-1], ",")
                    if len(parts) >= 2:
                        return [p.strip() for p in parts]
            except ValueError:
                pass
        return None

    @staticmethod
    def _find_rel(s):
        depth, q = 0, None
        for i, c in enumerate(s):
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
            elif depth == 0 and c in "<>":
                if s[i:i + 2] in ("<=", ">="):
                    return i, s[i:i + 2]
                return i, c
        return -1, ""

    def graph_batch(self, entries):
        old = self.deg
        self.deg = False                      # Graphen immer im Bogenmaß
        ns = self._ns()
        for k in list(self.vars):             # Rechner-Variablen stören die Schieberegler nicht
            ns.pop(k, None)
        G = {"ns": ns, "pts": {}}
        out = []
        try:
            for text in entries:
                try:
                    r = self._gp(str(text), G)
                    if r.get("kind") not in ("err", "empty"):
                        r["tex"] = self.preview_tex(str(text))
                    out.append(r)
                except Exception as ex:
                    out.append({"kind": "err", "msg": self._gmsg(ex)})
        finally:
            self.deg = old
        return out

    def _pe(self, s, G):
        s = s.strip()
        if s.count("(") != s.count(")"):
            raise ValueError("Die Klammern passen nicht zusammen.")
        v = self._parse(conv_group(s), G["ns"])
        if isinstance(v, Out):
            v = v.value
        if isinstance(v, UserFunc):
            if len(v.params) != 1:
                raise ValueError("Funktion mit mehreren Variablen kann nicht gezeichnet werden.")
            v = v.expr.subs(v.params[0], sp.Symbol("x"))
        if isinstance(v, (Raw, Sol, list, tuple, set, sp.Tuple, sp.MatrixBase)) or v is None:
            raise ValueError("Dieses Ergebnis kann nicht gezeichnet werden.")
        return sp.sympify(v)

    def _pt(self, arg, G):
        a = arg.strip()
        if a in G["pts"]:
            return G["pts"][a]
        parts = self._tuple_parts(a)
        if not parts or len(parts) != 2:
            raise ValueError("Punkt erwartet, z. B. (1; 2) oder ein benannter Punkt A.")
        return self._pe(parts[0], G), self._pe(parts[1], G)

    def _js(self, e, params):
        e = sp.sympify(e)
        ren = {}
        for sy in e.free_symbols:
            if sy.name not in ("x", "y", "t"):
                params.add(sy.name)
                ren[sy] = sp.Symbol("P." + sy.name)
        e = e.xreplace(ren)
        if e.has(sp.I):
            raise ValueError("Komplexe Werte lassen sich nicht zeichnen.")
        if e.has(sp.zoo, sp.nan):
            raise ValueError("Nicht definierter Ausdruck.")
        e = e.replace(lambda q: q.is_Pow and q.exp.is_Rational and q.exp.q > 3 and q.exp.q % 2 == 1,
                      lambda q: sp.Function("rroot")(q.base, q.exp.q) ** q.exp.p)
        code = sp.jscode(e, user_functions=self.GJS_FUNCS)
        if "Not supported" in code or "//" in code:
            raise ValueError("Ausdruck wird im Graph nicht unterstützt.")
        return code.replace("\n", " ")

    def _fin(self, kind, params, **codes):
        d = {"kind": kind, "params": sorted(params)}
        d.update(codes)
        return d

    def _gfunc(self, e, params):
        e = sp.sympify(e)
        names = {sy.name for sy in e.free_symbols}
        if "t" in names:
            raise ValueError("t gilt nur für Kurven  (x(t); y(t)).  Hier bitte x verwenden.")
        if "y" in names:
            return self._fin("implicit", params, js=self._js(e, params))
        return self._fin("func", params, js=self._js(e, params))

    def _gp(self, raw, G):
        raw = raw.strip()
        if not raw:
            return {"kind": "empty"}
        raw = raw.replace("θ", "t")
        raw = re.sub(r"([A-Za-z_]\w*)('+)\(\s*([A-Za-z_]\w*)\s*\)",
                     lambda m: "ableitung(%s(%s);%s;%d)" % (m.group(1), m.group(3), m.group(3), len(m.group(2))), raw)
        if self.decimal_comma:   # "(1,2)" ist ein Punkt, kein Dezimalbruch
            raw = re.sub(r"^(\s*(?:[^\W\d]\w*\s*(?::=|=)\s*)?)\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)\s*$",
                         r"\1(\2;\3)", raw)
        params, rng = set(), None
        m = self.GP_RANGE.match(raw)
        if m and ".." in raw:
            raw, rng = m.group(1).strip(), (m.group(2), m.group(3))
        s = self.prepare(raw)
        if s.count("(") != s.count(")"):
            raise ValueError("Die Klammern passen nicht zusammen.")
        name = None
        ml = self.GP_LABEL.match(s)
        if ml and self._tuple_parts(ml.group(2)):
            name, s = ml.group(1), ml.group(2)
        lo_js, hi_js = "0", "2*Math.PI"
        if rng:
            lo_js = self._js(self._pe(self.prepare(rng[0]), G), params)
            hi_js = self._js(self._pe(self.prepare(rng[1]), G), params)

        mc = self.GP_CMD.match(s)
        if mc:
            return self._gcmd(mc.group(1).lower(), split_top(mc.group(2), ","), G, params)

        parts = self._tuple_parts(s)
        if parts:
            if len(parts) != 2:
                raise ValueError("Nur 2D: (x; y).")
            ex, ey = self._pe(parts[0], G), self._pe(parts[1], G)
            if sp.Symbol("t") in (ex.free_symbols | ey.free_symbols) or rng:
                return self._fin("param", params, jx=self._js(ex, params), jy=self._js(ey, params),
                                 lo=lo_js, hi=hi_js)
            if name:
                G["pts"][name] = (ex, ey)
            return self._fin("point", params, jx=self._js(ex, params), jy=self._js(ey, params), label=name or "")

        x = sp.Symbol("x")
        i = find_top_eq(s)
        if i >= 0:
            L, R = s[:i].strip(), s[i + 1:].strip()
            mf = re.match(r"^([^\W\d]\w*)\s*\(\s*([^()]*?)\s*\)$", L)
            if mf and mf.group(1) not in self.builtin:
                names = [q.strip() for q in mf.group(2).split(",") if q.strip()]
                ns2 = {k: v for k, v in G["ns"].items() if k not in names}
                body = self._parse(conv_group(R), ns2)
                if isinstance(body, Out):
                    body = body.value
                body = sp.sympify(body)
                G["ns"][mf.group(1)] = UserFunc(mf.group(1), [sp.Symbol(n) for n in names], body)
                if len(names) == 1:
                    return self._gfunc(body.subs(sp.Symbol(names[0]), x), params)
                return {"kind": "def", "name": mf.group(1), "params": []}
            if re.match(r"^[^\W\d]\w*$", L) and L not in ("x", "y", "r", "z", "t") and L not in self.builtin:
                e = self._pe(R, G)
                if not e.free_symbols and e.is_number:
                    return {"kind": "slider", "name": L, "value": float(sp.N(e)), "params": []}
                G["ns"][L] = e
                return {"kind": "def", "name": L, "params": []}
            if L == "y":
                return self._gfunc(self._pe(R, G), params)
            if R == "y":
                return self._gfunc(self._pe(L, G), params)
            if L == "x":
                e = self._pe(R, G)
                if "x" not in {q.name for q in e.free_symbols}:
                    return self._fin("vline", params, js=self._js(e, params))
            if L == "r":
                e = self._pe(R, G)
                return self._fin("polar", params, js=self._js(e, params), lo=lo_js, hi=hi_js)
            if L == "z":
                e = self._pe(R, G)
                return self._fin("surface", params, js=self._js(e, params))
            F = self._pe(L, G) - self._pe(R, G)
            return self._fin("implicit", params, js=self._js(F, params))

        j, op = self._find_rel(s)
        if j >= 0:
            F = self._pe(s[:j], G) - self._pe(s[j + len(op):], G)
            return self._fin("ineq", params, js=self._js(F, params), op=op)

        e = self._pe(s, G)
        return self._gfunc(e, params)

    def _gcmd(self, cmd, args, G, params):
        x, y = sp.Symbol("x"), sp.Symbol("y")
        if cmd in ("kreis", "circle"):
            if len(args) != 2:
                raise ValueError("kreis(M; r)  –  z. B.  kreis((1;2); 3)")
            cx, cy = self._pt(args[0], G)
            r = self._pe(args[1], G)
            return self._fin("implicit", params, js=self._js((x - cx) ** 2 + (y - cy) ** 2 - r ** 2, params))
        if cmd in ("strecke", "segment", "gerade", "line"):
            if len(args) != 2:
                raise ValueError("%s(A; B)  –  zwei Punkte angeben" % cmd)
            (ax, ay), (bx, by) = self._pt(args[0], G), self._pt(args[1], G)
            kind = "segment" if cmd in ("strecke", "segment") else "line"
            return self._fin(kind, params, jx1=self._js(ax, params), jy1=self._js(ay, params),
                             jx2=self._js(bx, params), jy2=self._js(by, params))
        if cmd in ("polygon", "vieleck"):
            if len(args) < 3:
                raise ValueError("polygon(A; B; C; …)  –  mindestens 3 Punkte")
            pts = []
            for a in args:
                px, py = self._pt(a, G)
                pts.append([self._js(px, params), self._js(py, params)])
            return self._fin("polygon", params, pts=pts)
        if len(args) != 3:
            raise ValueError("flaeche(f; a; b)  –  z. B.  flaeche(x^2; 0; 2)")
        f = self._pe(args[0], G)
        return self._fin("area", params, js=self._js(f, params),
                         lo=self._js(self._pe(args[1], G), params), hi=self._js(self._pe(args[2], G), params))

    # ───────────── Hauptauswertung ─────────────
    CALC_RE = re.compile(
        r"(?<![\w.])(ableitung|diff|abl|integral|integrate|limes|grenzwert|lim|limes_plus|limes_minus|"
        r"grenzwert_rechts|grenzwert_links|reihe|series|taylor|dgl|dsolve|laplace|invlaplace|"
        r"gradient|nint|extrema|wendepunkte|tangente)\s*\(")

    def evaluate(self, text):
        raw = text.strip()
        old_deg = self.deg
        calc = bool(self.CALC_RE.search(raw) or re.search(
            r"∫|lim\s*_|(?<![A-Za-z0-9_])[d∂]\s*(?:\^\s*\{?\s*\d+\s*\}?|[²³])?\s*/\s*[d∂]", raw))
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
                    "extra": [], "value": None, "itex": self.preview_tex(raw),
                    "tex": self._safe(lambda: "%s\\left(%s\\right) = %s" % (
                        name, ",\\,".join(names), sp.latex(sp.sympify(body), **LATEX_OPTS)))}

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
            vt = self._safe(lambda: self.render_tex(self.vars[name]))
            return {"kind": "assign", "input": raw, "def": raw,
                    "main": "%s = %s" % (name, main) if "\n" not in main else "%s =\n%s" % (name, main),
                    "extra": extra, "value": self.vars[name], "itex": self.preview_tex(raw),
                    "tex": ("%s = %s" % (name, vt)) if vt else None}

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
        return {"kind": "ok", "input": raw, "main": main, "extra": extra, "value": newans,
                "tex": self._safe(lambda: self.render_tex(v)), "itex": self.preview_tex(raw)}


