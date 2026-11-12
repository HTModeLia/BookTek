"""Interface web de BookTek : fenêtre WebView2 (pywebview) affichant l'interface React de ``web/``.

Le visuel vient de la maquette Electron ; toute la logique reste en Python et
reprend celle de :mod:`booktek.app` (base, recherches en ligne, jaquettes,
imports, export, mises à jour).

* :class:`Api` : méthodes appelées depuis JavaScript par
  ``window.pywebview.api.<nom>(...)`` ; chacune retourne du JSON (dict, liste,
  texte). Une erreur à afficher est levée en :class:`ValueError` et arrive
  côté JavaScript comme une promesse rejetée, avec le message en français.
* Un petit serveur WSGI (bottle, fourni avec pywebview) sert les fichiers de
  ``web/dist`` et les jaquettes ``covers/<id>.jpg``.

Threads : pywebview exécute chaque appel JavaScript dans son propre thread.
Les accès à la base passent donc par le verrou ``Api._lock`` ; les recherches
en ligne se font hors verrou. Un thread de fond prévient l'interface par
:meth:`Api._push` (``window.onPush`` en JavaScript).
"""
import base64
import csv
import datetime as dt
import io
import json
import os
import sys
import threading
import time
import webbrowser

import bottle
import webview

from . import __version__, bkc_import, lookup, updater
# shortcut: helpers repris de l'interface Tkinter (importe tkinter dans l'exe), les déplacer si app.py disparaît
from .app import LABELS, LOAN_DAYS, data_dir, fmt_date, place
from .db import FIELDS, Library
from .isbn import find_in_lines, normalize

try:
    import winsound
except ImportError:  # hors Windows
    winsound = None

try:  # conversion des images choisies en JPEG ; sans Pillow, l'image est copiée telle quelle
    from PIL import Image
except ImportError:
    Image = None

#: Dossier de l'interface construite (``npm run build``) : embarquée dans l'exe, ou ``web/dist`` des sources.
DIST = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "web", "dist")


def data_url(img):
    """Image (octets) -> adresse ``data:`` affichable directement par le navigateur."""
    return "data:image/jpeg;base64," + base64.b64encode(img).decode()


def from_data_url(url):
    """Adresse ``data:`` envoyée par l'interface -> octets."""
    return base64.b64decode(url.split(",", 1)[1])


