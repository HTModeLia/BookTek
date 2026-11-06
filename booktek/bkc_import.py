"""Import des fichiers de collection Collectorz *Book Collector* (``.bkc``).

Le format ``.bkc`` est binaire, propriétaire et non documenté. Ce module
n'en fait pas un décodage complet : il extrait de façon fiable **l'ISBN et le
titre** de chaque livre, ce qui suffit ensuite à compléter les fiches via
:mod:`booktek.lookup`.

Ce qu'on sait du format (observé, pas spécifié) :

* l'en-tête contient les chaînes ASCII ``Collectorz.com`` et ``Book`` ;
* les textes sont en UTF-16 LE. Les chaînes courtes sont précédées d'un
  octet ``0x02`` puis d'un octet donnant leur longueur **en caractères**
  (``02 00`` = chaîne vide) ;
* chaque fiche livre contient, dans cet ordre : un GUID, le chemin de la
  couverture, l'ISBN, le chemin de la vignette
  (``...\\Thumbnails\\<hash>.png``), puis le titre et le titre de tri ;
* les auteurs sont stockés dans une table séparée et reliés aux livres par
  des index binaires : ils ne sont pas extraits.

Stratégie : on s'ancre sur chaque chemin de vignette, présent une fois par
livre. L'ISBN est la dernière chaîne « de type ISBN » dans les 600 octets qui
précèdent ; le titre est la première chaîne lisible préfixée par sa longueur
dans les 80 octets qui suivent (on saute ainsi les chaînes vides et les
octets de structure intermédiaires).
"""
import re

from .isbn import normalize

_U = lambda s: s.encode("utf-16-le")
# Chemin de vignette en UTF-16 : « \Thumbnails\ » + caractères ASCII + « .png ».
_THUMB = re.compile(re.escape(_U("\\Thumbnails\\")) + rb"(?:[\x20-\x7e]\x00)+?" + re.escape(_U(".png")))
# Suite de 10 à 17 chiffres / X / tirets en UTF-16 (ISBN-10 ou -13, avec ou sans tirets).
_ISBN = re.compile(rb"(?:[0-9Xx\-]\x00){10,17}")


def _readable(s):
    """Heuristique : ``s`` ressemble-t-il à un vrai texte (et non à des octets de structure) ?

    Au moins la moitié des caractères doivent être des lettres ASCII ou des
    espaces, ce qui écarte les faux positifs comme « ȀȀ » produits par une
    suite d'octets ``02 02 02 02``.
    """
    if not s or not all(c.isprintable() for c in s):
        return False
    return sum(c.isascii() and (c.isalpha() or c == " ") for c in s) >= len(s) / 2


def _title_after(data, pos):
    """Première chaîne lisible préfixée par ``0x02 <longueur>`` dans les 80 octets après ``pos``."""
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
    """Lit un fichier ``.bkc`` et retourne la liste des livres ``[{isbn, title}, …]``.

    L'ISBN est normalisé en ISBN-13 quand il est valide. Un ISBN dont la clé
    de contrôle est fausse est conservé tel quel (chiffres seuls) pour que
    l'utilisateur puisse le corriger ; ``None`` si la fiche n'a pas d'ISBN.

    Lève :class:`ValueError` si le fichier n'est pas une collection Book
    Collector.
    """
    with open(path, "rb") as f:
        data = f.read()
    if b"Collectorz.com" not in data[:64] or b"Book" not in data[:64]:
        raise ValueError("Ce fichier n'est pas une collection Book Collector (.bkc).")
    books = []
    for m in _THUMB.finditer(data):
        window = data[max(0, m.start() - 600):m.start()]
        cands = [c.group().decode("utf-16-le") for c in _ISBN.finditer(window)]
        # Écarte les suites de tirets ou de X qui ne sont pas des ISBN.
        cands = [c for c in cands if sum(ch.isdigit() for ch in c) >= 9]
        raw_isbn = cands[-1] if cands else ""
        title = _title_after(data, m.end())
        if not title and not raw_isbn:
            continue
        isbn = normalize(raw_isbn) or (re.sub(r"[^0-9Xx]", "", raw_isbn) or None)
        books.append({"isbn": isbn, "title": title or "(titre inconnu)"})
    return books
