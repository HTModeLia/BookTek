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

Journal : ``booktek.log`` à côté de la base (:func:`setup_log`). En standard,
les actions qui modifient les données, leur résultat et les erreurs ; en
verbeux (réglage ``verbose_log``), aussi chaque appel de l'interface (arguments,
durée, réponse) et chaque requête Internet de :mod:`booktek.lookup`.
"""
import base64
import csv
import datetime as dt
import functools
import http.server
import inspect
import io
import json
import logging
import logging.handlers
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
import zipfile

import bottle
import webview

from . import __version__, backup, barcode, bkc_import, lookup, qr, updater
# shortcut: helpers repris de l'interface Tkinter (importe tkinter dans l'exe), les déplacer si app.py disparaît
from .app import LABELS, LOAN_DAYS, data_dir, fmt_date, place
from .db import FIELDS, Library
from .isbn import find_in_lines, normalize

try:
    import winsound
except ImportError:  # hors Windows
    winsound = None

try:  # conversion des images choisies en JPEG ; sans Pillow, l'image est copiée telle quelle
    from PIL import Image, ImageChops, ImageFilter, ImageOps
except ImportError:
    Image = None

#: Dossier de l'interface construite (``npm run build``) : embarquée dans l'exe, ou ``web/dist`` des sources.
DIST = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "web", "dist")

log = logging.getLogger("booktek")

#: Méthodes de :class:`Api` qui modifient les données : tracées dans le journal standard (les autres en verbeux).
ACTIONS = {"scan", "save_book", "delete_book", "set_cover", "lend", "return_book", "save_borrower",
           "delete_borrower", "import_bkc", "import_isbn_list", "enrich", "export_csv", "create_backup",
           "restore_backup", "install_update", "set_setting"}


def setup_log(folder, verbose):
    """Écrit le journal dans ``folder/booktek.log`` (1 Mo, 3 anciens fichiers gardés) ; retourne son chemin."""
    path = os.path.join(folder, "booktek.log")
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s : %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    threading.excepthook = lambda a: log.error("Erreur dans un thread", exc_info=(a.exc_type, a.exc_value,
                                                                                  a.exc_traceback))
    return path


def _short(value):
    """Représentation tronquée pour le journal (les images ``data:`` font des centaines de Ko)."""
    text = repr(value)
    return text if len(text) <= 150 else text[:150] + "…"


def _logged(fn):
    """Trace un appel venu de l'interface : action, message de résultat et erreurs ; le reste en verbeux."""
    name = fn.__name__

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        log.log(logging.INFO if name in ACTIONS else logging.DEBUG, "%s(%s)", name,
                ", ".join(map(_short, args + tuple(kwargs.values()))))
        start = time.monotonic()
        try:
            res = fn(self, *args, **kwargs)
        except ValueError as exc:  # message prévu pour l'utilisateur
            log.warning("%s : %s", name, exc)
            raise
        except Exception:
            log.exception("%s : erreur inattendue", name)
            raise
        if isinstance(res, dict) and res.get("status"):
            log.info("%s : %s", name, res["status"])
        log.debug("%s -> %s (%.2f s)", name, _short(res), time.monotonic() - start)
        return res

    wrapper.__signature__ = inspect.signature(fn)  # pywebview y lit les paramètres de la fonction JavaScript
    return wrapper


def data_url(img):
    """Image (octets) -> adresse ``data:`` affichable directement par le navigateur."""
    return "data:image/jpeg;base64," + base64.b64encode(img).decode()


def from_data_url(url):
    """Adresse ``data:`` envoyée par l'interface -> octets."""
    return base64.b64decode(url.split(",", 1)[1])


