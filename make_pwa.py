#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quantumator für iPhone & iPad  –  erzeugt die komplett offline-fähige Web-App (PWA) in ./site

    python make_pwa.py            -> baut die App-Dateien (Pyodide muss danach in site/pyodide liegen)
    python make_pwa.py --fetch    -> lädt zusätzlich Pyodide + sympy herunter (benötigt Internet, 1x)

Der Rechenkern (engine.py, sympy) läuft in der Seite selbst (Pyodide/WebAssembly, in einem Web-Worker);
es gibt keinen Server. Nach dem ersten Laden funktioniert alles ohne Internet.
"""
import os
import sys
import json
import hashlib
import shutil
import urllib.request

PYODIDE_VERSION = "0.26.4"
HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
BASE = "https://cdn.jsdelivr.net/pyodide/v%s/full/" % PYODIDE_VERSION

# ───────────────────────── Python-Brücke (läuft in Pyodide) ─────────────────────────
GLUE = r'''
import sys, json
sys.path.insert(0, "/home/pyodide")
import engine as E

ENG = E.Engine()


def vars_snapshot():
    out = []
    for k, v in sorted(ENG.vars.items()):
        out.append({"kind": "v", "name": k, "text": ENG.one_line(v).replace("\n", " ")})
    for k, f in sorted(ENG.funcs.items()):
        out.append({"kind": "f", "name": k, "text": "%s(%s) = %s" % (
            k, ", ".join(p.name for p in f.params), ENG.one_line(f.expr))})
    return out


def qm_api(path, data_json):
    d = json.loads(data_json or "{}")
    try:
        if path == "/api/eval":
            ENG.deg = bool(d.get("deg", True))
            ENG.decimal_comma = bool(d.get("dec", True))
            ENG.digits = max(4, min(120, int(d.get("digits", 15))))
            r = ENG.evaluate(str(d.get("text", "")))
            out = {"kind": r["kind"], "input": r.get("input", ""), "main": r.get("main", ""),
                   "extra": [[a, b] for a, b in r.get("extra", [])], "msg": r.get("msg", ""),
                   "tex": r.get("tex"), "itex": r.get("itex"), "vars": vars_snapshot(),
                   "defs": list(ENG.defs.values())}
        elif path == "/api/preview":
            ENG.decimal_comma = bool(d.get("dec", True))
            out = {"tex": ENG.preview_tex(str(d.get("text", "")))}
        elif path == "/api/gparse":
            ENG.decimal_comma = bool(d.get("dec", True))
            entries = [str(t) for t in d.get("entries", [])][:40]
            out = {"results": ENG.graph_batch(entries)}
        elif path == "/api/state":
            out = {"vars": vars_snapshot()}
        elif path == "/api/restore":
            for x in d.get("defs", []):
                try:
                    ENG.evaluate(x)
                except Exception:
                    pass
            out = {"ok": True}
        else:
            out = {}
    except Exception as ex:
        out = {"kind": "err", "msg": str(ex), "extra": [], "vars": [], "results": [], "tex": None}
    return json.dumps(out, ensure_ascii=False)
'''

# ───────────────────────── Web-Worker ─────────────────────────
WORKER_JS = r'''
let py = null, ready = false;
const send = o => postMessage(o);
async function init(){
  try {
    send({type:'status', text:'Lade Rechenkern …'});
    importScripts('pyodide/pyodide.js');
    py = await loadPyodide({indexURL:'pyodide/'});
    send({type:'status', text:'Lade Mathematik-Bibliothek (sympy) …'});
    await py.loadPackage(['mpmath', 'sympy']);
    send({type:'status', text:'Starte Quantumator …'});
    const eng = await (await fetch('engine.py')).text();
    py.FS.writeFile('/home/pyodide/engine.py', eng);
    py.runPython(await (await fetch('pyglue.py')).text());
    ready = true; send({type:'ready'});
  } catch (e) { send({type:'ready', error:'Rechenkern konnte nicht geladen werden: ' + e}); }
}
onmessage = ev => {
  const m = ev.data;
  if (!ready){ send({id:m.id, result:JSON.stringify({kind:'err', msg:'Rechenkern startet noch …', extra:[], vars:[], results:[], tex:null})}); return; }
  let out;
  try { out = py.globals.get('qm_api')(m.path, JSON.stringify(m.body || {})); }
  catch (e) { out = JSON.stringify({kind:'err', msg:String(e), extra:[], vars:[], results:[], tex:null}); }
  send({id:m.id, result:out});
};
init();
'''

# ───────────────────────── Service-Worker (Offline-Cache) ─────────────────────────
SW_JS = r'''
const CACHE = 'quantumator-__VER__';
const FILES = __FILES__;
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(caches.match(e.request, {ignoreSearch:true}).then(r => r || fetch(e.request)));
});
'''

# ───────────────────────── Brücke Seite <-> Worker (ersetzt den Server) ─────────────────────────
SHIM_JS = r'''
(function(){
  if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
  let w = null, nid = 1, isReady = false, loadErr = null, readyRes = null, readyP = null;
  const pend = new Map();
  const setStatus = t => { const s = document.querySelector('#splash small'); if (s) s.textContent = t; };
  function rawCall(path, body, ms){
    return new Promise(res => {
      const id = nid++; let t = null;
      pend.set(id, r => { clearTimeout(t); res(r); });
      if (ms) t = setTimeout(() => { pend.delete(id); try { w.terminate(); } catch(e){} start();
        res(JSON.stringify({kind:'err', msg:'Zeitüberschreitung (' + Math.round(ms/1000) + ' s): Berechnung abgebrochen, Rechenkern wird neu gestartet.', extra:[], vars:[], results:[], tex:null})); }, ms);
      w.postMessage({id, path, body});
    });
  }
  function start(){
    isReady = false; loadErr = null; readyP = new Promise(r => { readyRes = r; });
    w = new Worker('worker.js');
    w.onmessage = async e => {
      const m = e.data;
      if (m.type === 'status'){ setStatus(m.text); return; }
      if (m.type === 'ready'){
        loadErr = m.error || null;
        if (!loadErr){ try { const defs = JSON.parse(localStorage.getItem('qm_defs') || '[]'); if (defs.length) await rawCall('/api/restore', {defs}, 0); } catch(e){} }
        isReady = true; readyRes(); return;
      }
      const p = pend.get(m.id); if (p){ pend.delete(m.id); p(m.result); }
    };
    w.onerror = ev => { loadErr = 'Worker-Fehler: ' + (ev.message || ''); isReady = true; readyRes(); };
  }
  const _f = window.fetch.bind(window), J = o => ({ok:true, json: async () => o});
  window.fetch = async (url, opts) => {
    if (typeof url === 'string' && url.startsWith('/api/')){
      if (url === '/api/ready') return J({ready:isReady, error:loadErr});
      await readyP;
      if (loadErr) return J(url === '/api/gparse' ? {results:[]} : url === '/api/preview' ? {tex:null} : {kind:'err', msg:loadErr, extra:[], vars:[]});
      const body = opts && opts.body ? JSON.parse(opts.body) : {};
      const txt = await rawCall(url, body, url === '/api/eval' ? 60000 : url === '/api/gparse' ? 30000 : 0);
      let o; try { o = JSON.parse(txt); } catch(e){ o = {kind:'err', msg:'Ungültige Antwort vom Rechenkern', extra:[], vars:[]}; }
      if (url === '/api/eval' && o.defs){ try { localStorage.setItem('qm_defs', JSON.stringify(o.defs)); } catch(e){} }
      return J(o);
    }
    return _f(url, opts);
  };
  start();
})();
'''

HEAD_ADD = '''<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Quantumator">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" href="icon-192.png">
<link rel="manifest" href="manifest.webmanifest">'''

MANIFEST = {
    "name": "Quantumator", "short_name": "Quantumator", "start_url": "./", "scope": "./",
    "display": "standalone", "orientation": "any", "background_color": "#03050A", "theme_color": "#ffffff",
    "lang": "de", "description": "Wissenschaftlicher Super-Rechner und Graph – 100 % offline",
    "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
              {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"}],
}


def fetch_pyodide():
    out = os.path.join(SITE, "pyodide")
    os.makedirs(out, exist_ok=True)

    def get(name, required=True):
        try:
            print("  lade", name)
            urllib.request.urlretrieve(BASE + name, os.path.join(out, name))
            return True
        except Exception as ex:
            if required:
                raise
            print("   (übersprungen: %s)" % ex)
            return False
    for n in ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"):
        get(n)
    get("pyodide.mjs", required=False)
    lock = json.load(open(os.path.join(out, "pyodide-lock.json"), encoding="utf-8"))["packages"]
    need, todo = [], ["sympy", "mpmath"]
    while todo:
        n = todo.pop()
        if n in need:
            continue
        need.append(n)
        todo += lock[n].get("depends", [])
    for n in need:
        get(lock[n]["file_name"])
    print("Pyodide-Pakete:", need)


def build(fetch=False):
    if os.path.isdir(SITE):
        keep = os.path.join(SITE, "pyodide")
        for e in os.listdir(SITE):
            fp = os.path.join(SITE, e)
            if fp != keep:
                shutil.rmtree(fp) if os.path.isdir(fp) else os.remove(fp)
    os.makedirs(SITE, exist_ok=True)
    sys.argv = [sys.argv[0]]
    sys.path.insert(0, HERE)
    import main  # liefert PAGE (die komplette Oberfläche) und make_icon

    page = main.PAGE
    page = page.replace("<title>Quantumator</title>", "<title>Quantumator</title>\n" + HEAD_ADD, 1)
    page = page.replace("<script>", "<script>\n" + SHIM_JS + "</script>\n<script>", 1)
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(page)
    shutil.copy(os.path.join(HERE, "engine.py"), os.path.join(SITE, "engine.py"))
    open(os.path.join(SITE, "pyglue.py"), "w", encoding="utf-8").write(GLUE)
    open(os.path.join(SITE, "worker.js"), "w", encoding="utf-8").write(WORKER_JS)
    open(os.path.join(SITE, "manifest.webmanifest"), "w", encoding="utf-8").write(json.dumps(MANIFEST, indent=1))
    main.make_icon(os.path.join(SITE, "apple-touch-icon.png"), 180, opaque=True)
    main.make_icon(os.path.join(SITE, "icon-192.png"), 192, opaque=True)
    main.make_icon(os.path.join(SITE, "icon-512.png"), 512)
    if fetch:
        fetch_pyodide()
    files = ["./"]
    h = hashlib.sha1()
    for root, _, names in os.walk(SITE):
        for n in sorted(names):
            if n == "sw.js":
                continue
            fp = os.path.join(root, n)
            rel = os.path.relpath(fp, SITE).replace(os.sep, "/")
            files.append(rel)
            h.update(rel.encode())
            h.update(str(os.path.getsize(fp)).encode())
    sw = SW_JS.replace("__VER__", h.hexdigest()[:10]).replace("__FILES__", json.dumps(sorted(files)))
    open(os.path.join(SITE, "sw.js"), "w", encoding="utf-8").write(sw)
    open(os.path.join(SITE, ".nojekyll"), "w").write("")
    print("Fertig: %d Dateien in %s" % (len(files), SITE))


if __name__ == "__main__":
    build(fetch="--fetch" in sys.argv)
