"""Page tri.html : chaque image Book Collector avec sa vignette, l'ISBN déduit, et des boutons Garder / Rejeter / Vérifier.

Usage : python tools/bookcollector/tri_html.py ["dossier Book Collector"]   -> écrit <dossier>/tri.html

Sources de l'ISBN, de la plus sûre à la moins sûre :

1. **Fiche Book Collector** : chaque fiche des ``.bkc`` (dossier et ``Backup``) contient,
   dans l'ordre, le chemin de l'image, l'ISBN et le chemin de la vignette
   (``Thumbnails\\<md5>.png``). La vignette est reliée à son image par comparaison
   visuelle (les vignettes sont des réductions des images).
2. **Recherche** : ISBN proposé dans ``livres_ocr.csv`` (Google Books ou BnF, voir isbn_list.py).

Les vignettes qui ne ressemblent à aucune image forment une section à part.
Les choix sont gardés dans le navigateur et exportés en CSV ; ce CSV peut être
rechargé dans la page (autre ordinateur, autre navigateur).
"""
import csv, glob, json, os, re, sys, unicodedata

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
here = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "Book Collector")  # dossier Book Collector
sys.path.insert(0, ROOT)
from booktek.bkc_import import _THUMB, _ISBN, _U, _title_after
from booktek.isbn import normalize

_IMG = re.compile(re.escape(_U("\\Images\\")) + rb"((?:[\x20-\x7e]\x00)+?\.\x00(?:j\x00p\x00g|g\x00i\x00f|p\x00n\x00g)\x00)")
SAME = 4  # écart visuel maximal entre une vignette et son image (mesuré : ~1-2 si identiques, >5 sinon)


def bkc_records():
    """{md5 de vignette: {image, isbn, title}} de tous les .bkc (le plus récent l'emporte)."""
    recs = {}
    paths = sorted(glob.glob(os.path.join(here, "*.bkc")) + glob.glob(os.path.join(here, "Backup", "*")), key=os.path.getmtime)
    for p in paths:
        data = open(p, "rb").read()
        for m in _THUMB.finditer(data):
            h = re.search(r"[0-9A-F]{32}", m.group().decode("utf-16-le").upper())
            if not h:
                continue
            win = data[max(0, m.start() - 600):m.start()]
            imgs = [i.group(1).decode("utf-16-le") for i in _IMG.finditer(win)]
            isbns = [c.group().decode("utf-16-le") for c in _ISBN.finditer(win)]
            isbns = [c for c in isbns if sum(ch.isdigit() for ch in c) >= 9]
            recs[h.group()] = {"image": imgs[-1] if imgs else "", "isbn": normalize(isbns[-1]) if isbns else None,
                               "title": _title_after(data, m.end())}
    return recs


def signature(path):
    """Empreinte visuelle grossière : proportions + image réduite à 8x12 pixels."""
    im = Image.open(path).convert("RGB")
    return im.size[0] / im.size[1], im.resize((8, 12), Image.BILINEAR).tobytes()


def distance(a, b):
    return sum(abs(x - y) for x, y in zip(a[1], b[1])) / len(a[1]) + 100 * abs(a[0] - b[0])


def sort_key(title):
    """Titre sans accents ni article de tête, pour le tri alphabétique."""
    t = unicodedata.normalize("NFD", title.lower()).encode("ascii", "ignore").decode().strip()
    t = re.sub(r"^(le |la |les |l'|un |une )", "", t)
    return t or "~"


assert sort_key("Les Ailes de Kama") == "ailes de kama"

images = sorted(f for f in os.listdir(os.path.join(here, "Images")) if os.path.isfile(os.path.join(here, "Images", f)))
thumbs = sorted(os.listdir(os.path.join(here, "Thumbnails")))
sig_i = {f: signature(os.path.join(here, "Images", f)) for f in images}
sig_t = {f: signature(os.path.join(here, "Thumbnails", f)) for f in thumbs}
thumb_of, orphans = {}, []
for t, s in sig_t.items():
    d, f = min((distance(s, i), f) for f, i in sig_i.items())
    if d < SAME:
        thumb_of.setdefault(f, []).append(t)
    else:
        orphans.append(t)

