"""Liste de livres à partir de l'OCR des images Book Collector : ISBN lu sur l'image, sinon proposé par Google Books ou la BnF.

Usage : python tools/bookcollector/isbn_list.py ["dossier Book Collector"]
Lit <dossier>/ocr.json (produit par ocr.ps1), écrit <dossier>/livres_ocr.csv. Relançable : les lignes déjà trouvées sont gardées.
"""
import csv, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
here = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "Book Collector")  # dossier Book Collector
sys.path.insert(0, ROOT)
from booktek.isbn import find_in_lines, normalize
from booktek.lookup import _get_json, GOOGLE_KEY, HEADERS, _DC, _OAI_DC, _bnf_person


def name_words(fname):
    """« ALombreDuClocherTome31486_f.jpg » -> « A Lombre Du Clocher Tome 3 » (id Book Collector retiré)."""
    base = re.sub(r"_[fb]$", "", fname.rsplit(".", 1)[0])
    base = re.sub(r"(?<=\d)[A-Z][A-Z0-9]{1,3}$", "", base)  # suffixe « I3DB », « CFX »…
    base = re.sub(r"\d{3,4}$", "", base)  # shortcut: id collé au tome (« Tome31486 ») coupé à 4 chiffres, faux si l'id a 5 chiffres
    if base.startswith("img"):
        return ""
    return re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[0-9])(?=[A-Za-z])", " ", base)


def ocr_words(text):
    """Lignes courtes et lisibles de l'OCR (titre, auteur), sans le texte de 4e de couverture."""
    lines = [l for l in text.splitlines() if 2 < len(l) < 40 and sum(c.isalpha() for c in l) > len(l) * .7]
    return " ".join(lines[:5])


def search(q):
    """Google Books : [(isbn13, titre, auteurs)] des 3 premiers résultats."""
    url = ("https://www.googleapis.com/books/v1/volumes?maxResults=5&q=" + urllib.parse.quote(q)
           + (f"&key={GOOGLE_KEY}" if GOOGLE_KEY else ""))
    for wait in (5, 15, 45, 0):  # quota Google (429) : on patiente puis on réessaie
        try:
            data = _get_json(url)
            break
        except Exception as e:
            if "429" not in str(e) or not wait:
                raise
            time.sleep(wait)
    out = []
    for it in data.get("items") or []:
        v = it.get("volumeInfo", {})
        ids = {i["type"]: i["identifier"] for i in v.get("industryIdentifiers") or []}
        isbn = normalize(ids.get("ISBN_13") or ids.get("ISBN_10") or "")
        if isbn:
            out.append((isbn, v.get("title", ""), ", ".join(v.get("authors") or [])))
    return out[:3]


def search_bnf(q):
    """Catalogue BnF (SRU, sans quota) : [(isbn13, titre, auteurs)] des 3 premières notices ayant un ISBN."""
    words = " ".join(w for w in re.findall(r"\w+", q) if len(w) > 2)
    url = ("https://catalogue.bnf.fr/api/SRU?version=1.2&operation=searchRetrieve&recordSchema=dublincore"
           "&maximumRecords=10&query=" + urllib.parse.quote(f'bib.anywhere all "{words}"'))
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=15) as resp:
        root = ET.fromstring(resp.read())
    out = []
    for rec in root.iter(_OAI_DC):
        get = lambda tag: [e.text or "" for e in rec.findall(_DC + tag)]
        isbn = next(iter(find_in_lines("\n".join(i for i in get("identifier") if "ISBN" in i))), None)
        if isbn:
            creators = get("creator")
            authors = [c for c in creators if "Auteur" in c] or creators
            out.append((isbn, (get("title") or [""])[0].split(" / ")[0], ", ".join(map(_bnf_person, authors))))
    return out[:3]


def _plain(s):
    """Minuscules sans accents, pour comparer des titres."""
    return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()


