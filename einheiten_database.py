# -*- coding: utf-8 -*-
"""
Quantumator – Einheiten-Datenbank (offline, reine Daten).

Jede Kategorie hat "subs" (Untergruppen, meist nur eine). Eine Einheit ist
    {"id", "n": Name, "s": Symbol, "f": Faktor zur Basiseinheit}
oder – bei nichtlinearen Umrechnungen – statt "f" ein Feld "k" (Formel-Kennung, siehe JS: NL),
bzw. "radix" für Zahlensysteme. Rechnung im Programm: immer double, Kürzung nur bei der Anzeige.
"""

PREFIXES = [
    ("q", "Quekto", -30), ("r", "Ronto", -27), ("y", "Yokto", -24), ("z", "Zepto", -21),
    ("a", "Atto", -18), ("f", "Femto", -15), ("p", "Piko", -12), ("n", "Nano", -9),
    ("µ", "Mikro", -6), ("m", "Milli", -3), ("c", "Zenti", -2), ("d", "Dezi", -1),
    ("", "", 0), ("da", "Deka", 1), ("h", "Hekto", 2), ("k", "Kilo", 3), ("M", "Mega", 6),
    ("G", "Giga", 9), ("T", "Tera", 12), ("P", "Peta", 15), ("E", "Exa", 18),
    ("Z", "Zetta", 21), ("Y", "Yotta", 24), ("R", "Ronna", 27), ("Q", "Quetta", 30),
]
STEP3 = {-30, -27, -24, -21, -18, -15, -12, -9, -6, -3, 0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30}


def U(id_, n, s, f=None, **kw):
    d = {"id": id_, "n": n, "s": s}
    if f is not None:
        d["f"] = f
    d.update(kw)
    return d


def si(base_id, base_name, base_sym, unit_factor=1.0, only=None):
    """SI-Präfixe von Quekto bis Quetta. Faktor relativ zur Basiseinheit der Kategorie."""
    out = []
    for sym, name, exp in PREFIXES:
        if only is not None and exp not in only:
            continue
        uname = base_name if not name else name + base_name.lower()
        out.append(U("%s%+d" % (base_id, exp), uname, sym + base_sym, unit_factor * 10.0 ** exp))
    return out


def sub(name, units, default):
    return {"name": name, "units": units, "def": default}


def cat(name, badge, subs):
    return {"name": name, "badge": badge, "subs": subs}


# ───────────────────────── LÄNGE (34) ─────────────────────────
LAENGE = si("m", "Meter", "m") + [
    U("ang", "Ångström", "Å", 1e-10),
    U("in", "Zoll (Inch)", "in", 0.0254),
    U("ft", "Fuß (Foot)", "ft", 0.3048),
    U("yd", "Yard", "yd", 0.9144),
    U("mi", "Meile (Statute Mile)", "mi", 1609.344),
    U("nmi", "Seemeile", "sm", 1852.0),
    U("au", "Astronomische Einheit", "AE", 149597870700.0),
    U("ly", "Lichtjahr", "ly", 9460730472580800.0),
    U("pc", "Parsec", "pc", 3.0856775814913673e16),
]

FLAECHE = [
    U("um2", "Quadratmikrometer", "µm²", 1e-12), U("mm2", "Quadratmillimeter", "mm²", 1e-6),
    U("cm2", "Quadratzentimeter", "cm²", 1e-4), U("dm2", "Quadratdezimeter", "dm²", 1e-2),
    U("m2", "Quadratmeter", "m²", 1.0), U("a", "Ar", "a", 100.0), U("ha", "Hektar", "ha", 1e4),
    U("km2", "Quadratkilometer", "km²", 1e6), U("in2", "Quadratzoll", "in²", 0.00064516),
    U("ft2", "Quadratfuß", "ft²", 0.09290304), U("yd2", "Quadratyard", "yd²", 0.83612736),
    U("ac", "Acre", "ac", 4046.8564224), U("mi2", "Quadratmeile", "mi²", 2589988.110336),
]

