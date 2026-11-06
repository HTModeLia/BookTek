"""Tests du module de mise à jour, sans réseau.

Un faux exécutable est créé dans un dossier temporaire et
``updater.exe_path`` est redirigé vers lui. Les téléchargements utilisent
des URL ``file://``, que :mod:`urllib` sait ouvrir.
"""
import hashlib
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from booktek import updater  # noqa: E402


class VersionTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(updater.parse_version("v1.10.2"), (1, 10, 2))
        self.assertEqual(updater.parse_version("1.2"), (1, 2))
        self.assertEqual(updater.parse_version(""), (0,))

    def test_is_newer(self):
        self.assertTrue(updater.is_newer("1.10.0", "1.9.9"))
        self.assertTrue(updater.is_newer("v2.0.0", "1.9"))
        self.assertFalse(updater.is_newer("1.1.0", "1.1.0"))
        self.assertFalse(updater.is_newer("1.0.9", "1.1.0"))


class DownloadInstallTest(unittest.TestCase):
    """Téléchargement, vérification, mise en attente et installation."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.exe = os.path.join(self.dir, "BookTek.exe")
        pathlib.Path(self.exe).write_bytes(b"ancienne version")
        self.payload = b"nouvelle version " * 1000
        src = os.path.join(self.dir, "source.bin")
        pathlib.Path(src).write_bytes(self.payload)
        self.release = updater.Release(
            version="99.0.0", url=pathlib.Path(src).as_uri(), size=len(self.payload),
            sha256=hashlib.sha256(self.payload).hexdigest(), notes="", page="")
        patcher = mock.patch.object(updater, "exe_path", return_value=self.exe)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_download_then_pending(self):
        seen = []
        updater.download(self.release, lambda r, t: seen.append(r))
        self.assertEqual(seen[-1], len(self.payload))
        self.assertEqual(updater.pending_version(), "99.0.0")
        self.assertFalse(os.path.exists(self.exe + ".part"))

    def test_bad_checksum_rejected(self):
        self.release.sha256 = "0" * 64
        with self.assertRaises(updater.UpdateError):
            updater.download(self.release)
        self.assertIsNone(updater.pending_version())
        self.assertFalse(os.path.exists(self.exe + ".new"))

    def test_bad_size_rejected(self):
        self.release.size += 1
        with self.assertRaises(updater.UpdateError):
            updater.download(self.release)
        self.assertFalse(os.path.exists(self.exe + ".new"))

    def test_tampered_pending_discarded(self):
        updater.download(self.release)
        pathlib.Path(self.exe + ".new").write_bytes(b"modifie apres coup")
        self.assertIsNone(updater.pending_version())
        self.assertFalse(os.path.exists(self.exe + ".new"))

    def test_older_pending_discarded(self):
        self.release.version = "0.0.1"
        updater.download(self.release)
        self.assertIsNone(updater.pending_version())

    def test_apply_replaces_exe_and_restarts(self):
        updater.download(self.release)
        with mock.patch.object(updater, "restart") as restart:
            updater.apply_and_restart()
        restart.assert_called_once()
        self.assertEqual(pathlib.Path(self.exe).read_bytes(), self.payload)
        olds = [f for f in os.listdir(self.dir) if ".old-" in f]
        self.assertEqual(len(olds), 1)
        self.assertIsNone(updater.pending_version())
        updater.cleanup_old()
        self.assertFalse(any(".old-" in f for f in os.listdir(self.dir)))

    def test_apply_without_pending_fails(self):
        with self.assertRaises(updater.UpdateError):
            updater.apply_and_restart()
        self.assertEqual(pathlib.Path(self.exe).read_bytes(), b"ancienne version")

    def test_startup_noop_when_not_frozen(self):
        updater.download(self.release)
        self.assertFalse(updater.install_pending_on_startup())  # tests lancés depuis les sources


if __name__ == "__main__":
    unittest.main()
