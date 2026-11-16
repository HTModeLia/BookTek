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


if __name__ == "__main__":
    unittest.main()