def plausible(title, ref, authors=""):
    """Au moins la moitié des mots du titre trouvé (avant « : ») apparaissent dans ``ref`` (nom de fichier + OCR),
    et au moins deux mots, sauf titre d'un seul mot ou nom d'auteur présent dans ``ref``."""
    words = set(re.findall(r"\w{4,}", _plain(title.split(" : ")[0].split(" / ")[0])))
    hits = sum(w in _plain(ref) for w in words)
    author = any(n in _plain(ref) for n in re.findall(r"\w{4,}", _plain(authors)))
    return bool(words) and hits * 2 >= len(words) and (hits >= 2 or len(words) == 1 or author)


def bnf_queries(nw, ow):
    """Combinaisons de mots à essayer, de la plus précise à la plus large (un mot faux suffit à tout bloquer)."""
    fw = [w for w in nw.split() if len(w) > 3 or w.isdigit()]
    if len(fw) > 2:
        fw = fw[:-1]  # le nom de fichier est tronqué : dernier mot souvent coupé
    ow = [w for w in re.findall(r"[^\W\d_]{4,}", ow) if not (w[:-1].isupper() and w[-1].islower())][:4]
    cands = [fw, ow, fw + ow[:2]] + [fw[:i] + fw[i + 1:] for i in range(len(fw))]
    seen = []
    for c in cands:
        if len(c) >= 2 and c not in seen:
            seen.append(c)
    return [" ".join(c) for c in seen[:8]]


assert plausible("Le procès de la momie", "LeProcesDeLaMomieChrist")
assert not plausible("Cuisine à la vapeur", "LlleSousLaMerIsabelAll ")
assert plausible("Coeur de Gaël", "CoeurDeGalSoniaMarmen", "Sonia Marmen")
assert not plausible("Juillet en hiver", "LesVendangesDeJuilletLes", "Françoise Bourdin")
assert name_words("ALombreDuClocherTome31486_f.jpg") == "A Lombre Du Clocher Tome 3"
assert name_words("AngesDmonsDanBrown16084CFX_f.jpg") == "Anges Dmons Dan Brown 1"

ocr = json.load(open(os.path.join(here, "ocr.json"), encoding="utf-8-sig"))
try:  # reprise : les lignes déjà trouvées lors d'un passage précédent sont gardées
    done = {r["fichier"]: r for r in csv.DictReader(open(os.path.join(here, "livres_ocr.csv"), encoding="utf-8-sig"), delimiter=";") if r["isbn"]}
except FileNotFoundError:
    done = {}
rows, google_ok = [], True
for fname, text in ocr.items():
    if fname in done:
        rows.append(done[fname]); continue
    nw, ow = name_words(fname), ocr_words(text or "")
    read = find_in_lines(text or "")
    found, q = [], (nw + " " + ow).strip()
    if not read and q and google_ok:
        for query in (q, nw or ow):  # texte complet, puis nom de fichier seul si rien
            try:
                found = search(query)
            except Exception as e:
                print(fname, e)
                google_ok = False  # quota épuisé : BnF seule pour la suite
                break
            if found:
                break
            time.sleep(.2)
    source = "Google Books"
    if not read and not found:
        source = "BnF"
        for query in bnf_queries(nw, ow):
            try:
                found = [f for f in search_bnf(query) if plausible(f[1], nw.replace(" ", "") + " " + ow, f[2])]
            except Exception as e:
                print(fname, e)
            if found:
                break
    best = read[0] if read else (found[0][0] if found else "")
    rows.append({"isbn": best, "source": "image" if read else (source if found else ""),
                 "fichier": fname, "titre (nom de fichier)": nw, "texte lu (OCR)": ow,
                 "titre trouvé": found[0][1] if found else "", "auteurs trouvés": found[0][2] if found else "",
                 "autres ISBN proposés": " ".join(f[0] for f in found[1:])})

with open(os.path.join(here, "livres_ocr.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, rows[0].keys(), delimiter=";")
    w.writeheader(); w.writerows(rows)
print(len(rows), "images,", sum(r["source"] == "image" for r in rows), "ISBN lus,",
      sum(r["source"] == "Google Books" for r in rows), "proposés,", sum(not r["isbn"] for r in rows), "sans ISBN")
