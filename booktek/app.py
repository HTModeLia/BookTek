"""Interface graphique BookTek (Tkinter).

Organisation :

* :class:`App` : fenêtre principale. En haut, le champ de scan et le choix du
  mode ; en dessous, la ligne de statut, puis trois onglets (bibliothèque,
  prêts en cours, historique) et un pied de page avec les compteurs.
* :class:`Dialog` et ses sous-classes : fenêtres modales. ``show()`` bloque
  jusqu'à leur fermeture et retourne ``result`` (``None`` si annulé).

Lecture d'ISBN : une douchette code-barres se comporte comme un clavier qui
tape les chiffres puis Entrée. Le champ de scan garde donc le focus autant que
possible (voir :meth:`App.refocus`, raccourci F2) et tout le traitement part
de :meth:`App.on_scan`.

Threads : les recherches en ligne (:mod:`booktek.lookup`) peuvent prendre
plusieurs secondes et tournent dans des threads secondaires. Ni Tkinter ni la
connexion SQLite ne doivent être utilisés hors du thread principal : les
threads déposent donc leurs résultats dans une file via :meth:`App.post`, que
:meth:`App._poll` vide toutes les 100 ms depuis le thread de l'interface.
"""
import csv
import io
import json
import datetime as dt
import os
import queue
import re
import shutil
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from . import __version__, bkc_import, lookup, updater
from .db import FIELDS, Library
from .isbn import find_in_lines, normalize

#: Durée de prêt par défaut, en jours (date de retour proposée).
LOAN_DAYS = 21
#: Libellés français des champs de :data:`booktek.db.FIELDS`.
LABELS = {
    "isbn": "ISBN", "title": "Titre", "authors": "Auteur(s)", "publisher": "Éditeur",
    "year": "Année", "genre": "Genre", "pages": "Pages", "location": "Meuble / pièce", "shelf": "Étage (1 = haut)",
    "box": "Box", "depth": "Rangée (1 = devant)", "read_date": "Lu le (JJ/MM/AAAA)", "summary": "Résumé",
    "notes": "Notes",
}
#: Champs proposés pour filtrer (« Tout » = recherche plein texte) et trier la bibliothèque.
SEARCH_IN = {"Tout": None, "Titre": "title", "Auteur": "authors", "Année": "year", "Genre": "genre"}
SORTS = {"Titre": "title", "Auteur": "authors", "Année": "year", "Genre": "genre"}
#: Regroupements du panneau de gauche (menu Affichage), et libellé des livres sans valeur.
GROUPS = {"Auteur": "authors", "Année": "year", "Genre": "genre"}
NO_VALUE = "(non renseigné)"
#: Couleurs du thème clair : messages (ok, warn, err, info), fond des zones blanches (panel),
#: texte (fg), texte secondaire (muted), case sans couverture (tile, tile_fg), une ligne sur deux des tableaux (stripe).
LIGHT = {"ok": "#1b7f3b", "warn": "#b36b00", "err": "#c0262d", "info": "#1f5fa8",
         "panel": "white", "fg": "black", "muted": "#555", "tile": "#e6e6e6", "tile_fg": "#444",
         "stripe": "#e8f0fb"}
#: Thème sombre à fort contraste (texte presque blanc, couleurs vives) : lisible sans fatigue.
DARK = {"ok": "#6ee08f", "warn": "#ffc14d", "err": "#ff8080", "info": "#7cc0ff",
        "panel": "#1e1e1e", "fg": "#f2f2f2", "muted": "#d0d0d0", "tile": "#3a3a3a", "tile_fg": "#e8e8e8",
        "stripe": "#3a3f48"}
#: Couleurs en cours, remplies par :meth:`App._apply_theme`.
COLORS = dict(LIGHT)
#: Points ajoutés à toutes les polices (réglage « Grands caractères »), fixé par :meth:`App._apply_theme`.
FONT_BONUS = [0]


def ui_font(size, *style):
    """Police Segoe UI de ``size`` points, agrandie si « Grands caractères » est coché."""
    return ("Segoe UI", size + FONT_BONUS[0], *style)

try:
    import winsound
except ImportError:  # hors Windows
    winsound = None

try:  # Tk 8.6 ne lit pas le JPEG des couvertures ; sans Pillow, elles ne sont pas affichées
    from PIL import Image, ImageTk
except ImportError:
    Image = None


def data_dir():
    """Dossier de la base : à côté de l'exe s'il est inscriptible, sinon %APPDATA%\\BookTek.

    Une fois empaqueté par PyInstaller (``sys.frozen``), ``sys.executable``
    est l'exe lui-même ; depuis les sources, on prend le dossier du script
    lancé (``main.py``).
    """
    base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0]))
    if os.access(base, os.W_OK):
        return base
    alt = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "BookTek")
    os.makedirs(alt, exist_ok=True)
    return alt


def fmt_date(iso):
    """Date ISO de la base -> affichage ``JJ/MM/AAAA`` (chaîne vide si absente)."""
    return dt.date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else ""


def parse_date(text):
    """Saisie ``JJ/MM/AAAA`` -> :class:`datetime.date`. Lève :class:`ValueError` si invalide."""
    return dt.datetime.strptime(text.strip(), "%d/%m/%Y").date()


def place(book):
    """Code d'emplacement universel « Meuble › É<étage> › B<box> › R<rangée> » (parties vides omises)."""
    parts = (book["location"], book["shelf"] and f"É{book['shelf']}",
             book["box"] and f"B{book['box']}", book["depth"] and f"R{book['depth']}")
    return " › ".join(p for p in parts if p)


def days_since(iso, until=None):
    """Nombre de jours entre la date ISO ``iso`` et ``until`` (aujourd'hui par défaut)."""
    end = dt.date.fromisoformat(until) if until else dt.date.today()
    return (end - dt.date.fromisoformat(iso)).days


def sort_key(text, col=""):
    """Clé de tri « naturelle » : nombres comparés en valeur (É2 avant É10), dates JJ/MM/AAAA
    dans l'ordre chronologique, auteurs par nom de famille du premier auteur."""
    if col == "authors":
        # shortcut: nom = dernier mot du 1er auteur ; faux pour « Ben Jelloun » ou « Nom Prénom », ajouter un champ dédié si gênant
        text = ((text.split(",")[0].split() or [""])[-1]) + " " + text
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", text):
        text = "-".join(reversed(text.split("/")))
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def group_names(value, field):
    """Groupes du panneau de gauche auxquels appartient un livre : un par auteur
    (``authors`` séparés par des virgules), sinon la valeur du champ ; :data:`NO_VALUE` si vide."""
    names = value.split(",") if field == "authors" else [value or ""]
    return [n.strip() for n in names if n.strip()] or [NO_VALUE]