PHONE_MAX = 30_000_000  # octets : une photo de téléphone en fait 2 à 10 Mo
#: Page ouverte par le téléphone (couleurs fixes : elle est hors de l'application et de ses thèmes).
#: ``@INTRO@`` et ``@BUTTON@`` sont remplacés selon l'usage (:data:`PHONE_TEXTS`) ; le message affiché
#: après l'envoi est la réponse du serveur.
PHONE_PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>BookTek : photo</title><style>
body{font:20px system-ui,sans-serif;margin:0;padding:24px;text-align:center;background:#f3f6fc;color:#1b2333}
label{display:block;padding:28px;margin:24px 0;border-radius:16px;background:#2563eb;color:#fff;font-weight:600}
input{display:none}img{max-width:100%;max-height:50vh;border-radius:8px}#msg{min-height:3em}
</style></head><body><h1>BookTek</h1><p>@INTRO@</p>
<label>@BUTTON@<input type="file" accept="image/*" capture="environment" id="f"></label>
<p id="msg"></p><img id="prev" alt="">
<script>
f.onchange = async () => {
  const file = f.files[0]; if (!file) return
  prev.src = URL.createObjectURL(file); msg.textContent = "Envoi en cours…"
  try {
    const r = await fetch(location.pathname, {method: "POST", body: file})
    const t = await r.text()
    msg.textContent = r.ok ? t : "Erreur : " + t
  } catch (e) { msg.textContent = "BookTek ne répond plus : scannez à nouveau le QR code affiché sur l'ordinateur." }
  f.value = ""
}
</script></body></html>"""
PHONE_TEXTS = {
    "photo": ("Photographiez la couverture du livre, bien à plat.", "Prendre la photo"),
    "isbn": ("Photographiez le code-barres du livre (au dos), de près, bien en face et net. "
             "Un livre après l'autre : chaque ISBN lu arrive dans BookTek.", "Photographier le code-barres"),
}


def phone_page(kind):
    """Page du téléphone pour ``kind`` (``"photo"`` : jaquette, ``"isbn"`` : code-barres)."""
    intro, button = PHONE_TEXTS[kind]
    return PHONE_PAGE.replace("@INTRO@", intro).replace("@BUTTON@", button)


def adjust_image(img, action, box=None):
    """Retouche une jaquette (octets) et retourne le JPEG obtenu.

    ``action`` : ``"left"`` / ``"right"`` (quart de tour), ``"auto"`` (retire les bords unis autour
    du livre), ``"enhance"`` (contraste automatique) ou ``"crop"`` avec ``box`` = (gauche, haut,
    droite, bas) en fractions de l'image (0 à 1). Lève ``ValueError`` avec un message pour l'utilisateur.
    """
    try:
        im = Image.open(io.BytesIO(img)).convert("RGB")
    except Exception:
        raise ValueError("Image illisible.") from None
    if action in ("left", "right"):
        im = im.rotate(90 if action == "left" else -90, expand=True)
    elif action == "enhance":
        im = ImageOps.autocontrast(im, cutoff=1)
    elif action == "crop":
        x0, y0, x1, y1 = (min(1.0, max(0.0, float(v))) for v in box)
        if x1 - x0 < 0.05 or y1 - y0 < 0.05:
            raise ValueError("Zone trop petite : tracez un cadre autour de la couverture.")
        im = im.crop((round(x0 * im.width), round(y0 * im.height), round(x1 * im.width), round(y1 * im.height)))
    elif action == "auto":
        # shortcut: fond supposé uni (couleur médiane du pourtour), sans redresser la perspective ;
        # suffisant pour un livre posé sur une table ou scanné, sinon recadrer à la main.
        small = im.copy()
        small.thumbnail((300, 300))
        small = small.filter(ImageFilter.MedianFilter(5))
        w, h = small.size
        edge = [small.getpixel((x, y)) for x in range(w) for y in (0, h - 1)] + \
               [small.getpixel((x, y)) for y in range(h) for x in (0, w - 1)]
        bg = tuple(sorted(c[k] for c in edge)[len(edge) // 2] for k in range(3))
        diff = ImageChops.difference(small, Image.new("RGB", small.size, bg)).convert("L")
        bbox = diff.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MinFilter(3)).getbbox()
        if not bbox or (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) > 0.95 * w * h:
            raise ValueError("Pas de bord à retirer : utilisez « Recadrer » pour tracer le cadre à la main.")
        sx, sy = im.width / w, im.height / h
        im = im.crop((int(bbox[0] * sx), int(bbox[1] * sy), int(bbox[2] * sx), int(bbox[3] * sy)))
    else:
        raise ValueError(f"Retouche inconnue : {action}")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


#: Numérisation par WIA (le service de numérisation de Windows) : fenêtre standard de Windows pour
#: choisir le scanner (imprimante multifonction en USB ou en Wi-Fi), prévisualiser et cadrer.
#: Codes de sortie : 0 image enregistrée, 2 aucun scanner, 3 WIA absent, 4 annulé.
WIA_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
try { $dlg = New-Object -ComObject WIA.CommonDialog } catch { exit 3 }
try {
  $img = $dlg.ShowAcquireImage(1, 1, 131072, '{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}', $false, $true, $false)
} catch {
  $e = $_.Exception; while ($e.InnerException) { $e = $e.InnerException }
  if ($e.HResult -eq -2145320939) { exit 2 }  # 0x80210015 : aucun scanner disponible
  [Console]::Error.WriteLine($e.Message); exit 1
}
if ($img -eq $null) { exit 4 }
$img.SaveFile('@PATH@')
"""


def wia_scan():
    """Ouvre la fenêtre de numérisation de Windows ; retourne les octets de l'image, ou None si annulé.

    Passe par PowerShell (objet COM ``WIA.CommonDialog``) : aucune dépendance Python. Lève
    ``ValueError`` avec un message pour l'utilisateur si aucun scanner n'est trouvé.
    """
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "scan.jpg")
    script = WIA_SCRIPT.replace("@PATH@", path.replace("'", "''"))
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-STA", "-EncodedCommand",
                              base64.b64encode(script.encode("utf-16-le")).decode()],
                             capture_output=True, text=True, encoding="oem", errors="replace", timeout=900,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if res.returncode == 4:
            return None
        if res.returncode == 2:
            raise ValueError("Aucun scanner trouvé. Allumez l'imprimante, puis vérifiez qu'elle apparaît dans "
                             "Windows : Paramètres › Bluetooth et appareils › Imprimantes et scanners.")
        if res.returncode == 3:
            raise ValueError("La numérisation de Windows (WIA) n'est pas disponible sur cet ordinateur.")
        if res.returncode or not os.path.exists(path):
            err = (res.stderr or "").strip().splitlines() or ["erreur inconnue"]
            raise ValueError("Le scanner n'a pas répondu : " + err[-1])
        with open(path, "rb") as f:
            return f.read()
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Impossible de lancer la numérisation de Windows.") from None
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _lan_ip():
    """Adresse de l'ordinateur sur le réseau local (celle de la carte qui sort vers Internet)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))  # UDP : aucun paquet envoyé, choisit seulement la carte réseau
        return s.getsockname()[0]


def phone_server(token, on_photo, page=None):
    """Serveur web du réseau local pour la photo par téléphone, sur un port libre.

    Seule l'adresse ``/<token>`` répond (page en GET, photo en POST) : le jeton aléatoire, transmis
    par le QR code, empêche un autre appareil du réseau de deviner l'adresse. ``page`` : la page
    servie (photo de couverture par défaut). ``on_photo(octets)`` retourne le message à afficher sur
    le téléphone, ou lève ``ValueError`` (image illisible) : ce message-là est renvoyé en erreur.
    """
    class Handler(http.server.BaseHTTPRequestHandler):
        def _reply(self, code, text, ctype="text/plain; charset=utf-8"):
            body = text.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/" + token:
                return self._reply(404, "Page inconnue")
            self._reply(200, page or phone_page("photo"), "text/html; charset=utf-8")

        def do_POST(self):
            size = self.headers.get("Content-Length", "")
            if self.path != "/" + token or not size.isdigit() or not 0 < int(size) <= PHONE_MAX:
                return self._reply(400, "Envoi refusé")
            try:
                text = on_photo(self.rfile.read(int(size)))
            except ValueError as exc:
                return self._reply(400, str(exc))
            self._reply(200, text or "ok")

        def log_message(self, fmt, *args):
            log.debug("Téléphone %s : %s", self.client_address[0], fmt % args)

    return http.server.ThreadingHTTPServer(("0.0.0.0", 0), Handler)


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
        self._phone = None  # serveur de la photo par téléphone, s'il est ouvert
        self._settings_path = os.path.join(os.path.dirname(db_path), "settings.json")
        self._log_path = os.path.join(os.path.dirname(db_path), "booktek.log")  # écrit si setup_log() a été appelé
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
                "backupDir": backup.folder(self._db_path),
                "sources": lookup.SOURCES,
                "update": self._update_ready and self._update_ready.version,
            }

    def set_setting(self, key, value):
        """Enregistre un réglage d'affichage (thème sombre, grands caractères…) dans ``settings.json``."""
        self._settings[key] = value
        if key == "verbose_log":
            log.setLevel(logging.DEBUG if value else logging.INFO)
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

    def phone_start(self, kind="photo"):
        """Ouvre la page du téléphone sur le réseau local ; retourne ``{"url", "qr"}`` (QR code en SVG).

        ``kind="photo"`` : chaque photo reçue arrive dans l'interface par un événement ``phone_photo``,
        la dernière remplace la précédente. ``kind="isbn"`` : le téléphone sert de scanner, chaque
        code-barres lu arrive par un événement ``phone_isbn`` ; la page reste ouverte d'un livre à l'autre.
        """
        self.phone_stop()
        try:
            ip = _lan_ip()
        except OSError:
            raise ValueError("Cet ordinateur n'est relié à aucun réseau : le téléphone ne pourra pas le joindre.") from None
        token = secrets.token_urlsafe(8)
        handler = self._phone_isbn if kind == "isbn" else self._phone_photo
        self._phone = phone_server(token, handler, phone_page(kind))
        threading.Thread(target=self._phone.serve_forever, daemon=True).start()
        url = f"http://{ip}:{self._phone.server_port}/{token}"
        return {"url": url, "qr": qr.svg(url)}

    def phone_stop(self):
        """Ferme la page « photo par téléphone »."""
        if self._phone:
            self._phone.shutdown()
            self._phone.server_close()
            self._phone = None

    def _phone_photo(self, img):
        """Photo reçue du téléphone : redressée, réduite (1200 px au plus), puis envoyée à l'interface."""
        if Image:
            try:
                im = ImageOps.exif_transpose(Image.open(io.BytesIO(img))).convert("RGB")
            except Exception:
                raise ValueError("Image illisible : reprenez la photo.") from None
            im.thumbnail((1200, 1200))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=90)
            img = buf.getvalue()
        log.info("Photo reçue du téléphone (%d Ko)", len(img) // 1000)
        self._push("phone_photo", image=data_url(img))
        return "Photo envoyée à BookTek. Si elle ne convient pas, reprenez-en une autre."

    def _phone_isbn(self, img):
        """Photo d'un code-barres reçue du téléphone : l'ISBN lu est envoyé à l'interface, qui le traite comme un scan."""
        if not Image:
            raise ValueError("Lecture des codes-barres impossible sur cet ordinateur.")
        try:
            code = barcode.read(img)
        except Exception:
            raise ValueError("Image illisible : reprenez la photo.") from None
        if not code:
            raise ValueError("Code-barres non lu : rapprochez le téléphone, bien en face, avec assez de lumière.")
        isbn = normalize(code)
        if not isbn:
            raise ValueError(f"Ce code-barres ({code}) n'est pas un ISBN.")
        log.info("ISBN lu par le téléphone : %s", isbn)
        self._push("phone_isbn", isbn=isbn)
        return f"ISBN {isbn} envoyé à BookTek. Livre suivant : reprenez une photo."

    # ---- retouche et numérisation des jaquettes --------------------------------
    def adjust_cover(self, src, action, box=None):
        """Retouche la jaquette affichée dans la fiche (voir :func:`adjust_image`) ; retourne la nouvelle en ``data:``.

        ``src`` est une adresse ``data:`` (image pas encore enregistrée) ou ``covers/<id>.jpg?v=…``.
        """
        if not Image:
            raise ValueError("Retouche impossible sur cet ordinateur.")
        if src.startswith("data:"):
            img = from_data_url(src)
        else:
            name = src.split("?")[0].rsplit("/", 1)[-1]
            if not name.removesuffix(".jpg").isdigit():
                raise ValueError("Jaquette introuvable.")
            with open(self._cover_path(int(name.removesuffix(".jpg"))), "rb") as f:
                img = f.read()
        return data_url(adjust_image(img, action, box))

    def scan_cover(self):
        """Numérise la couverture avec le scanner (imprimante multifonction) ; retourne l'image en ``data:`` ou None si annulé."""
        img = wia_scan()
        if img is None:
            return None
        if Image:  # un scan en haute résolution pèse lourd : réduit comme les photos du téléphone
            im = Image.open(io.BytesIO(img)).convert("RGB")
            im.thumbnail((1200, 1200))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=90)
            img = buf.getvalue()
        log.info("Couverture numérisée (%d Ko)", len(img) // 1000)
        return data_url(img)

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
            recent = self._lib.checked_recently()
        todo = sorted((k, v) for k, v in todo.items() if k not in recent)
        if not todo:
            return 0

        def work():
            found = 0
            for i, (book_id, isbn) in enumerate(todo, 1):
                log.debug("Complément %d/%d : livre %s, ISBN %s", i, len(todo), book_id, isbn)
                info = lookup.fetch(isbn)
                with self._lock:
                    self._lib.mark_checked(book_id)
                    if info and (self._lib.fill_missing(book_id, info)
                                 | self._write_cover(book_id, info.get("cover"), replace=False)):
                        found += 1
                done = i == len(todo)
                if done:
                    log.info("Complément terminé : %d fiche(s) complétée(s) sur %d", found, len(todo))
                self._push("status", level="ok" if done else "info", refresh=done or i % 10 == 0, busy=not done,
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

    def open_log(self):
        """Ouvre le journal dans le Bloc-notes (programme associé aux fichiers .log)."""
        if not os.path.exists(self._log_path):
            raise ValueError("Le journal est vide pour l'instant.")
        os.startfile(self._log_path)

    def install_certificate(self):
        """Fait reconnaître la signature de BookTek par Windows, pour l'utilisateur courant (sans droits administrateur).

        Installe ``BookTek.cer`` (certificat auto-signé, voir docs/publier-une-version.md) dans les autorités
        racines, ce que Windows fait confirmer, puis dans les éditeurs approuvés.
        """
        cer = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BookTek.cer")
        for store in ("Root", "TrustedPublisher"):
            res = subprocess.run(["certutil", "-user", "-f", "-addstore", store, cer], capture_output=True,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if res.returncode:
                raise ValueError("Le certificat n'a pas été installé (installation annulée ou refusée).")

    def open_url(self, url):
        if url.startswith("https://"):
            webbrowser.open(url)

    # ---- sauvegardes (voir booktek.backup) -----------------------------------
    def backups(self):
        return backup.list_backups(self._db_path)

    def create_backup(self):
        with self._lock:
            return backup.create(self._db_path)

    def restore_backup(self, name):
        """Restaure une sauvegarde ; une copie de sécurité est faite avant. L'interface doit recharger ses données."""
        with self._lock:
            try:
                backup.restore(self._db_path, name, self._lib.con.close)
            finally:
                self._lib = Library(self._db_path)  # rouvre la base, restaurée ou non

    def _auto_backup(self):
        """Sauvegarde automatique au lancement, dans un thread ; un échec ne bloque pas l'application."""
        with self._lock:
            try:
                backup.auto(self._db_path)
            except (OSError, sqlite3.Error, zipfile.BadZipFile) as exc:
                log.warning("Sauvegarde automatique impossible : %s", exc)

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
            log.info("Mise à jour %s téléchargée", rel.version)
            self._push("update", version=rel.version, notes=rel.notes.strip()[:700])
            return f"Mise à jour {rel.version} prête."
        except Exception as exc:
            log.warning("Mise à jour impossible : %s", exc)
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


for _name, _fn in list(vars(Api).items()):
    if inspect.isfunction(_fn) and not _name.startswith("_"):
        setattr(Api, _name, _logged(_fn))


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
    setup_log(data_dir(), api._settings.get("verbose_log"))
    log.info("Démarrage de BookTek %s, base %s", __version__, api._db_path)
    api._window = webview.create_window(f"BookTek {__version__}", make_server(api), js_api=api,
                                        width=1280, height=800, min_size=(1050, 650), maximized=True,
                                        background_color="#f3f6fc")
    threading.Thread(target=api._auto_updates, daemon=True).start()
    threading.Thread(target=api._auto_backup, daemon=True).start()
    webview.start()
