"""Tests de la lecture des codes-barres EAN-13 (booktek.barcode) sur des images générées."""
import io
import unittest

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    Image = None

from booktek import barcode


def ean13_image(code, module=4, angle=0, blur=0):
    """Image JPEG d'un code EAN-13, posée sur un fond gris clair comme une photo de livre."""
    parity = barcode.FIRST[int(code[0])]
    bits = "101"
    for d, p in zip(code[1:7], parity):
        w = barcode.L_WIDTHS[int(d)] if p == "L" else barcode.L_WIDTHS[int(d)][::-1]
        bits += "".join(("0" if k % 2 == 0 else "1") * n for k, n in enumerate(w))
    bits += "01010"
    for d in code[7:]:
        bits += "".join(("1" if k % 2 == 0 else "0") * n for k, n in enumerate(barcode.L_WIDTHS[int(d)]))
    bits += "101"
    img = Image.new("L", ((len(bits) + 30) * module, 60 * module), 245)
    draw = ImageDraw.Draw(img)
    for k, b in enumerate(bits):
        if b == "1":
            x = (15 + k) * module
            draw.rectangle((x, 5 * module, x + module - 1, 55 * module), fill=20)
    photo = Image.new("L", (img.width * 3, img.height * 3), 170)  # le livre autour du code
    photo.paste(img, (img.width, img.height))
    photo = photo.rotate(angle, expand=True, fillcolor=170)
    if blur:
        photo = photo.filter(ImageFilter.GaussianBlur(blur))
    buf = io.BytesIO()
    photo.convert("RGB").save(buf, "JPEG", quality=85)
    return buf.getvalue()


@unittest.skipIf(Image is None, "Pillow absent")
class LectureTest(unittest.TestCase):
    def test_codes_lus_dans_tous_les_sens(self):
        for code, angle in (("9782070368228", 0), ("9780306406157", 90), ("9791032102534", 180),
                            ("9782253004226", 270)):
            with self.subTest(code=code, angle=angle):
                self.assertEqual(barcode.read(ean13_image(code, angle=angle)), code)

    def test_flou_et_petit(self):
        self.assertEqual(barcode.read(ean13_image("9782070368228", module=3, blur=1)), "9782070368228")

    def test_sans_code(self):
        buf = io.BytesIO()
        Image.new("RGB", (400, 300), "white").save(buf, "JPEG")
        self.assertIsNone(barcode.read(buf.getvalue()))


if __name__ == "__main__":
    unittest.main()
