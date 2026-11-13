"""Sauvegardes : création, rotation, restauration avec copie de sécurité, refus d'une archive invalide."""
import os
import shutil
import sqlite3
import tempfile
import unittest
import zipfile

from booktek import backup
from booktek.db import Library


class BackupTest(unittest.TestCase):
    """Base et jaquettes dans un dossier temporaire, comme à côté de BookTek.exe."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.db = os.path.join(self.dir, "booktek.db")
        self.lib = Library(self.db)
        self.bid = self.lib.add_book({"isbn": "9782290254738", "title": "Bridgerton 1&2"})
        os.makedirs(os.path.join(self.dir, "covers"))
        self.cover = os.path.join(self.dir, "covers", f"{self.bid}.jpg")
        with open(self.cover, "wb") as f:
            f.write(b"jpeg-factice")

    def tearDown(self):
        self.lib.con.close()

    def test_create_and_restore(self):
        name = backup.create(self.db)
        self.assertEqual(backup.list_backups(self.db)[0]["name"], name)
        self.lib.delete_book(self.bid)
        os.remove(self.cover)
        safety = backup.restore(self.db, name, self.lib.con.close)
        self.lib = Library(self.db)  # comme web.Api.restore_backup
        self.assertIsNotNone(self.lib.book(self.bid))
        self.assertTrue(os.path.exists(self.cover))
        self.assertIn(safety, [r["name"] for r in backup.list_backups(self.db)])

    def test_rotation_keeps_ten(self):
        for _ in range(backup.KEEP + 2):
            backup.create(self.db)
        self.assertEqual(len(backup.list_backups(self.db)), backup.KEEP)

    def test_auto_once_a_day(self):
        self.assertIsNotNone(backup.auto(self.db))
        self.assertIsNone(backup.auto(self.db))

    def test_invalid_archive_refused(self):
        bad = os.path.join(backup.folder(self.db), "booktek-20200101-000000-manual.zip")
        os.makedirs(backup.folder(self.db), exist_ok=True)
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("../booktek.db", "x")  # chemin qui sort du dossier : refusé avant toute écriture
        with self.assertRaises(ValueError):
            backup.restore(self.db, os.path.basename(bad), self.lib.con.close)
        self.assertIsNotNone(self.lib.book(self.bid))  # la base actuelle n'a pas été touchée

    def test_unknown_name_refused(self):
        with self.assertRaises(ValueError):
            backup.restore(self.db, "../../booktek.db", self.lib.con.close)


if __name__ == "__main__":
    unittest.main()
