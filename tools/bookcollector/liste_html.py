"""Page liste.html : une ligne par image Book Collector, triée par titre, ISBN à côté, case « Garder ».

Usage : python tools/bookcollector/liste_html.py ["dossier Book Collector"]   -> écrit Book Collector\\liste.html, à ouvrir dans un navigateur.
"""
import csv, json, os, sys, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
here = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "Book Collector")  # dossier Book Collector
rows = list(csv.DictReader(open(os.path.join(here, "livres_ocr.csv"), encoding="utf-8-sig"), delimiter=";"))


def sort_key(r):
    """Titre du nom de fichier (ou titre trouvé pour les images « img0xx »), sans accents ni article."""
    t = unicodedata.normalize("NFD", (r["titre (nom de fichier)"] or r["titre trouvé"]).lower())
    t = t.encode("ascii", "ignore").decode().strip()
    for art in ("le ", "la ", "les ", "l'", "un ", "une "):
        if t.startswith(art):
            return t[len(art):]
    return t


data = [{"file": r["fichier"], "title": r["titre (nom de fichier)"], "found": r["titre trouvé"],
         "authors": r["auteurs trouvés"], "isbn": r["isbn"], "others": r["autres ISBN proposés"].split()}
        for r in sorted(rows, key=sort_key)]

page = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Liste des images</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1d;--mute:#666;--line:#ddd;--acc:#1a5fb4}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1d;--card:#262629;--ink:#eee;--mute:#aaa;--line:#444;--acc:#78aeed}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.4 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--card);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;z-index:1}
h1{font-size:20px;margin:0}button{font:inherit;padding:8px 16px;border-radius:6px;border:1px solid var(--acc);background:var(--acc);color:#fff;cursor:pointer}
button.alt{background:transparent;color:var(--acc)}
table{border-collapse:collapse;margin:16px auto;max-width:1200px;width:calc(100% - 32px);background:var(--card)}
td{border-top:1px solid var(--line);padding:8px;vertical-align:middle}tr.off{opacity:.35}
td.k{text-align:center;width:90px}td.k input{width:24px;height:24px}
img{height:120px;max-width:90px;object-fit:contain;display:block}
.t{font-weight:600}.m{color:var(--mute);font-size:13px;word-break:break-all}
td img{cursor:zoom-in}
#zoom{position:fixed;inset:0;background:rgba(0,0,0,.85);display:flex;align-items:center;justify-content:center;z-index:2;cursor:zoom-out}
#zoom[hidden]{display:none}#zoom img{height:auto;max-height:92vh;max-width:92vw;width:auto;min-height:60vh}
input.isbn{font:inherit;width:15ch;padding:4px}.alts{font-size:13px}.alts a{margin-right:6px}a{color:var(--acc)}
</style></head><body>
<header><h1>Liste des images</h1><span id="count"></span>
<button class="alt" id="all">Tout cocher</button><button id="export">Exporter les ISBN gardés</button></header>
<table><tbody id="list"></tbody></table>
<div id="zoom" hidden><img alt=""></div>
<script>
const DATA = __DATA__;
const esc = s => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const cover = i => i ? `https://books.google.com/books/content?vid=ISBN${i}&printsec=frontcover&img=1&zoom=1` : '';
let saved = {};
try { saved = JSON.parse(localStorage.getItem('booktek-liste') || '{}'); } catch (e) {}
const list = document.getElementById('list');
list.innerHTML = DATA.map((r, n) => {
  const s = saved[r.file] || {keep: true, isbn: r.isbn};
  return `<tr data-f="${esc(r.file)}">
    <td class="k"><label><input type="checkbox" class="keep" ${s.keep ? 'checked' : ''}><br>Garder</label></td>
    <td><img src="Images/${encodeURI(r.file)}" loading="lazy" alt=""></td>
    <td><div class="t">${esc(r.title || '(sans titre)')}</div><div class="m">${esc(r.file)}</div>
        <div>${esc(r.found)}${r.authors ? ' / ' + esc(r.authors) : ''}</div></td>
    <td><input class="isbn" value="${esc(s.isbn)}" placeholder="à scanner">
        <div class="alts">${r.others.map(o => `<a href="#" data-i="${o}">${o}</a>`).join('')}</div>
        <a class="m" href="#" data-check>voir sur Google</a></td>
    <td><img class="cov" src="${cover(s.isbn)}" loading="lazy" alt="" onerror="this.style.visibility='hidden'"></td></tr>`;
}).join('');
function save() {
  const out = {};
  list.querySelectorAll('tr').forEach(tr => out[tr.dataset.f] = {keep: tr.querySelector('.keep').checked, isbn: tr.querySelector('.isbn').value.trim()});
  try { localStorage.setItem('booktek-liste', JSON.stringify(out)); } catch (e) {}
  list.querySelectorAll('tr').forEach(tr => tr.classList.toggle('off', !tr.querySelector('.keep').checked));
  document.getElementById('count').textContent = `${kept().length} ISBN gardés sur ${DATA.length} images`;
}
function kept() {
  const out = [];
  list.querySelectorAll('tr').forEach(tr => {
    const v = tr.querySelector('.isbn').value.replace(/[^0-9X]/gi, '');
    if (tr.querySelector('.keep').checked && v && !out.includes(v)) out.push(v);
  });
  return out;
}
list.addEventListener('change', e => {
  if (e.target.classList.contains('isbn')) {
    const img = e.target.closest('tr').querySelector('.cov');
    img.style.visibility = ''; img.src = cover(e.target.value.trim());
  }
  save();
});
list.addEventListener('click', e => {
  const tr = e.target.closest('tr'), input = tr?.querySelector('.isbn');
  if (e.target.tagName == 'IMG') {  // agrandir la jaquette
    zoom.querySelector('img').src = e.target.src; zoom.hidden = false;
  } else if (e.target.dataset.i) {  // clic sur un autre ISBN proposé : il remplace l'actuel
    e.preventDefault(); const old = input.value; input.value = e.target.dataset.i;
    e.target.dataset.i = e.target.textContent = old || ''; input.dispatchEvent(new Event('change', {bubbles: true}));
  } else if (e.target.hasAttribute('data-check')) {
    e.preventDefault(); window.open('https://www.google.com/search?tbm=bks&q=isbn:' + input.value.trim());
  }
});
const zoom = document.getElementById('zoom');
zoom.onclick = () => zoom.hidden = true;
document.addEventListener('keydown', e => { if (e.key == 'Escape') zoom.hidden = true; });
document.getElementById('all').onclick = () => { list.querySelectorAll('.keep').forEach(c => c.checked = true); save(); };
document.getElementById('export').onclick = () => {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([kept().join('\\r\\n') + '\\r\\n'], {type: 'text/plain'}));
  a.download = 'livres_isbn_gardes.txt'; a.click();
};
save();
</script></body></html>"""
with open(os.path.join(here, "liste.html"), "w", encoding="utf-8") as f:
    f.write(page.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
print(len(data), "images")
