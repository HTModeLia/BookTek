"""Recherche des informations d'un livre en ligne à partir de son ISBN.

Trois catalogues publics sont interrogés (adresses des API dans :data:`SOURCES`) :

=================  ==========================================================
Source             Remarques
=================  ==========================================================
BnF (SRU)          Très complet pour les éditions françaises, y compris les
                   clubs (France Loisirs…). Les anciennes notices ne sont
                   indexées qu'en ISBN-10.
Google Books       Bonne couverture internationale, mais renvoie souvent
                   l'erreur 429 (quota) sans clé d'API.
Open Library       Couverture surtout anglophone.
=================  ==========================================================

Chaque source est une fonction ``source(isbn) -> dict`` qui retourne les
champs de :data:`KEYS` qu'elle a trouvés (``{}`` si le livre est inconnu) et
peut lever n'importe quelle exception réseau. :func:`fetch` les combine.

Toutes les fonctions sont bloquantes (délai de 8 s par requête) : dans
l'interface, elles sont appelées depuis un thread secondaire.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .isbn import to10

try:  # clé d'API Google Books : fichier local hors dépôt, embarqué dans l'exe (docs/publier-une-version.md)
    from ._key import GOOGLE_KEY
except ImportError:
    GOOGLE_KEY = ""  # sans clé : quota anonyme partagé, souvent épuisé (erreur 429)

HEADERS = {"User-Agent": "BookTek/1.0"}
#: Champs recherchés : clés de :data:`booktek.db.FIELDS`, plus ``cover`` (URL de la couverture).
KEYS = ("title", "authors", "publisher", "year", "genre", "pages", "summary", "cover")
TIMEOUT = 8  # secondes, par requête
#: Services interrogés, avec la page de leur API (cités dans le menu Aide > Sources des données).
SOURCES = (
    ("BnF : catalogue général (API SRU)", "https://api.bnf.fr/fr/api-sru-catalogue-general"),
    ("Google Books API", "https://developers.google.com/books/docs/v1/using"),
    ("Open Library : Books API", "https://openlibrary.org/dev/docs/api/books"),
    ("Open Library : Covers API", "https://openlibrary.org/dev/docs/api/covers"),
)


def _get_json(url):
    """Télécharge et décode une réponse JSON."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)


def _get_bytes(url):
    """Télécharge le contenu brut de ``url`` (image de couverture)."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _year(text):
    """Extrait la première année sur 4 chiffres d'une date libre (« 2006 », « mars 2015 »…)."""
    m = re.search(r"\d{4}", text or "")
    return m.group() if m else ""


def google_books(isbn):
    """Source Google Books (API ``volumes``), fiche détaillée comprise. Le sous-titre est ajouté au titre."""
    url = "https://www.googleapis.com/books/v1/volumes?q=" + urllib.parse.quote(f"isbn:{isbn}")
    data = _get_json(url + (f"&key={GOOGLE_KEY}" if GOOGLE_KEY else ""))
    items = data.get("items") or []
    if not items:
        return {}
    v = items[0].get("volumeInfo", {})
    if items[0].get("selfLink"):  # la recherche renvoie une fiche abrégée, souvent sans résumé ni genre
        try:
            key = f"?key={GOOGLE_KEY}" if GOOGLE_KEY else ""
            v = {**v, **_get_json(items[0]["selfLink"] + key).get("volumeInfo", {})}
        except Exception:
            pass  # on garde la fiche abrégée
    title = v.get("title", "")
    if v.get("subtitle"):
        title = f"{title} : {v['subtitle']}"
    return {
        "title": title,
        "authors": ", ".join(v.get("authors") or []),
        "publisher": v.get("publisher", ""),
        "year": _year(v.get("publishedDate")),
        "genre": ", ".join(v.get("categories") or []),
        "pages": str(v.get("pageCount") or ""),
        "summary": re.sub(r"<[^>]+>", "", v.get("description", "")).strip(),  # description parfois en HTML
        "cover": (v.get("imageLinks") or {}).get("thumbnail", "").replace("http://", "https://"),
    }