recs = bkc_records()
by_image = {r["image"]: r for r in recs.values() if r["image"]}
csv_rows = {r["fichier"]: r for r in csv.DictReader(open(os.path.join(here, "livres_ocr.csv"), encoding="utf-8-sig"), delimiter=";")}

rows = []
for f in images:
    c = csv_rows.get(f, {})
    ts = thumb_of.get(f, [])
    rec = by_image.get(f) or next((recs[t[:32]] for t in ts if t[:32] in recs), None)
    title = c.get("titre (nom de fichier)", "") or (rec or {}).get("title", "")
    if rec and rec["isbn"]:
        isbn, source, section = rec["isbn"], "fiche Book Collector", 1
    elif c.get("isbn"):
        isbn, source, section = c["isbn"], "recherche " + c["source"], 2
    else:
        isbn, source, section = "", "", 3
    others = [i for i in [c.get("isbn", "")] + c.get("autres ISBN proposés", "").split() if i and i != isbn]
    rows.append({"id": f, "image": f, "thumbs": ts, "title": title or "(sans titre)", "isbn": isbn, "source": source,
                 "found": " / ".join(x for x in (c.get("titre trouvé"), c.get("auteurs trouvés")) if x),
                 "others": others, "section": section})
for t in orphans:
    rec = recs.get(t[:32], {})
    rows.append({"id": t, "image": "", "thumbs": [t], "title": rec.get("title") or "(vignette seule)",
                 "isbn": rec.get("isbn") or "", "source": "fiche Book Collector" if rec.get("isbn") else "",
                 "found": "", "others": [], "section": 4})
rows.sort(key=lambda r: (r["section"], sort_key(r["title"]), r["id"]))
counts = {s: sum(r["section"] == s for r in rows) for s in (1, 2, 3, 4)}

