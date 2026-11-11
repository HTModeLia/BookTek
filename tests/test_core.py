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
from booktek.lookup import _bnf_pages, _bnf_person  # noqa: E402


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

    def test_fetch_cover(self):
        from unittest import mock
        from booktek import lookup
        info = {"title": "T", "summary": "S", "cover": "https://x/c.jpg"}
        with mock.patch.object(lookup, "bnf", return_value=info),                 mock.patch.object(lookup, "google_books", return_value={}),                 mock.patch.object(lookup, "open_library", return_value={}):
            with mock.patch.object(lookup, "_get_bytes", return_value=b"JPEG"):
                self.assertEqual(lookup.fetch("9782226440235")["cover"], b"JPEG")
            with mock.patch.object(lookup, "_get_bytes", side_effect=OSError):
                self.assertNotIn("cover", lookup.fetch("9782226440235"))

    def test_fetch_merges_all_sources(self):
        """Chaque source complète les autres ; résumé le plus long ; couverture de repli si la 1re échoue."""
        from unittest import mock
        from booktek import lookup
        bnf = {"title": "Titre BnF", "authors": "A", "pages": "300", "cover": "https://bnf/c.jpg"}
        google = {"title": "Titre Google", "summary": "court", "genre": "Romance", "cover": "https://g/c.jpg"}
        ol = {"title": "Titre OL", "summary": "un résumé bien plus long", "publisher": "J'ai lu"}
        get = lambda url: b"G" if url.startswith("https://g/") else (_ for _ in ()).throw(OSError())
        with mock.patch.object(lookup, "bnf", return_value=bnf), \
                mock.patch.object(lookup, "google_books", return_value=google), \
                mock.patch.object(lookup, "open_library", return_value=ol), \
                mock.patch.object(lookup, "_get_bytes", side_effect=get):
            r = lookup.fetch("9782290254738")  # ISBN français : BnF prioritaire
        self.assertEqual(r["title"], "Titre BnF")
        self.assertEqual((r["genre"], r["publisher"], r["pages"]), ("Romance", "J'ai lu", "300"))
        self.assertEqual(r["summary"], "un résumé bien plus long")
        self.assertEqual(r["cover"], b"G")

    def test_find_covers_filters(self):
        """Jaquettes : doublons et vignettes vides écartés, ordre conservé, URL en erreur ignorée."""
        from unittest import mock
        from booktek import lookup
        imgs = {"a": b"A" * 2000, "b": b"A" * 2000, "c": b"tiny", "d": b"D" * 3000}

        def get(url):
            if url == "e":
                raise OSError
            return imgs[url]
        with mock.patch.object(lookup, "cover_urls", return_value=["a", "b", "c", "e", "d"]), \
                mock.patch.object(lookup, "_get_bytes", side_effect=get):
            self.assertEqual(lookup.find_covers("x", "t", ""), [b"A" * 2000, b"D" * 3000])

    def test_bnf_pages(self):
        self.assertEqual(_bnf_pages("1 vol. (586 p.) ; 24 cm"), "586")
        self.assertEqual(_bnf_pages("1 vol. (non paginé [47] p.) : ill. en coul. ; 22 cm"), "47")
        self.assertEqual(_bnf_pages("1 vol. ; 22 cm"), "")

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

    def test_genre(self):
        self.lib.fill_missing(self.bid, {"genre": "Romance"})
        self.assertEqual(len(self.lib.search("roman")), 1)  # recherche plein texte sur le genre
        self.lib.fill_missing(self.bid, {"genre": "Fiction"})  # genre déjà saisi : conservé
        self.assertEqual(self.lib.book(self.bid)["genre"], "Romance")


class V12Test(unittest.TestCase):
    """Version 1.2 : migration, annuaire, rangement, tri."""

    def test_migration_keeps_old_data(self):
        import sqlite3
        from booktek import db as dbmod
        path = os.path.join(tempfile.mkdtemp(), "old.db")
        con = sqlite3.connect(path)  # base au format 1.1 (schéma initial, user_version 0)
        con.executescript(dbmod.SCHEMA + """
            INSERT INTO books (isbn, title, added_at) VALUES ('9782290254738', 'Bridgerton', '2026-01-01');
            INSERT INTO loans (book_id, borrower, loan_date) VALUES (1, 'Marie', '2026-01-02');""")
        con.close()
        lib = Library(path)
        self.addCleanup(lib.con.close)
        self.assertEqual(lib.con.execute("PRAGMA user_version").fetchone()[0], len(dbmod.MIGRATIONS))
        self.assertEqual((lib.book(1)["shelf"], lib.book(1)["summary"]), ("", ""))
        self.assertEqual(lib.borrowers(), ["Marie"])
        lib.con.close()
        Library(path).con.close()  # réouverture : pas de nouvelle migration

    def test_directory_rename_delete(self):
        lib = Library(":memory:")
        self.addCleanup(lib.con.close)
        b = lib.add_book({"title": "A"})
        lib.lend(b, "Marie", None)
        row = lib.directory()[0]
        self.assertEqual((row["name"], row["active"], row["total"]), ("Marie", 1, 1))
        self.assertEqual(row["oldest_active"], lib.active_loan(b)["loan_date"])
        lib.save_borrower("Marie", {"name": "Marie D.", "phone": "06"})
        self.assertEqual(lib.active_loan(b)["borrower"], "Marie D.")
        with self.assertRaises(ValueError):
            lib.delete_borrower("Marie D.")
        lib.save_borrower(None, {"name": "Paul"})
        with self.assertRaises(ValueError):
            lib.save_borrower(None, {"name": "Paul"})
        lib.return_book(b)
        lib.delete_borrower("Marie D.")
        self.assertEqual([r["name"] for r in lib.directory()], ["Paul"])
        self.assertEqual(len(lib.history()), 1)  # historique conservé

    def test_place_and_sort(self):
        from booktek.app import days_since, place, sort_key
        self.assertEqual(place({"location": "Salon", "shelf": "2", "box": "", "depth": "1"}), "Salon › É2 › R1")
        codes = ["Salon › É10 › B1", "Salon › É2 › B3", "Salon › É2 › B1"]
        self.assertEqual(sorted(codes, key=sort_key), ["Salon › É2 › B1", "Salon › É2 › B3", "Salon › É10 › B1"])
        dates = ["01/02/2025", "15/01/2026", "31/12/2024"]
        self.assertEqual(sorted(dates, key=sort_key), ["31/12/2024", "01/02/2025", "15/01/2026"])
        authors = ["Julia Quinn", "Juliette Benzoni", "Marie-Bernadette Dupuy"]
        self.assertEqual(sorted(authors, key=lambda a: sort_key(a, "authors"))[0], "Juliette Benzoni")
        self.assertEqual(days_since("2026-01-01", "2026-01-31"), 30)


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