def open_library(isbn):
    """Source Open Library (API ``books``, format ``jscmd=data``)."""
    data = _get_json(f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data")
    b = data.get(f"ISBN:{isbn}")
    if not b:
        return {}
    return {
        "title": b.get("title", ""),
        "authors": ", ".join(a.get("name", "") for a in b.get("authors") or []),
        "publisher": ", ".join(p.get("name", "") for p in b.get("publishers") or []),
        "year": _year(b.get("publish_date")),
        "genre": ", ".join(s.get("name", "") for s in (b.get("subjects") or [])[:3]),
        "pages": str(b.get("number_of_pages") or ""),
        "cover": (b.get("cover") or {}).get("medium", ""),
    }


# Espaces de noms XML des notices Dublin Core renvoyées par la BnF.
_DC = "{http://purl.org/dc/elements/1.1/}"
_OAI_DC = "{http://www.openarchives.org/OAI/2.0/oai_dc/}dc"


def _bnf_query(isbn):
    """Interroge l'API SRU de la BnF ; retourne l'élément ``oai_dc:dc`` de la 1re notice, ou ``None``."""
    query = urllib.parse.quote(f'bib.isbn adj "{isbn}"')
    url = ("https://catalogue.bnf.fr/api/SRU?version=1.2&operation=searchRetrieve"
           f"&recordSchema=dublincore&maximumRecords=1&query={query}")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        root = ET.fromstring(resp.read())
    return next(root.iter(_OAI_DC), None)


def _bnf_person(creator):
    """Convertit un auteur au format BnF en « Prénom Nom ».

    « Cantini, Barbara (1977-....). Auteur du texte » -> « Barbara Cantini ».
    On coupe avant les dates entre parenthèses ou avant la mention de rôle,
    puis on inverse « Nom, Prénom ».
    """
    name = re.split(r"\s*\(|\.\s", creator)[0].strip()
    last, _, first = name.partition(",")
    return f"{first.strip()} {last.strip()}".strip()


def _bnf_pages(fmt):
    """Nombre de pages d'un ``dc:format`` BnF : « 1 vol. (586 p.) » ou « (non paginé [47] p.) » -> « 586 » / « 47 »."""
    m = re.search(r"(\d+)\]?\s*p\.", fmt)
    return m.group(1) if m else ""


def bnf(isbn):
    """Source catalogue de la Bibliothèque nationale de France.

    Particularités des notices traitées ici :

    * titre suivi de la mention de responsabilité (« Titre / texte de X ;
      traduit par Y ») : on ne garde que ce qui précède « / » ;
    * ``dc:creator`` contient aussi illustrateurs, préfaciers… : on garde
      ceux dont le rôle contient « Auteur », ou tous à défaut ;
    * éditeur suivi de la ville entre parenthèses, supprimée ;
    * nombre de pages lu dans ``dc:format`` (« 1 vol. (586 p.) ; 24 cm »),
      y compris les livres non paginés (« [47] p. »).
    """
    rec = _bnf_query(isbn)
    if rec is None and to10(isbn):  # anciennes notices indexées en ISBN-10
        rec = _bnf_query(to10(isbn))
    if rec is None:
        return {}
    get = lambda tag: [e.text or "" for e in rec.findall(_DC + tag)]
    creators = get("creator")
    authors = [c for c in creators if "Auteur" in c] or creators
    pages = _bnf_pages(" ".join(get("format")))
    return {
        "title": (get("title") or [""])[0].split(" / ")[0].strip(),
        "authors": ", ".join(_bnf_person(a) for a in authors),
        "publisher": re.sub(r"\s*\([^)]*\)\s*$", "", (get("publisher") or [""])[0]).strip(),
        "year": _year((get("date") or [""])[0]),
        "pages": pages,
    }


def fetch(isbn):
    """Interroge tous les catalogues (en parallèle) et combine leurs réponses.

    Pour avoir la fiche la plus complète, chaque champ vient de la première
    source qui le fournit, dans l'ordre de fiabilité : BnF d'abord pour les
    ISBN français (``978-2``, ``979-10``), en dernier pour les autres. Deux
    exceptions : le **résumé** retenu est le plus long, et la **couverture**
    est la première image qui se télécharge réellement, avec en dernier
    recours la Covers API d'Open Library. Une source en erreur (réseau,
    quota, réponse inattendue) est simplement ignorée.

    Retourne un dict (seuls les champs trouvés sont présents), ou ``None`` si
    aucune source n'a fourni de titre. ``cover`` y contient l'image de
    couverture déjà téléchargée (octets), absente si aucune n'a pu l'être.
    """
    french = isbn.startswith(("9782", "97910"))
    sources = (bnf, google_books, open_library) if french else (google_books, open_library, bnf)

    def safe(source):
        try:
            return source(isbn)
        except Exception:
            return {}

    with ThreadPoolExecutor(len(sources)) as pool:
        infos = list(pool.map(safe, sources))  # dans l'ordre de priorité, quel que soit le plus rapide
    result = {}
    for k in KEYS:
        values = [info[k] for info in infos if info.get(k)]
        if values and k != "cover":
            result[k] = max(values, key=len) if k == "summary" else values[0]
    covers = [info["cover"] for info in infos if info.get("cover")]
    for url in covers + [f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg?default=false"]:
        try:
            result["cover"] = _get_bytes(url)  # ?default=false : erreur 404 plutôt qu'une image vide
            break
        except Exception:
            continue
    return result if result.get("title") else None