VOLUMEN = [  # Basis: Liter
    U("mm3", "Kubikmillimeter", "mm³", 1e-6), U("ml", "Milliliter", "ml", 1e-3),
    U("cl", "Zentiliter", "cl", 1e-2), U("dl", "Deziliter", "dl", 0.1), U("l", "Liter", "l", 1.0),
    U("hl", "Hektoliter", "hl", 100.0), U("cm3", "Kubikzentimeter", "cm³", 1e-3),
    U("dm3", "Kubikdezimeter", "dm³", 1.0), U("m3", "Kubikmeter", "m³", 1000.0),
    U("km3", "Kubikkilometer", "km³", 1e12), U("tl", "Teelöffel (5 ml)", "TL", 0.005),
    U("el", "Esslöffel (15 ml)", "EL", 0.015), U("tasse", "Tasse (250 ml)", "Tasse", 0.25),
    U("floz", "Fluid Ounce (US)", "fl oz", 0.0295735295625), U("cup", "Cup (US)", "cup", 0.2365882365),
    U("pt", "Pint (US)", "pt", 0.473176473), U("qt", "Quart (US)", "qt", 0.946352946),
    U("gal", "Gallone (US)", "gal", 3.785411784), U("galuk", "Gallone (UK)", "gal UK", 4.54609),
    U("ptuk", "Pint (UK)", "pt UK", 0.56826125), U("in3", "Kubikzoll", "in³", 0.016387064),
    U("ft3", "Kubikfuß", "ft³", 28.316846592), U("bbl", "Barrel (Öl)", "bbl", 158.987294928),
]

MASSE = si("g", "Gramm", "g") + [  # Basis: Gramm
    U("t", "Tonne", "t", 1e6), U("ztr", "Zentner (50 kg)", "Ztr", 50000.0),
    U("dz", "Doppelzentner", "dz", 100000.0), U("ct", "Karat", "ct", 0.2),
    U("gr", "Grain", "gr", 0.06479891), U("oz", "Unze (Ounce)", "oz", 28.349523125),
    U("lb", "Pfund (Pound)", "lb", 453.59237), U("st", "Stone", "st", 6350.29318),
    U("ston", "Short Ton (US)", "sh tn", 907184.74), U("lton", "Long Ton (UK)", "lg tn", 1016046.9088),
    U("u", "Atomare Masseneinheit", "u", 1.66053906660e-24),
    U("mearth", "Erdmasse", "M⊕", 5.9722e27), U("msun", "Sonnenmasse", "M☉", 1.98847e33),
]

ZEIT = si("s", "Sekunde", "s", only=STEP3) + [  # Basis: Sekunde
    U("min", "Minute", "min", 60.0), U("h", "Stunde", "h", 3600.0), U("d", "Tag", "d", 86400.0),
    U("wk", "Woche", "Wo", 604800.0), U("mon", "Monat (Ø 30,4369 d)", "Mon", 2629746.0),
    U("yr", "Jahr (365,2425 d)", "a", 31556952.0), U("dec", "Jahrzehnt", "10 a", 315569520.0),
    U("cen", "Jahrhundert", "Jh", 3155695200.0), U("mil", "Jahrtausend", "Jt", 31556952000.0),
    U("tp", "Planck-Zeit", "tₚ", 5.391247e-44),
]

TEMPERATUR = [  # Basis: °C (Formeln "k": siehe JS)
    U("c", "Celsius", "°C", k="c"), U("f", "Fahrenheit", "°F", k="f"),
    U("k", "Kelvin", "K", k="k"), U("r", "Rankine", "°Ra", k="r"),
]

GESCHW = [  # Basis: m/s
    U("ms", "Meter pro Sekunde", "m/s", 1.0), U("kmh", "Kilometer pro Stunde", "km/h", 1.0 / 3.6),
    U("mph", "Meilen pro Stunde", "mph", 0.44704), U("kn", "Knoten", "kn", 1852.0 / 3600.0),
    U("mach", "Mach (340,29 m/s)", "Ma", 340.29), U("c", "Lichtgeschwindigkeit", "c", 299792458.0),
    U("fts", "Fuß pro Sekunde", "ft/s", 0.3048), U("cms", "Zentimeter pro Sekunde", "cm/s", 0.01),
    U("kms", "Kilometer pro Sekunde", "km/s", 1000.0),
]

