"""Tests du journal de l'interface web (booktek.web) ; sautés si pywebview n'est pas installé."""
import inspect
import logging
import os
import tempfile
import unittest

try:
    from booktek import lookup, web
except ImportError:
    web = None


@unittest.skipIf(web is None, "pywebview absent")
class JournalTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.api = web.Api(os.path.join(self.dir, "t.db"))
        self.path = web.setup_log(self.dir, verbose=False)
        self.addCleanup(self._close)

    def _close(self):
        for h in list(web.log.handlers):
            h.close()
            web.log.removeHandler(h)
        self.api._lib.con.close()

    def read(self):
        for h in web.log.handlers:
            h.flush()
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def test_parametres_conserves_pour_pywebview(self):
        self.assertEqual(inspect.getfullargspec(web.Api.lend).args, ["self", "book_id", "borrower", "due_date"])

    def test_standard_puis_verbeux(self):
        self.api.load()
        self.api.scan("123", "add")
        self.api.save_book(None, {"title": "A", "isbn": "9782070368228"})
        with self.assertRaises(ValueError):
            self.api.save_book(None, {"title": "B", "isbn": "9782070368228"})
        text = self.read()
        self.assertNotIn("load(", text)                      # lecture : verbeux seulement
        self.assertIn("scan : « 123 » n'est pas un ISBN valide.", text)
        self.assertIn("save_book : Un livre avec cet ISBN existe déjà.", text)
        self.api.set_setting("verbose_log", True)
        self.api.load()
        self.assertIn("load()", self.read())

    def test_cle_masquee(self):
        web.log.setLevel(logging.DEBUG)
        lookup._trace("https://www.googleapis.com/books/v1/volumes?q=isbn:1&key=SECRET")
        self.assertIn("key=***", self.read())
        self.assertNotIn("SECRET", self.read())


@unittest.skipIf(web is None, "pywebview absent")
class TelephoneTest(unittest.TestCase):
    """Page « photo par téléphone » : jeton exigé, photo transmise, image illisible refusée."""

    def test_envoi_photo(self):
        import threading
        import urllib.error
        import urllib.request
        got = []

        def on_photo(img):
            if img == b"mauvais":
                raise ValueError("Image illisible")
            got.append(img)
        srv = web.phone_server("jeton", on_photo)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_port}/jeton"
        self.assertIn(b"Prendre la photo", urllib.request.urlopen(url).read())
        self.assertEqual(urllib.request.urlopen(urllib.request.Request(url, data=b"JPEG")).read(), b"ok")
        self.assertEqual(got, [b"JPEG"])
        for bad_url, data in ((url[:-5] + "autre", None), (url, b"mauvais")):
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(urllib.request.Request(bad_url, data=data))
        self.assertEqual(got, [b"JPEG"])


@unittest.skipIf(web is None or web.Image is None, "pywebview ou Pillow absent")
class JaquetteTest(unittest.TestCase):
    """Retouche des jaquettes et téléphone utilisé comme scanner d'ISBN."""

    def image(self, size=(300, 200), book=None):
        import io
        img = web.Image.new("RGB", size, (200, 190, 170))  # la table
        if book:
            img.paste((20, 40, 120), book)  # la couverture
        buf = io.BytesIO()
        img.save(buf, "JPEG")
        return buf.getvalue()

    def size(self, data):
        import io
        return web.Image.open(io.BytesIO(data)).size

    def test_rotation_recadrage(self):
        self.assertEqual(self.size(web.adjust_image(self.image(), "left")), (200, 300))
        self.assertEqual(self.size(web.adjust_image(self.image(), "crop", [0.5, 0, 1, 0.5])), (150, 100))
        with self.assertRaises(ValueError):
            web.adjust_image(self.image(), "crop", [0.5, 0.5, 0.51, 0.9])

    def test_recadrage_auto(self):
        w, h = self.size(web.adjust_image(self.image(book=(100, 40, 220, 180)), "auto"))
        self.assertTrue(110 <= w <= 125 and 130 <= h <= 145, (w, h))
        with self.assertRaises(ValueError):  # rien à retirer
            web.adjust_image(self.image(), "auto")

    def test_isbn_par_telephone(self):
        from test_barcode import ean13_image
        api = web.Api(os.path.join(tempfile.mkdtemp(), "t.db"))
        self.addCleanup(api._lib.con.close)
        pushed = []
        api._push = lambda kind, **data: pushed.append((kind, data))
        self.assertIn("9782070368228", api._phone_isbn(ean13_image("9782070368228")))
        self.assertEqual(pushed, [("phone_isbn", {"isbn": "9782070368228"})])
        with self.assertRaises(ValueError):
            api._phone_isbn(self.image())
        self.assertIn("code-barres", web.phone_page("isbn"))


if __name__ == "__main__":
    unittest.main()
