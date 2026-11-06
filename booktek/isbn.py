"""Validation et normalisation des ISBN (tout est ramené en ISBN-13)."""
import re


def _clean(raw):
    return re.sub(r"[^0-9Xx]", "", raw or "").upper()


def _check13(first12):
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(first12))
    return str((10 - total % 10) % 10)


def is_valid13(s):
    return len(s) == 13 and s.isdigit() and _check13(s[:12]) == s[12]


def is_valid10(s):
    if len(s) != 10 or not s[:9].isdigit() or not (s[9].isdigit() or s[9] == "X"):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(s))
    return total % 11 == 0


def to10(isbn13):
    """ISBN-13 (préfixe 978) -> ISBN-10, sinon None."""
    if not (isbn13 and len(isbn13) == 13 and isbn13.startswith("978")):
        return None
    body = isbn13[3:12]
    check = (11 - sum((10 - i) * int(c) for i, c in enumerate(body)) % 11) % 11
    return body + ("X" if check == 10 else str(check))


def normalize(raw):
    """Retourne l'ISBN-13 correspondant à `raw`, ou None s'il n'est pas valide.

    Accepte ISBN-10, ISBN-13 (avec ou sans tirets) et les codes EAN avec
    add-on de prix (2 ou 5 chiffres) que certaines douchettes renvoient.
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
