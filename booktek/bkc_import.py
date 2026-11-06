"""Import des fichiers de collection Collectorz Book Collector (.bkc).

Le format est binaire et non documenté. On extrait de façon fiable
l'ISBN et le titre de chaque fiche en s'ancrant sur le chemin de la
vignette (« ...\\Thumbnails\\XXXX.png ») présent dans chaque livre :
l'ISBN est la dernière chaîne de type ISBN qui le précède, le titre est
la première chaîne lisible qui le suit (chaînes UTF-16 préfixées par
0x02 + longueur).
"""
import re

from .isbn import normalize

_U = lambda s: s.encode("utf-16-le")
_THUMB = re.compile(re.escape(_U("\\Thumbnails\\")) + rb"(?:[\x20-\x7e]\x00)+?" + re.escape(_U(".png")))
_ISBN = re.compile(rb"(?:[0-9Xx\-]\x00){10,17}")


def _readable(s):
    if not s or not all(c.isprintable() for c in s):
        return False
    return sum(c.isascii() and (c.isalpha() or c == " ") for c in s) >= len(s) / 2


def _title_after(data, pos):
    for k in range(pos, min(pos + 80, len(data) - 2)):
        n = data[k + 1]
        if data[k] != 0x02 or n == 0:
            continue
        raw = data[k + 2:k + 2 + 2 * n]
        if len(raw) != 2 * n:
            continue
        try:
            s = raw.decode("utf-16-le")
        except UnicodeDecodeError:
            continue
        if _readable(s):
            return s.strip()
    return ""


def parse(path):
    """Retourne une liste de dicts {isbn, title} lus dans le fichier .bkc."""
    with open(path, "rb") as f:
        data = f.read()
    if b"Collectorz.com" not in data[:64] or b"Book" not in data[:64]:
        raise ValueError("Ce fichier n'est pas une collection Book Collector (.bkc).")
    books = []
    for m in _THUMB.finditer(data):
        window = data[max(0, m.start() - 600):m.start()]
        cands = [c.group().decode("utf-16-le") for c in _ISBN.finditer(window)]
        cands = [c for c in cands if sum(ch.isdigit() for ch in c) >= 9]
        raw_isbn = cands[-1] if cands else ""
        title = _title_after(data, m.end())
        if not title and not raw_isbn:
            continue
        isbn = normalize(raw_isbn) or (re.sub(r"[^0-9Xx]", "", raw_isbn) or None)
        books.append({"isbn": isbn, "title": title or "(titre inconnu)"})
    return books
