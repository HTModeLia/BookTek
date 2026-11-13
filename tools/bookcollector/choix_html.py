"""Page de choix (choix.html) : images Book Collector, ISBN proposés avec leur jaquette, doublons regroupés.

Usage : python tools/bookcollector/choix_html.py ["dossier Book Collector"]   -> écrit Book Collector\\choix.html, à ouvrir dans un navigateur.
"""
import csv, json, os, sys, re, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
here = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "Book Collector")  # dossier Book Collector
rows = list(csv.DictReader(open(os.path.join(here, "livres_ocr.csv"), encoding="utf-8-sig"), delimiter=";"))


def key(r):
    """Clé de doublon : l'ISBN proposé, sinon le titre du nom de fichier sans accents ni espaces."""
    t = unicodedata.normalize("NFD", r["titre (nom de fichier)"].lower()).encode("ascii", "ignore").decode()
    return r["isbn"] or re.sub(r"\W", "", t) or r["fichier"]


groups = {}
for r in rows:
    groups.setdefault(key(r), []).append(r)
# même titre de fichier avec des ISBN différents : on fusionne aussi ces groupes
by_title = {}
for k, g in list(groups.items()):
    t = re.sub(r"\W", "", g[0]["titre (nom de fichier)"].lower())
    if t and t in by_title and by_title[t] in groups:
        groups[by_title[t]] += groups.pop(k)
    elif t:
        by_title[t] = k
data = sorted(([{"file": r["fichier"], "title": r["titre (nom de fichier)"], "found": r["titre trouvé"],
                 "authors": r["auteurs trouvés"], "source": r["source"],
                 "isbns": [i for i in [r["isbn"]] + r["autres ISBN proposés"].split() if i]} for r in g]
               for g in groups.values()), key=lambda g: (len(g) == 1, g[0]["title"].lower()))

page = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Choix des ISBN</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1d;--mute:#666;--line:#ddd;--acc:#1a5fb4;--dup:#fff4d6}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1d;--card:#262629;--ink:#eee;--mute:#aaa;--line:#444;--acc:#78aeed;--dup:#3a3220}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.4 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--card);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;z-index:1}
h1{font-size:20px;margin:0}button{font:inherit;padding:8px 16px;border-radius:6px;border:1px solid var(--acc);background:var(--acc);color:#fff;cursor:pointer}
main{padding:16px;display:grid;gap:16px;max-width:1300px;margin:auto}
.group{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}
.group.dup{background:var(--dup)}.group h2{font-size:15px;margin:0 0 8px;color:var(--mute)}
.row{display:flex;gap:16px;padding:8px 0;border-top:1px solid var(--line);align-items:flex-start;flex-wrap:wrap}
.row:first-of-type{border-top:0}.row.off{opacity:.4}
.mine img{height:170px;border-radius:4px}.mine{width:200px}.mine small{display:block;color:var(--mute);word-break:break-all}
.cands{display:flex;gap:12px;flex-wrap:wrap}
label.c{display:flex;flex-direction:column;align-items:center;gap:4px;padding:6px;border:2px solid transparent;border-radius:6px;cursor:pointer;width:130px;text-align:center;font-size:13px}
label.c:has(input:checked){border-color:var(--acc)}label.c img{height:150px;max-width:120px;object-fit:contain;background:var(--line)}
.none{height:150px;width:100px;display:flex;align-items:center;justify-content:center;background:var(--line);color:var(--mute);font-size:12px}
.keep{font-weight:600}a{color:var(--acc)}
</style></head><body>
<header><h1>Choix des ISBN</h1><label><input type="checkbox" id="onlydup"> Doublons seulement</label>
<span id="count"></span><button id="export">Exporter les ISBN choisis</button></header><main id="list"></main>
<script>
const DATA = __DATA__;
const esc = s => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const list = document.getElementById('list');
DATA.forEach((g, gi) => {
  const el = document.createElement('section');
  el.className = 'group' + (g.length > 1 ? ' dup' : '');
  el.innerHTML = (g.length > 1 ? `<h2>${g.length} images pour ce livre : cochez celles à garder</h2>` : '') +
    g.map((r, ri) => `<div class="row" data-g="${gi}" data-r="${ri}">
      <div class="mine"><img src="Images/${encodeURI(r.file)}" loading="lazy" alt="">
        <label class="keep"><input type="checkbox" class="k" ${ri == 0 ? 'checked' : ''}> Garder</label>
        <div>${esc(r.title)}</div><small>${esc(r.file)}</small>
        ${r.found ? `<small>Trouvé (${esc(r.source)}) : ${esc(r.found)} / ${esc(r.authors)}</small>` : ''}</div>
      <div class="cands">${r.isbns.map((i, ci) => `<label class="c"><input type="radio" name="r${gi}_${ri}" value="${i}" ${ci == 0 ? 'checked' : ''}>
          <img src="https://books.google.com/books/content?vid=ISBN${i}&printsec=frontcover&img=1&zoom=1" loading="lazy" alt=""
               onerror="this.onerror=()=>this.outerHTML='<div class=none>pas de jaquette en ligne</div>';this.src='https://covers.openlibrary.org/b/isbn/${i}-M.jpg?default=false'">
          ${i} <a href="https://www.google.com/search?tbm=bks&q=isbn:${i}" target="_blank">voir</a></label>`).join('')}
        <label class="c"><input type="radio" name="r${gi}_${ri}" value="" ${r.isbns.length ? '' : 'checked'}>
          <div class="none">aucun / à scanner</div>Aucun</label></div></div>`).join('');
  list.append(el);
});
function update() {
  document.querySelectorAll('.row').forEach(r => r.classList.toggle('off', !r.querySelector('.k').checked));
  const n = chosen().length;
  document.getElementById('count').textContent = `${n} ISBN choisis`;
}
function chosen() {
  const out = [];
  document.querySelectorAll('.row').forEach(r => {
    const v = r.querySelector('input[type=radio]:checked')?.value;
    if (r.querySelector('.k').checked && v && !out.includes(v)) out.push(v);
  });
  return out;
}
list.addEventListener('change', update);
document.getElementById('onlydup').onchange = e =>
  document.querySelectorAll('.group:not(.dup)').forEach(g => g.hidden = e.target.checked);
document.getElementById('export').onclick = () => {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([chosen().join('\\r\\n') + '\\r\\n'], {type: 'text/plain'}));
  a.download = 'livres_isbn_choisis.txt'; a.click();
};
update();
</script></body></html>"""
with open(os.path.join(here, "choix.html"), "w", encoding="utf-8") as f:
    f.write(page.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
print(len(data), "livres,", sum(len(g) > 1 for g in data), "groupes de doublons")