DRUCK = [  # Basis: Pascal
    U("pa", "Pascal", "Pa", 1.0), U("hpa", "Hektopascal", "hPa", 100.0), U("kpa", "Kilopascal", "kPa", 1e3),
    U("mpa", "Megapascal", "MPa", 1e6), U("gpa", "Gigapascal", "GPa", 1e9), U("bar", "Bar", "bar", 1e5),
    U("mbar", "Millibar", "mbar", 100.0), U("atm", "Physikalische Atmosphäre", "atm", 101325.0),
    U("at", "Technische Atmosphäre", "at", 98066.5), U("torr", "Torr", "Torr", 101325.0 / 760.0),
    U("mmhg", "Millimeter Quecksilbersäule", "mmHg", 133.322387415),
    U("inhg", "Zoll Quecksilbersäule", "inHg", 3386.389), U("psi", "Pound per Square Inch", "psi", 6894.757293168),
    U("ksi", "Kilopound per Square Inch", "ksi", 6894757.293168),
]

ENERGIE = [  # Basis: Joule
    U("j", "Joule", "J", 1.0), U("kj", "Kilojoule", "kJ", 1e3), U("mj", "Megajoule", "MJ", 1e6),
    U("gj", "Gigajoule", "GJ", 1e9), U("wh", "Wattstunde", "Wh", 3600.0), U("kwh", "Kilowattstunde", "kWh", 3.6e6),
    U("mwh", "Megawattstunde", "MWh", 3.6e9), U("cal", "Kalorie (thermochemisch)", "cal", 4.184),
    U("kcal", "Kilokalorie", "kcal", 4184.0), U("btu", "British Thermal Unit (IT)", "BTU", 1055.05585262),
    U("ev", "Elektronenvolt", "eV", 1.602176634e-19), U("erg", "Erg", "erg", 1e-7),
    U("ftlbf", "Fuß-Pfund-Kraft", "ft·lbf", 1.3558179483314004),
]

LEISTUNG = [  # Basis: Watt
    U("uw", "Mikrowatt", "µW", 1e-6), U("mw", "Milliwatt", "mW", 1e-3), U("w", "Watt", "W", 1.0),
    U("kw", "Kilowatt", "kW", 1e3), U("mgw", "Megawatt", "MW", 1e6), U("gw", "Gigawatt", "GW", 1e9),
    U("ps", "Pferdestärke (metrisch)", "PS", 735.49875), U("hp", "Horsepower (mechanisch)", "hp", 745.69987158227022),
    U("btuh", "BTU pro Stunde", "BTU/h", 0.29307107), U("kcalh", "Kilokalorie pro Stunde", "kcal/h", 1.163),
    U("ftlbfs", "Fuß-Pfund-Kraft pro Sekunde", "ft·lbf/s", 1.3558179483314004),
]

BITS = 1.0
DATEN = [  # Basis: Bit
    U("bit", "Bit", "bit", 1.0), U("kbit", "Kilobit", "kbit", 1e3), U("mbit", "Megabit", "Mbit", 1e6),
    U("gbit", "Gigabit", "Gbit", 1e9), U("B", "Byte", "B", 8.0),
] + [U("B%+d" % e, n + "byte", s + "B", 8.0 * 10.0 ** e)
     for (s, n, e) in (("k", "Kilo", 3), ("M", "Mega", 6), ("G", "Giga", 9), ("T", "Tera", 12), ("P", "Peta", 15),
                       ("E", "Exa", 18), ("Z", "Zetta", 21), ("Y", "Yotta", 24), ("R", "Ronna", 27), ("Q", "Quetta", 30))
     ] + [U("iB%d" % k, n + "byte", s + "iB", 8.0 * 2.0 ** (10 * k))
          for (s, n, k) in (("Ki", "Kibi", 1), ("Mi", "Mebi", 2), ("Gi", "Gibi", 3), ("Ti", "Tebi", 4), ("Pi", "Pebi", 5),
                            ("Ei", "Exbi", 6), ("Zi", "Zebi", 7), ("Yi", "Yobi", 8), ("Ri", "Robi", 9), ("Qi", "Quebi", 10))]

