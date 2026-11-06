"""Recherche des informations d'un livre en ligne à partir de son ISBN.

Trois catalogues publics, sans clé d'API, sont interrogés :

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
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .isbn import to10

HEADERS = {"User-Agent": "BookTek/1.0"}
#: Champs recherchés ; ce sont aussi des clés de :data:`booktek.db.FIELDS`.
KEYS = ("title", "authors", "publisher", "year", "pages")
TIMEOUT = 8  # secondes, par requête


def _get_json(url):
    """Télécharge et décode une réponse JSON."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)


def _year(text):
    """Extrait la première année sur 4 chiffres d'une date libre (« 2006 », « mars 2015 »…)."""
    m = re.search(r"\d{4}", text or "")
    return m.group() if m else ""


def google_books(isbn):
    """Source Google Books (API ``volumes``). Le sous-titre est ajouté au titre."""
    data = _get_json("https://www.googleapis.com/books/v1/volumes?q=" + urllib.parse.quote(f"isbn:{isbn}"))
    items = data.get("items") or []
    if not items:
        return {}
    v = items[0].get("volumeInfo", {})
    title = v.get("title", "")
    if v.get("subtitle"):
        title = f"{title} : {v['subtitle']}"
    return {
        "title": title,
        "authors": ", ".join(v.get("authors") or []),
        "publisher": v.get("publisher", ""),
        "year": _year(v.get("publishedDate")),
        "pages": str(v.get("pageCount") or ""),
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
        "pages": str(b.get("number_of_pages") or ""),
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


def bnf(isbn):
    """Source catalogue de la Bibliothèque nationale de France.

    Particularités des notices traitées ici :

    * titre suivi de la mention de responsabilité (« Titre / texte de X ;
      traduit par Y ») : on ne garde que ce qui précède « / » ;
    * ``dc:creator`` contient aussi illustrateurs, préfaciers… : on garde
      ceux dont le rôle contient « Auteur », ou tous à défaut ;
    * éditeur suivi de la ville entre parenthèses, supprimée ;
    * nombre de pages lu dans ``dc:format`` (« 1 vol. (586 p.) ; 24 cm »).
    """
    rec = _bnf_query(isbn)
    if rec is None and to10(isbn):  # anciennes notices indexées en ISBN-10
        rec = _bnf_query(to10(isbn))
    if rec is None:
        return {}
    get = lambda tag: [e.text or "" for e in rec.findall(_DC + tag)]
    creators = get("creator")
    authors = [c for c in creators if "Auteur" in c] or creators
    fmt = " ".join(get("format"))
    pages = re.search(r"(\d+)\s*p\.", fmt)
    return {
        "title": (get("title") or [""])[0].split(" / ")[0].strip(),
        "authors": ", ".join(_bnf_person(a) for a in authors),
        "publisher": re.sub(r"\s*\([^)]*\)\s*$", "", (get("publisher") or [""])[0]).strip(),
        "year": _year((get("date") or [""])[0]),
        "pages": pages.group(1) if pages else "",
    }


def fetch(isbn):
    """Interroge les catalogues et combine leurs réponses.

    Les sources sont consultées dans l'ordre jusqu'à ce que tous les champs de
    :data:`KEYS` soient remplis ; chaque champ vient de la première source qui
    le fournit. La BnF passe en premier pour les ISBN français (``978-2``,
    ``979-10``), en dernier pour les autres. Une source en erreur (réseau,
    quota, réponse inattendue) est simplement ignorée.

    Retourne un dict (seuls les champs trouvés sont présents), ou ``None`` si
    aucune source n'a fourni de titre.
    """
    french = isbn.startswith(("9782", "97910"))
    sources = (bnf, google_books, open_library) if french else (google_books, open_library, bnf)
    result = {}
    for source in sources:
        try:
            info = source(isbn)
        except Exception:
            continue
        for k in KEYS:
            if not result.get(k) and info.get(k):
                result[k] = info[k]
        if all(result.get(k) for k in KEYS):
            break
    return result if result.get("title") else None
