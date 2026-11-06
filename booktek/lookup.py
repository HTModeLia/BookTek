"""Recherche des informations d'un livre en ligne à partir de son ISBN."""
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .isbn import to10

HEADERS = {"User-Agent": "BookTek/1.0"}
KEYS = ("title", "authors", "publisher", "year", "pages")


def _get_json(url, timeout=8):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _year(text):
    m = re.search(r"\d{4}", text or "")
    return m.group() if m else ""


def google_books(isbn):
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


_DC = "{http://purl.org/dc/elements/1.1/}"


def _bnf_query(isbn):
    query = urllib.parse.quote(f'bib.isbn adj "{isbn}"')
    url = ("https://catalogue.bnf.fr/api/SRU?version=1.2&operation=searchRetrieve"
           f"&recordSchema=dublincore&maximumRecords=1&query={query}")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=8) as resp:
        root = ET.fromstring(resp.read())
    return next(root.iter("{http://www.openarchives.org/OAI/2.0/oai_dc/}dc"), None)


def _bnf_person(creator):
    # « Cantini, Barbara (1977-....). Auteur du texte » -> « Barbara Cantini »
    name = re.split(r"\s*\(|\.\s", creator)[0].strip()
    last, _, first = name.partition(",")
    return f"{first.strip()} {last.strip()}".strip()


def bnf(isbn):
    """Catalogue de la Bibliothèque nationale de France (idéal pour les livres français)."""
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
    """Interroge plusieurs catalogues et combine leurs réponses.

    La BnF passe en premier pour les ISBN français (978-2, 979-10) ;
    Google Books limite fortement les requêtes sans clé d'API (erreur 429).
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