DATENRATE = [  # Basis: Bit/s
    U("bps", "Bit pro Sekunde", "bit/s", 1.0), U("kbps", "Kilobit pro Sekunde", "kbit/s", 1e3),
    U("mbps", "Megabit pro Sekunde", "Mbit/s", 1e6), U("gbps", "Gigabit pro Sekunde", "Gbit/s", 1e9),
    U("tbps", "Terabit pro Sekunde", "Tbit/s", 1e12), U("Bps", "Byte pro Sekunde", "B/s", 8.0),
    U("kBps", "Kilobyte pro Sekunde", "kB/s", 8e3), U("MBps", "Megabyte pro Sekunde", "MB/s", 8e6),
    U("GBps", "Gigabyte pro Sekunde", "GB/s", 8e9), U("TBps", "Terabyte pro Sekunde", "TB/s", 8e12),
    U("KiBps", "Kibibyte pro Sekunde", "KiB/s", 8.0 * 1024), U("MiBps", "Mebibyte pro Sekunde", "MiB/s", 8.0 * 1024 ** 2),
    U("GiBps", "Gibibyte pro Sekunde", "GiB/s", 8.0 * 1024 ** 3),
]

WINKEL = [  # Basis: Grad
    U("deg", "Grad", "°", 1.0), U("rad", "Radiant", "rad", 57.29577951308232),
    U("mrad", "Milliradiant", "mrad", 0.05729577951308232), U("gon", "Gon (Neugrad)", "gon", 0.9),
    U("arcmin", "Bogenminute", "′", 1.0 / 60.0), U("arcsec", "Bogensekunde", "″", 1.0 / 3600.0),
    U("turn", "Umdrehung", "U", 360.0),
]

ELEKTRISCH = [
    sub("Spannung", [U("uv", "Mikrovolt", "µV", 1e-6), U("mv", "Millivolt", "mV", 1e-3), U("v", "Volt", "V", 1.0),
                     U("kv", "Kilovolt", "kV", 1e3), U("mgv", "Megavolt", "MV", 1e6)], ["v", "mv"]),
    sub("Strom", [U("na", "Nanoampere", "nA", 1e-9), U("ua", "Mikroampere", "µA", 1e-6), U("ma", "Milliampere", "mA", 1e-3),
                  U("a", "Ampere", "A", 1.0), U("ka", "Kiloampere", "kA", 1e3)], ["a", "ma"]),
    sub("Widerstand", [U("uo", "Mikroohm", "µΩ", 1e-6), U("mo", "Milliohm", "mΩ", 1e-3), U("o", "Ohm", "Ω", 1.0),
                       U("ko", "Kiloohm", "kΩ", 1e3), U("mgo", "Megaohm", "MΩ", 1e6), U("go", "Gigaohm", "GΩ", 1e9)], ["o", "ko"]),
    sub("Ladung", [U("pc", "Pikocoulomb", "pC", 1e-12), U("nc", "Nanocoulomb", "nC", 1e-9), U("uc", "Mikrocoulomb", "µC", 1e-6),
                   U("mc", "Millicoulomb", "mC", 1e-3), U("c", "Coulomb", "C", 1.0), U("kc", "Kilocoulomb", "kC", 1e3),
                   U("mah", "Milliamperestunde", "mAh", 3.6), U("ah", "Amperestunde", "Ah", 3600.0),
                   U("e", "Elementarladung", "e", 1.602176634e-19)], ["ah", "mah"]),
    sub("Kapazität", [U("pf", "Pikofarad", "pF", 1e-12), U("nf", "Nanofarad", "nF", 1e-9), U("uf", "Mikrofarad", "µF", 1e-6),
                      U("mf", "Millifarad", "mF", 1e-3), U("f", "Farad", "F", 1.0)], ["uf", "nf"]),
    sub("Induktivität", [U("nh", "Nanohenry", "nH", 1e-9), U("uh", "Mikrohenry", "µH", 1e-6), U("mh", "Millihenry", "mH", 1e-3),
                         U("h", "Henry", "H", 1.0)], ["mh", "uh"]),
    sub("Frequenz", [U("mhz", "Millihertz", "mHz", 1e-3), U("hz", "Hertz", "Hz", 1.0), U("khz", "Kilohertz", "kHz", 1e3),
                     U("mgz", "Megahertz", "MHz", 1e6), U("ghz", "Gigahertz", "GHz", 1e9), U("thz", "Terahertz", "THz", 1e12),
                     U("rpm", "Umdrehungen pro Minute", "U/min", 1.0 / 60.0)], ["mgz", "khz"]),
]

KRAFTSTOFF = [  # Basis: l/100 km (Kehrwert-Formeln "k")
    U("l100", "Liter pro 100 km", "l/100km", k="l100"), U("kmpl", "Kilometer pro Liter", "km/l", k="kmpl"),
    U("mpgus", "Meilen pro Gallone (US)", "mpg US", k="mpgus"), U("mpguk", "Meilen pro Gallone (UK)", "mpg UK", k="mpguk"),
]