# ---------------------------------------------------------------------------
# Boîtes de dialogue
# ---------------------------------------------------------------------------
class Dialog(tk.Toplevel):
    """Base des fenêtres modales.

    Les sous-classes placent leurs widgets dans ``self.body`` et renseignent
    ``self.result`` avant d'appeler ``destroy()``. Échap ferme sans résultat.
    """

    def __init__(self, master, title):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        self.body = ttk.Frame(self, padding=14)
        self.body.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda e: self.destroy())

    def show(self):
        """Centre la fenêtre sur la fenêtre parente, la rend modale et attend sa fermeture.

        Retourne ``self.result`` (``None`` si l'utilisateur a annulé).
        """
        self.update_idletasks()
        m = self.master
        x = m.winfo_rootx() + (m.winfo_width() - self.winfo_width()) // 2
        y = m.winfo_rooty() + (m.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()
        self.wait_window()
        return self.result


class BookForm(Dialog):
    """Saisie / modification d'une fiche livre.

    ``data`` pré-remplit le formulaire (dict ou ligne de base). ``result``
    est un dict des champs de :data:`FIELDS`, avec l'ISBN normalisé.

    Avec ``cover`` (chemin de la couverture d'un livre existant), le
    formulaire affiche la jaquette et un bouton pour en choisir une autre :
    l'image choisie est dans ``cover_src`` (chemin d'un fichier, ou octets
    d'une jaquette trouvée en ligne par *Rechercher une jaquette…*), à
    enregistrer par l'appelant si le formulaire est validé.
    """

    #: Champs remplacés par *Actualiser les informations* (les autres sont propres à l'utilisateur).
    ONLINE = ("title", "authors", "publisher", "year", "genre", "pages", "summary")

    def __init__(self, master, data, title="Livre", cover=None):
        super().__init__(master, title)
        self.vars = {}
        self.cover_src = None
        # Colonne de droite : jaquette (en modification) puis tous les boutons, Enregistrer et Annuler en bas.
        side = ttk.Frame(self.body)
        side.grid(row=0, column=2, rowspan=len(FIELDS), sticky="ns", padx=(14, 0))
        ttk.Button(side, text="Annuler", command=self.destroy).pack(side="bottom", fill="x", pady=(4, 3))
        ttk.Button(side, text="Enregistrer", command=self.save).pack(side="bottom", fill="x")
        if cover is not None:
            self.cover_label = ttk.Label(side, text="Pas de jaquette", width=20, anchor="center")
            self.cover_label.pack(pady=(3, 6))
            ttk.Button(side, text="Changer la jaquette…", command=self.pick_cover).pack(fill="x")
            if Image:  # sans Pillow, les jaquettes trouvées ne pourraient pas être montrées
                self.search_btn = ttk.Button(side, text="Rechercher une jaquette…", command=self.search_cover)
                self.search_btn.pack(fill="x", pady=(4, 0))
            self._preview(cover)
        self.info_btn = ttk.Button(side, text="Actualiser les informations", command=self.refresh_info)
        self.info_btn.pack(fill="x", pady=(4, 0))
        for r, f in enumerate(FIELDS):
            ttk.Label(self.body, text=LABELS[f] + " :").grid(row=r, column=0, sticky="ne", padx=(0, 8), pady=3)
            if f in ("summary", "notes"):
                w = tk.Text(self.body, width=50, height=4, font="TkTextFont", wrap="word")
                w.insert("1.0", data.get(f) or "")
            else:
                w = ttk.Entry(self.body, width=52)
                value = data.get(f) or ""
                w.insert(0, fmt_date(value) if f == "read_date" else value)
            w.grid(row=r, column=1, sticky="we", pady=3)
            self.vars[f] = w
        # Entrée valide le formulaire, sauf dans les champs Résumé et Notes (multilignes).
        self.bind("<Return>", lambda e: self.save() if not isinstance(e.widget, tk.Text) else None)
        # Focus sur le premier champ utile : titre si l'ISBN est connu mais pas
        # le titre (introuvable en ligne), emplacement si la fiche est déjà
        # remplie, ISBN pour une saisie entièrement manuelle.
        focus = "title" if data.get("isbn") and not data.get("title") else "location" if data.get("title") else "isbn"
        self.vars[focus].focus_set()

    def refresh_info(self):
        """Recherche en ligne (:func:`lookup.fetch`, dans un thread) les informations de l'ISBN saisi.

        Les champs trouvés (:attr:`ONLINE`) remplacent ceux du formulaire ;
        rien n'est enregistré avant **Enregistrer**.
        """
        isbn = normalize(self.vars["isbn"].get().strip())
        if not isbn:
            messagebox.showinfo("Informations", "Saisissez un ISBN valide pour chercher les informations en ligne.",
                                parent=self)
            return
        self.info_btn.configure(state="disabled", text="Recherche en cours…")
        app = self.master
        threading.Thread(target=lambda: app.post(self._info_found, lookup.fetch(isbn)), daemon=True).start()

    def _info_found(self, info):
        """Fin de :meth:`refresh_info`, dans le thread de l'interface."""
        if not self.winfo_exists():  # formulaire fermé pendant la recherche
            return
        self.info_btn.configure(state="normal", text="Actualiser les informations")
        found = [f for f in self.ONLINE if (info or {}).get(f)]
        if not found:
            messagebox.showinfo("Informations", "Aucune information trouvée en ligne pour cet ISBN.", parent=self)
            return
        for f in found:
            w = self.vars[f]
            if isinstance(w, tk.Text):
                w.delete("1.0", "end")
                w.insert("1.0", info[f])
            else:
                w.delete(0, "end")
                w.insert(0, info[f])
        messagebox.showinfo("Informations", "Informations mises à jour : vérifiez-les puis cliquez sur Enregistrer.",
                            parent=self)

    def _preview(self, src):
        """Affiche l'image ``src`` (chemin ou octets) dans l'aperçu ; retourne ``False`` si elle est illisible."""
        if not Image or (isinstance(src, str) and not os.path.exists(src)):
            return False
        try:
            img = open_image(src)
            img.thumbnail((160, 240))
            self.photo = ImageTk.PhotoImage(img)  # référence à garder, sinon Tk efface l'image
        except Exception:
            return False
        self.cover_label.configure(image=self.photo, text="", width=0)
        return True

    def pick_cover(self):
        """Choisit une nouvelle jaquette sur le disque (enregistrée seulement si le formulaire est validé)."""
        src = filedialog.askopenfilename(parent=self, title="Choisir la jaquette",
                                         filetypes=[("Images", "*.jpg *.jpeg *.png *.gif *.bmp *.webp"),
                                                    ("Tous les fichiers", "*.*")])
        if not src:
            return
        if Image and not self._preview(src):
            messagebox.showerror("Jaquette", "Ce fichier n'est pas une image lisible.", parent=self)
            return
        self.cover_src = src
        if not Image:
            self.cover_label.configure(text=os.path.basename(src))

    def search_cover(self):
        """Cherche en ligne des jaquettes d'après l'ISBN, le titre et l'auteur saisis (dans un thread).

        Une seule trouvée : elle est affichée dans l'aperçu. Plusieurs : on
        choisit dans :class:`CoverPicker`.
        """
        get = lambda f: self.vars[f].get().strip()
        isbn, title, authors = normalize(get("isbn")) if get("isbn") else None, get("title"), get("authors")
        if not (isbn or title):
            messagebox.showinfo("Jaquette", "Saisissez l'ISBN ou le titre du livre.", parent=self)
            return
        self.search_btn.configure(state="disabled", text="Recherche en cours…")
        app = self.master
        threading.Thread(target=lambda: app.post(self._covers_found, lookup.find_covers(isbn, title, authors)),
                         daemon=True).start()

    def _covers_found(self, images):
        """Fin de :meth:`search_cover`, dans le thread de l'interface."""
        if not self.winfo_exists():  # formulaire fermé pendant la recherche
            return
        self.search_btn.configure(state="normal", text="Rechercher une jaquette…")
        if not images:
            messagebox.showinfo("Jaquette", "Aucune jaquette trouvée en ligne pour ce livre.", parent=self)
            return
        book = " - ".join(filter(None, (self.vars["title"].get().strip(), self.vars["authors"].get().strip())))
        img = images[0] if len(images) == 1 else CoverPicker(self, images, book).show()
        if img and self._preview(img):
            self.cover_src = img

    def save(self):
        """Valide la saisie (ISBN facultatif mais valide, titre obligatoire) et ferme."""
        out = {f: (w.get("1.0", "end").strip() if isinstance(w, tk.Text) else w.get().strip())
               for f, w in self.vars.items()}
        if out["isbn"]:
            isbn = normalize(out["isbn"])
            if not isbn:
                messagebox.showerror("ISBN invalide", "L'ISBN saisi n'est pas valide (laisser vide si le livre n'en a pas).", parent=self)
                return
            out["isbn"] = isbn
        if not out["title"]:
            messagebox.showerror("Titre manquant", "Le titre est obligatoire.", parent=self)
            return
        if out["read_date"]:
            try:
                out["read_date"] = parse_date(out["read_date"]).isoformat()
            except ValueError:
                messagebox.showerror("Date invalide", "Date de lecture : format attendu JJ/MM/AAAA.", parent=self)
                return
        self.result = out
        self.destroy()


def open_image(src):
    """Ouvre avec Pillow une image donnée par son chemin ou par ses octets."""
    return Image.open(io.BytesIO(src) if isinstance(src, bytes) else src)


class CoverPicker(Dialog):
    """Choix d'une jaquette parmi celles trouvées en ligne : un clic sur une image la choisit.

    ``book`` (« titre - auteur ») rappelle le livre concerné. Les boutons
    **−** et **+** changent la taille des images (:attr:`ZOOMS`).
    ``result`` contient les octets de l'image choisie.
    """
    #: Tailles proposées : (largeur, hauteur maximales, nombre de colonnes).
    ZOOMS = ((140, 210, 4), (220, 330, 3), (320, 480, 2))

    def __init__(self, master, images, book=""):
        super().__init__(master, "Choisir une jaquette")
        if book:
            ttk.Label(self.body, text=book, font=ui_font(13, "bold")).pack(anchor="w")
        ttk.Label(self.body, text=f"{len(images)} jaquettes trouvées : cliquez sur celle de votre édition.",
                  font=ui_font(11)).pack(anchor="w", pady=(0, 10))
        self.images, self.zoom = [], 0
        for data in images:
            try:
                self.images.append((data, open_image(data)))
            except Exception:
                pass  # image illisible : ignorée
        bar = ttk.Frame(self.body)
        bar.pack(side="bottom", fill="x", pady=(10, 0))  # avant les images : reste visible quand elles sont grandes
        # Images dans un canevas qui défile : en grand, elles dépasseraient de l'écran.
        self.canvas = tk.Canvas(self.body, highlightthickness=0, bg=COLORS["panel"])
        sb = ttk.Scrollbar(self.body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.grid_box = ttk.Frame(self.canvas)
        self.canvas.create_window(0, 0, window=self.grid_box, anchor="nw")
        self.bind("<MouseWheel>", lambda e: (self.canvas.yview_scroll(-e.delta // 120, "units"), "break")[1])
        ttk.Label(bar, text="Taille des images :").pack(side="left")
        self.smaller = ttk.Button(bar, text="−", width=3, command=lambda: self._render(-1))
        self.smaller.pack(side="left", padx=(6, 2))
        self.bigger = ttk.Button(bar, text="+", width=3, command=lambda: self._render(1))
        self.bigger.pack(side="left")
        ttk.Button(bar, text="Annuler", command=self.destroy).pack(side="right")
        self._render(0)

    def _render(self, step):
        """Redessine les jaquettes à la taille ``zoom + step``."""
        self.zoom = max(0, min(len(self.ZOOMS) - 1, self.zoom + step))
        w, h, cols = self.ZOOMS[self.zoom]
        self.smaller.state(["disabled" if self.zoom == 0 else "!disabled"])
        self.bigger.state(["disabled" if self.zoom == len(self.ZOOMS) - 1 else "!disabled"])
        for child in self.grid_box.winfo_children():
            child.destroy()
        self.photos = []  # références à garder, sinon Tk efface les images
        for n, (data, img) in enumerate(self.images):
            thumb = img.copy()
            thumb.thumbnail((w, h))
            photo = ImageTk.PhotoImage(thumb)
            self.photos.append(photo)
            ttk.Button(self.grid_box, image=photo, text=f"{img.width} × {img.height}", compound="top",
                       command=lambda d=data: self.choose(d)).grid(row=n // cols, column=n % cols, padx=4, pady=4,
                                                                    sticky="n")
        self.grid_box.update_idletasks()
        bw, bh = self.grid_box.winfo_reqwidth(), self.grid_box.winfo_reqheight()
        self.canvas.configure(width=bw, height=min(bh, self.winfo_screenheight() - 260), scrollregion=(0, 0, bw, bh))
        self.canvas.yview_moveto(0)
        if self.winfo_ismapped():  # agrandie : on la remonte et on la décale pour qu'elle reste dans l'écran
            self.update_idletasks()
            x = min(self.winfo_x(), self.winfo_screenwidth() - self.winfo_width() - 10)
            y = min(self.winfo_y(), self.winfo_screenheight() - self.winfo_height() - 60)
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def choose(self, data):
        self.result = data
        self.destroy()


class AboutDialog(Dialog):
    """Aide > À propos : version, dépôt, emplacement de la base et tableau des sources en ligne."""

    def __init__(self, master, db_path):
        super().__init__(master, "À propos de BookTek")
        ttk.Label(self.body, text=f"BookTek {__version__}", font=ui_font(14, "bold")).pack(anchor="w")
        ttk.Label(self.body, text="Gestion de bibliothèque par lecture d'ISBN.").pack(anchor="w")
        link = ttk.Label(self.body, text=f"https://github.com/{updater.REPO}", foreground=COLORS["info"], cursor="hand2")
        link.pack(anchor="w", pady=(6, 0))
        link.bind("<Button-1>", lambda e: webbrowser.open(link.cget("text")))
        ttk.Label(self.body, text=f"Base de données : {db_path}", foreground=COLORS["muted"]).pack(anchor="w", pady=(6, 12))
        ttk.Label(self.body, text="Sources des données (API utilisées) — double-clic pour ouvrir la page",
                  font=ui_font(10, "bold")).pack(anchor="w")
        tree = ttk.Treeview(self.body, columns=("name", "use", "url"), show="headings", height=len(lookup.SOURCES),
                            selectmode="browse")
        for key, label, width in (("name", "Service", 210), ("use", "Utilisé pour", 260), ("url", "Adresse", 330)):
            tree.heading(key, text=label, anchor="w")
            tree.column(key, width=width, anchor="w")
        tree.tag_configure("odd", background=COLORS["stripe"])
        for n, row in enumerate(lookup.SOURCES):
            tree.insert("", "end", values=row, tags=("odd",) if n % 2 else ())
        tree.bind("<Double-1>", lambda e: tree.focus() and webbrowser.open(tree.set(tree.focus(), "url")))
        tree.pack(fill="x", pady=(4, 12))
        ttk.Button(self.body, text="Fermer", command=self.destroy).pack(anchor="e")


class LendDialog(Dialog):
    """Saisie d'un prêt : emprunteur et date de retour prévue.

    ``borrowers`` alimente la liste déroulante (emprunteurs déjà connus).
    ``result`` est un tuple ``(emprunteur, date_retour_iso_ou_None)`` ;
    vider le champ date crée un prêt sans échéance.
    """

    def __init__(self, master, book, borrowers):
        super().__init__(master, "Prêter un livre")
        ttk.Label(self.body, text=book["title"], font=ui_font(11, "bold"), wraplength=380).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(self.body, text="Emprunteur :").grid(row=1, column=0, sticky="e", padx=(0, 8), pady=3)
        self.who = ttk.Combobox(self.body, values=borrowers, width=32)
        self.who.grid(row=1, column=1, sticky="we", pady=3)
        ttk.Label(self.body, text="Retour prévu le :").grid(row=2, column=0, sticky="e", padx=(0, 8), pady=3)
        self.due = ttk.Entry(self.body, width=14)
        self.due.insert(0, (dt.date.today() + dt.timedelta(days=LOAN_DAYS)).strftime("%d/%m/%Y"))
        self.due.grid(row=2, column=1, sticky="w", pady=3)
        bar = ttk.Frame(self.body)
        bar.grid(row=3, column=0, columnspan=2, pady=(10, 0), sticky="e")
        ttk.Button(bar, text="Prêter", command=self.ok).pack(side="left", padx=4)
        ttk.Button(bar, text="Annuler", command=self.destroy).pack(side="left")
        self.bind("<Return>", lambda e: self.ok())
        self.who.focus_set()

    def ok(self):
        """Valide l'emprunteur (obligatoire) et la date (facultative, JJ/MM/AAAA) puis ferme."""
        who = self.who.get().strip()
        if not who:
            messagebox.showerror("Emprunteur manquant", "Indiquez le nom de l'emprunteur.", parent=self)
            return
        due_text = self.due.get().strip()
        due = None
        if due_text:
            try:
                due = parse_date(due_text).isoformat()
            except ValueError:
                messagebox.showerror("Date invalide", "Format attendu : JJ/MM/AAAA.", parent=self)
                return
        self.result = (who, due)
        self.destroy()


class BorrowerForm(Dialog):
    """Fiche d'un contact de l'annuaire ; ``result`` est un dict name/phone/email/notes."""

    FIELDS = (("name", "Nom"), ("phone", "Téléphone"), ("email", "E-mail"), ("notes", "Notes"))

    def __init__(self, master, data, title="Contact"):
        super().__init__(master, title)
        self.vars = {}
        for r, (f, label) in enumerate(self.FIELDS):
            ttk.Label(self.body, text=label + " :").grid(row=r, column=0, sticky="e", padx=(0, 8), pady=3)
            w = ttk.Entry(self.body, width=40)
            w.insert(0, data.get(f) or "")
            w.grid(row=r, column=1, sticky="we", pady=3)
            self.vars[f] = w
        bar = ttk.Frame(self.body)
        bar.grid(row=len(self.FIELDS), column=0, columnspan=2, pady=(10, 0), sticky="e")
        ttk.Button(bar, text="Enregistrer", command=self.save).pack(side="left", padx=4)
        ttk.Button(bar, text="Annuler", command=self.destroy).pack(side="left")
        self.bind("<Return>", lambda e: self.save())
        self.vars["name"].focus_set()

    def save(self):
        out = {f: w.get().strip() for f, w in self.vars.items()}
        if not out["name"]:
            messagebox.showerror("Nom manquant", "Le nom est obligatoire.", parent=self)
            return
        self.result = out
        self.destroy()


def book_details(parent, book, loan, cover, wrap=440, summary_max=600, cover_parent=None):
    """Place la jaquette (dans ``cover_parent``, à défaut à gauche de ``parent``) et la description
    du livre (titre, auteurs, détails, état du prêt, résumé) dans ``parent``.

    Le résumé est coupé à ``summary_max`` caractères ; avec ``None``, il est
    affiché en entier dans une zone qui défile.

    Utilisé par la fiche (:class:`BookCard`) et le panneau sous la liste.
    Retourne l'image affichée (à garder en référence, sinon Tk l'efface), ou ``None``.
    """
    photo = None
    if Image and os.path.exists(cover):
        try:
            img = Image.open(cover)
            img.thumbnail((160, 240))
            photo = ImageTk.PhotoImage(img)
            ttk.Label(cover_parent or parent, image=photo).pack(side="left", anchor="n", padx=(0, 14))
        except Exception:
            pass  # image illisible : fiche sans couverture
    ttk.Label(parent, text=book["title"], font=ui_font(13, "bold"), wraplength=wrap).pack(anchor="w")
    if book["authors"]:
        ttk.Label(parent, text=book["authors"], font=ui_font(11)).pack(anchor="w")
    details = " · ".join(x for x in (book["isbn"], book["publisher"], book["year"], book["genre"],
                                     book["pages"] and f"{book['pages']} pages", place(book)) if x)
    ttk.Label(parent, text=details, foreground=COLORS["muted"], wraplength=wrap).pack(anchor="w", pady=(2, 8))
    if loan:
        late = loan["due_date"] and loan["due_date"] < dt.date.today().isoformat()
        msg = f"Prêté à {loan['borrower']} depuis le {fmt_date(loan['loan_date'])}"
        if loan["due_date"]:
            msg += f" — retour prévu le {fmt_date(loan['due_date'])}"
        ttk.Label(parent, text=msg + (" (EN RETARD)" if late else ""), foreground=COLORS["err" if late else "warn"],
                  font=ui_font(11, "bold"), wraplength=wrap, justify="left").pack(anchor="w")
    else:
        ttk.Label(parent, text="Disponible", foreground=COLORS["ok"], font=ui_font(11, "bold")).pack(anchor="w")
    if book["summary"] and summary_max is None:  # panneau : résumé complet, avec défilement
        box = ttk.Frame(parent)
        box.pack(fill="both", expand=True, pady=(8, 0))
        sb = ttk.Scrollbar(box, orient="vertical")
        t = tk.Text(box, wrap="word", font="TkDefaultFont", relief="flat", highlightthickness=0, height=1,
                    bg=ttk.Style(parent).lookup("TFrame", "background"), fg=COLORS["fg"], yscrollcommand=sb.set)
        sb.config(command=t.yview)
        t.insert("1.0", book["summary"])
        t.config(state="disabled")
        sb.pack(side="right", fill="y")
        t.pack(side="left", fill="both", expand=True)
    elif book["summary"]:
        text = book["summary"]
        if len(text) > summary_max:
            text = text[:summary_max].rstrip() + "…"
        ttk.Label(parent, text=text, wraplength=wrap, justify="left").pack(anchor="w", pady=(8, 0))
    return photo


class BookCard(Dialog):
    """Fiche d'un livre connu, avec les actions possibles.

    Affiche le livre et son état (disponible, prêté, en retard). ``result``
    vaut ``"lend"``, ``"return"``, ``"edit"`` ou ``None`` (fermé) ; c'est
    l'appelant (:meth:`App.book_actions`) qui exécute l'action.

    Entrée n'est volontairement pas liée : une douchette envoie Entrée après
    chaque code, et un scan fait par erreur pendant que la fiche est ouverte
    ne doit pas déclencher un retour. L'action principale a le focus, la
    barre d'espace la déclenche.
    """

    def __init__(self, master, book, loan, cover):
        super().__init__(master, "Livre")
        self.photo = book_details(self.body, book, loan, cover)
        bar = ttk.Frame(self.body)
        bar.pack(anchor="e", pady=(14, 0))
        main = ttk.Button(bar, text="Enregistrer le retour" if loan else "Prêter…",
                          command=lambda: self.choose("return" if loan else "lend"))
        main.pack(side="left", padx=4)
        ttk.Button(bar, text="Modifier…", command=lambda: self.choose("edit")).pack(side="left", padx=4)
        ttk.Button(bar, text="Fermer", command=self.destroy).pack(side="left")
        main.focus_set()  # Espace = action principale

    def choose(self, action):
        """Mémorise l'action choisie et ferme la fiche."""
        self.result = action
        self.destroy()


class CoverGrid(ttk.Frame):
    """Vue « Miniatures » de la bibliothèque : une case par livre (couverture, titre, auteur), en grille.

    La grille n'a pas d'état propre : :meth:`show` reçoit les livres déjà
    filtrés et triés (dans l'ordre du tableau de la vue Liste). Un clic
    appelle ``on_select(iid)``, un double-clic ``on_open(iid)``. Sans
    couverture (ou sans Pillow), la case affiche le titre sur fond gris.
    """
    TILE = 124  # largeur d'une case, marges comprises (pixels)
    W, H = 100, 150  # taille maximale d'une miniature

    def __init__(self, master, on_select, on_open, on_menu):
        super().__init__(master)
        self.on_select, self.on_open, self.on_menu = on_select, on_open, on_menu
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=COLORS["panel"])
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.inner = tk.Frame(self.canvas, bg=COLORS["panel"])
        self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self._layout())
        # Molette : liée globalement (les cases captent le pointeur), filtrée sur la position.
        self.bind_all("<MouseWheel>", self._wheel, add="+")
        self.blank = tk.PhotoImage(width=self.W, height=self.H)
        self.cache = {}  # (chemin, date de modification) -> PhotoImage ou None
        self.tiles = {}  # iid -> case, dans l'ordre d'affichage
        self.cols = 0

    def _wheel(self, event):
        w = self.winfo_containing(event.x_root, event.y_root)
        if w is not None and str(w).startswith(str(self)):
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _thumb(self, path):
        """Miniature de la couverture ``path`` (mise en cache), ou ``None`` si absente ou illisible."""
        if not (Image and os.path.exists(path)):
            return None
        key = (path, os.path.getmtime(path))
        if key not in self.cache:
            try:
                img = Image.open(path)
                img.thumbnail((self.W, self.H))
                self.cache[key] = ImageTk.PhotoImage(img)
            except Exception:
                self.cache[key] = None
        return self.cache[key]

    def show(self, items, selected=None):
        """Affiche ``items`` : suite de ``(iid, titre, auteurs, chemin de couverture)``."""
        for tile in self.tiles.values():
            tile.destroy()
        self.tiles = {}
        cut = lambda s, n: s if len(s) <= n else s[:n - 1].rstrip() + "…"
        for iid, title, authors, cover in items:
            bg = COLORS["panel"]
            tile = tk.Frame(self.inner, bg=bg, padx=4, pady=4, highlightthickness=2, highlightbackground=bg)
            img = self._thumb(cover)
            tk.Label(tile, image=img or self.blank, width=self.W, height=self.H, compound="center",
                     text="" if img else cut(title, 60), wraplength=self.W - 12, fg=COLORS["tile_fg"],
                     bg=bg if img else COLORS["tile"]).pack()
            tk.Label(tile, text=cut(title, 30), font=ui_font(9, "bold"), bg=bg, fg=COLORS["fg"],
                     wraplength=self.TILE - 16, height=2).pack()
            tk.Label(tile, text=cut(authors.split(",")[0], 20), font=ui_font(8), fg=COLORS["muted"], bg=bg).pack()
            for w in (tile, *tile.winfo_children()):
                w.bind("<Button-1>", lambda e, i=iid: self.select(i))
                w.bind("<Double-1>", lambda e, i=iid: self.on_open(i))
                w.bind("<Button-3>", lambda e, i=iid: (self.select(i), self.on_menu(e)))
            self.tiles[iid] = tile
        self.cols = 0  # force la remise en grille
        self.update_idletasks()  # sinon les nouvelles cases ont une largeur demandée de 1 px : tout sur une ligne
        self._layout()
        self.canvas.yview_moveto(0)
        if selected in self.tiles:
            self.select(selected, notify=False)

    def _layout(self):
        """Place les cases en autant de colonnes que la largeur le permet (recalculé au redimensionnement)."""
        tile_w = max((t.winfo_reqwidth() for t in self.tiles.values()), default=self.TILE)  # largeur réelle, bordures comprises
        cols = max(1, self.canvas.winfo_width() // tile_w)
        if cols == self.cols:
            return
        self.cols = cols
        for n, tile in enumerate(self.tiles.values()):
            tile.grid(row=n // cols, column=n % cols, sticky="n")

    def select(self, iid, notify=True):
        """Encadre la case ``iid`` (et prévient l'application)."""
        for i, tile in self.tiles.items():
            tile.configure(highlightbackground=COLORS["info"] if i == iid else COLORS["panel"])
        if notify:
            self.on_select(iid)


# ---------------------------------------------------------------------------
# Fenêtre principale
# ---------------------------------------------------------------------------
class App(tk.Tk):
    """Fenêtre principale de BookTek.

    Attributs principaux :

    * ``lib`` : la :class:`~booktek.db.Library` ouverte sur ``db_path`` ;
    * ``mode`` : mode de scan (``"auto"``, ``"add"`` ou ``"return"``) ;
    * ``q`` : file des callbacks envoyés par les threads (voir :meth:`post`) ;
    * ``pending`` : ISBN en cours de recherche en ligne, pour ignorer un
      double scan du même livre pendant la recherche ;
    * ``update_ready`` : :class:`~booktek.updater.Release` téléchargée et
      prête à installer, ou ``None``.
    """

    def __init__(self, db_path):
        super().__init__()
        self.title(f"BookTek {__version__}")
        self.geometry("1100x700")
        self.minsize(820, 520)
        try:  # icône de toutes les fenêtres ; embarquée dans l'exe par tools/release.py (--add-data)
            self.iconbitmap(default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico"))
        except tk.TclError:
            pass  # fichier absent : icône Tk par défaut
        self.lib = Library(db_path)
        self.db_path = db_path
        self.q = queue.Queue()
        self.pending = set()  # ISBN en cours de recherche en ligne
        self.update_ready = None
        self.group_value = None  # groupe choisi dans le panneau de gauche (None = tous les livres)
        self._update_busy = False  # une vérification de mise à jour est en cours
        self.settings_path = os.path.join(os.path.dirname(db_path), "settings.json")
        try:
            with open(self.settings_path, encoding="utf-8") as f:
                self.settings = json.load(f)
        except (OSError, ValueError):
            self.settings = {}  # premier lancement ou fichier abîmé : réglages par défaut
        self._build()
        self.refresh()
        self.after(100, self._poll)
        self.after(3000, self.check_updates_auto)  # laisse l'interface s'afficher d'abord
        self.set_status(f"Prêt. Scannez un ISBN. (Base : {db_path})", "info")

    # ---- construction ---------------------------------------------------
    def _build(self):
        """Crée le menu, la zone de scan, la ligne de statut, les onglets et le pied de page."""
        self._apply_theme()

        menubar = tk.Menu(self)
        m = tk.Menu(menubar, tearoff=False)
        m.add_command(label="Importer une collection Book Collector (.bkc)…", command=self.import_bkc)
        m.add_command(label="Importer une liste d'ISBN (texte ou CSV)…", command=self.import_isbn_list)
        m.add_command(label="Compléter les fiches via Internet (résumés, couvertures…)", command=self.enrich)
        m.add_command(label="Exporter en CSV…", command=self.export_csv)
        m.add_separator()
        m.add_command(label="Quitter", command=self.destroy)
        menubar.add_cascade(label="Fichier", menu=m)
        m = tk.Menu(menubar, tearoff=False)
        for key, label in (("dark", "Thème sombre"), ("large", "Grands caractères"),
                           ("groups", "Liste par auteur, année ou genre à gauche")):
            var = tk.BooleanVar(self, value=bool(self.settings.get(key)))
            m.add_checkbutton(label=label, variable=var, command=lambda k=key, v=var: self.set_setting(k, v.get()))
        m.add_separator()
        side = tk.StringVar(self, value=self.settings.get("detail", "bottom"))
        for val, label in (("bottom", "Fiche du livre en bas"), ("right", "Fiche du livre à droite")):
            m.add_radiobutton(label=label, value=val, variable=side, command=lambda: self.set_setting("detail", side.get()))
        menubar.add_cascade(label="Affichage", menu=m)
        m = tk.Menu(menubar, tearoff=False)
        m.add_command(label="Rechercher une mise à jour", command=self.check_updates_manual)
        m.add_command(label="À propos de BookTek", command=self.about)
        menubar.add_cascade(label="Aide", menu=m)
        self.config(menu=menubar)

        top = ttk.Frame(self, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        ttk.Label(top, text="ISBN :", font=ui_font(14)).pack(side="left")
        self.scan = ttk.Entry(top, font=("Consolas", 18), width=20)
        self.scan.pack(side="left", padx=8)
        self.scan.bind("<Return>", self.on_scan)
        ttk.Button(top, text="OK", command=self.on_scan).pack(side="left")

        modes = ttk.LabelFrame(top, text="Mode de scan", padding=(8, 2))
        modes.pack(side="left", padx=16)
        self.mode = tk.StringVar(value="auto")
        for val, txt in (("auto", "Automatique"), ("add", "Ajout rapide"), ("return", "Retour rapide")):
            ttk.Radiobutton(modes, text=txt, value=val, variable=self.mode,
                            command=lambda: self.scan.focus_set()).pack(side="left", padx=4)

        # Bouton affiché seulement quand une mise à jour est téléchargée (voir _update_done).
        self.update_btn = tk.Button(top, text="Mettre à jour", command=self.install_update, bg=COLORS["info"],
                                    fg="white", activebackground=COLORS["ok"], activeforeground="white",
                                    font=ui_font(10, "bold"), relief="flat", padx=10, pady=4, cursor="hand2")

        self.status = tk.Label(self, anchor="w", font=ui_font(12, "bold"), padx=14, pady=4)
        self.status.pack(fill="x")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(4, 0))

        # Onglet bibliothèque. Les lignes ont pour iid l'id du livre en base.
        lib = ttk.Frame(self.nb, padding=6)
        self.nb.add(lib, text="Bibliothèque")
        bar = ttk.Frame(lib)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Rechercher :").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *a: self.refresh_books())
        ttk.Entry(bar, textvariable=self.search, width=30).pack(side="left", padx=6)
        self.count = ttk.Label(bar, font=ui_font(11, "bold"))  # nombre de livres affichés (filtre compris)
        self.count.pack(side="left", padx=10)
        ttk.Button(bar, text="Ajouter manuellement…", command=self.add_manual).pack(side="right", padx=3)
        bar = ttk.Frame(lib)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Chercher dans :").pack(side="left")
        self.search_in = ttk.Combobox(bar, values=list(SEARCH_IN), state="readonly", width=8)
        self.search_in.set("Tout")
        self.search_in.bind("<<ComboboxSelected>>", lambda e: self.refresh_books())
        self.search_in.pack(side="left", padx=(6, 16))
        ttk.Label(bar, text="Trier par :").pack(side="left")
        self.sort_by = ttk.Combobox(bar, values=list(SORTS), state="readonly", width=8)
        self.sort_by.bind("<<ComboboxSelected>>", self.sort_books)
        self.sort_by.pack(side="left", padx=6)
        self.sort_desc = tk.BooleanVar()
        ttk.Checkbutton(bar, text="Décroissant", variable=self.sort_desc, command=self.sort_books).pack(side="left")
        self.view = tk.StringVar(value="list")
        for val, txt in (("grid", "Miniatures"), ("list", "Liste")):
            ttk.Radiobutton(bar, text=txt, value=val, variable=self.view, command=self.show_view).pack(side="right", padx=4)
        ttk.Label(bar, text="Affichage :").pack(side="right")
        # Liste (ou miniatures), puis fiche du livre sélectionné en bas ou à droite ; la séparation se déplace à la souris.
        # Si activé (menu Affichage), panneau de gauche : auteurs, années ou genres, un clic filtre la bibliothèque.
        outer = ttk.PanedWindow(lib, orient="horizontal")
        outer.pack(fill="both", expand=True)
        self.group_tree = None
        if self.settings.get("groups"):
            side = ttk.Frame(outer, width=250, padding=(0, 0, 8, 0))
            side.pack_propagate(False)
            outer.add(side, weight=0)
            row = ttk.Frame(side)
            row.pack(fill="x", pady=(0, 6))
            ttk.Label(row, text="Par :").pack(side="left")
            self.group_by = ttk.Combobox(row, values=list(GROUPS), state="readonly", width=8)
            self.group_by.set(self.settings.get("group_by", "Auteur"))
            self.group_by.bind("<<ComboboxSelected>>", self._group_changed)
            self.group_by.pack(side="left", padx=6)
            self.group_tree = self._tree(side, (("name", "Auteur", 150), ("n", "Livres", 55)))
            self.group_tree.bind("<<TreeviewSelect>>", self._group_selected)
        self.detail_right = self.settings.get("detail") == "right"  # menu Affichage
        paned = ttk.PanedWindow(outer, orient="horizontal" if self.detail_right else "vertical")
        outer.add(paned, weight=1)
        self.view_box = ttk.Frame(paned)
        self.detail = ttk.Frame(paned, width=460, height=280, padding=(12, 0, 0, 0) if self.detail_right else (4, 10, 4, 0))
        self.detail.pack_propagate(False)  # taille fixée par la séparation, pas par le contenu
        self._detail_w = 0
        self.detail.bind("<Configure>", lambda e: e.width != self._detail_w and self.show_detail())
        paned.add(self.view_box, weight=3)
        paned.add(self.detail, weight=1)
        self.books = self._tree(self.view_box, (("isbn", "ISBN", 110), ("title", "Titre", 280), ("authors", "Auteur(s)", 160),
                                      ("publisher", "Éditeur", 110), ("year", "Année", 55), ("genre", "Genre", 100),
                                      ("read_date", "Lu le", 85), ("place", "Emplacement", 160),
                                      ("status", "Statut", 140)))
        self.books.bind("<Double-1>", lambda e: self.open_selected())
        self.books.bind("<<TreeviewSelect>>", lambda e: self.show_detail())
        self.books._on_sort = self._books_sorted  # synchronise « Trier par » avec un clic sur un en-tête
        self.covers = CoverGrid(self.view_box, on_select=self.books.selection_set, on_open=lambda iid: self.open_selected(),
                                on_menu=self.book_menu)
        self.books.bind("<Button-3>", lambda e: self.books.identify_row(e.y) and (
            self.books.selection_set(self.books.identify_row(e.y)), self.book_menu(e)))

        # Onglet prêts en cours. iid = id du livre (un seul prêt en cours par livre).
        loans = ttk.Frame(self.nb, padding=6)
        self.nb.add(loans, text="Prêts en cours")
        bar = ttk.Frame(loans)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="Enregistrer le retour", command=self.return_selected_loan).pack(side="right")
        self.loans = self._tree(loans, (("title", "Titre", 340), ("borrower", "Emprunteur", 160),
                                        ("loan", "Prêté le", 90), ("elapsed", "Depuis", 70),
                                        ("due", "Retour prévu", 100), ("late", "Retard", 80)))
        self.loans.tag_configure("late", foreground=COLORS["err"])

        # Onglet historique
        hist = ttk.Frame(self.nb, padding=6)
        self.nb.add(hist, text="Historique des prêts")
        self.hist = self._tree(hist, (("title", "Titre", 380), ("borrower", "Emprunteur", 160),
                                      ("loan", "Prêté le", 90), ("ret", "Rendu le", 90), ("elapsed", "Durée", 70)))

        # Onglet annuaire. iid = nom du contact.
        people = ttk.Frame(self.nb, padding=6)
        self.nb.add(people, text="Annuaire")
        bar = ttk.Frame(people)
        bar.pack(fill="x", pady=(0, 6))
        for txt, cmd in (("Supprimer", self.delete_borrower), ("Modifier…", self.edit_borrower),
                         ("Ajouter…", self.add_borrower)):
            ttk.Button(bar, text=txt, command=cmd).pack(side="right", padx=3)
        self.people = self._tree(people, (("name", "Nom", 180), ("phone", "Téléphone", 120), ("email", "E-mail", 200),
                                          ("active", "En cours", 70), ("elapsed", "Prêt le plus ancien", 130),
                                          ("total", "Total prêts", 80), ("notes", "Notes", 200)))
        self.people.tag_configure("late", foreground=COLORS["err"])
        self.people.bind("<Double-1>", lambda e: self.edit_borrower())

        self.footer = ttk.Label(self, padding=(14, 4))
        self.footer.pack(fill="x")
        self.bind_all("<F2>", lambda e: self.scan.focus_set())
        self.scan.focus_set()
        if self.update_ready:  # interface reconstruite (changement d'affichage) après le téléchargement
            self.update_btn.config(text=f"⬆ Mettre à jour vers {self.update_ready.version}")
            self.update_btn.pack(side="right")

    def _apply_theme(self):
        """Applique les réglages d'affichage : thème clair (Windows) ou sombre, taille du texte.

        Les widgets ttk suivent le style ; les widgets tk (statut, miniatures,
        champs multilignes) lisent :data:`COLORS` et la base d'options à leur
        création, d'où la reconstruction de l'interface dans :meth:`set_setting`.
        """
        dark = bool(self.settings.get("dark"))
        COLORS.clear()
        COLORS.update(DARK if dark else LIGHT)
        FONT_BONUS[0] = 3 if self.settings.get("large") else 0
        size = 9 + FONT_BONUS[0]  # 9 = taille par défaut de Windows
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(name).configure(size=size)
        style = ttk.Style(self)
        self.option_clear()
        if dark:
            bg, field, fg, sel, btn = COLORS["panel"], "#2d2d2d", COLORS["fg"], "#2f6fc0", "#3c3c3c"
            style.theme_use("clam")  # le thème Windows (vista) ne se recolore pas
            style.configure(".", background=bg, foreground=fg, fieldbackground=field, bordercolor="#6a6a6a",
                            lightcolor=field, darkcolor=bg, troughcolor=bg, selectbackground=sel,
                            selectforeground="white", insertcolor=fg, arrowcolor=fg)
            style.map(".", foreground=[("disabled", "#9a9a9a")])
            style.configure("TButton", background=btn, padding=(8, 3))
            style.configure("TScrollbar", background=btn, troughcolor=bg, bordercolor=bg, arrowcolor=fg)
            style.map("TScrollbar", background=[("active", "#5a5a5a")])
            style.map("TButton", background=[("pressed", "#5a5a5a"), ("active", "#4c4c4c")])
            style.configure("Treeview", background=field, fieldbackground=field, foreground=fg)
            style.map("Treeview", background=[("selected", sel)], foreground=[("selected", "white")])
            style.configure("Treeview.Heading", background=btn, foreground=fg)
            style.map("Treeview.Heading", background=[("active", "#4c4c4c")])
            style.configure("TNotebook.Tab", background=field, padding=(10, 4))
            style.map("TNotebook.Tab", background=[("selected", sel)], foreground=[("selected", "white")])
            style.map("TCombobox", fieldbackground=[("readonly", field)], selectbackground=[("readonly", field)],
                      selectforeground=[("readonly", fg)])
            for w in ("TCheckbutton", "TRadiobutton"):
                style.configure(w, indicatorbackground=field, indicatorforeground=fg)
                style.map(w, background=[("active", bg)], indicatorbackground=[("selected", sel)])
            for opt, val in (("*Label.background", bg), ("*Label.foreground", fg), ("*Frame.background", bg),
                             ("*Text.background", field), ("*Text.foreground", fg), ("*Text.insertBackground", fg),
                             ("*TCombobox*Listbox.background", field), ("*TCombobox*Listbox.foreground", fg),
                             ("*TCombobox*Listbox.selectBackground", sel)):
                self.option_add(opt, val)
        elif "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=tkfont.nametofont("TkDefaultFont").metrics("linespace") + 8)

    def set_setting(self, key, value):
        """Enregistre un réglage d'affichage et reconstruit l'interface pour l'appliquer tout de suite."""
        self.settings[key] = value
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f)
        except OSError:
            pass  # réglage appliqué pour cette session seulement
        tab, view, sel = self.nb.index("current"), self.view.get(), self.books.selection()
        for w in self.winfo_children():
            if not isinstance(w, tk.Toplevel):
                w.destroy()
        self._build()
        self.view.set(view)
        self.show_view()
        self.refresh()
        self.nb.select(tab)
        if sel and self.books.exists(sel[0]):
            self.books.selection_set(sel[0])
        self.set_status("Affichage modifié.", "info")

    def _tree(self, parent, cols):
        """Crée un tableau (Treeview + barre de défilement) dans ``parent``.

        ``cols`` est une suite de ``(clé, en-tête, largeur)``. Un clic sur un
        en-tête trie la colonne, un 2e clic inverse l'ordre.
        """
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=[c[0] for c in cols], show="headings", selectmode="browse")
        tree._labels = {key: label for key, label, _ in cols}
        tree._sort_state = None
        for key, label, width in cols:
            tree.heading(key, text=label, command=lambda k=key: self._sort(
                tree, k, tree._sort_state == (k, False)))
            tree.column(key, width=width, minwidth=width, anchor="w")  # minwidth : défilement horizontal plutôt que colonnes écrasées
        tree.tag_configure("odd", background=COLORS["stripe"])  # une ligne sur deux en relief, voir _stripe
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=sb.set, xscrollcommand=hsb.set)
        sb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        tree.pack(side="left", fill="both", expand=True)
        return tree

    @staticmethod
    def _sort(tree, col, desc):
        """Trie ``tree`` sur ``col`` (voir :func:`sort_key`) et marque l'en-tête d'une flèche.

        Le tri est mémorisé sur le widget (``tree._sort_state``) et réappliqué
        après chaque rafraîchissement par :meth:`_resort`.
        """
        rows = sorted(tree.get_children(""), key=lambda i: sort_key(tree.set(i, col), col), reverse=desc)
        for idx, i in enumerate(rows):
            tree.move(i, "", idx)
        tree._sort_state = (col, desc)
        for key, label in tree._labels.items():
            tree.heading(key, text=label + ((" ▼" if desc else " ▲") if key == col else ""))
        if hasattr(tree, "_on_sort"):
            tree._on_sort(col, desc)
        App._stripe(tree)

    def _resort(self, tree):
        """Réapplique le tri mémorisé (après un rafraîchissement) et l'alternance des lignes."""
        if tree._sort_state:
            self._sort(tree, *tree._sort_state)
        self._stripe(tree)

    @staticmethod
    def _stripe(tree):
        """Colore une ligne sur deux (tag ``odd``) dans l'ordre affiché, en gardant les autres tags (``late``)."""
        for idx, i in enumerate(tree.get_children("")):
            tags = [t for t in tree.item(i, "tags") if t != "odd"]
            tree.item(i, tags=tags + ["odd"] * (idx % 2))

    # ---- utilitaires ----------------------------------------------------
    def set_status(self, msg, kind="info"):
        """Affiche ``msg`` dans la ligne de statut, coloré selon ``kind`` (clé de :data:`COLORS`).

        Les erreurs émettent aussi un bip système, pour qu'on les remarque
        sans regarder l'écran pendant une série de scans.
        """
        self.status.config(text=msg, fg=COLORS[kind])
        if kind == "err" and winsound:
            winsound.MessageBeep(winsound.MB_ICONHAND)

    def post(self, fn, *args):
        """Planifie ``fn(*args)`` dans le thread de l'interface.

        C'est la seule méthode d'``App`` qu'un thread secondaire a le droit
        d'appeler : :class:`queue.Queue` est sûre entre threads, contrairement
        à Tkinter et SQLite.
        """
        self.q.put((fn, args))

    def _poll(self):
        """Exécute les callbacks en attente dans :attr:`q`, puis se replanifie dans 100 ms."""
        try:
            while True:
                fn, args = self.q.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def refocus(self):
        """Redonne le focus au champ de scan, pour que le prochain code lu y arrive."""
        self.scan.focus_set()

    # ---- rafraîchissement -----------------------------------------------
    def refresh(self):
        """Recharge les trois onglets et les compteurs depuis la base.

        Appelé après chaque modification. Le volume d'une bibliothèque
        personnelle (quelques milliers de livres) permet de tout recharger
        plutôt que de mettre à jour ligne par ligne.
        """
        self.refresh_books()
        self.loans.delete(*self.loans.get_children())
        for r in self.lib.active_loans():
            late = days_since(r["due_date"]) if r["due_date"] else 0
            self.loans.insert("", "end", iid=str(r["book_id"]), tags=("late",) if late > 0 else (),
                              values=(r["title"], r["borrower"], fmt_date(r["loan_date"]),
                                      f"{days_since(r['loan_date'])} j", fmt_date(r["due_date"]),
                                      f"{late} j" if late > 0 else ""))
        self.hist.delete(*self.hist.get_children())
        for r in self.lib.history():
            self.hist.insert("", "end", values=(r["title"], r["borrower"], fmt_date(r["loan_date"]),
                                                fmt_date(r["return_date"]) or "en cours",
                                                f"{days_since(r['loan_date'], r['return_date'])} j"))
        self.people.delete(*self.people.get_children())
        overdue = {r["borrower"] for r in self.lib.active_loans() if r["due_date"] and days_since(r["due_date"]) > 0}
        for r in self.lib.directory():
            oldest = f"{days_since(r['oldest_active'])} j" if r["oldest_active"] else ""
            self.people.insert("", "end", iid=r["name"], tags=("late",) if r["name"] in overdue else (), values=(
                r["name"], r["phone"], r["email"], r["active"] or "", oldest, r["total"], r["notes"]))
        for tree in (self.loans, self.hist, self.people):
            self._resort(tree)
        s = self.lib.stats()
        self.footer.config(text=f"{s['books']} livres · {s['lent']} prêtés · {s['overdue']} en retard")
        self.nb.tab(1, text=f"Prêts en cours ({s['lent']})")

    def refresh_books(self):
        """Recharge l'onglet Bibliothèque selon la recherche (appelé à chaque frappe).

        « Chercher dans : Tout » fait la recherche plein texte de la base ;
        sinon le texte est cherché dans le seul champ choisi.
        """
        field, text = SEARCH_IN[self.search_in.get()], self.search.get().strip().lower()
        rows = self.lib.search("" if field else text)
        if field:
            rows = [r for r in rows if text in (r[field] or "").lower()]
        if self.group_tree:
            rows = self._fill_groups(rows)
        sel = self.books.selection()
        self.books.delete(*self.books.get_children())
        for r in rows:
            status = f"Prêté à {r['borrower']}" if r["borrower"] else "Disponible"
            self.books.insert("", "end", iid=str(r["id"]), values=(
                r["isbn"] or "", r["title"], r["authors"], r["publisher"], r["year"], r["genre"],
                fmt_date(r["read_date"]), place(r), status))
        self._resort(self.books)
        if sel and self.books.exists(sel[0]):
            self.books.selection_set(sel[0])  # la fiche du bas reste sur le livre, mise à jour
        self.count.config(text=f"{len(rows)} livre{'s' if len(rows) > 1 else ''}")
        self.show_covers()
        self.show_detail()

    def _fill_groups(self, rows):
        """Remplit le panneau de gauche à partir des livres ``rows`` (recherche appliquée)
        et retourne ceux du groupe sélectionné (tous si « Tous les livres »).

        Chaque valeur du champ choisi y figure avec son nombre de livres, triée
        comme « Trier par » (auteurs par nom de famille), « non renseigné » en dernier.
        """
        label = self.group_by.get()
        field = GROUPS[label]
        counts = {}
        for r in rows:
            for n in group_names(r[field], field):
                counts[n] = counts.get(n, 0) + 1
        if self.group_value not in counts:
            self.group_value = None
        tree = self.group_tree
        tree._labels["name"] = label
        tree.heading("name", text=label)
        tree.delete(*tree.get_children())
        tree.insert("", "end", iid="*", values=("(Tous les livres)", len(rows)))
        names = sorted(counts, key=lambda n: (n == NO_VALUE, sort_key(n, field)))
        for i, n in enumerate(names):
            tree.insert("", "end", iid=str(i), values=(n, counts[n]))
        iid = "*" if self.group_value is None else str(names.index(self.group_value))
        tree.selection_set(iid)
        tree.see(iid)
        self._resort(tree)
        if self.group_value is None:
            return rows
        return [r for r in rows if self.group_value in group_names(r[field], field)]

    def _group_selected(self, event=None):
        """Clic dans le panneau de gauche : n'affiche que les livres du groupe choisi."""
        sel = self.group_tree.selection()
        value = None if not sel or sel[0] == "*" else self.group_tree.set(sel[0], "name")
        if value != self.group_value:  # sinon : sélection remise par _fill_groups, rien à faire
            self.group_value = value
            self.refresh_books()

    def _group_changed(self, event=None):
        """Changement de regroupement (auteur, année, genre) : retour à « Tous les livres »."""
        self.settings["group_by"] = self.group_by.get()  # shortcut: gardé en mémoire, enregistré au prochain réglage d'affichage
        self.group_value = None
        self.refresh_books()

    def show_detail(self):
        """Affiche sous la liste la fiche du livre sélectionné, avec ses boutons d'action."""
        for w in self.detail.winfo_children():
            w.destroy()
        self._detail_w = self.detail.winfo_width()
        sel = self.books.selection()
        book = self.lib.book(int(sel[0])) if sel else None
        if not book:
            ttk.Label(self.detail, text="Sélectionnez un livre pour afficher sa fiche ici.",
                      foreground=COLORS["muted"], font=ui_font(11)).pack(anchor="w")
            return
        loan = self.lib.active_loan(book["id"])
        left = ttk.Frame(self.detail)  # jaquette : à gauche du texte, ou au-dessus quand la fiche est à droite
        if self.detail_right:
            left.pack(side="top", anchor="w", pady=(0, 8))
        else:
            left.pack(side="left", fill="y")
        text = ttk.Frame(self.detail)
        text.pack(side="left", fill="both", expand=True)
        bar = ttk.Frame(text)
        bar.pack(side="bottom", anchor="w", pady=(10, 0))  # en bas : visible même si le résumé est long
        ttk.Button(bar, text="Enregistrer le retour" if loan else "Prêter…",
                   command=lambda: self.run_action(book, loan, "return" if loan else "lend")).pack(side="left")
        ttk.Button(bar, text="Modifier…", command=lambda: self.run_action(book, loan, "edit")).pack(side="left", padx=6)
        ttk.Button(bar, text="Supprimer", command=self.delete_selected).pack(side="left")
        self.detail_photo = book_details(text, book, loan, self.cover_path(book["id"]),
                                         max(200, self._detail_w - (40 if self.detail_right else 200)), None,
                                         cover_parent=left)

    def sort_books(self, event=None):
        """Applique « Trier par » / « Décroissant » (les deux vues suivent l'ordre du tableau)."""
        if self.sort_by.get():
            self._sort(self.books, SORTS[self.sort_by.get()], self.sort_desc.get())
            self.show_covers()

    def _books_sorted(self, col, desc):
        """Après un tri du tableau, reflète la colonne choisie dans « Trier par » (vide si hors liste)."""
        self.sort_by.set(next((label for label, key in SORTS.items() if key == col), ""))
        self.sort_desc.set(desc)

    def show_view(self):
        """Bascule entre la vue Liste (tableau) et la vue Miniatures (couvertures)."""
        grid = self.view.get() == "grid"
        (self.books.master if grid else self.covers).pack_forget()
        (self.covers if grid else self.books.master).pack(fill="both", expand=True)
        self.show_covers()

    def show_covers(self):
        """Redessine la vue Miniatures (si affichée) à partir des lignes du tableau, dans le même ordre."""
        if self.view.get() != "grid":
            return
        sel = self.books.selection()
        self.covers.show([(i, self.books.set(i, "title"), self.books.set(i, "authors"), self.cover_path(int(i)))
                          for i in self.books.get_children()], sel[0] if sel else None)

    def select_book(self, book_id):
        """Affiche l'onglet Bibliothèque et y sélectionne le livre (s'il est visible avec le filtre actuel)."""
        self.nb.select(0)
        iid = str(book_id)
        if not self.books.exists(iid) and self.group_value is not None:
            self.group_value = None  # livre scanné hors du groupe affiché à gauche : on revient à tous les livres
            self.refresh_books()
        if self.books.exists(iid):
            self.books.selection_set(iid)
            self.books.see(iid)
            self.covers.select(iid, notify=False)

    # ---- scan -------------------------------------------------------------
    def on_scan(self, event=None):
        """Traite le code saisi ou scanné (Entrée dans le champ ISBN, ou bouton OK).

        Selon le mode et l'état du livre :

        ===============  ======================  =================================
        Mode             Livre connu             Livre inconnu
        ===============  ======================  =================================
        Automatique      fiche + actions         recherche en ligne + formulaire
        Ajout rapide     simple avertissement    recherche en ligne + ajout direct
        Retour rapide    retour enregistré       erreur
        ===============  ======================  =================================

        Le champ est vidé immédiatement, prêt pour le scan suivant.
        """
        raw = self.scan.get().strip()
        self.scan.delete(0, "end")
        if not raw:
            return
        isbn = normalize(raw)
        if not isbn:
            self.set_status(f"« {raw} » n'est pas un ISBN valide.", "err")
            return
        book = self.lib.book_by_isbn(isbn)
        mode = self.mode.get()
        if mode == "return":
            if not book:
                self.set_status(f"{isbn} : livre absent de la bibliothèque.", "err")
            else:
                loan = self.lib.return_book(book["id"])
                if loan:
                    self.set_status(f"Retour enregistré : « {book['title']} » (rendu par {loan['borrower']}).", "ok")
                    self.refresh()
                else:
                    self.set_status(f"« {book['title']} » n'était pas prêté.", "warn")
            return
        if book:
            if mode == "add":
                self.set_status(f"Déjà dans la bibliothèque : « {book['title']} ».", "warn")
                self.select_book(book["id"])
            else:
                self.select_book(book["id"])
                self.book_actions(book)
            return
        self.register(isbn, quick=(mode == "add"))

    def register(self, isbn, quick):
        """Lance l'enregistrement d'un nouveau livre : recherche en ligne dans un thread.

        La suite se passe dans :meth:`_registered`, rappelé via :meth:`post`
        une fois la recherche terminée. Un ISBN déjà en cours de recherche
        est ignoré (double scan).
        """
        if isbn in self.pending:
            return
        self.pending.add(isbn)
        self.set_status(f"{isbn} : nouveau livre, recherche des informations en ligne…", "info")
        threading.Thread(target=lambda: self.post(self._registered, isbn, lookup.fetch(isbn), quick),
                         daemon=True).start()

    def _registered(self, isbn, info, quick):
        """Fin de :meth:`register`, dans le thread de l'interface.

        En ajout rapide avec infos trouvées, le livre est enregistré
        directement. Sinon (mode automatique, ou livre introuvable en ligne),
        le formulaire s'ouvre pré-rempli pour validation ou saisie manuelle.
        """
        self.pending.discard(isbn)
        if self.lib.book_by_isbn(isbn):  # ajouté entre-temps
            return
        if quick and info:
            book_id = self.lib.add_book({"isbn": isbn, **info})
            self.save_cover(book_id, info)
            self.set_status(f"Ajouté : « {info['title']} »{' — ' + info['authors'] if info.get('authors') else ''}", "ok")
        else:
            if not info:
                self.set_status(f"{isbn} : introuvable en ligne, saisie manuelle.", "warn")
            data = BookForm(self, {"isbn": isbn, **(info or {})}, "Nouveau livre").show()
            self.refocus()
            if not data:
                self.set_status("Enregistrement annulé.", "warn")
                return
            try:
                book_id = self.lib.add_book(data)
            except Exception as exc:
                messagebox.showerror("Erreur", str(exc), parent=self)
                return
            self.save_cover(book_id, info or {})
            self.set_status(f"Ajouté : « {data['title']} ».", "ok")
        self.refresh()
        self.select_book(book_id)

    def cover_path(self, book_id):
        """Fichier de couverture du livre : ``covers/<id>.jpg`` à côté de la base (il peut ne pas exister)."""
        return os.path.join(os.path.dirname(self.db_path), "covers", f"{book_id}.jpg")

    def save_cover(self, book_id, info):
        """Enregistre la couverture téléchargée par :func:`lookup.fetch`, sans remplacer une couverture existante.

        Retourne ``True`` si un fichier a été écrit.
        """
        path = self.cover_path(book_id)
        if not info.get("cover") or os.path.exists(path):
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(info["cover"])
        return True

    def change_cover(self, book, src):
        """Remplace la couverture du livre par l'image ``src`` (chemin ou octets, convertie en JPEG)."""
        path = self.cover_path(book["id"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            if Image:
                open_image(src).convert("RGB").save(path, "JPEG", quality=90)
            elif isinstance(src, bytes):
                with open(path, "wb") as f:
                    f.write(src)
            else:
                shutil.copyfile(src, path)
        except Exception as exc:
            messagebox.showerror("Jaquette", f"Image illisible : {exc}", parent=self)

    # ---- actions sur un livre ---------------------------------------------
    def book_actions(self, book):
        """Ouvre la fiche (:class:`BookCard`) d'un livre et exécute l'action choisie."""
        loan = self.lib.active_loan(book["id"])
        self.run_action(book, loan, BookCard(self, book, loan, self.cover_path(book["id"])).show())

    def run_action(self, book, loan, action):
        """Exécute une action de fiche (``"lend"``, ``"return"``, ``"edit"`` ou ``None``) puis rafraîchit."""
        if action == "lend":
            self.lend(book)
        elif action == "return":
            self.lib.return_book(book["id"])
            self.set_status(f"Retour enregistré : « {book['title']} » (rendu par {loan['borrower']}).", "ok")
        elif action == "edit":
            self.edit(book)
        self.refresh()
        self.refocus()

    def lend(self, book):
        """Demande l'emprunteur et l'échéance (:class:`LendDialog`) puis enregistre le prêt."""
        res = LendDialog(self, book, self.lib.borrowers()).show()
        if not res:
            return
        who, due = res
        try:
            self.lib.lend(book["id"], who, due)
        except ValueError as exc:
            messagebox.showerror("Prêt impossible", str(exc), parent=self)
            return
        suffix = f", retour prévu le {fmt_date(due)}" if due else ""
        self.set_status(f"« {book['title']} » prêté à {who}{suffix}.", "ok")

    def book_menu(self, event):
        """Menu du clic droit sur un livre (liste ou miniatures) : actualisations directes, sans formulaire."""
        book = self._selected()
        if not book:
            return
        menu = tk.Menu(self, tearoff=False)
        if Image:  # sans Pillow, les jaquettes trouvées ne pourraient pas être montrées
            menu.add_command(label="Actualiser la jaquette…", command=lambda: self.refresh_cover(book))
        menu.add_command(label="Actualiser les informations…", command=lambda: self.refresh_info(book))
        menu.add_separator()
        menu.add_command(label="Modifier…", command=lambda: self.run_action(book, None, "edit"))
        menu.tk_popup(event.x_root, event.y_root)

    def refresh_cover(self, book):
        """Cherche en ligne les jaquettes du livre (dans un thread) ; celle choisie est enregistrée aussitôt."""
        self.set_status(f"Recherche de jaquettes pour « {book['title']} »…", "info")
        args = (book["isbn"], book["title"], book["authors"])
        threading.Thread(target=lambda: self.post(self._covers_found, book["id"], lookup.find_covers(*args)),
                         daemon=True).start()

    def _covers_found(self, book_id, images):
        """Fin de :meth:`refresh_cover` : choix parmi les jaquettes trouvées (:class:`CoverPicker`)."""
        book = self.lib.book(book_id)
        if not book:  # supprimé pendant la recherche
            return
        if not images:
            self.set_status(f"Aucune jaquette trouvée en ligne pour « {book['title']} ».", "warn")
            return
        img = CoverPicker(self, images, " - ".join(filter(None, (book["title"], book["authors"])))).show()
        if img:
            self.change_cover(book, img)
            self.refresh()
            self.set_status(f"Jaquette actualisée : « {book['title']} ».", "ok")
        else:
            self.set_status("Jaquette inchangée.", "info")

    def refresh_info(self, book):
        """Cherche en ligne les informations du livre d'après son ISBN (dans un thread)."""
        if not book["isbn"]:
            self.set_status(f"« {book['title']} » n'a pas d'ISBN : impossible de chercher ses informations.", "err")
            return
        self.set_status(f"Recherche des informations de « {book['title']} »…", "info")
        threading.Thread(target=lambda: self.post(self._info_found, book["id"], lookup.fetch(book["isbn"])),
                         daemon=True).start()

    def _info_found(self, book_id, info):
        """Fin de :meth:`refresh_info` : montre les champs qui changent (:attr:`BookForm.ONLINE`)
        et les enregistre après confirmation, pour ne pas écraser une correction sans le voir."""
        book = self.lib.book(book_id)
        if not book:
            return
        data = {f: book[f] for f in FIELDS}
        new = {f: str(info[f]) for f in BookForm.ONLINE if (info or {}).get(f) and str(info[f]) != (data[f] or "")}
        if not new:
            self.set_status(f"Rien de nouveau en ligne pour « {book['title']} ».", "info")
            return
        cut = lambda s: s if len(s) <= 90 else s[:89].rstrip() + "…"
        lines = "\n".join(f"{LABELS[f]} : {cut(v)}" for f, v in new.items())
        if not messagebox.askyesno("Actualiser les informations",
                                   f"Remplacer dans la fiche « {book['title']} » :\n\n{lines}", parent=self):
            self.set_status("Fiche inchangée.", "info")
            return
        data.update(new)
        self.lib.update_book(book_id, data)
        self.refresh()
        self.set_status(f"Informations actualisées : « {data['title']} ».", "ok")

    def edit(self, book):
        """Ouvre le formulaire de modification du livre et enregistre les changements.

        Une erreur (ex. ISBN déjà utilisé par un autre livre) est affichée
        sans rien modifier.
        """
        form = BookForm(self, dict(book), "Modifier le livre", self.cover_path(book["id"]))
        data = form.show()
        if not data:
            return
        try:
            self.lib.update_book(book["id"], data)
            if form.cover_src:
                self.change_cover(book, form.cover_src)
            self.set_status(f"Fiche modifiée : « {data['title']} ».", "ok")
        except Exception as exc:
            messagebox.showerror("Erreur", str(exc), parent=self)

    # Les méthodes *_selected agissent sur le livre sélectionné dans l'onglet
    # Bibliothèque (boutons de la barre d'outils et double-clic).
    def _selected(self):
        """Livre sélectionné dans l'onglet Bibliothèque, ou ``None`` (avec un message)."""
        sel = self.books.selection()
        if not sel:
            messagebox.showinfo("Aucune sélection", "Sélectionnez d'abord un livre dans la liste.", parent=self)
            return None
        return self.lib.book(int(sel[0]))

    def open_selected(self):
        book = self._selected()
        if book:
            self.book_actions(book)

    def delete_selected(self):
        book = self._selected()
        if not book or not messagebox.askyesno("Supprimer", f"Supprimer « {book['title']} » ?", parent=self):
            return
        try:
            self.lib.delete_book(book["id"])
            if os.path.exists(self.cover_path(book["id"])):
                os.remove(self.cover_path(book["id"]))  # sinon un futur livre réutilisant cet id hériterait de l'image
            self.set_status(f"Supprimé : « {book['title']} ».", "ok")
        except ValueError as exc:
            messagebox.showerror("Suppression impossible", str(exc), parent=self)
        self.refresh()

    def add_manual(self):
        """Ajout d'un livre au clavier, sans scan (ISBN facultatif, pas de recherche en ligne)."""
        data = BookForm(self, {}, "Nouveau livre").show()
        if data:
            if data["isbn"] and self.lib.book_by_isbn(data["isbn"]):
                messagebox.showwarning("Doublon", "Un livre avec cet ISBN existe déjà.", parent=self)
            else:
                self.select_book(self.lib.add_book(data))
                self.set_status(f"Ajouté : « {data['title']} ».", "ok")
                self.refresh()
        self.refocus()

    def return_selected_loan(self):
        """Enregistre le retour du prêt sélectionné dans l'onglet Prêts en cours."""
        sel = self.loans.selection()
        if not sel:
            return
        book = self.lib.book(int(sel[0]))
        loan = self.lib.return_book(book["id"])
        if loan:
            self.set_status(f"Retour enregistré : « {book['title']} » (rendu par {loan['borrower']}).", "ok")
        self.refresh()

    # ---- annuaire -----------------------------------------------------------
    def add_borrower(self):
        self._save_borrower(None, {}, "Nouveau contact")

    def edit_borrower(self):
        sel = self.people.selection()
        if sel:
            self._save_borrower(sel[0], dict(self.lib.borrower(sel[0])), "Modifier le contact")

    def _save_borrower(self, old_name, data, title):
        """Ouvre la fiche contact puis l'enregistre ; un renommage s'applique aussi aux prêts."""
        out = BorrowerForm(self, data, title).show()
        if out:
            try:
                self.lib.save_borrower(old_name, out)
                self.set_status(f"Contact enregistré : {out['name']}.", "ok")
            except ValueError as exc:
                messagebox.showerror("Annuaire", str(exc), parent=self)
            self.refresh()
        self.refocus()

    def delete_borrower(self):
        sel = self.people.selection()
        if not sel or not messagebox.askyesno(
                "Supprimer", f"Retirer « {sel[0]} » de l'annuaire ?\n(L'historique de ses prêts est conservé.)",
                parent=self):
            return
        try:
            self.lib.delete_borrower(sel[0])
            self.set_status(f"Contact supprimé : {sel[0]}.", "ok")
        except ValueError as exc:
            messagebox.showerror("Suppression impossible", str(exc), parent=self)
        self.refresh()

    # ---- import / export / enrichissement ---------------------------------
    def import_bkc(self):
        """Importe une collection Book Collector (``.bkc``), voir :mod:`booktek.bkc_import`.

        Les livres dont l'ISBN est déjà en base sont ignorés : l'import peut
        être relancé sans créer de doublons. Le fichier ne fournissant que
        l'ISBN et le titre, on propose ensuite de compléter les fiches en
        ligne (:meth:`enrich`).
        """
        path = filedialog.askopenfilename(parent=self, title="Collection Book Collector",
                                          filetypes=[("Book Collector", "*.bkc"), ("Tous les fichiers", "*.*")])
        if not path:
            return
        try:
            items = bkc_import.parse(path)
        except Exception as exc:
            messagebox.showerror("Import impossible", str(exc), parent=self)
            return
        self._import_items(items, "Le fichier .bkc ne contient pas les auteurs de façon exploitable.")

    def import_isbn_list(self):
        """Importe une liste d'ISBN (fichier texte ou CSV), voir :func:`booktek.isbn.find_in_lines`.

        Chaque livre est créé avec son ISBN pour titre provisoire, remplacé
        par le vrai titre lors du complément en ligne proposé ensuite.
        """
        path = filedialog.askopenfilename(parent=self, title="Liste d'ISBN",
                                          filetypes=[("Texte ou CSV", "*.txt *.csv"), ("Tous les fichiers", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                isbns = find_in_lines(f.read())
        except OSError as exc:
            messagebox.showerror("Import impossible", str(exc), parent=self)
            return
        if not isbns:
            messagebox.showerror("Import impossible", "Aucun ISBN valide dans ce fichier.", parent=self)
            return
        self._import_items([{"isbn": i, "title": i} for i in isbns], "Le fichier ne contient que les ISBN.")

    def _import_items(self, items, note):
        """Ajoute les livres ``items`` absents de la base, puis propose de compléter les fiches en ligne.

        Les livres dont l'ISBN est déjà en base sont ignorés : l'import peut
        être relancé sans créer de doublons.
        """
        added = skipped = 0
        for it in items:
            if it["isbn"] and self.lib.book_by_isbn(it["isbn"]):
                skipped += 1
                continue
            self.lib.add_book(it)
            added += 1
        self.refresh()
        msg = f"{added} livre(s) importé(s), {skipped} déjà présent(s)."
        self.set_status(msg, "ok")
        if added and messagebox.askyesno(
                "Import terminé", msg + f"\n\n{note}\n"
                "Compléter maintenant les fiches (titre, auteur, éditeur, couverture…) via Internet ?", parent=self):
            self.enrich()

    def enrich(self):
        """Complète en ligne les fiches incomplètes (:meth:`Library.books_missing_info`) ou sans couverture.

        Les recherches sont faites l'une après l'autre dans un thread (pour ne
        pas saturer les catalogues). Chaque résultat est appliqué dans le
        thread de l'interface par ``apply``, qui affiche la progression et
        n'écrase jamais un champ déjà rempli (:meth:`Library.fill_missing`).
        """
        todo = dict(self.lib.books_missing_info())
        todo.update((r["id"], r["isbn"]) for r in self.lib.search()
                    if r["isbn"] and not os.path.exists(self.cover_path(r["id"])))
        todo = sorted(todo.items())
        if not todo:
            self.set_status("Toutes les fiches sont déjà complètes.", "ok")
            return
        self.set_status(f"Recherche en ligne de {len(todo)} fiche(s)…", "info")
        found = [0]  # liste pour pouvoir l'incrémenter depuis la fonction imbriquée

        def apply(book_id, info, i):
            if info and (self.lib.fill_missing(book_id, info) | self.save_cover(book_id, info)):
                found[0] += 1
            self.set_status(f"Recherche en ligne : {i}/{len(todo)} ({found[0]} complétée(s))…", "info")
            if i == len(todo):
                self.refresh()
                self.set_status(f"Terminé : {found[0]} fiche(s) complétée(s) sur {len(todo)}.", "ok")

        def work():
            for i, (book_id, isbn) in enumerate(todo, 1):
                self.post(apply, book_id, lookup.fetch(isbn), i)

        threading.Thread(target=work, daemon=True).start()

    def export_csv(self):
        """Exporte toute la bibliothèque, avec l'état des prêts, en CSV.

        Encodage UTF-8 avec BOM et séparateur « ; » : c'est ce qu'attend un
        Excel français pour ouvrir le fichier correctement par double-clic.
        """
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", initialfile="bibliotheque.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([LABELS[k] for k in FIELDS] + ["Prêté à", "Retour prévu"])
            for r in self.lib.search():
                w.writerow([r[k] for k in FIELDS] + [r["borrower"] or "", fmt_date(r["due_date"])])
        self.set_status(f"Exporté : {path}", "ok")


    # ---- mises à jour ------------------------------------------------------
    def check_updates_auto(self):
        """Vérification à chaud silencieuse, puis toutes les :data:`updater.CHECK_INTERVAL` secondes."""
        self._check_updates(manual=False)
        self.after(updater.CHECK_INTERVAL * 1000, self.check_updates_auto)

    def check_updates_manual(self):
        """Menu Aide > Rechercher une mise à jour : comme la vérification auto, mais avec retours visibles."""
        self._check_updates(manual=True)

    def _check_updates(self, manual):
        """Lance :meth:`_update_worker` dans un thread (une seule vérification à la fois)."""
        if self._update_busy:
            if manual:
                self.set_status("Recherche de mise à jour déjà en cours…", "info")
            return
        self._update_busy = True
        if manual:
            self.set_status("Recherche de mise à jour…", "info")
        threading.Thread(target=self._update_worker, args=(manual,), daemon=True).start()

    def _update_worker(self, manual):
        """Thread : interroge GitHub et télécharge la nouvelle version si besoin.

        N'accède jamais à l'interface directement : les résultats passent par
        :meth:`post`. En vérification automatique, la progression n'est pas
        affichée pour ne pas masquer les messages de scan.
        """
        try:
            rel = updater.latest_release()
            if rel is None or not updater.is_newer(rel.version):
                self.post(self._update_done, None, None, manual)
                return
            if not updater.can_self_update():
                self.post(self._update_done, rel, "manual-install", manual)
                return
            if updater.pending_version() != rel.version:
                step = [-1]

                def progress(received, total):
                    pct = received * 100 // total if total else 0
                    if manual and pct // 10 != step[0]:
                        step[0] = pct // 10
                        self.post(self.set_status, f"Téléchargement de la version {rel.version} : {pct} %", "info")

                updater.download(rel, progress)
            self.post(self._update_done, rel, "ready", manual)
        except Exception as exc:
            self.post(self._update_failed, str(exc), manual)

    def _update_done(self, rel, state, manual):
        """Résultat de la vérification, dans le thread de l'interface.

        ``state`` vaut ``None`` (déjà à jour), ``"ready"`` (téléchargée,
        installable) ou ``"manual-install"`` (exécution depuis les sources ou
        dossier protégé : l'utilisateur doit mettre à jour lui-même).
        """
        self._update_busy = False
        if rel is None:
            if manual:
                self.set_status(f"BookTek est à jour (version {__version__}).", "ok")
            return
        if state == "manual-install":
            self.set_status(f"La version {rel.version} de BookTek est disponible.", "info")
            if manual:
                messagebox.showinfo(
                    "Mise à jour disponible",
                    f"La version {rel.version} est disponible :\n{rel.page}\n\n"
                    "Elle ne peut pas être installée automatiquement ici (lancement depuis les sources, "
                    "ou dossier de l'application protégé en écriture).", parent=self)
            return
        self.update_ready = rel
        self.update_btn.config(text=f"⬆ Mettre à jour vers {rel.version}")
        self.update_btn.pack(side="right")
        self.set_status(f"Mise à jour {rel.version} prête : elle sera installée au prochain démarrage, "
                        "ou cliquez sur « Mettre à jour ».", "info")
        if manual:
            self.install_update()

    def _update_failed(self, message, manual):
        """Échec de vérification ou de téléchargement : signalé seulement si demandé par l'utilisateur."""
        self._update_busy = False
        if manual:
            self.set_status(f"Mise à jour impossible : {message}", "err")

    def install_update(self):
        """Bouton « Mettre à jour » : confirme, installe la version téléchargée et redémarre."""
        rel = self.update_ready
        if not rel:
            return
        notes = rel.notes.strip()
        if len(notes) > 700:
            notes = notes[:700].rstrip() + "…"
        if not messagebox.askyesno(
                "Mettre à jour BookTek",
                f"Installer la version {rel.version} (actuelle : {__version__}) ?\n\n"
                f"{notes}\n\nBookTek va redémarrer.", parent=self):
            self.refocus()
            return
        try:
            updater.apply_and_restart()
        except updater.UpdateError as exc:
            messagebox.showerror("Mise à jour impossible", str(exc), parent=self)
            return
        self.lib.con.close()
        self.destroy()

    def about(self):
        """Menu Aide > À propos : version, dépôt, base et sources des données (:class:`AboutDialog`)."""
        AboutDialog(self, self.db_path).show()


def main():
    """Point d'entrée.

    Installe d'abord une éventuelle mise à jour téléchargée lors d'une
    session précédente (la nouvelle version est alors lancée et on quitte),
    puis ouvre la base (voir :func:`data_dir`) et lance l'interface.
    """
    if updater.install_pending_on_startup():
        return
    db_path = os.path.join(data_dir(), "booktek.db")
    App(db_path).mainloop()
