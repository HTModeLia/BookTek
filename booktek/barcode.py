"""Lecture d'un code-barres EAN-13 (celui des ISBN) sur une photo, avec Pillow seul.

Utilisé par la page « scanner avec le téléphone » : le navigateur du téléphone
ne décode pas lui-même (``BarcodeDetector`` et la caméra en direct exigent une
page https, or le serveur local est en http), il envoie donc une photo.

Principe : on lit des lignes horizontales de l'image (au milieu d'abord), dans
les deux sens et aussi après un quart de tour, on les binarise par rapport à la
moyenne locale, puis on cherche les 59 barres et espaces d'un EAN-13 (gardes,
6 chiffres, garde centrale, 6 chiffres, garde). Chaque chiffre est le motif de
4 largeurs le plus proche ; la clé de contrôle écarte les lectures fausses.

shortcut: pas de correction de perspective ni de flou fort, il faut une photo nette et
de face ; passer à une bibliothèque (pyzbar) si les lectures ratent trop souvent.
"""
import io

from .isbn import _check13

#: Largeurs (en modules) des 4 éléments de chaque chiffre, codage L (espace, barre, espace, barre).
#: Le codage R a les mêmes largeurs (barre d'abord), le codage G les largeurs inversées.
L_WIDTHS = ((3, 2, 1, 1), (2, 2, 2, 1), (2, 1, 2, 2), (1, 4, 1, 1), (1, 1, 3, 2),
            (1, 2, 3, 1), (1, 1, 1, 4), (1, 3, 1, 2), (1, 2, 1, 3), (3, 1, 1, 2))
LEFT = [(d, "L", w) for d, w in enumerate(L_WIDTHS)] + [(d, "G", w[::-1]) for d, w in enumerate(L_WIDTHS)]
RIGHT = [(d, "R", w) for d, w in enumerate(L_WIDTHS)]
#: Premier chiffre, déduit de l'alternance L / G des 6 chiffres de gauche.
FIRST = ("LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL")


def _match(widths, table):
    """Chiffre dont le motif ressemble le plus aux 4 largeurs mesurées : ``(chiffre, codage)``, ou None si trop loin."""
    total = sum(widths)
    norm = [x * 7 / total for x in widths]
    err, digit, code = min((sum((a - b) ** 2 for a, b in zip(norm, t[2])), t[0], t[1]) for t in table)
    return (digit, code) if err < 0.8 else None


def _runs(row):
    """Ligne de pixels (gris) -> listes parallèles (sombre ?, largeur).

    Seuil local : à mi-chemin entre le plus sombre et le plus clair des blocs voisins (une moyenne
    serait faussée au bord du code, à côté de la marge blanche). Zone sans contraste : claire.
    """
    size = max(4, len(row) // 40)
    blocks = [row[k:k + size] for k in range(0, len(row), size)]
    lows, highs = [min(b) for b in blocks], [max(b) for b in blocks]
    dark, width = [], []
    for i, v in enumerate(row):
        b = i // size
        lo, hi = min(lows[max(0, b - 1):b + 2]), max(highs[max(0, b - 1):b + 2])
        d = hi - lo > 30 and v < (lo + hi) / 2
        if dark and dark[-1] == d:
            width[-1] += 1
        else:
            dark.append(d)
            width.append(1)
    return dark, width


def _decode(dark, width):
    """Cherche un EAN-13 valide dans une suite de largeurs ; retourne ses 13 chiffres ou None."""
    for i in range(1, len(width) - 58):
        if not dark[i]:
            continue
        w = width[i:i + 59]
        module = sum(w) / 95
        if i + 59 >= len(width) or min(width[i - 1], width[i + 59]) < 3 * module:  # marges blanches
            continue
        if any(not 0.4 * module < x < 2 * module for x in w[0:3] + w[27:32] + w[56:59]):
            continue
        left = [_match(w[3 + 4 * k:7 + 4 * k], LEFT) for k in range(6)]
        right = [_match(w[32 + 4 * k:36 + 4 * k], RIGHT) for k in range(6)]
        if None in left or None in right:
            continue
        parity = "".join(p for _, p in left)
        if parity not in FIRST:
            continue
        code = str(FIRST.index(parity)) + "".join(str(d) for d, _ in left + right)
        if _check13(code[:12]) == code[12]:
            return code
    return None


def read(data, rows=24):
    """Octets d'une photo -> les 13 chiffres du code EAN-13 lu, ou None.

    Le code doit être lu identique sur deux lignes : une seule lecture peut venir d'un motif du hasard.

    Lève une exception de Pillow si l'image est illisible.
    """
    from PIL import Image, ImageOps
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
    img.thumbnail((2000, 2000))
    for turned in (img, img.rotate(90, expand=True)):
        w, h = turned.size
        seen = set()
        # du milieu vers les bords : le code-barres est en général visé au centre
        for k in range(rows):
            step = (k + 1) // 2 * h // (rows + 2)
            y = h // 2 + (step if k % 2 else -step)
            row = list(turned.crop((0, y, w, y + 1)).tobytes())
            for line in (row, row[::-1]):
                code = _decode(*_runs(line))
                if code in seen:
                    return code
                if code:
                    seen.add(code)
                    break  # même ligne lue à l'envers : ce ne serait pas une seconde lecture
    return None