ZAHLEN = [
    U("dec", "Dezimal", "dez", radix=10), U("bin", "Binär", "bin", radix=2),
    U("hex", "Hexadezimal", "hex", radix=16), U("oct", "Oktal", "okt", radix=8),
]

DB = {
    "groups": [
        {"id": "math", "name": "Mathematik & Digital", "cats": ["zahlen", "daten", "datenrate", "winkel"]},
        {"id": "ing", "name": "Ingenieur", "cats": ["druck", "energie", "leistung", "elektrisch"]},
        {"id": "alltag", "name": "Alltag", "cats": ["laenge", "flaeche", "volumen", "masse", "temperatur", "kraftstoff"]},
        {"id": "spezial", "name": "Spezial", "cats": ["zeit", "geschwindigkeit"]},
    ],
    "cats": {
        "laenge": cat("Länge", "m", [sub(None, LAENGE, ["m+0", "ft"])]),
        "flaeche": cat("Fläche", "m²", [sub(None, FLAECHE, ["m2", "ft2"])]),
        "volumen": cat("Volumen", "l", [sub(None, VOLUMEN, ["l", "gal"])]),
        "masse": cat("Masse", "kg", [sub(None, MASSE, ["g+3", "lb"])]),
        "zeit": cat("Zeit", "s", [sub(None, ZEIT, ["h", "min"])]),
        "temperatur": cat("Temperatur", "°C", [sub(None, TEMPERATUR, ["c", "f"])]),
        "geschwindigkeit": cat("Geschwindigkeit", "m/s", [sub(None, GESCHW, ["kmh", "mph"])]),
        "druck": cat("Druck", "Pa", [sub(None, DRUCK, ["bar", "psi"])]),
        "energie": cat("Energie", "J", [sub(None, ENERGIE, ["kwh", "mj"])]),
        "leistung": cat("Leistung", "W", [sub(None, LEISTUNG, ["kw", "ps"])]),
        "daten": cat("Daten", "B", [sub(None, DATEN, ["B+9", "iB3"])]),
        "datenrate": cat("Datenrate", "bit/s", [sub(None, DATENRATE, ["mbps", "MBps"])]),
        "winkel": cat("Winkel", "°", [sub(None, WINKEL, ["deg", "rad"])]),
        "elektrisch": cat("Elektrisch", "V·A", ELEKTRISCH),
        "kraftstoff": cat("Kraftstoff", "l/100", [sub(None, KRAFTSTOFF, ["l100", "mpgus"])]),
        "zahlen": cat("Zahlensysteme", "0x", [sub(None, ZAHLEN, ["dec", "hex"])]),
    },
}


def count(cat_key):
    return sum(len(s["units"]) for s in DB["cats"][cat_key]["subs"])


def validate():
    """Selbsttest: eindeutige IDs, endliche Faktoren, Standardeinheiten vorhanden."""
    problems = []
    seen_cats = set()
    for g in DB["groups"]:
        for c in g["cats"]:
            seen_cats.add(c)
            if c not in DB["cats"]:
                problems.append("Kategorie fehlt: " + c)
    if seen_cats != set(DB["cats"]):
        problems.append("Kategorien ohne Gruppe: %s" % (set(DB["cats"]) - seen_cats))
    for key, c in DB["cats"].items():
        for s in c["subs"]:
            ids = [u["id"] for u in s["units"]]
            if len(ids) != len(set(ids)):
                problems.append("doppelte IDs in " + key)
            for d in s["def"]:
                if d not in ids:
                    problems.append("Standard-ID %s fehlt in %s" % (d, key))
            for u in s["units"]:
                if "f" in u and not (u["f"] > 0 and u["f"] < float("inf")):
                    problems.append("ungültiger Faktor %s/%s" % (key, u["id"]))
                if "f" not in u and "k" not in u and "radix" not in u:
                    problems.append("keine Umrechnung %s/%s" % (key, u["id"]))
    return problems


if __name__ == "__main__":
    print("Probleme:", validate() or "keine")
    for k in DB["cats"]:
        print("%-16s %3d Einheiten" % (DB["cats"][k]["name"], count(k)))
