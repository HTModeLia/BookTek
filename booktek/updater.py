"""Mise à jour automatique depuis les releases GitHub du dépôt.

Fonctionnement
--------------
1. **Vérification à chaud** : pendant que l'application tourne, un thread
   interroge l'API GitHub (dernière release publiée) au démarrage puis
   périodiquement. Si la version publiée est plus récente que
   :data:`booktek.__version__`, l'exécutable est téléchargé à côté de l'exe
   courant sous le nom ``BookTek.exe.new``, et son empreinte SHA-256 est
   vérifiée par rapport à celle que GitHub publie pour le fichier.
2. **Installation** : au démarrage suivant (:func:`install_pending_on_startup`),
   ou immédiatement quand l'utilisateur clique sur « Mettre à jour »
   (:func:`apply_and_restart`).

Windows interdit d'écraser un exe en cours d'exécution, mais autorise à le
**renommer**. L'installation renomme donc ``BookTek.exe`` en
``BookTek.exe.old-<horodatage>``, place la nouvelle version sous le nom
``BookTek.exe``, la lance et quitte. Les ``.old-*`` sont supprimés au
démarrage suivant, quand plus aucun processus ne les utilise.

La mise à jour automatique ne s'applique qu'à l'exécutable PyInstaller
(``sys.frozen``) placé dans un dossier accessible en écriture. Depuis les
sources, on signale seulement qu'une nouvelle version existe.

Fichiers utilisés, à côté de l'exe :

==========================  ===============================================
``BookTek.exe.part``        téléchargement en cours
``BookTek.exe.new``         nouvelle version téléchargée et vérifiée
``BookTek.exe.update.json`` version et empreinte du ``.new``
``BookTek.exe.old-*``       ancienne version, supprimée au démarrage suivant
==========================  ===============================================
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass

from . import __version__

#: Dépôt GitHub dont on suit les releases.
REPO = "HTModeLia/BookTek"
#: Point d'API interrogé. Surchargeable par variable d'environnement pour les tests.
API_URL = os.environ.get("BOOKTEK_UPDATE_API", f"https://api.github.com/repos/{REPO}/releases/latest")
#: Nom du fichier à télécharger dans les assets de la release.
ASSET_NAME = "BookTek.exe"
#: Intervalle entre deux vérifications à chaud, en secondes.
CHECK_INTERVAL = 6 * 3600
HEADERS = {"User-Agent": f"BookTek/{__version__}", "Accept": "application/vnd.github+json"}
TIMEOUT = 15


class UpdateError(Exception):
    """Échec de vérification, de téléchargement ou d'installation (message affichable)."""


@dataclass
class Release:
    """Release GitHub contenant un exécutable BookTek."""
    version: str      # ex. « 1.1.0 » (tag sans le « v »)
    url: str          # URL de téléchargement de l'exe
    size: int         # taille en octets
    sha256: str       # empreinte attendue (hexadécimal), « » si GitHub ne la fournit pas
    notes: str        # description de la release (Markdown)
    page: str         # page web de la release


# ---- versions -----------------------------------------------------------
def parse_version(text):
    """« v1.10.2 » -> (1, 10, 2). Les parties non numériques sont ignorées."""
    return tuple(int(n) for n in re.findall(r"\d+", text or "")[:3]) or (0,)


def is_newer(version, current=__version__):
    """Indique si ``version`` est strictement plus récente que ``current``."""
    return parse_version(version) > parse_version(current)


# ---- emplacements ---------------------------------------------------------
def exe_path():
    """Chemin de l'exécutable en cours."""
    return os.path.abspath(sys.executable)


def _paths():
    exe = exe_path()
    return {"exe": exe, "part": exe + ".part", "new": exe + ".new", "meta": exe + ".update.json"}


def can_self_update():
    """Vrai si l'application tourne en exe PyInstaller dans un dossier modifiable."""
    return bool(getattr(sys, "frozen", False)) and os.access(os.path.dirname(exe_path()), os.W_OK)


# ---- GitHub -------------------------------------------------------------
def latest_release():
    """Interroge GitHub et retourne la dernière :class:`Release`, ou ``None`` si elle n'a pas d'exe.

    Lève :class:`UpdateError` en cas d'erreur réseau ou de réponse inattendue.
    """
    try:
        req = urllib.request.Request(API_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.load(resp)
    except Exception as exc:
        raise UpdateError(f"Impossible de contacter GitHub : {exc}") from exc
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET_NAME), None)
    if not asset:
        return None
    digest = asset.get("digest") or ""
    return Release(
        version=(data.get("tag_name") or "").lstrip("vV"),
        url=asset["browser_download_url"],
        size=int(asset.get("size") or 0),
        sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else "",
        notes=data.get("body") or "",
        page=data.get("html_url") or "",
    )