page = r"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Tri des livres</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1d;--mute:#666;--line:#ddd;--acc:#1a5fb4;--ok:#2e7d32;--ko:#c62828;--chk:#b26a00}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1d;--card:#262629;--ink:#eee;--mute:#aaa;--line:#444;--acc:#78aeed;--ok:#66bb6a;--ko:#ef5350;--chk:#ffb74d}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.4 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--card);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:10px 16px;align-items:center;flex-wrap:wrap;z-index:1}
h1{font-size:20px;margin:0}h2{max-width:1250px;margin:24px auto 0;padding:0 16px;font-size:18px}h2 small{color:var(--mute);font-weight:400}
button,.btn{font:inherit;padding:6px 14px;border-radius:6px;border:1px solid var(--acc);background:transparent;color:var(--acc);cursor:pointer}
button.main{background:var(--acc);color:#fff}
.filters button.on{background:var(--acc);color:#fff}
table{border-collapse:collapse;margin:8px auto;max-width:1250px;width:calc(100% - 32px);background:var(--card)}
td{border-top:1px solid var(--line);padding:8px;vertical-align:middle}
td img{height:120px;max-width:90px;object-fit:contain;display:inline-block;cursor:zoom-in;vertical-align:middle}
td.th img{height:80px}.t{font-weight:600}.m{color:var(--mute);font-size:13px;word-break:break-all}
input.isbn{font:inherit;width:15ch;padding:4px}.alts{font-size:13px}.alts a{margin-right:6px}a{color:var(--acc)}
.dec{display:flex;flex-direction:column;gap:4px;width:110px}
.dec button[data-d=garder].on{background:var(--ok);border-color:var(--ok);color:#fff}
.dec button[data-d=rejeter].on{background:var(--ko);border-color:var(--ko);color:#fff}
.dec button[data-d=verifier].on{background:var(--chk);border-color:var(--chk);color:#fff}
tr.rejeter td:not(.d){opacity:.35}
#zoom{position:fixed;inset:0;background:rgba(0,0,0,.85);display:flex;align-items:center;justify-content:center;z-index:2;cursor:zoom-out}
#zoom[hidden]{display:none}#zoom img{max-height:92vh;max-width:92vw;min-height:60vh}
</style></head><body>
<header><h1>Tri des livres</h1><span id="count"></span>
<span class="filters">Afficher : <button data-f="" class="on">tout</button> <button data-f="aucun">à décider</button>
<button data-f="garder">gardés</button> <button data-f="verifier">à vérifier</button> <button data-f="rejeter">rejetés</button></span>
<button class="main" id="export">Exporter les décisions</button><button id="exportIsbn">Exporter les ISBN gardés</button>
<label class="btn">Reprendre un fichier de décisions<input type="file" id="load" accept=".csv" hidden></label></header>
<main id="list"></main>
<div id="zoom" hidden><img alt=""></div>
<script>
const DATA = __DATA__, COUNTS = __COUNTS__;
const SECTIONS = {1: "ISBN de la fiche Book Collector (sûr)", 2: "ISBN proposé par la recherche (à confirmer)",
                  3: "Sans ISBN", 4: "Vignettes sans image correspondante"};
const KEY = 'booktek-tri';
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const cover = i => i ? `https://books.google.com/books/content?vid=ISBN${i}&printsec=frontcover&img=1&zoom=1` : '';
// Site d'où vient l'ISBN : [libellé, adresse]. Une fiche Book Collector n'a pas de site : on vérifie à la BnF.
const BNF = i => 'https://catalogue.bnf.fr/rechercher.do?motRecherche=' + i;
const site = r => /Google/.test(r.source) ? ['voir sur Google Books', i => 'https://books.google.fr/books?vid=ISBN' + i]
                : /BnF/.test(r.source) ? ['voir à la BnF', BNF] : ['vérifier à la BnF', BNF];
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
const st = r => state[r.id] || {d: '', isbn: r.isbn};

function render() {
  let html = '', sec = 0;
  for (const r of DATA) {
    if (r.section != sec) {
      if (sec) html += '</tbody></table>';
      sec = r.section;
      html += `<h2>${SECTIONS[sec]} <small>${COUNTS[sec]} lignes</small></h2><table><tbody>`;
    }
    const s = st(r);
    html += `<tr data-id="${esc(r.id)}" class="${s.d}">
      <td class="d"><div class="dec">${['garder', 'rejeter', 'verifier'].map(d =>
        `<button data-d="${d}" class="${s.d == d ? 'on' : ''}">${{garder: 'Garder', rejeter: 'Rejeter', verifier: 'Vérifier'}[d]}</button>`).join('')}</div></td>
      <td>${r.image ? `<img src="Images/${encodeURI(r.image)}" loading="lazy" alt="">` : ''}</td>
      <td class="th">${r.thumbs.map(t => `<img src="Thumbnails/${t}" loading="lazy" alt="" title="vignette">`).join(' ')}</td>
      <td><div class="t">${esc(r.title)}</div><div class="m">${esc(r.image || 'vignette ' + r.thumbs[0])}</div>
          <div>${esc(r.found)}</div><div class="m">${esc(r.source)}</div></td>
      <td><input class="isbn" value="${esc(s.isbn)}" placeholder="à scanner">
          <div class="alts">${r.others.map(o => `<a href="#" data-i="${o}">${o}</a>`).join('')}</div>
          <a class="m" href="#" data-check>${site(r)[0]}</a></td>
      <td><img class="cov" src="${cover(s.isbn)}" loading="lazy" alt="" onerror="this.style.visibility='hidden'"></td></tr>`;
  }
  document.getElementById('list').innerHTML = html + '</tbody></table>';
  filter(); count();
}
function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} count(); }
function count() {
  const n = {garder: 0, rejeter: 0, verifier: 0};
  DATA.forEach(r => { const d = st(r).d; if (d) n[d]++; });
  document.getElementById('count').textContent =
    `${DATA.length} lignes : ${n.garder} gardées, ${n.verifier} à vérifier, ${n.rejeter} rejetées`;
}
let shown = '';
function filter() {
  document.querySelectorAll('#list tr').forEach(tr => {
    const d = st(DATA.find(r => r.id == tr.dataset.id)).d;
    tr.hidden = shown && (shown == 'aucun' ? d : d != shown);
  });
}
const byId = id => DATA.find(r => r.id == id);
const list = document.getElementById('list'), zoom = document.getElementById('zoom');
list.addEventListener('click', e => {
  const tr = e.target.closest('tr'); if (!tr) return;
  const r = byId(tr.dataset.id), s = st(r), input = tr.querySelector('.isbn');
  if (e.target.tagName == 'IMG') { zoom.querySelector('img').src = e.target.src; zoom.hidden = false; }
  else if (e.target.dataset.d) {  // un 2e clic sur le même bouton annule la décision
    s.d = s.d == e.target.dataset.d ? '' : e.target.dataset.d; state[r.id] = s;
    tr.className = s.d; tr.querySelectorAll('.dec button').forEach(b => b.classList.toggle('on', b.dataset.d == s.d)); save();
  } else if (e.target.dataset.i) {  // autre ISBN proposé : il remplace l'actuel
    e.preventDefault(); const old = input.value; input.value = e.target.dataset.i;
    e.target.dataset.i = e.target.textContent = old; input.dispatchEvent(new Event('change', {bubbles: true}));
  } else if (e.target.hasAttribute('data-check')) {
    // ces sites refusent d'être affichés dans la page (X-Frame-Options) : fenêtre popup, réutilisée d'un clic à l'autre
    e.preventDefault();
    window.open(site(r)[1](input.value.replace(/[^0-9X]/gi, '')), 'booktek-source', 'popup,width=1000,height=800');
  }
});
list.addEventListener('change', e => {
  if (!e.target.classList.contains('isbn')) return;
  const tr = e.target.closest('tr'), r = byId(tr.dataset.id), s = st(r), img = tr.querySelector('.cov');
  s.isbn = e.target.value.trim(); state[r.id] = s; save();
  img.style.visibility = ''; img.src = cover(s.isbn);
});
zoom.onclick = () => zoom.hidden = true;
document.addEventListener('keydown', e => { if (e.key == 'Escape') zoom.hidden = true; });
document.querySelectorAll('.filters button').forEach(b => b.onclick = () => {
  document.querySelectorAll('.filters button').forEach(x => x.classList.toggle('on', x == b)); shown = b.dataset.f; filter();
});
function download(name, text) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['﻿' + text], {type: 'text/csv'})); a.download = name; a.click();
}
const cell = v => /[;"\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
document.getElementById('export').onclick = () => {
  const lines = [['decision', 'isbn', 'image', 'vignettes', 'titre', 'source'].join(';')];
  DATA.forEach(r => { const s = st(r);
    lines.push([s.d || 'a decider', s.isbn.replace(/[^0-9X]/gi, ''), r.image, r.thumbs.join(' '), r.title, r.source].map(cell).join(';')); });
  download('booktek_tri.csv', lines.join('\r\n') + '\r\n');
};
document.getElementById('exportIsbn').onclick = () => {
  const out = [];
  DATA.forEach(r => { const s = st(r), v = s.isbn.replace(/[^0-9X]/gi, ''); if (s.d == 'garder' && v && !out.includes(v)) out.push(v); });
  download('livres_isbn_gardes.txt', out.join('\r\n') + '\r\n');
};
document.getElementById('load').onchange = async e => {  // reprise d'un export (autre ordinateur)
  const text = (await e.target.files[0].text()).replace(/^﻿/, '');
  let n = 0;
  text.split(/\r?\n/).slice(1).forEach(line => {
    const c = line.split(';'); if (c.length < 4) return;  // image et vignettes viennent avant le titre libre
    const r = DATA.find(r => (r.image || r.thumbs[0]) == (c[2] || c[3].split(' ')[0])); if (!r) return;
    state[r.id] = {d: c[0] == 'a decider' ? '' : c[0], isbn: c[1]}; n++;
  });
  save(); render(); alert(n + ' décisions reprises.');
};
render();
</script></body></html>"""
data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
with open(os.path.join(here, "tri.html"), "w", encoding="utf-8") as f:
    f.write(page.replace("__DATA__", data).replace("__COUNTS__", json.dumps(counts)))
print(f"{len(rows)} lignes : {counts[1]} ISBN Book Collector, {counts[2]} ISBN proposés, {counts[3]} sans ISBN, "
      f"{counts[4]} vignettes seules ; {len(recs)} fiches .bkc")
