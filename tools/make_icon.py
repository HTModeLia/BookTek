"""Dessine l'icône de BookTek (``booktek/icon.ico``) avec Pillow.

Livre ouvert blanc sur fond bleu, traversé par le trait rouge d'un lecteur
de code-barres. Dessiné en 1024 px puis réduit, pour des bords nets à toutes
les tailles (16 à 256 px). Relancer après modification :
``python tools/make_icon.py``.
"""
import os

from PIL import Image, ImageDraw

S = 1024
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def draw():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((32, 32, S - 32, S - 32), radius=200, fill="#1f5fa8")
    # Livre ouvert : deux pages légèrement inclinées, reliure au centre.
    left = [(150, 300), (490, 360), (490, 800), (150, 740)]
    right = [(S - x, y) for x, y in left]
    d.polygon(left, fill="white")
    d.polygon(right, fill="white")
    d.polygon([(150, 740), (490, 800), (534, 800), (S - 150, 740), (S - 150, 770), (534, 830), (490, 830),
               (150, 770)], fill="#cfe0f5")  # tranche des pages
    for i in range(4):  # lignes de texte
        y = 430 + i * 85
        d.line([(205, y), (440, y + 42)], fill="#9db9dd", width=26)
        d.line([(S - 205, y), (S - 440, y + 42)], fill="#9db9dd", width=26)
    d.rounded_rectangle((90, 520, S - 90, 576), radius=28, fill="#e8423f")  # trait du scanner
    return img


if __name__ == "__main__":
    out = os.path.join(ROOT, "booktek", "icon.ico")
    draw().resize((256, 256), Image.LANCZOS).save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                                            (64, 64), (128, 128), (256, 256)])
    print(out)
