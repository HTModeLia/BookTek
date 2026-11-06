"""Tests unitaires de BookTek (sans réseau ni interface graphique).

Lancement : ``python -m unittest discover -s tests``

Le test d'import ``.bkc`` utilise le fichier d'exemple
``books_pour_aurelien.bkc`` à la racine du projet. Ce fichier contient des
données personnelles et n'est pas versionné : le test est sauté s'il est
absent.
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from booktek import bkc_import  # noqa: E402
from booktek.db import Library  # noqa: E402
from booktek.isbn import normalize, to10  # noqa: E402
from booktek.lookup import _bnf_person  # noqa: E402


class IsbnTest(unittest.TestCase):
    """Normalisation et conversion des ISBN, analyse des noms d'auteurs BnF."""

    def test_isbn13(self):
        self.assertEqual(normalize("978-2-290-25473-8"), "9782290254738")

    def test_isbn10_converted(self):
        self.assertEqual(normalize("2-7242-7568-3"), "9782724275681")
        self.assertIsNone(normalize("2-7242-7568-1"))  # clé fausse (présent dans le .bkc d'exemple)

    def test_ean_addon(self):
        self.assertEqual(normalize("978229025473851234"), "9782290254738")

    def test_to10(self):
        self.assertEqual(to10("9782744196231"), "2744196231")
        self.assertIsNone(to10("9791032704426"))

    def test_bnf_person(self):
        self.assertEqual(_bnf_person("Cantini, Barbara (1977-....). Auteur du texte"), "Barbara Cantini")
        self.assertEqual(_bnf_person("Collectif. Auteur du texte"), "Collectif")

    def test_invalid(self):
        self.assertIsNone(normalize("9782290254739"))
        self.assertIsNone(normalize("3017620422003"))  # EAN non livre
        self.assertIsNone(normalize("abc"))


class LibraryTest(unittest.TestCase):
    """Base SQLite en mémoire : prêts, retours, recherche, complément des fiches."""

    def setUp(self):
        self.lib = Library(":memory:")
        self.addCleanup(self.lib.con.close)
        self.bid = self.lib.add_book({"isbn": "9782290254738", "title": "Bridgerton 1&2"})

    def test_lend_and_return(self):
        self.lib.lend(self.bid, "Marie", "2026-12-01")
        with self.assertRaises(ValueError):
            self.lib.lend(self.bid, "Paul", None)
        with self.assertRaises(ValueError):
            self.lib.delete_book(self.bid)
        self.assertEqual(self.lib.stats()["lent"], 1)
        loan = self.lib.return_book(self.bid)
        self.assertEqual(loan["borrower"], "Marie")
        self.assertIsNone(self.lib.return_book(self.bid))
        self.lib.lend(self.bid, "Paul", None)
        self.assertEqual(len(self.lib.history()), 2)
        self.assertEqual(self.lib.borrowers()[0], "Paul")

    def test_fill_missing_keeps_title(self):
        self.lib.fill_missing(self.bid, {"title": "Autre", "authors": "Julia Quinn"})
        b = self.lib.book(self.bid)
        self.assertEqual((b["title"], b["authors"]), ("Bridgerton 1&2", "Julia Quinn"))

    def test_search(self):
        self.assertEqual(len(self.lib.search("bridger")), 1)
        self.assertEqual(len(self.lib.search("zzz")), 0)


class BkcImportTest(unittest.TestCase):
    """Lecture des fichiers Book Collector (.bkc)."""

    PATH = os.path.join(ROOT, "books_pour_aurelien.bkc")

    @unittest.skipUnless(os.path.exists(PATH), "fichier exemple absent")
    def test_parse_sample(self):
        books = bkc_import.parse(self.PATH)
        self.assertEqual(len(books), 59)
        self.assertEqual(books[0], {"isbn": "9782290254738", "title": "La Chronique Des Bridgerton: Tomes 1&2"})
        bad = [b for b in books if len(b["isbn"]) != 13]
        self.assertEqual(bad, [{"isbn": "2724275681", "title": "Les Treize Vents Tome 2 Le Réfugié"}])

    def test_rejects_other_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bkc") as f:
            f.write(b"not a collection")
        try:
            with self.assertRaises(ValueError):
                bkc_import.parse(f.name)
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