class Api:
    """Fonctions appelées par l'interface. Les attributs privés (``_``) ne sont pas exposés à JavaScript."""

    def __init__(self, db_path):
        self._lib = Library(db_path)
        self._db_path = db_path
        self._lock = threading.RLock()
        self._window = None
        self._pending = set()  # ISBN en cours de recherche en ligne (double scan)
        self._update_ready = None
        self._update_busy = False
        self._settings_path = os.path.join(os.path.dirname(db_path), "settings.json")
        try:
            with open(self._settings_path, encoding="utf-8") as f:
                self._settings = json.load(f)
        except (OSError, ValueError):
            self._settings = {}  # premier lancement ou fichier abîmé : réglages par défaut

    # ---- outils internes ---------------------------------------------------
    def _push(self, kind, **data):
        """Envoie un événement à l'interface (statut, rafraîchissement, mise à jour prête)."""
        if self._window:
            self._window.evaluate_js(f"window.onPush && window.onPush({json.dumps({'kind': kind, **data})})")

    def _cover_path(self, book_id):
        """Fichier de couverture du livre : ``covers/<id>.jpg`` à côté de la base (il peut ne pas exister)."""
        return os.path.join(os.path.dirname(self._db_path), "covers", f"{book_id}.jpg")

    def _write_cover(self, book_id, img, replace=True):
        """Enregistre la jaquette ``img`` (octets) ; sans ``replace``, garde une jaquette existante."""
        path = self._cover_path(book_id)
        if not img or (not replace and os.path.exists(path)):
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if Image:
            try:
                Image.open(io.BytesIO(img)).convert("RGB").save(path, "JPEG", quality=90)
                return True
            except Exception as exc:
                raise ValueError(f"Image illisible : {exc}") from None
        with open(path, "wb") as f:
            f.write(img)
        return True

    def _book(self, row):
        """Ligne de la base -> dict pour l'interface (emplacement, adresse de la jaquette, prêt en cours)."""
        b = dict(row)
        b["place"] = place(row)
        path = self._cover_path(b["id"])
        b["cover"] = f"covers/{b['id']}.jpg?v={int(os.path.getmtime(path))}" if os.path.exists(path) else ""
        return b

    def _beep(self):
        if winsound:
            winsound.MessageBeep(winsound.MB_ICONHAND)

    # ---- lecture -------------------------------------------------------------
    def load(self):
        """Tout ce qu'affiche l'interface : livres, prêts (historique complet), annuaire, compteurs, réglages."""
        with self._lock:
            return {
                "books": [self._book(r) for r in self._lib.search()],
                "loans": [dict(r) for r in self._lib.history(100000)],
                "borrowers": [dict(r) for r in self._lib.directory()],
                "stats": self._lib.stats(),
                "version": __version__,
                "settings": self._settings,
                "today": dt.date.today().isoformat(),
                "loanDays": LOAN_DAYS,
                "dbPath": self._db_path,
                "sources": lookup.SOURCES,
                "update": self._update_ready and self._update_ready.version,
            }

    def set_setting(self, key, value):
        """Enregistre un réglage d'affichage (thème sombre, grands caractères…) dans ``settings.json``."""
        self._settings[key] = value
        try:
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f)
        except OSError:
            pass  # réglage appliqué pour cette session seulement

    # ---- scan ----------------------------------------------------------------
    def scan(self, raw, mode):
        """Traite un code scanné ; même comportement que :meth:`booktek.app.App.on_scan`.

        Retourne ``{"status", "kind"}`` et éventuellement ``"select"`` (livre à
        montrer), ``"open"`` (livre connu en mode automatique : sa fiche
        reçoit le focus) ou ``"form"`` (nouveau livre à valider, avec la
        jaquette trouvée en ``data:``).
        """
        raw = (raw or "").strip()
        isbn = normalize(raw)
        if not isbn:
            self._beep()
            return {"status": f"« {raw} » n'est pas un ISBN valide.", "kind": "err"}
        with self._lock:
            book = self._lib.book_by_isbn(isbn)
            if mode == "return":
                if not book:
                    self._beep()
                    return {"status": f"{isbn} : livre absent de la bibliothèque.", "kind": "err"}
                loan = self._lib.return_book(book["id"])
                if not loan:
                    return {"status": f"« {book['title']} » n'était pas prêté.", "kind": "warn", "select": book["id"]}
                return {"status": f"Retour enregistré : « {book['title']} » (rendu par {loan['borrower']}).",
                        "kind": "ok", "select": book["id"]}
            if book:
                if mode == "add":
                    return {"status": f"Déjà dans la bibliothèque : « {book['title']} ».", "kind": "warn",
                            "select": book["id"]}
                return {"status": f"« {book['title']} »", "kind": "info", "select": book["id"], "open": True}
            if isbn in self._pending:
                return {"status": f"{isbn} : recherche déjà en cours…", "kind": "info"}
            self._pending.add(isbn)
        self._push("status", text=f"{isbn} : nouveau livre, recherche des informations en ligne…", level="info")
        try:
            info = lookup.fetch(isbn)
        finally:
            self._pending.discard(isbn)
        with self._lock:
            if self._lib.book_by_isbn(isbn):  # ajouté entre-temps
                return {"status": "", "kind": "info"}
            if mode == "add" and info:
                book_id = self._lib.add_book({"isbn": isbn, **info})
                self._write_cover(book_id, info.get("cover"), replace=False)
                by = f" — {info['authors']}" if info.get("authors") else ""
                return {"status": f"Ajouté : « {info['title']} »{by}", "kind": "ok", "select": book_id}
        form = {"isbn": isbn, **{k: str(v) for k, v in (info or {}).items() if k != "cover"}}
        if info and info.get("cover"):
            form["coverData"] = data_url(info["cover"])
        return {"status": "" if info else f"{isbn} : introuvable en ligne, saisie manuelle.",
                "kind": "info" if info else "warn", "form": form}

    # ---- livres --------------------------------------------------------------
    def save_book(self, book_id, data, cover_data=None):
        """Ajoute (``book_id`` None) ou modifie un livre ; ``cover_data`` (``data:``) remplace la jaquette.

        Retourne l'id du livre. Un doublon d'ISBN est refusé avec un message.
        """
        data = dict(data)
        data["isbn"] = normalize(data.get("isbn") or "") or (data.get("isbn") or "").strip()
        with self._lock:
            other = data["isbn"] and self._lib.book_by_isbn(data["isbn"])
            if other and other["id"] != book_id:
                raise ValueError("Un livre avec cet ISBN existe déjà.")
            if book_id:
                self._lib.update_book(book_id, data)
            else:
                book_id = self._lib.add_book(data)
            if cover_data:
                self._write_cover(book_id, from_data_url(cover_data))
            return book_id

    def delete_book(self, book_id):
        with self._lock:
            self._lib.delete_book(book_id)  # ValueError si prêté
            if os.path.exists(self._cover_path(book_id)):
                os.remove(self._cover_path(book_id))  # sinon un futur livre réutilisant cet id hériterait de l'image

    def fetch_info(self, isbn):
        """Informations en ligne d'un ISBN (sans la jaquette), ou ``None``."""
        info = lookup.fetch(isbn) if isbn else None
        return {k: str(v) for k, v in info.items() if k != "cover"} if info else None

    def find_covers(self, isbn, title, authors):
        """Jaquettes trouvées en ligne, en adresses ``data:``."""
        return [data_url(img) for img in lookup.find_covers(isbn or "", title or "", authors or "")]

    def set_cover(self, book_id, cover_data):
        with self._lock:
            self._write_cover(book_id, from_data_url(cover_data))

    # ---- prêts et annuaire ---------------------------------------------------
    def lend(self, book_id, borrower, due_date):
        """Prêt du livre ; ``due_date`` ISO ou vide (sans échéance)."""
        with self._lock:
            self._lib.lend(book_id, borrower or "", due_date or None)

    def return_book(self, book_id):
        with self._lock:
            loan = self._lib.return_book(book_id)
            return loan and loan["borrower"]

    def save_borrower(self, old_name, data):
        with self._lock:
            self._lib.save_borrower(old_name, data)

    def delete_borrower(self, name):
        with self._lock:
            self._lib.delete_borrower(name)

    # ---- import / export / enrichissement ------------------------------------
    def _open_file(self, kinds):
        paths = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=kinds)
        return paths[0] if paths else None

    def import_bkc(self):
        """Importe une collection Book Collector (``.bkc``) ; voir :meth:`booktek.app.App.import_bkc`."""
        path = self._open_file(("Book Collector (*.bkc)", "Tous les fichiers (*.*)"))
        return path and self._import_items(bkc_import.parse(path))

    def import_isbn_list(self):
        """Importe une liste d'ISBN (texte ou CSV), chaque livre ayant son ISBN pour titre provisoire."""
        path = self._open_file(("Texte ou CSV (*.txt;*.csv)", "Tous les fichiers (*.*)"))
        if not path:
            return None
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            isbns = find_in_lines(f.read())
        if not isbns:
            raise ValueError("Aucun ISBN valide dans ce fichier.")
        return self._import_items([{"isbn": i, "title": i} for i in isbns])

    def _import_items(self, items):
        """Ajoute les livres absents de la base ; retourne ``{"added", "skipped"}``."""
        added = skipped = 0
        with self._lock:
            for it in items:
                if it["isbn"] and self._lib.book_by_isbn(it["isbn"]):
                    skipped += 1
                    continue
                self._lib.add_book(it)
                added += 1
        return {"added": added, "skipped": skipped}

    def enrich(self):
        """Complète en ligne, dans un thread, les fiches incomplètes ou sans jaquette (champs vides seulement).

        La progression arrive dans la ligne de statut par :meth:`_push`.
        """
        with self._lock:
            todo = dict(self._lib.books_missing_info())
            todo.update((r["id"], r["isbn"]) for r in self._lib.search()
                        if r["isbn"] and not os.path.exists(self._cover_path(r["id"])))
        todo = sorted(todo.items())
        if not todo:
            return 0

        def work():
            found = 0
            for i, (book_id, isbn) in enumerate(todo, 1):
                info = lookup.fetch(isbn)
                with self._lock:
                    if info and (self._lib.fill_missing(book_id, info)
                                 | self._write_cover(book_id, info.get("cover"), replace=False)):
                        found += 1
                done = i == len(todo)
                self._push("status", level="ok" if done else "info", refresh=done or i % 10 == 0,
                           text=f"Terminé : {found} fiche(s) complétée(s) sur {len(todo)}." if done
                           else f"Recherche en ligne : {i}/{len(todo)} ({found} complétée(s))…")

        threading.Thread(target=work, daemon=True).start()
        return len(todo)

    def export_csv(self):
        """Exporte la bibliothèque en CSV pour Excel (UTF-8 avec BOM, séparateur « ; »)."""
        paths = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename="bibliotheque.csv",
                                                file_types=("CSV (*.csv)",))
        if not paths:
            return None
        path = paths if isinstance(paths, str) else paths[0]
        with self._lock, open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([LABELS[k] for k in FIELDS] + ["Prêté à", "Retour prévu"])
            for r in self._lib.search():
                w.writerow([r[k] for k in FIELDS] + [r["borrower"] or "", fmt_date(r["due_date"])])
        return path

    def open_url(self, url):
        if url.startswith("https://"):
            webbrowser.open(url)

    # ---- mises à jour (même logique que booktek.app) -------------------------
    def check_update(self, manual=False):
        """Vérifie et télécharge une nouvelle version ; retourne un message (vérification manuelle)."""
        if self._update_busy:
            return "Recherche de mise à jour déjà en cours…"
        self._update_busy = True
        try:
            rel = updater.latest_release()
            if rel is None or not updater.is_newer(rel.version):
                return f"BookTek est à jour (version {__version__})."
            if not updater.can_self_update():
                return (f"La version {rel.version} est disponible ({rel.page}), mais elle ne peut pas être "
                        "installée automatiquement ici (sources, ou dossier protégé en écriture).")
            if updater.pending_version() != rel.version:
                updater.download(rel)
            self._update_ready = rel
            self._push("update", version=rel.version, notes=rel.notes.strip()[:700])
            return f"Mise à jour {rel.version} prête."
        except Exception as exc:
            return f"Mise à jour impossible : {exc}"
        finally:
            self._update_busy = False

    def install_update(self):
        """Installe la version téléchargée puis ferme (le nouvel exe redémarre)."""
        try:
            updater.apply_and_restart()
        except updater.UpdateError as exc:
            raise ValueError(str(exc)) from None
        self._window.destroy()

    def _auto_updates(self):
        time.sleep(3)  # laisse l'interface s'afficher d'abord
        while True:
            self.check_update()
            time.sleep(updater.CHECK_INTERVAL)


def make_server(api):
    """Serveur WSGI local : interface construite et jaquettes."""
    app = bottle.Bottle()
    covers = os.path.join(os.path.dirname(api._db_path), "covers")
    app.route("/covers/<name>", callback=lambda name: bottle.static_file(name, root=covers))
    app.route("/", callback=lambda: bottle.static_file("index.html", root=DIST))
    app.route("/<path:path>", callback=lambda path: bottle.static_file(path, root=DIST))
    return app


def main():
    """Point d'entrée : installe une mise à jour en attente, puis ouvre la fenêtre."""
    if updater.install_pending_on_startup():
        return
    if not os.path.exists(os.path.join(DIST, "index.html")):
        sys.exit("Interface absente : lancez « npm run build » dans le dossier web.")
    api = Api(os.path.join(data_dir(), "booktek.db"))
    api._window = webview.create_window(f"BookTek {__version__}", make_server(api), js_api=api,
                                        width=1280, height=800, min_size=(1050, 650), maximized=True,
                                        background_color="#f3f6fc")
    threading.Thread(target=api._auto_updates, daemon=True).start()
    webview.start()