def download(release, progress=None):
    """Télécharge et vérifie l'exe de ``release`` ; il devient la mise à jour en attente.

    ``progress(reçu, total)`` est appelé régulièrement (depuis le thread
    courant). Le fichier n'est renommé en ``.new`` qu'une fois la taille et
    l'empreinte vérifiées : un téléchargement interrompu ou altéré n'est
    jamais installé.
    """
    p = _paths()
    h = hashlib.sha256()
    received = 0
    try:
        req = urllib.request.Request(release.url, headers={"User-Agent": HEADERS["User-Agent"]})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp, open(p["part"], "wb") as out:
            while chunk := resp.read(256 * 1024):
                out.write(chunk)
                h.update(chunk)
                received += len(chunk)
                if progress:
                    progress(received, release.size)
    except Exception as exc:
        _remove(p["part"])
        raise UpdateError(f"Téléchargement interrompu : {exc}") from exc
    if release.size and received != release.size:
        _remove(p["part"])
        raise UpdateError("Fichier téléchargé incomplet.")
    if release.sha256 and h.hexdigest() != release.sha256:
        _remove(p["part"])
        raise UpdateError("Empreinte SHA-256 incorrecte : fichier rejeté.")
    os.replace(p["part"], p["new"])
    with open(p["meta"], "w", encoding="utf-8") as f:
        json.dump({"version": release.version, "sha256": h.hexdigest()}, f)


def pending_version():
    """Version de la mise à jour téléchargée et prête à installer, ou ``None``.

    Une mise à jour en attente n'est retenue que si elle est plus récente que
    la version courante et que son fichier correspond toujours à l'empreinte
    notée au téléchargement ; sinon elle est supprimée.
    """
    p = _paths()
    if not (os.path.exists(p["new"]) and os.path.exists(p["meta"])):
        return None
    try:
        with open(p["meta"], encoding="utf-8") as f:
            meta = json.load(f)
        if is_newer(meta["version"]) and _sha256(p["new"]) == meta["sha256"]:
            return meta["version"]
    except Exception:
        pass
    discard_pending()
    return None


def discard_pending():
    """Supprime une mise à jour téléchargée (fichiers ``.new`` et ``.update.json``)."""
    p = _paths()
    for k in ("new", "meta", "part"):
        _remove(p[k])


# ---- installation ---------------------------------------------------------
def apply_and_restart():
    """Installe la mise à jour en attente et lance la nouvelle version.

    L'appelant doit quitter l'application juste après (sans rien écrire en
    base). En cas d'échec, l'exe d'origine est remis en place et
    :class:`UpdateError` est levée.
    """
    p = _paths()
    if not pending_version():
        raise UpdateError("Aucune mise à jour prête à installer.")
    old = f"{p['exe']}.old-{int(time.time())}"
    try:
        os.replace(p["exe"], old)          # possible même si l'exe est en cours d'exécution
    except OSError as exc:
        raise UpdateError(f"Impossible de remplacer l'exécutable : {exc}") from exc
    try:
        os.replace(p["new"], p["exe"])
    except OSError as exc:
        os.replace(old, p["exe"])          # retour arrière
        raise UpdateError(f"Impossible d'installer la nouvelle version : {exc}") from exc
    _remove(p["meta"])
    restart()


def restart():
    """Lance une nouvelle instance de l'exe, indépendante de celle-ci.

    ``PYINSTALLER_RESET_ENVIRONMENT`` empêche la nouvelle instance de
    réutiliser le dossier temporaire de l'instance courante (qui sera
    supprimé à sa fermeture).
    """
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([exe_path()], env=env, close_fds=True, creationflags=flags, cwd=os.path.dirname(exe_path()))


def cleanup_old():
    """Supprime les anciennes versions ``.old-*`` (ignore celles encore verrouillées)."""
    for f in glob.glob(glob.escape(exe_path()) + ".old-*"):
        _remove(f)


def install_pending_on_startup():
    """À appeler au tout début du programme.

    Nettoie les anciennes versions, puis installe la mise à jour en attente
    s'il y en a une. Retourne ``True`` si une nouvelle version a été lancée :
    l'appelant doit alors quitter immédiatement.
    """
    if not can_self_update():
        return False
    cleanup_old()
    if not pending_version():
        return False
    try:
        apply_and_restart()
        return True
    except UpdateError:
        discard_pending()  # sera retéléchargée à la prochaine vérification
        return False


# ---- utilitaires ------------------------------------------------------------
def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass
