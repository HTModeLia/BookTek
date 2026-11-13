"""Sauvegardes de la bibliothèque : une archive ZIP par sauvegarde, dans ``backups/`` à côté de la base.

Chaque archive contient ``booktek.db`` (copie faite par l'API de sauvegarde de SQLite, donc cohérente)
et les jaquettes ``covers/*.jpg``. On en garde :data:`KEEP`. Le nom indique la date et le type :
``auto`` (une par jour, au lancement), ``manual`` ou ``before-restore`` (copie de sécurité).
"""
import datetime as dt
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing

KEEP = 10
_NAME = re.compile(r"^booktek-\d{8}-\d{6}-(auto|manual|before-restore)\.zip$")
# seuls ces fichiers sont acceptés à la restauration (pas de chemin qui sort du dossier)
_MEMBER = re.compile(r"^(booktek\.db|covers/[^/\\]+\.jpg)$")


def folder(db_path):
    """Dossier des sauvegardes : ``backups/`` à côté de la base."""
    return os.path.join(os.path.dirname(db_path), "backups")


def _covers(db_path):
    return os.path.join(os.path.dirname(db_path), "covers")


def _archive(db_path, name):
    """Chemin d'une sauvegarde existante ; refuse tout nom qui ne ressemble pas à une sauvegarde."""
    if not _NAME.match(name or ""):
        raise ValueError("Sauvegarde inconnue.")
    return os.path.join(folder(db_path), name)


def list_backups(db_path):
    """Sauvegardes existantes, la plus récente d'abord : ``[{"name", "date", "size"}]``."""
    rows = []
    if os.path.isdir(folder(db_path)):
        for name in os.listdir(folder(db_path)):
            if _NAME.match(name):
                st = os.stat(_archive(db_path, name))
                rows.append({"name": name, "date": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                             "size": st.st_size})
    return sorted(rows, key=lambda r: r["name"], reverse=True)


def create(db_path, kind="manual"):
    """Crée une sauvegarde de type ``kind`` et retourne son nom ; supprime les plus anciennes au-delà de :data:`KEEP`."""
    os.makedirs(folder(db_path), exist_ok=True)
    now = dt.datetime.now()
    while os.path.exists(_archive(db_path, f"booktek-{now:%Y%m%d-%H%M%S}-{kind}.zip")):
        now += dt.timedelta(seconds=1)  # deux sauvegardes dans la même seconde : pas d'écrasement
    name = f"booktek-{now:%Y%m%d-%H%M%S}-{kind}.zip"
    target = _archive(db_path, name)
    snap = os.path.join(folder(db_path), "instantane.db")
    with closing(sqlite3.connect(db_path)) as src, closing(sqlite3.connect(snap)) as dst:
        src.backup(dst)
    try:
        with zipfile.ZipFile(target + ".tmp", "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "booktek.db")
            covers = _covers(db_path)
            for img in sorted(os.listdir(covers)) if os.path.isdir(covers) else []:
                if _MEMBER.match(f"covers/{img}"):
                    z.write(os.path.join(covers, img), f"covers/{img}")
        os.replace(target + ".tmp", target)
    finally:
        os.remove(snap)
    for old in list_backups(db_path)[KEEP:]:
        os.remove(_archive(db_path, old["name"]))
    return name


def auto(db_path):
    """Sauvegarde automatique : au plus une par jour. Retourne le nom créé, ou ``None`` si elle existe déjà."""
    today = dt.date.today().strftime("%Y%m%d")
    if any(r["name"].startswith(f"booktek-{today}-") and r["name"].endswith("-auto.zip")
           for r in list_backups(db_path)):
        return None
    return create(db_path, "auto")


def restore(db_path, name, close_db):
    """Remplace la base et les jaquettes par la sauvegarde ``name``.

    Une copie de sécurité est faite d'abord. La sauvegarde est vérifiée avant tout remplacement.
    ``close_db`` ferme la base ouverte (Windows ne remplace pas un fichier ouvert).
    Retourne le nom de la copie de sécurité.
    """
    src = _archive(db_path, name)
    if not os.path.exists(src):
        raise ValueError("Sauvegarde introuvable.")
    safety = create(db_path, "before-restore")
    stage = tempfile.mkdtemp(dir=folder(db_path))
    try:
        with zipfile.ZipFile(src) as z:
            names = z.namelist()
            if "booktek.db" not in names or not all(_MEMBER.match(n) for n in names):
                raise ValueError("Sauvegarde invalide.")
            z.extractall(stage)
        with closing(sqlite3.connect(os.path.join(stage, "booktek.db"))) as check:
            try:
                check.execute("SELECT count(*) FROM books").fetchone()
            except sqlite3.DatabaseError:
                raise ValueError("Sauvegarde invalide : base illisible.") from None
        close_db()
        os.replace(os.path.join(stage, "booktek.db"), db_path)
        shutil.rmtree(_covers(db_path), ignore_errors=True)
        if os.path.isdir(os.path.join(stage, "covers")):
            shutil.move(os.path.join(stage, "covers"), _covers(db_path))
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return safety
