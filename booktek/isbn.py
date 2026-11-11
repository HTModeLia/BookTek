"""Validation et normalisation des ISBN.

Toute l'application manipule les ISBN sous une forme unique : **ISBN-13 sans
tirets** (ex. ``9782290254738``). C'est la clé de recherche des livres en base,
il faut donc toujours passer par :func:`normalize` avant de comparer ou de
stocker un ISBN saisi ou scanné.

Rappel des algorithmes de clé de contrôle :

* ISBN-13 : les 12 premiers chiffres sont pondérés alternativement par 1 et 3 ;
  la clé est ce qu'il faut ajouter à la somme pour atteindre un multiple de 10.
* ISBN-10 : les 10 caractères sont pondérés de 10 à 1 ; la somme doit être un
  multiple de 11. La clé peut valoir 10, notée ``X``.
"""
import re


def _clean(raw):
    """Ne garde que les chiffres et le ``X`` (tirets, espaces… supprimés), en majuscules."""
    return re.sub(r"[^0-9Xx]", "", raw or "").upper()


def find_in_lines(text):
    """ISBN-13 trouvés dans ``text`` : le premier ISBN valide de chaque ligne, sans doublon, dans l'ordre.

    Une seule valeur par ligne, car un tableau (CSV…) peut contenir dans
    d'autres colonnes les ISBN d'autres éditions : on retient la première
    colonne qui en contient un.
    """
    found = (next(filter(None, map(normalize, re.findall(r"[0-9Xx-]{10,}", line))), None)
             for line in text.splitlines())
    return list(dict.fromkeys(filter(None, found)))


def _check13(first12):
    """Calcule la clé de contrôle ISBN-13 à partir des 12 premiers chiffres."""
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(first12))
    return str((10 - total % 10) % 10)


def is_valid13(s):
    """Indique si ``s`` (13 chiffres, sans tirets) a une clé ISBN-13 correcte."""
    return len(s) == 13 and s.isdigit() and _check13(s[:12]) == s[12]


def is_valid10(s):
    """Indique si ``s`` (10 caractères, sans tirets) est un ISBN-10 valide."""
    if len(s) != 10 or not s[:9].isdigit() or not (s[9].isdigit() or s[9] == "X"):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(s))
    return total % 11 == 0


def to10(isbn13):
    """Convertit un ISBN-13 en ISBN-10.

    Seuls les ISBN-13 commençant par ``978`` ont un équivalent ISBN-10 ; pour
    les autres (``979``…) la fonction retourne ``None``. Sert à interroger les
    catalogues dont les anciennes notices ne sont indexées qu'en ISBN-10.
    """
    if not (isbn13 and len(isbn13) == 13 and isbn13.startswith("978")):
        return None
    body = isbn13[3:12]
    check = (11 - sum((10 - i) * int(c) for i, c in enumerate(body)) % 11) % 11
    return body + ("X" if check == 10 else str(check))


def normalize(raw):
    """Retourne l'ISBN-13 correspondant à ``raw``, ou ``None`` s'il n'est pas valide.

    Formats acceptés :

    * ISBN-13, avec ou sans tirets/espaces ;
    * ISBN-10, converti en ISBN-13 (préfixe ``978`` et nouvelle clé) ;
    * code EAN suivi d'une extension de prix de 2 ou 5 chiffres (15 ou 18
      chiffres au total), que certaines douchettes renvoient : l'extension est
      ignorée.

    Les EAN-13 qui ne sont pas des livres (préfixe autre que 978/979) sont
    refusés, de même que tout code dont la clé de contrôle est fausse.
    """
    s = _clean(raw)
    if len(s) in (15, 18) and s[:3] in ("978", "979"):
        s = s[:13]
    if len(s) == 13 and s[:3] in ("978", "979") and is_valid13(s):
        return s
    if is_valid10(s):
        base = "978" + s[:9]
        return base + _check13(base)
    return None
